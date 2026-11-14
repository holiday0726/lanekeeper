#!/usr/bin/env python3
"""PreToolUse 훅: 레인 소유 경로는 그 레인 세션만 쓴다.

소유 경로는 허브 폴더(플러그인 설정 hub_dir, 훅에는 CLAUDE_PLUGIN_OPTION_HUB_DIR)의 lanes.json 에서 읽는다.
  {"lanes": {"WEB": ["~/projects/web"], "API": ["~/projects/api", "~/projects/shared/api"]}}
lanes.json 이 없으면 agents.json 의 "lanes"(0.7 까지의 자리)를 읽는다. 둘 다 없으면 레인이 없다.
허브 폴더 자체는 늘 HUB 레인 소유다. hub_dir 가 비어 있으면 아무것도 막지 않는다.
상대 경로는 허브 폴더 기준이다. 경로가 겹치면 가장 깊은 쪽이 주인이다.
레인 파일을 읽지 못하면(JSON 이 깨짐, 모양이 틀림) 레인을 모르니 허브 폴더 밖 쓰기를 모두 막는다. 허브는 허브 폴더를 고칠 수 있다.

세션의 레인은 CLAUDE_PROJECT_DIR(없으면 입력의 cwd)이 든 경로의 레인이다. worktree 는 <저장소>/.claude/worktrees/ 아래라
저장소 레인으로 잡힌다. 어느 레인에도 들지 않는 세션은 모든 소유 경로에 못 쓴다.

막는 것:
- Edit, Write, MultiEdit, NotebookEdit 의 대상이 다른 레인 경로일 때.
- Bash 는 최선으로만 본다: 리다이렉트(>, >>), tee, sed -i, cp, mv(원본도), install, rm, rmdir, unlink, touch, mkdir,
  truncate, ln, chmod, chown, dd of=, patch(-d, 대상 파일, 없으면 그 폴더), find -delete, git(-C, --work-tree, --git-dir,
  없으면 그 폴더. status, log, diff, fetch 같은 읽기는 뺀다)의 대상. cd, pushd 는 따라가고 괄호 안 cd 는 괄호 밖으로 잇지 않는다.
  rm, rmdir, mv 원본, find -delete 는 대상 아래에 다른 레인이 있어도 막는다.
  ponytail: 변수, 명령 치환, 스크립트 안의 쓰기, bash -c, python -c, PowerShell 은 보지 못하고 우회도 쉽다.
  실수를 막는 장치이고 보안 경계가 아니다. 경계가 필요하면 permissions.deny 를 같이 쓴다(scripts/lane_deny.py).
- 설정 lane_message_hub_only 를 켜면 허브가 아닌 세션의 SendMessage 는 허브(agents.json 에서 lane 이 HUB 인 이름)와
  main 에게만 간다. uds: 주소는 누구인지 알 수 없어 그대로 둔다(허브 메시지에 답할 때 쓰는 주소다).
"""
import json
import os
import posixpath
import re
import shlex
import sys

from hubpath import NT, inside, native, norm

HUB = 'HUB'
LANES = 'lanes.json'
WRITE_TOOLS = ('Edit', 'Write', 'MultiEdit', 'NotebookEdit')
SPLIT = {';', ';;', '&&', '||', '|', '&', '|&', '(', ')'}
REDIRECT = {'>', '>>', '>|', '&>', '&>>', '>&'}
WRAPPERS = ('sudo', 'command', 'builtin', 'env', 'nohup', 'time', 'exec', 'timeout', 'nice', 'stdbuf')
WRAPPER_ARGS = {'sudo': ('-u', '-g', '-C', '-D', '-h', '-p', '-r', '-t', '-U'), 'env': ('-u', '-C', '-S'),
                'nice': ('-n',), 'timeout': ('-s', '-k', '--signal', '--kill-after'), 'stdbuf': ('-i', '-o', '-e')}
SEP_CHARS = set(';&|()\n')
# 히어독 본문은 명령이 아니다. 여는 줄의 나머지는 두고 본문과 끝 줄만 걷어낸다
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1([^\n]*)\n(?:.*?\n)?[ \t]*\2[ \t]*(?=\n|$)", re.S)


def read_json(path):
    """(값, 이유). 파일이 없으면 (None, ''), 읽지 못하면 (None, 이유)."""
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f), ''
    except FileNotFoundError:
        return None, ''
    except (OSError, ValueError) as e:
        return None, str(e)[:200] or type(e).__name__


