#!/usr/bin/env python3
"""PreToolUse 훅: 레인 소유 경로는 그 레인 세션만 쓴다.

소유 경로는 허브 폴더(플러그인 설정 hub_dir, 훅에는 CLAUDE_PLUGIN_OPTION_HUB_DIR)의 agents.json "lanes" 에서 읽는다.
  "lanes": {"WEB": ["~/projects/web"], "API": ["~/projects/api", "~/projects/shared/api"]}
허브 폴더 자체는 늘 HUB 레인 소유다. hub_dir 가 비어 있으면 아무것도 막지 않는다.
상대 경로는 허브 폴더 기준이다. 경로가 겹치면 가장 깊은 쪽이 주인이다.

세션의 레인은 CLAUDE_PROJECT_DIR(없으면 입력의 cwd)이 든 경로의 레인이다. worktree 는 <저장소>/.claude/worktrees/ 아래라
저장소 레인으로 잡힌다. 어느 레인에도 들지 않는 세션은 모든 소유 경로에 못 쓴다.

막는 것:
- Edit, Write, MultiEdit, NotebookEdit 의 대상이 다른 레인 경로일 때.
- Bash 는 최선으로만 본다: 리다이렉트(>, >>), tee, sed -i, cp, mv, install 의 대상. 단순 cd 는 따라간다.
  ponytail: 변수, 명령 치환, 스크립트 안의 쓰기, python -c, git, PowerShell 은 보지 못하고 우회도 쉽다.
  실수를 막는 장치이고 보안 경계가 아니다. 경계가 필요하면 permissions.deny 를 같이 쓴다(scripts/lane_deny.py).
- 설정 lane_message_hub_only 를 켜면 허브가 아닌 세션의 SendMessage 는 허브(agents.json 에서 lane 이 HUB 인 이름)와
  main 에게만 간다. uds: 주소는 누구인지 알 수 없어 그대로 둔다(허브 메시지에 답할 때 쓰는 주소다).
"""
import json
import os
import posixpath
import shlex
import sys

from hubpath import NT, inside, native, norm

HUB = 'HUB'
WRITE_TOOLS = ('Edit', 'Write', 'MultiEdit', 'NotebookEdit')
SPLIT = {';', ';;', '&&', '||', '|', '&', '|&', '(', ')'}
REDIRECT = {'>', '>>', '>|', '&>', '&>>', '>&'}
WRAPPERS = ('sudo', 'command', 'env', 'nohup', 'time', 'exec')


def read_roster(hub):
    """허브 폴더 agents.json. 없거나 깨졌으면 {}."""
    try:
        with open(os.path.join(native(hub), 'agents.json'), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def lane_roots(hub, roster, nt=NT):
    """[(정규화된 경로, 레인)], 깊은 경로가 앞. 허브 폴더는 HUB."""
    out = [(norm(hub, nt), HUB)]
    lanes = roster.get('lanes')
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


def bash_targets(cmd):
    """명령 문자열의 쓰기 대상 [(경로, 그때까지 cd 한 폴더 또는 '')]. 따옴표가 깨져 못 읽으면 []."""
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=';&|()<>')
        lex.whitespace_split = True
        lex.commenters = ''
        toks = list(lex)
    except ValueError:
        return []
    out, base, cur = [], '', []
    for t in toks + [';']:
        if t not in SPLIT:
            cur.append(t)
            continue
        args, it = [], iter(cur)
        for w in it:
            if w in REDIRECT:
                nxt = next(it, '')
                if nxt and not nxt.isdigit() and nxt != '-':
                    out.append((nxt, base))
            elif w in ('<', '<<', '<<<', '<>', '<&'):
                next(it, '')
            else:
                args.append(w)
        cur = []
        while args and ('=' in args[0] and not args[0].startswith('-') or args[0] in WRAPPERS):
            args.pop(0)                               # FOO=1 cmd, sudo cmd
        if not args:
            continue
        name, rest = posixpath.basename(args[0]), args[1:]
        if name == 'cd' and len(nonopts(rest)) == 1:
            p = nonopts(rest)[0]
            base = p if not base or p.startswith(('/', '~')) or ':' in p else posixpath.join(base, p)
        elif name == 'tee':
            out += [(p, base) for p in nonopts(rest)]
        elif name == 'sed' and any(a.startswith(('-i', '--in-place')) for a in rest):
            out += [(p, base) for p in sed_files(rest)]
        elif name in ('cp', 'mv', 'install'):
            dest = [a.split('=', 1)[1] for a in rest if a.startswith('--target-directory=')]
            dest += [b for a, b in zip(rest, rest[1:]) if a == '-t']
            pos = nonopts(rest)
            out += [(p, base) for p in (dest or (pos[-1:] if len(pos) >= 2 else []))]
    return out


def targets(inp):
    ti = inp.get('tool_input') or {}
    tool = inp.get('tool_name') or ''
    if tool in WRITE_TOOLS:
        f = ti.get('file_path') or ti.get('notebook_path')
        return [(f, '')] if f else []
    if tool == 'Bash':
        return bash_targets(ti.get('command') or '')
    return []


def check(inp, hub, project='', nt=NT, roster=None, message_hub_only=False):
    """막을 이유 문자열, 아니면 None. project 는 CLAUDE_PROJECT_DIR(없으면 입력의 cwd). roster 는 시험용."""
    if not hub:
        return None
    roster = read_roster(hub) if roster is None else roster
    roots = lane_roots(hub, roster, nt)
    cwd = inp.get('cwd') or ''
    mine = owner(norm(project or cwd, nt), roots)
    if inp.get('tool_name') == 'SendMessage':
        to = str((inp.get('tool_input') or {}).get('to') or '').strip()
        names = hub_names(roster)
        if message_hub_only and mine != HUB and to and not to.startswith('uds:') and to != 'main' \
                and to.split(' [')[0] not in names:
            return '이 설정에서 워커는 허브(%s)에게만 메시지를 보낸다. 다른 세션에 전할 것은 허브에 보고해라.' % (
                ', '.join(sorted(names)) or 'agents.json 에서 lane 이 HUB 인 세션')
        return None
    for f, base in targets(inp):
        if not f or f.startswith('/dev/'):
            continue
        if base and not base.startswith(('/', '~')) and ':' not in base:
            base = posixpath.join(cwd, base)
        lane = owner(norm(f, nt, base or cwd), roots)
        if lane and lane != mine:
            if lane == HUB:
                return '허브 폴더 파일은 허브만 고친다. 바꿀 내용은 SendMessage 로 허브 세션에 보고해라. (%s)' % f
            return '%s 는 레인 %s 소유다. 고칠 일은 SendMessage 로 허브에 요청해라.' % (f, lane)
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
