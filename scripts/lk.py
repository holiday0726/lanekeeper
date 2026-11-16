#!/usr/bin/env python3
"""lk: 작업 세션을 띄우고 닫는다. 허브와 슈퍼바이저가 claude --bg, claude rm 대신 쓴다(설정 예시가 그 둘을 deny 한다).

  lk spawn --name task-T<YYYYMMDD>-<NN>-<주제> --cwd <저장소> [--effort high] [--verify "<명령>"]... [--hub <허브>]
           [-- <claude 인자>...]
  lk spawn --resident <agents.json resident 이름> [--cwd <폴더>] [--effort high] [--hub <허브>] [-- <claude 인자>...]
  lk close <이름 또는 id> [--hub <허브>]

플러그인 bin/lk 가 이 파일을 부른다. 플러그인이 켜져 있으면 bin/ 이 Bash 도구 PATH 에 있다.
허브 폴더: --hub, 환경 변수 LANEKEEPER_HUB_DIR, cwd 와 그 위 폴더 중 lanes.json 이나 resident 가 있는 agents.json 이 든 곳 순.
동시 작업 세션 상한: 환경 변수 LANEKEEPER_MAX_TASKS(기본 8). claude agents --json(끝난 세션 빼고)에서 이름이
task- 로 시작하는 세션을 센다. 상주 세션은 이름이 task- 로 시작하지 않으니 세지 않는다. 막힌(blocked) 세션도 떠 있으니 센다.
--resident: 이름이 agents.json resident 에 있을 때만(대소문자까지 같게, task- 아님, lane HUB 아님) 띄운다. 이름 규칙과
  상한을 보지 않고 T 번호 기록을 남기지 않는다. --cwd 가 없으면 명부의 cwd. 같은 이름이 떠 있으면 거부한다.

spawn 기록: <허브>/.lanekeeper/tasks/<T>.json 과 <저장소 git 공통 폴더>/lanekeeper/tasks/<T>.json 에 같은 내용을 쓴다.
  {"task": "T-YYYYMMDD-NN", "verify": ["명령", ...], "sessions": [{"name", "id", "cwd", "spawned_at", "by", "args",
   "git_at_spawn": {"head", "dirty": [git status --porcelain 줄]} 또는 null}], "updated_at": ISO}
  --verify 없이 같은 T 로 또 띄우면 앞의 verify 를 둔다. 다음 판의 lk verify 는 워커 worktree 에서
  git rev-parse --git-common-dir 로 이 파일을 찾고, 결과를 git rev-parse --git-dir 아래 lanekeeper/verify.jsonl 에 한 줄씩
  {"task", "cmd", "exit", "head", ...} 로 남긴다. 작업 트리 밖이라 "변경 없음" 검사에 걸리지 않는다.
close: claude agents --json 의 cwd 는 믿을 수 없어(떠 있는 세션은 옮겨 간 worktree 일 때도 있고, 멈춘 세션은 띄운 폴더다)
  세션이 일한 곳은 그 transcript 에서 찾는다(session_places).
  - 옮겨 간 worktree(worktree-state, relocated, EnterWorktree 결과) 하나하나: 커밋하지 않은 변경(무시되지 않은 새 파일 포함,
    <저장소>/.claude/worktrees 는 뺌)이 없고 HEAD 가 원격 추적 브랜치나 main/master 에 들어 있어야 한다. 폴더가 없어졌으면
    그 브랜치가 남아 있을 때 브랜치를 본다.
  - 띄운 폴더: worktree 로 옮겨 가지 않았거나, 나와서 띄운 저장소에서 끝났을 때만 같은 검사를 한다. transcript 의 마지막 cwd 가
    남의 저장소나 허브 폴더면(셸이 따라간 곳) 보지 않는다. lk spawn 기록의 git_at_spawn 이 있으면 그때부터
    있던 변경 줄은 빼고, HEAD 가 그때와 같으면(세션이 커밋하지 않음) 된다. 옮겨 간 세션은 띄운 폴더의 사용자 파일을 보지 않는다.
  - transcript 를 찾지 못하면 어디서 일했는지 모르니 거부한다. git 이 없거나 실패해도 거부한다.
  그다음 claude stop, 다시 같은 검사, 기록, claude rm 순이다. claude rm 이 worktree 와 그 git 폴더를 지우니
  기록이 먼저다. rm 이 0 을 돌려줘도 claude agents --json --all 에 행이 남으면 실패로 알린다.
  기록은 <허브>/.lanekeeper/closed.jsonl 에 세션마다 한 줄(같은 sessionId 는 다시 쓰지 않음). branch, head, git, verify.runs 는
  세션이 마지막에 일한 곳(workdir) 기준이고, places 에 본 곳마다 {path, branch, head, git} 를 둔다.
  토큰은 대시보드 claude_tokens() 와 같은 값이다(본문과 subagents, cache_read 는 total 밖에 따로).
  재지시(redirects)는 lk close 를 부른 세션(CLAUDE_CODE_SESSION_ID)이 그 세션에 보낸 메시지 수에서 첫 배정 하나를 뺀 값이다.
  부른 세션을 모르면(Claude 세션 밖에서 부름) 받은 메시지 전체에서 하나를 뺀다. 원래 수는 messages_in, from_caller 에 둔다.
종료 코드: 0 됨, 2 규칙으로 거부(안전한지 모를 때 포함), 1 claude 실패나 기록 실패. 출력은 UTF-8 이다.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'hooks'))
sys.path.insert(0, os.path.join(ROOT, 'dashboard'))
from hubpath import native, task_name  # noqa: E402
import server  # noqa: E402  claude_tokens, transcript_path, claude_scan, merge_messages, BG_OUT

MAX_TASKS = 8
STATE = '.lanekeeper'


class Refuse(Exception):
    code = 2


class Fail(Exception):
    code = 1


def run_claude(args, cwd=None):
    """(종료 코드, stdout, stderr). 시험은 이 함수를 바꿔 끼운다."""
    try:
        r = subprocess.run([shutil.which('claude') or 'claude'] + list(args), cwd=cwd, capture_output=True,
                           encoding='utf-8', errors='replace', timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, '', str(e)
    return r.returncode, r.stdout or '', r.stderr or ''


def git_run(cwd, *args):
    """(종료 코드, stdout, stderr). git 이 없거나 시간을 넘기면 None."""
    try:
        r = subprocess.run(['git', '-C', cwd] + list(args), capture_output=True, encoding='utf-8', errors='replace',
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.returncode, r.stdout or '', r.stderr or ''


def git_out(cwd, *args):
    """git 출력(앞뒤 공백 뺌), 실패하면 None."""
    r = git_run(cwd, *args)
    return r[1].strip() if r and r[0] == 0 else None


def in_git(cwd):
    """cwd 나 그 위 폴더에 .git(폴더나 worktree 의 파일)이 있는지. git 의 오류 문구는 로캘마다 달라 기대지 않는다."""
    d = os.path.abspath(cwd)
    while not os.path.exists(os.path.join(d, '.git')):
        if os.path.dirname(d) == d:
            return False
        d = os.path.dirname(d)
    return True


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat(timespec='seconds')


def version():
    try:
        with open(os.path.join(ROOT, '.claude-plugin', 'plugin.json'), encoding='utf-8') as f:
            return str(json.load(f)['version'])
    except (OSError, ValueError, KeyError):
        return ''


def is_hub(d):
    if os.path.isfile(os.path.join(d, 'lanes.json')):
        return True
    try:
        with open(os.path.join(d, 'agents.json'), encoding='utf-8-sig') as f:
            return isinstance(json.load(f).get('resident'), dict)
    except (OSError, ValueError, AttributeError):
        return False


def hub_dir(arg, cwd):
    """--hub, LANEKEEPER_HUB_DIR, cwd 와 그 위 폴더 순. 못 찾으면 None."""
    for d in (arg, os.environ.get('LANEKEEPER_HUB_DIR', '')):
        if d and d.strip() and not ('<' in d and '>' in d):   # 채우지 않은 설정 예시 자리표시는 없는 것으로 본다
            return os.path.abspath(native(d))
    d = os.path.abspath(cwd)
    while True:
        if is_hub(d):
            return d
        if os.path.dirname(d) == d:
            return None
        d = os.path.dirname(d)


def need_hub(a):
    hub = hub_dir(a.hub, os.getcwd())
    if not hub or not os.path.isdir(hub):
        raise Refuse('허브 폴더를 찾지 못했다. --hub <허브 폴더> 를 주거나 LANEKEEPER_HUB_DIR 를 설정한다')
    return hub


def max_tasks():
    try:
        return max(1, int(os.environ.get('LANEKEEPER_MAX_TASKS') or MAX_TASKS))
    except ValueError:
        return MAX_TASKS


def agents(claude, all_=False):
    code, out, err = claude(['agents', '--json'] + (['--all'] if all_ else []))
    if code != 0:
        raise Fail('claude agents --json 이 실패했다: ' + err.strip()[:300])
    try:
        rows = json.loads(out or '[]')
    except ValueError:
        raise Fail('claude agents --json 출력을 JSON 으로 읽지 못했다')
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def caller(rows):
    """lk 를 부른 Claude 세션의 이름. 세션 밖에서 불렀으면 ''."""
    sid = os.environ.get('CLAUDE_CODE_SESSION_ID', '')
    return next((str(r.get('name') or '') for r in rows if sid and r.get('sessionId') == sid), '')


def read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, path)


def record_paths(hub, cwd, t):
    paths = [os.path.join(hub, STATE, 'tasks', t + '.json')]
    common = git_out(cwd, 'rev-parse', '--git-common-dir') if cwd and os.path.isdir(cwd) else None
    if common:
        paths.append(os.path.join(cwd, common, 'lanekeeper', 'tasks', t + '.json'))
    return paths


def record_spawn(hub, cwd, t, verify, sess):
    paths = record_paths(hub, cwd, t)
    rec = next((d for d in map(read_json, paths) if isinstance(d, dict)), None) or {'task': t, 'verify': [], 'sessions': []}
    if verify:
        rec['verify'] = list(verify)
    rec.setdefault('sessions', []).append(sess)
    rec['updated_at'] = iso(time.time())
    for p in paths:
        write_json(p, rec)
    return paths


def spawn_resident(a, extra, claude):
    """agents.json resident 에 있는 상주 세션을 띄운다. 이름 규칙과 작업 세션 상한을 보지 않고 T 번호 기록도 남기지 않는다.

    명부에 있는 이름만 받는 것은 --resident 가 이름 규칙과 상한을 건너뛰는 길이 되지 않게, 그리고 대시보드가 상주로 알아보는
    이름(명부의 resident)과 어긋나지 않게 하려는 것이다. 허브(lane HUB)는 사용자가 띄운다.
    """
    name = a.resident
    if name.startswith('task-'):
        raise Refuse('task- 이름은 작업 세션이다. --name 으로 띄운다: ' + name)
    if a.verify:
        raise Refuse('--verify 는 작업 세션(--name)에만 준다')
    hub = need_hub(a)
    d = read_json(os.path.join(hub, 'agents.json'))
    res = d.get('resident') if isinstance(d, dict) and isinstance(d.get('resident'), dict) else {}
    if not isinstance(res.get(name), dict):
        raise Refuse('agents.json resident 에 없는 이름이다: %s. 상주 세션은 명부에 먼저 적는다(이름은 대소문자까지 같게). '
                     '있는 이름: %s' % (name, ', '.join(sorted(res)) or '없음'))
    ent = res[name]
    if str(ent.get('lane') or '').upper() == 'HUB':
        raise Refuse('허브 세션은 사용자가 띄운다(lane 이 HUB 인 상주): ' + name)
    listed = str(ent.get('cwd') or '')
    cwd = os.path.abspath(native(a.cwd or listed))
    if not (a.cwd or listed):
        raise Refuse('--cwd 를 주거나 agents.json resident.%s.cwd 를 채운다' % name)
    if not os.path.isdir(cwd):
        raise Refuse('폴더가 없다: ' + cwd)
    if a.cwd and listed and not same(cwd, native(listed)):
        print('lk: 명부의 cwd(%s)와 다른 폴더에서 띄운다: %s' % (listed, cwd), file=sys.stderr)
    rows = agents(claude)
    live = [r for r in rows if r.get('name') == name]
    if live:
        raise Refuse('같은 이름의 세션이 이미 떠 있다: %s(id %s). 맥락을 새로 하려면 옛 세션을 claude stop 으로 멈추고, '
                     '목록에서 지우는 claude rm 은 사용자에게 부탁한 뒤 다시 띄운다' % (
                         name, ', '.join(str(r.get('id') or r.get('sessionId')) for r in live)))
    args = ['--bg', '--name', name, '--effort', a.effort] + extra
    code, out, err = claude(args, cwd)
    sys.stdout.write(out)
    sys.stderr.write(err)
    if code != 0:
        raise Fail('claude --bg 가 실패했다(종료 코드 %d)' % code)
    print('lk: 상주 세션 %s 를 띄웠다(작업 세션 상한 셈 밖, %s)' % (name, cwd))
    return 0


def spawn(a, extra, claude):
    if bool(a.name) == bool(a.resident):
        raise Refuse('--name(작업 세션)이나 --resident(상주 세션) 중 하나만 준다')
    if a.resident:
        return spawn_resident(a, extra, claude)
    info = task_name(a.name)
    if not info:
        raise Refuse('이름은 task-T<YYYYMMDD>-<NN>-<주제> 꼴이다(주제는 영어 소문자, 숫자, 하이픈). '
                     '예: task-T20261114-09-lanes-split. 받은 이름: %s' % a.name)
    if not a.cwd:
        raise Refuse('--cwd <저장소> 가 필요하다(허브 폴더에서 잘못 띄우지 않게 꼭 준다)')
    hub = need_hub(a)
    cwd = os.path.abspath(native(a.cwd))
    if not os.path.isdir(cwd):
        raise Refuse('폴더가 없다: ' + cwd)
    rows = agents(claude)
    if any(r.get('name') == a.name for r in rows):
        raise Refuse('같은 이름의 세션이 이미 떠 있다: ' + a.name)
    tasks = sorted(str(r.get('name')) for r in rows if str(r.get('name') or '').startswith('task-'))
    limit = max_tasks()
    if len(tasks) >= limit:
        raise Refuse('작업 세션이 이미 %d개 떠 있어(상한 %d) 띄우지 않는다. 끝난 세션을 lk close 로 닫고 다시 띄운다: %s' % (
            len(tasks), limit, ', '.join(tasks)))
    args = ['--bg', '--name', a.name, '--effort', a.effort] + extra
    base = snapshot(cwd)   # 세션이 쓰기 전에. lk close 가 띄운 폴더의 사용자 파일을 세션 변경과 가른다
    code, out, err = claude(args, cwd)
    sys.stdout.write(out)   # backgrounded · <id> 줄을 그대로 둔다. 대시보드가 이 줄로 누가 띄웠는지 잇는다
    sys.stderr.write(err)
    if code != 0:
        raise Fail('claude --bg 가 실패했다(종료 코드 %d). 기록을 남기지 않았다' % code)
    m = server.BG_OUT.search(out)
    sess = {'name': a.name, 'id': m.group(1) if m else '', 'cwd': cwd, 'spawned_at': iso(time.time()),
            'by': caller(rows), 'args': args, 'git_at_spawn': base}
    try:
        paths = record_spawn(hub, cwd, info['task'], a.verify, sess)
    except OSError as e:
        raise Fail('세션은 떴지만(%s) 기록을 남기지 못했다: %s' % (sess['id'] or a.name, e))
    print('lk: 작업 세션 %d/%d. 기록 %s' % (len(tasks) + 1, limit, ', '.join(paths)))
    return 0


STATUS = ('status', '--porcelain', '--', ':/', ':(top,exclude).claude/worktrees')


def git_failed(args, r):
    why = (r[2].strip().splitlines() or ['종료 코드 %d' % r[0]])[-1][:200] if r else 'git 을 돌리지 못함'
    return (False, 'git %s 이 실패해 브랜치가 안전한지 확인하지 못했다(%s). 원인을 고친 뒤 닫는다' % (args[0], why),
            '', '')


def snapshot(cwd):
    """lk spawn 때 띄운 폴더의 git 상태 {'head', 'dirty'}. 세션이 그 폴더에서만 일했을 때 lk close 가 이것을 빼고 본다.

    nipa 처럼 루트 checkout 에 사용자 파일(.orca/, settings.local.json.bak-*)이 늘 있는 저장소에서, 세션이 만든 변경만 보려고 둔다.
    git 저장소가 아니거나 git 이 실패하면 None.
    """
    if not cwd or not os.path.isdir(cwd) or not in_git(cwd):
        return None
    r = git_run(cwd, *STATUS)
    if not r or r[0] != 0:
        return None
    return {'head': git_out(cwd, 'rev-parse', '--verify', '-q', 'HEAD') or '',
            'dirty': [x for x in r[1].splitlines() if x.strip()]}


def git_safety(cwd, base=None):
    """(닫아도 되는지, 설명, 브랜치, HEAD). 위로 .git 이 없으면 지울 커밋이 없으니 된다.

    .git 이 있는데 git 이 없거나 실패하거나 시간을 넘기면 안전한지 모르니 안 된다. 변경은 저장소 전체에서 보되
    <저장소>/.claude/worktrees 는 다른 세션의 worktree 라 뺀다(저장소 루트에서 연 세션도 닫을 수 있게).
    base(snapshot() 값)를 주면 그때 이미 있던 변경 줄은 빼고, HEAD 가 그때와 같으면 세션이 커밋하지 않았으니 된다.
    """
    if not cwd or not os.path.isdir(cwd):
        return True, '폴더 없음', '', ''
    if not in_git(cwd):
        return True, 'git 저장소 아님', '', ''
    r = git_run(cwd, *STATUS)
    if not r or r[0] != 0:
        return git_failed(STATUS, r)
    before = set((base or {}).get('dirty') or [])
    dirty = [x for x in r[1].splitlines() if x.strip() and x not in before]
    if dirty:
        return False, '커밋하지 않은 변경이 있다(%s%s). 커밋하고 push 하거나 병합한 뒤 닫는다' % (
            dirty[0].strip(), ' 외 %d개' % (len(dirty) - 1) if len(dirty) > 1 else ''), '', ''
    r = git_run(cwd, 'rev-parse', '--verify', '-q', 'HEAD')
    if r and r[0] == 1:
        return True, '커밋 없음', '', ''
    if not r or r[0] != 0:
        return git_failed(('rev-parse',), r)
    head = r[1].strip()
    r = git_run(cwd, 'rev-parse', '--abbrev-ref', 'HEAD')
    if not r or r[0] != 0:
        return git_failed(('rev-parse',), r)
    branch = r[1].strip()
    if base and base.get('head') == head:
        return True, '띄울 때와 같은 커밋(%s), 띄울 때 있던 변경은 뺌' % head[:8], branch, head
    return ref_safety(cwd, head, branch)


def ref_safety(cwd, head, branch):
    """커밋 head 가 원격 추적 브랜치나 main/master 에 들어 있는지. (된다, 설명, 브랜치, HEAD)."""
    failed = git_failed
    r = git_run(cwd, 'for-each-ref', '--contains', head, '--format=%(refname)', 'refs/remotes')
    if not r or r[0] != 0:
        return failed(('for-each-ref',), r)
    if r[1].split():
        return True, '원격에 있음: ' + r[1].split()[0], branch, head
    for ref in ('main', 'master'):
        if ref == branch or git_out(cwd, 'rev-parse', '--verify', '-q', 'refs/heads/' + ref) is None:
            continue
        r = git_run(cwd, 'merge-base', '--is-ancestor', head, 'refs/heads/' + ref)
        if r and r[0] == 0:
            return True, '병합됨: ' + ref, branch, head
        if not r or r[0] != 1:
            return failed(('merge-base',), r)
    return False, ('브랜치 %s 의 커밋 %s 가 원격에 없고 main 이나 master 에도 병합되지 않았다. '
                   'push 하거나 병합한 뒤 닫는다' % (branch, head[:8])), branch, head


def real(p):
    """비교용 경로. Windows 의 짧은 이름(RUNNER~1), 대소문자, 슬래시가 달라도 같은 값."""
    return os.path.normcase(os.path.realpath(p))


def same(a, b):
    return bool(a and b) and real(a) == real(b)


def within(path, root):
    p, r = real(path), real(root)
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def toplevel(p):
    return (git_out(p, 'rev-parse', '--show-toplevel') if p and os.path.isdir(p) else None) or p


def session_places(path):
    """transcript 에서 세션이 일한 곳. {'launch': 첫 cwd, 'last': 마지막 cwd, 'entered': [{'path', 'branch', 'repo'}]}.

    claude agents --json 의 cwd 는 믿을 수 없다(2.1.325 실측: 떠 있는 77cf7a84 는 띄운 폴더였다가 worktree 로 바뀌었고, 멈춘
    시험 세션은 띄운 폴더로 돌아갔다). 옮겨 간 worktree 는 transcript 의
    worktree-state(worktreeSession.worktreePath, worktreeBranch, originalCwd), relocated(relocatedCwd),
    EnterWorktree 결과(toolUseResult.worktreePath)에 남는다. entered 는 이 셋에 나온 곳을 처음 나온 차례로 둔다.
    """
    launch = last = ''
    entered, enter_ids = {}, set()
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if '"cwd"' not in line and 'orktree' not in line and '"relocated' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            c = d.get('cwd')
            if isinstance(c, str) and c:
                launch, last = launch or c, c
            hits = []
            w = d.get('worktreeSession')
            if d.get('type') == 'worktree-state' and isinstance(w, dict):
                hits.append((w.get('worktreePath'), w.get('worktreeBranch'), w.get('originalCwd')))
            if d.get('type') == 'relocated':
                hits.append((d.get('relocatedCwd'), '', ''))
            content = (d.get('message') or {}).get('content') if isinstance(d.get('message'), dict) else None
            for x in content if isinstance(content, list) else []:
                if isinstance(x, dict) and x.get('type') == 'tool_use' and x.get('name') == 'EnterWorktree':
                    enter_ids.add(x.get('id'))
                elif isinstance(x, dict) and x.get('type') == 'tool_result' and x.get('tool_use_id') in enter_ids:
                    t = d.get('toolUseResult')
                    if isinstance(t, dict):
                        hits.append((t.get('worktreePath'), t.get('worktreeBranch'), ''))
            t = d.get('toolUseResult')
            if not content and isinstance(t, dict) and t.get('worktreePath'):   # 본문 없이 결과만 남은 줄
                hits.append((t.get('worktreePath'), t.get('worktreeBranch'), ''))
            for p, b, o in hits:
                if isinstance(p, str) and p:
                    e = entered.setdefault(p, {'path': p, 'branch': '', 'repo': ''})
                    e['branch'], e['repo'] = e['branch'] or str(b or ''), e['repo'] or str(o or '')
    return {'launch': launch, 'last': last, 'entered': list(entered.values())}


def gone_safety(e, launch):
    """폴더가 없어진 worktree: 그 브랜치가 남아 있으면 브랜치를 본다. 브랜치도 없으면 잃을 것이 없다."""
    repo, branch = e.get('repo') or launch, e.get('branch')
    if not branch:
        return False, '폴더가 없어졌고 브랜치를 몰라 안전한지 확인하지 못했다', '', ''
    if not repo or not os.path.isdir(repo) or not in_git(repo):
        return False, '폴더가 없어졌고 브랜치 %s 가 든 저장소를 찾지 못했다' % branch, branch, ''
    r = git_run(repo, 'rev-parse', '--verify', '-q', 'refs/heads/' + branch)
    if r and r[0] == 1:
        return True, '폴더와 브랜치 %s 가 없어짐' % branch, branch, ''
    if not r or r[0] != 0:
        return git_failed(('rev-parse',), r)
    return ref_safety(repo, r[1].strip(), branch)


def spawn_base(hub, launch, t, r):
    """lk spawn 이 그 세션 기록에 남긴 띄운 폴더 git 상태. 없으면 None(lk spawn 밖에서 띄움, 0.8 전 기록)."""
    for d in map(read_json, record_paths(hub, launch, t) if t else []):
        for s in (d.get('sessions') or []) if isinstance(d, dict) else []:
            if isinstance(s, dict) and s.get('id') and s.get('id') == r.get('id') and isinstance(s.get('git_at_spawn'), dict):
                return s['git_at_spawn']
    return None


def session_safety(r, hub, t):
    """(닫아도 되는지, 설명, 본 곳 [{'path', 'branch', 'head', 'git'}], 세션이 마지막에 있던 곳, transcript).

    세션이 옮겨 간 worktree 는 claude rm 이 지울 수 있으니 하나하나 커밋과 push 를 본다. 띄운 폴더는 세션이 마지막에 거기
    있었을 때만 보고, lk spawn 기록에 그때 상태가 있으면 그때부터 있던 변경과 커밋은 뺀다. transcript 를 찾지 못하면 어디서
    일했는지 모르니 닫지 않는다.
    """
    sid, row_cwd = str(r.get('sessionId') or ''), str(r.get('cwd') or '')
    path = server.transcript_path(sid, row_cwd) if sid else None
    if not path:
        return (False, '세션 transcript 를 찾지 못해(sessionId %s) 세션이 옮겨 간 worktree 를 알 수 없다. 닫지 않는다'
                % (sid or '없음'), [], None, None)
    try:
        s = session_places(path)
    except OSError as e:
        return False, '세션 transcript 를 읽지 못해 세션이 일한 곳을 알 수 없다(%s)' % e, [], None, path
    launch, last = s['launch'] or row_cwd, s['last'] or row_cwd
    entered = [e for e in s['entered'] if not same(e['path'], launch)]
    seen, work, alive = [], None, None
    for e in entered:
        ok, why, branch, head = git_safety(e['path']) if os.path.isdir(e['path']) else gone_safety(e, launch)
        seen.append({'path': e['path'], 'branch': branch or e['branch'], 'head': head, 'git': why})
        if not ok:
            return False, 'worktree %s: %s' % (e['path'], why), seen, None, path
        if os.path.isdir(e['path']):
            alive = seen[-1]
            if last and within(last, e['path']):
                work = seen[-1]
    # transcript 의 cwd 는 셸을 따라 남의 저장소나 허브 폴더로도 간다(nipa 190개 중 19개가 그런 곳에서 끝남). 그런 곳은 세션이
    # 일한 곳이 아니니 보지 않는다. 띄운 폴더는 옮겨 가지 않았거나, worktree 에서 나와 띄운 저장소에서 끝났을 때 본다
    if not entered or work is None and last and same(toplevel(last), toplevel(launch)):
        base = spawn_base(hub, launch, t, r)
        ok, why, branch, head = git_safety(launch, base)
        seen.append({'path': launch, 'branch': branch, 'head': head, 'git': why})
        if not ok:
            hint = '' if base or entered or not why.startswith('커밋하지 않은') else (
                '. 띄운 폴더에 늘 있는 사용자 파일이면 그 저장소의 .git/info/exclude 에 적거나, 세션을 lk spawn 으로 띄워 '
                '띄울 때 상태를 남긴다')
            return False, why + hint, seen, None, path
        work = seen[-1]
    work = work or alive or seen[-1]
    return True, work['git'], seen, work, path


def roster_task(hub, name):
    """0.7 까지 agents.json task 에 적던 T 번호."""
    d = read_json(os.path.join(hub, 'agents.json'))
    v = ((d or {}).get('task') or {}).get(name) if isinstance(d, dict) else None
    return str(v.get('task') or '') if isinstance(v, dict) else ''


def verify_record(hub, launch, cwd, t):
    """spec 은 lk spawn 기록(띄운 폴더나 세션 폴더 저장소)에서, runs 는 세션이 일한 폴더의 git 폴더에서 읽는다."""
    paths = (record_paths(hub, launch, t) + record_paths(hub, cwd, t)[1:]) if t else []
    spec = next((d.get('verify') for d in map(read_json, paths)
                 if isinstance(d, dict) and isinstance(d.get('verify'), list)), [])
    runs = []
    gd = git_out(cwd, 'rev-parse', '--git-dir') if cwd and os.path.isdir(cwd) else None
    if gd:
        try:
            with open(os.path.join(cwd, gd, 'lanekeeper', 'verify.jsonl'), encoding='utf-8') as f:
                for line in f:
                    try:
                        runs.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            pass
    return {'spec': spec, 'runs': runs}


def received(path, name):
    """그 세션이 받은 다른 세션 메시지. 대기열에 들어갔다 전달되며 두 번 남은 것은 하나로 센다(msg_id, 없으면 본문과 시각)."""
    if not path:
        return []
    try:
        recv = server.claude_scan(path)['recv']
    except OSError:
        return []
    return server.merge_messages([], [dict(x, to=name) for x in recv])


def close_record(r, rows, hub, t, places, work, path):
    name, sid, cwd = str(r.get('name')), str(r.get('sessionId') or ''), str(r.get('cwd') or '')
    who = caller(rows)
    msgs = received(path, name)
    mine = sum(1 for m in msgs if who and m['from'] == who)
    now, started = time.time(), r.get('startedAt')
    started = started / 1000 if isinstance(started, (int, float)) else None
    last = os.path.getmtime(path) if path else None
    return {'closed_at': iso(now), 'task': t, 'name': name, 'id': r.get('id'), 'sessionId': sid, 'cwd': cwd,
            'workdir': work['path'], 'branch': work['branch'], 'head': work['head'], 'git': work['git'], 'places': places,
            'started_at': iso(started) if started else '', 'last_activity_at': iso(last) if last else '',
            'elapsed_s': round(now - started) if started else None,
            'active_s': round(last - started) if started and last else None,
            'tokens': server.claude_tokens(path), 'messages_in': len(msgs), 'from_caller': mine, 'caller': who,
            'redirects': max((mine if who else len(msgs)) - 1, 0), 'verify': verify_record(hub, cwd, work['path'], t),
            'transcript': path or '', 'lk': version()}


def append_once(path, rec):
    """같은 sessionId 줄이 이미 있으면 쓰지 않는다(rm 이 실패해 다시 닫을 때)."""
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                try:
                    if json.loads(line).get('sessionId') == rec['sessionId'] and rec['sessionId']:
                        return False
                except (ValueError, AttributeError):
                    continue
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return True


def close(a, claude):
    hub = need_hub(a)
    rows = agents(claude, all_=True)
    hit = [r for r in rows if a.key and (r.get('name') == a.key or r.get('id') == a.key)]
    if not hit:
        raise Refuse('claude agents --json --all 에 없는 세션이다: ' + a.key)
    if len(hit) > 1:
        raise Refuse('이름이 같은 세션이 %d개다. id 로 닫는다: %s' % (len(hit), ', '.join(str(r.get('id')) for r in hit)))
    r = hit[0]
    name, sid = str(r.get('name') or ''), r.get('id')
    if not name.startswith('task-'):
        raise Refuse('작업 세션(이름이 task- 로 시작)만 닫는다. 상주 세션은 lk close 로 닫지 않는다: ' + (name or str(sid)))
    if not sid:
        raise Refuse('background 세션만 닫는다(claude rm 이 받을 id 가 없다): ' + name)
    t = (task_name(name) or {}).get('task') or roster_task(hub, name)
    ok, why, _, _, _ = session_safety(r, hub, t)
    if not ok:
        raise Refuse(why)
    code, out, err = claude(['stop', sid])   # 멈춘 세션에 다시 불러도 0 이었다(2.1.325). 끝난 차례지만 살아 있는 세션도 멈춘다
    sys.stdout.write(out)
    if code != 0 and any(x.get('id') == sid for x in agents(claude)):   # 이미 끝나 목록에 없으면 멈출 것이 없다
        raise Fail('claude stop %s 이 실패했고 세션이 아직 떠 있다: %s' % (sid, err.strip()[:300]))
    ok, why, places, work, tpath = session_safety(r, hub, t)   # 멈추는 사이 커밋하거나 옮겨 갔을 수 있다
    if not ok:
        raise Refuse(why + '. 세션은 멈춰 두었다(claude attach %s 로 다시 연다)' % sid)
    path = os.path.join(hub, STATE, 'closed.jsonl')
    try:
        append_once(path, close_record(r, rows, hub, t, places, work, tpath))
    except OSError as e:
        raise Fail('기록을 남기지 못해 지우지 않았다. 세션은 멈춰 두었다(claude attach %s 로 다시 연다): %s' % (sid, e))
    code, out, err = claude(['rm', sid])
    sys.stdout.write(out)
    sys.stderr.write(err)
    if code != 0:
        raise Fail('claude rm %s 이 실패했다. 기록은 남겼다(%s). 위 출력을 사용자에게 보인다' % (sid, path))
    if any(x.get('id') == sid for x in agents(claude, all_=True)):
        raise Fail('claude rm %s 이 0 을 돌려줬지만 세션이 claude agents --json --all 에 남아 있다(지우지 않고 남긴 worktree 가 '
                   '있을 수 있다). 기록은 남겼다(%s). 위 출력을 사용자에게 보인다' % (sid, path))
    print('lk: %s 를 닫았다(%s, %s). 기록 %s' % (name, work['path'], why, path))
    return 0


def main(argv=None, claude=run_claude):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if '--' in argv:
        i = argv.index('--')
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog='lk', description='lanekeeper 작업 세션 띄우기와 닫기')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sp = sub.add_parser('spawn', help='claude --bg 로 작업 세션(--name)이나 상주 세션(--resident)을 띄운다')
    sp.add_argument('--name', default='', help='task-T<YYYYMMDD>-<NN>-<주제>')
    sp.add_argument('--resident', default='', metavar='이름', help='agents.json resident 에 있는 상주 세션 이름')
    sp.add_argument('--cwd', default='', help='세션을 열 저장소. 작업 세션은 꼭 준다. 상주는 없으면 명부의 cwd')
    sp.add_argument('--effort', default='high', help='claude --effort. 기본 high, 복잡한 일은 xhigh')
    sp.add_argument('--verify', action='append', default=[], metavar='명령', help='완료 확인 명령(여러 번)')
    sp.add_argument('--hub', default='', help='허브 폴더')
    cp = sub.add_parser('close', help='기록을 남기고 claude stop, claude rm 으로 닫는다')
    cp.add_argument('key', metavar='이름|id')
    cp.add_argument('--hub', default='', help='허브 폴더')
    a = ap.parse_args(argv)
    try:
        if a.cmd == 'spawn':
            return spawn(a, extra, claude)
        if extra:
            raise Refuse('lk close 는 -- 뒤 인자를 받지 않는다')
        return close(a, claude)
    except (Refuse, Fail) as e:
        print('lk: ' + str(e), file=sys.stderr)
        return e.code


if __name__ == '__main__':
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding='utf-8', errors='backslashreplace')   # Bash 도구가 UTF-8 로 읽는다(Windows 기본은 cp949)
    sys.exit(main())