def read_roster(hub):
    """허브 폴더 agents.json. 없거나 깨졌으면 {}."""
    d, _ = read_json(os.path.join(native(hub), 'agents.json'))
    return d if isinstance(d, dict) else {}


def lanes_problem(lanes):
    """lanes 값의 모양이 틀렸으면 이유, 맞으면 ''. 레인마다 경로 문자열 하나나 문자열 목록이다."""
    if not isinstance(lanes, dict):
        return '"lanes" 가 객체가 아님'
    for lane, paths in lanes.items():
        if isinstance(paths, list) and all(isinstance(p, str) for p in paths) or isinstance(paths, str):
            continue
        return '레인 %s 의 경로가 문자열이나 문자열 목록이 아님' % lane
    return ''


def read_lanes(hub):
    """(lanes, 읽은 파일, 이유). lanes.json 이 있으면 그것만, 없으면 agents.json 의 "lanes"(0.7 까지의 자리)를 읽는다.

    둘 다 없거나 agents.json 에 "lanes" 가 없으면 ({}, 파일 또는 '', ''). 읽지 못하면 (None, 그 파일, 이유).
    agents.json 은 허브가 자주 고치는 명부라 깨지기 쉽다. lanes.json 으로 옮기면 명부가 깨져도 레인 보호가 남는다.
    """
    path = os.path.normpath(os.path.join(native(hub), LANES))   # 알림에 쓰는 경로라 이 OS 꼴로
    d, why = read_json(path)
    if d is not None or why:
        if why:
            return None, path, why
        if not isinstance(d, dict) or 'lanes' not in d:
            return None, path, '"lanes" 키가 있는 JSON 객체가 아님'
        why = lanes_problem(d['lanes'])
        return (None, path, why) if why else (d['lanes'], path, '')
    path = os.path.normpath(os.path.join(native(hub), 'agents.json'))
    d, why = read_json(path)
    if d is None and not why:
        return {}, '', ''
    if why or not isinstance(d, dict):
        return None, path, why or 'JSON 객체가 아님'
    why = 'lanes' in d and lanes_problem(d['lanes'])
    return (None, path, why) if why else (d.get('lanes') or {}, path, '')


def lane_roots(hub, lanes, nt=NT):
    """[(정규화된 경로, 레인)], 깊은 경로가 앞. 허브 폴더는 HUB."""
    out = [(norm(hub, nt), HUB)]
    for lane, paths in (lanes.items() if isinstance(lanes, dict) else ()):
        for p in ([paths] if isinstance(paths, str) else paths if isinstance(paths, list) else []):
            if isinstance(p, str) and p.strip():
                out.append((norm(p, nt, hub), str(lane)))
    return sorted(out, key=lambda x: -len(x[0].rstrip('/')))


def owner(path, roots):
    for root, lane in roots:
        if inside(path, root):
            return lane
    return None


def hub_names(roster):
    return {n for g in ('resident', 'task') for n, v in (roster.get(g) or {}).items()
            if isinstance(v, dict) and v.get('lane') == HUB}


def nonopts(args):
    return [a for a in args if not a.startswith('-')]


def positional(args, takes=()):
    """옵션이 아닌 인자. takes 는 값을 하나 받는 옵션이고 그 값은 뺀다. -- 뒤는 모두 위치 인자다."""
    out, it = [], iter(args)
    for a in it:
        if a == '--':
            out += list(it)
        elif a in takes:
            next(it, None)
        elif not a.startswith('-'):
            out.append(a)
    return out


def opt_values(args, short=(), long=()):
    """-d DIR, -dDIR, --directory DIR, --directory=DIR 꼴 옵션 값들."""
    out, it = [], iter(args)
    for a in it:
        if a == '--':
            break
        if a in short or a in long:
            v = next(it, None)
            out += [v] if v is not None else []
        elif a.startswith(tuple(x + '=' for x in long)):
            out.append(a.split('=', 1)[1])
        elif not a.startswith('--') and a[:2] in short and len(a) > 2:
            out.append(a[2:])
    return out


def is_abs(p):
    return p.startswith(('/', '~')) or ':' in p


def join(base, p):
    return p if not base or is_abs(p) else posixpath.join(base, p)


def sed_files(args):
    files, script_given, skip = [], False, False
    for a in args:
        if skip:
            skip = False
        elif a in ('-e', '-f', '--expression', '--file'):
            script_given = skip = True
        elif a.startswith(('--expression=', '--file=')):
            script_given = True
        elif not a.startswith('-'):
            files.append(a)
    return files if script_given else files[1:]


# git 하위 명령 중 저장소를 바꾸지 않는 것. fetch 는 원격 추적 ref 만 바꾸고 작업 트리와 로컬 브랜치를 건드리지 않아 읽기로 본다
GIT_READ = {'status', 'log', 'diff', 'show', 'blame', 'annotate', 'grep', 'describe', 'shortlog', 'rev-parse', 'rev-list',
            'ls-files', 'ls-tree', 'ls-remote', 'cat-file', 'merge-base', 'name-rev', 'for-each-ref', 'show-ref',
            'show-branch', 'whatchanged', 'var', 'help', 'version', 'count-objects', 'check-ignore', 'check-attr',
            'fetch', 'cherry', 'range-diff', 'archive', 'difftool', 'verify-commit', 'verify-tag', 'fsck'}
GIT_OPT_ARG = {'-C', '-c', '--git-dir', '--work-tree', '--namespace', '--config-env', '--super-prefix'}
BRANCH_WRITE = {'-d', '-D', '--delete', '-m', '-M', '--move', '-c', '-C', '--copy', '-f', '--force', '-u',
                '--set-upstream-to', '--unset-upstream', '--edit-description', '-t', '--track', '--no-track',
                '--create-reflog'}
BRANCH_LIST = {'-l', '--list', '--contains', '--no-contains', '--merged', '--no-merged', '--points-at', '-a', '--all',
               '-r', '--remotes', '--show-current', '-v', '-vv', '--verbose', '--format', '--sort'}
TAG_WRITE = {'-a', '--annotate', '-s', '--sign', '-u', '--local-user', '-d', '--delete', '-f', '--force', '-m',
             '--message', '-F', '--file', '-e', '--edit'}
TAG_LIST = {'-l', '--list', '-n', '--contains', '--no-contains', '--merged', '--no-merged', '--points-at', '--sort',
            '--format'}
CONFIG_READ = {'--get', '--get-all', '--get-regexp', '--get-urlmatch', '--get-color', '--get-colorbool', '-l', '--list'}
CONFIG_WRITE = {'--unset', '--unset-all', '--add', '--replace-all', '--rename-section', '--remove-section', '-e', '--edit'}
PATCH_ARGS = ('-p', '-d', '--directory', '-i', '--input', '-o', '--output', '-r', '--reject-file', '-F', '--fuzz', '-B',
              '--prefix', '-z', '--suffix', '-V', '--version-control', '-Y', '--basename-prefix', '-D', '--ifdef', '-g',
              '--get')


def git_reads(sub, rest):
    """이 git 하위 명령이 읽기만 하는지. 모르는 하위 명령은 쓰기로 본다."""
    if sub in GIT_READ:
        return True
    pos = positional(rest)
    opts = {a.split('=', 1)[0] for a in rest if a.startswith('-')}
    first = pos[0] if pos else ''
    if sub == 'branch':
        return not opts & BRANCH_WRITE and (not pos or bool(opts & BRANCH_LIST))
    if sub == 'tag':
        return not opts & TAG_WRITE and (not pos or bool(opts & TAG_LIST))
    if sub == 'config':
        return bool(opts & CONFIG_READ) or first in ('get', 'list') or len(pos) == 1 and not opts & CONFIG_WRITE
    return {'remote': not pos or first in ('show', 'get-url'), 'stash': first in ('list', 'show'),
            'worktree': first == 'list', 'reflog': not pos or first in ('show', 'exists'),
            'notes': not pos or first in ('list', 'show'), 'submodule': not pos or first in ('status', 'summary')
            }.get(sub, False)


def git_target(args):
    """git 다음 인자들의 쓰기 대상 폴더. 읽기 명령이면 None. -C 는 앞의 -C 에 이어 붙고 --work-tree 가 --git-dir 보다 앞선다."""
    c, tree, gitdir, i = '', '', '', 0
    while i < len(args) and args[i].startswith('-'):
        k, _, v = args[i].partition('=')
        if args[i] in GIT_OPT_ARG:
            k, v = args[i], args[i + 1] if i + 1 < len(args) else ''
            i += 1
        if k == '-C' and v:
            c = join(c, v)
        elif k == '--work-tree':
            tree = v
        elif k == '--git-dir':
            gitdir = v
        i += 1
    if i >= len(args) or git_reads(args[i], args[i + 1:]):
        return None
    sub, pos = args[i], positional(args[i + 1:])
    where = tree or gitdir
    if sub == 'clone':
        where = pos[-1] if len(pos) >= 2 else ''
    elif sub == 'init' and pos:
        where = pos[-1]
    return join(c, where) if where else c or '.'


def strip_wrappers(args):
    """FOO=1 cmd, sudo -u x cmd, timeout 30 cmd, nice -n 5 cmd 에서 cmd 부터."""
    while args:
        a = args[0]
        if '=' in a and not a.startswith('-'):
            args.pop(0)
        elif a in WRAPPERS:
            args.pop(0)
            while args and args[0].startswith('-'):
                if args.pop(0) in WRAPPER_ARGS.get(a, ()) and args:
                    args.pop(0)
            if a == 'timeout' and args:
                args.pop(0)                           # 시간
        else:
            break
    return args


def find_deletes(rest):
    """find 가 지우는(-delete, -exec rm) 시작 경로들. 지우지 않으면 []."""
    dele = '-delete' in rest or any(a in ('-exec', '-execdir', '-ok', '-okdir') and posixpath.basename(b) in
                                    ('rm', 'rmdir', 'unlink') for a, b in zip(rest, rest[1:]))
    if not dele:
        return []
    i = 0
    while i < len(rest) and (rest[i] in ('-H', '-L', '-P', '-D') or rest[i].startswith('-O')):
        i += 2 if rest[i] == '-D' else 1
    starts = []
    for a in rest[i:]:
        if a.startswith('-') or a in ('!', '(', ')'):
            break
        starts.append(a)
    return starts or ['.']


def command_targets(name, rest):
    """명령 하나의 [(대상, 지우기인지)]."""
    if name == 'tee':
        return [(p, False) for p in nonopts(rest)]
    if name == 'sed' and any(a.startswith(('-i', '--in-place')) for a in rest):
        return [(p, False) for p in sed_files(rest)]
    if name in ('cp', 'mv', 'install', 'ln'):
        dest = opt_values(rest, ('-t',), ('--target-directory',))
        pos = positional(rest, ('-t', '-S', '--suffix', '-m', '--mode', '-o', '--owner', '-g', '--group'))
        if not dest:
            dest = pos[-1:] if len(pos) >= 2 else ['.'] if name == 'ln' and pos else []
            pos = pos[:-1]
        return [(p, False) for p in dest] + [(p, True) for p in pos if name == 'mv']
    if name in ('rm', 'rmdir', 'unlink'):
        return [(p, True) for p in positional(rest)]
    if name in ('touch', 'mkdir', 'truncate'):
        return [(p, False) for p in positional(rest, ('-r', '-d', '-t', '-m', '-s', '--reference', '--date', '--mode',
                                                       '--size'))]
    if name in ('chmod', 'chown', 'chgrp'):
        pos = positional(rest)
        return [(p, False) for p in (pos if any(a.startswith('--reference') for a in rest) else pos[1:])]
    if name == 'dd':
        return [(a[3:], False) for a in rest if a.startswith('of=')]
    if name == 'patch':
        d = opt_values(rest, ('-d',), ('--directory',))
        p = (opt_values(rest, ('-o',), ('--output',)) or positional(rest, PATCH_ARGS) or [''])[0]
        return [(join(d[-1], p) if d and p else d[-1] if d else p or '.', False)]
    if name == 'find':
        return [(p, True) for p in find_deletes(rest)]
    if name == 'git':
        t = git_target(rest)
        return [(t, False)] if t else []
    return []


def split_ops(t):
    """shlex 가 붙여 읽은 연산자 묶음(');', '&&(')을 하나씩 나눈다."""
    out, i = [], 0
    while i < len(t):
        n = 2 if t[i:i + 2] in SPLIT else 1
        out.append(t[i:i + n])
        i += n
    return out


def bash_targets(cmd):
    """명령 문자열의 쓰기 대상 [(경로, 그때까지 cd 한 폴더 또는 '', 지우기인지)]. 따옴표가 깨져 못 읽으면 []."""
    try:
        cmd = HEREDOC.sub(lambda m: '<< ' + m.group(2) + m.group(3), cmd)
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=';&|()<>\n')
        lex.whitespace_split = True
        lex.whitespace = ' \t\r'   # 따옴표 밖 줄바꿈은 명령을 나눈다
        lex.commenters = ''
        toks = list(lex)
    except ValueError:
        return []
    toks = [p for t in toks for p in (split_ops(t) if set(t) <= SEP_CHARS and t not in SPLIT else [t])]
    out, base, stack, cur = [], '', [], []
    for t in toks + [';']:
        if t not in SPLIT and not (set(t) <= SEP_CHARS and '\n' in t):
            cur.append(t)
            continue
        args, it = [], iter(cur)
        for w in it:
            if w in REDIRECT:
                nxt = next(it, '')
                if nxt and not nxt.isdigit() and nxt != '-':
                    out.append((nxt, base, False))
            elif w in ('<', '<<', '<<<', '<>', '<&'):
                next(it, '')
            else:
                args.append(w)
        cur = []
        args = strip_wrappers(args)
        if args:
            name, rest = posixpath.basename(args[0]), args[1:]
            if name in ('cd', 'pushd') and len(nonopts(rest)) == 1:
                base = join(base, nonopts(rest)[0])
            else:
                out += [(p, base, d) for p, d in command_targets(name, rest)]
        if t == '(':
            stack.append(base)                        # 괄호(서브셸) 안 cd 는 괄호 밖으로 잇지 않는다
        elif t == ')' and stack:
            base = stack.pop()
    return out


def targets(inp):
    ti = inp.get('tool_input') or {}
    tool = inp.get('tool_name') or ''
    if tool in WRITE_TOOLS:
        f = ti.get('file_path') or ti.get('notebook_path')
        return [(f, '', False)] if f else []
    if tool == 'Bash':
        return bash_targets(ti.get('command') or '')
    return []


def check(inp, hub, project='', nt=NT, roster=None, message_hub_only=False, lanes=None):
    """막을 이유 문자열, 아니면 None. project 는 CLAUDE_PROJECT_DIR(없으면 입력의 cwd).

    roster 와 lanes 는 시험용이다. lanes 는 read_lanes() 꼴 (lanes, 파일, 이유)이고, 없고 roster 가 있으면 roster 의 "lanes" 를 쓴다.
    """
    if not hub:
        return None
    if lanes is None:
        lanes = read_lanes(hub) if roster is None else (roster.get('lanes') or {}, 'agents.json', '')
    got, where, why = lanes
    roots = lane_roots(hub, got, nt)
    cwd = inp.get('cwd') or ''
    mine = owner(norm(project or cwd, nt), roots)
    if inp.get('tool_name') == 'SendMessage':
        to = str((inp.get('tool_input') or {}).get('to') or '').strip()
        names = hub_names(read_roster(hub) if roster is None else roster)
        if message_hub_only and mine != HUB and to and not to.startswith('uds:') and to != 'main' \
                and to.split(' [')[0] not in names:
            return '이 설정에서 워커는 허브(%s)에게만 메시지를 보낸다. 다른 세션에 전할 것은 허브에 보고해라.' % (
                ', '.join(sorted(names)) or 'agents.json 에서 lane 이 HUB 인 세션')
        return None
    for f, base, dele in targets(inp):
        if not f or f.startswith('/dev/'):
            continue
        if base and not is_abs(base):
            base = posixpath.join(cwd, base)
        path = norm(f, nt, base or cwd)
        lane = owner(path, roots)
        if lane and lane != mine:
            if lane == HUB:
                return '허브 폴더 파일은 허브만 고친다. 바꿀 내용은 SendMessage 로 허브 세션에 보고해라. (%s)' % f
            return '%s 는 레인 %s 소유다. 고칠 일은 SendMessage 로 허브에 요청해라.' % (f, lane)
        if got is None and lane != HUB:
            return ('레인 정의 %s 를 읽지 못해(%s) 허브 폴더 밖 쓰기를 모두 막는다. 허브가 이 파일을 고치면 풀린다. '
                    '워커는 SendMessage 로 허브에 알려라. (%s)' % (where, why, f))
        under = dele and next(((r, n) for r, n in roots if n != mine and inside(r, path)), None)
        if under:
            return '%s 아래에 레인 %s 경로(%s)가 있다. 지울 일은 SendMessage 로 허브에 요청해라.' % (f, under[1], under[0])
    return None


def main():
    for s in (sys.stdin, sys.stdout, sys.stderr):
        s.reconfigure(encoding='utf-8')   # Windows 는 기본이 로캘 코드 페이지(cp949)
    try:
        inp = json.load(sys.stdin)
    except ValueError:
        return 0
    # 첫 인자(${user_config.lane_message_hub_only})나 환경 변수 중 하나가 켜짐이면 메시지를 막는다
    vals = sys.argv[1:2] + [os.environ.get('CLAUDE_PLUGIN_OPTION_LANE_MESSAGE_HUB_ONLY', '')]
    flag = any(v.strip().lower() in ('true', '1', 'yes', 'on') for v in vals)
    why = check(inp, os.environ.get('CLAUDE_PLUGIN_OPTION_HUB_DIR', ''), os.environ.get('CLAUDE_PROJECT_DIR', ''),
                message_hub_only=flag)
    if why:
        print(why, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
