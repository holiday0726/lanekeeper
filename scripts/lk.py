#!/usr/bin/env python3
"""lk: 작업 세션을 띄우고 닫는다. 허브와 슈퍼바이저가 claude --bg, claude rm 대신 쓴다(설정 예시가 그 둘을 deny 한다).

  lk spawn --name task-T<YYYYMMDD>-<NN>-<주제> --cwd <저장소> [--effort high] [--verify "<명령>"]... [--hub <허브>]
           [-- <claude 인자>...]
  lk close <이름 또는 id> [--hub <허브>]

플러그인 bin/lk 가 이 파일을 부른다. 플러그인이 켜져 있으면 bin/ 이 Bash 도구 PATH 에 있다.
허브 폴더: --hub, 환경 변수 LANEKEEPER_HUB_DIR, cwd 와 그 위 폴더 중 lanes.json 이나 resident 가 있는 agents.json 이 든 곳 순.
동시 작업 세션 상한: 환경 변수 LANEKEEPER_MAX_TASKS(기본 8). claude agents --json(끝난 세션 빼고)에서 이름이
task- 로 시작하는 세션을 센다. 상주 세션은 이름이 task- 로 시작하지 않으니 세지 않는다. 막힌(blocked) 세션도 떠 있으니 센다.

spawn 기록: <허브>/.lanekeeper/tasks/<T>.json 과 <저장소 git 공통 폴더>/lanekeeper/tasks/<T>.json 에 같은 내용을 쓴다.
  {"task": "T-YYYYMMDD-NN", "verify": ["명령", ...], "sessions": [{"name", "id", "cwd", "spawned_at", "by", "args"}],
   "updated_at": ISO}
  --verify 없이 같은 T 로 또 띄우면 앞의 verify 를 둔다. 다음 판의 lk verify 는 워커 worktree 에서
  git rev-parse --git-common-dir 로 이 파일을 찾고, 결과를 git rev-parse --git-dir 아래 lanekeeper/verify.jsonl 에 한 줄씩
  {"task", "cmd", "exit", "head", ...} 로 남긴다. 작업 트리 밖이라 "변경 없음" 검사에 걸리지 않는다.
close: 세션 폴더가 git 이면 커밋하지 않은 변경(무시되지 않은 새 파일 포함, <저장소>/.claude/worktrees 는 뺌)이 없고
  HEAD 가 원격 추적 브랜치나 main/master 에 들어 있을 때만 claude stop, 기록, claude rm 순으로 닫는다.
  git 이 없거나 실패하면 안전한지 모르니 거부한다. claude rm 이 worktree 와 그 git 폴더를 지우니
  기록이 먼저다. 기록은 <허브>/.lanekeeper/closed.jsonl 에 세션마다 한 줄(같은 sessionId 는 다시 쓰지 않음).
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


def spawn(a, extra, claude):
    info = task_name(a.name)
    if not info:
        raise Refuse('이름은 task-T<YYYYMMDD>-<NN>-<주제> 꼴이다(주제는 영어 소문자, 숫자, 하이픈). '
                     '예: task-T20261114-09-lanes-split. 받은 이름: %s' % a.name)
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
    code, out, err = claude(args, cwd)
    sys.stdout.write(out)   # backgrounded · <id> 줄을 그대로 둔다. 대시보드가 이 줄로 누가 띄웠는지 잇는다
    sys.stderr.write(err)
    if code != 0:
        raise Fail('claude --bg 가 실패했다(종료 코드 %d). 기록을 남기지 않았다' % code)
    m = server.BG_OUT.search(out)
    sess = {'name': a.name, 'id': m.group(1) if m else '', 'cwd': cwd, 'spawned_at': iso(time.time()),
            'by': caller(rows), 'args': args}
    try:
        paths = record_spawn(hub, cwd, info['task'], a.verify, sess)
    except OSError as e:
        raise Fail('세션은 떴지만(%s) 기록을 남기지 못했다: %s' % (sess['id'] or a.name, e))
    print('lk: 작업 세션 %d/%d. 기록 %s' % (len(tasks) + 1, limit, ', '.join(paths)))
    return 0


def git_safety(cwd):
    """(닫아도 되는지, 설명, 브랜치, HEAD). 위로 .git 이 없으면 지울 커밋이 없으니 된다.

    .git 이 있는데 git 이 없거나 실패하거나 시간을 넘기면 안전한지 모르니 안 된다. 변경은 저장소 전체에서 보되
    <저장소>/.claude/worktrees 는 다른 세션의 worktree 라 뺀다(저장소 루트에서 연 세션도 닫을 수 있게).
    """
    if not cwd or not os.path.isdir(cwd):
        return True, '폴더 없음', '', ''
    if not in_git(cwd):
        return True, 'git 저장소 아님', '', ''

    def failed(args, r):
        why = (r[2].strip().splitlines() or ['종료 코드 %d' % r[0]])[-1][:200] if r else 'git 을 돌리지 못함'
        return (False, 'git %s 이 실패해 브랜치가 안전한지 확인하지 못했다(%s). 원인을 고친 뒤 닫는다' % (args[0], why),
                '', '')

    args = ('status', '--porcelain', '--', ':/', ':(top,exclude).claude/worktrees')
    r = git_run(cwd, *args)
    if not r or r[0] != 0:
        return failed(args, r)
    dirty = [x for x in r[1].splitlines() if x.strip()]
    if dirty:
        return False, '커밋하지 않은 변경이 있다(%s%s). 커밋하고 push 하거나 병합한 뒤 닫는다' % (
            dirty[0].strip(), ' 외 %d개' % (len(dirty) - 1) if len(dirty) > 1 else ''), '', ''
    r = git_run(cwd, 'rev-parse', '--verify', '-q', 'HEAD')
    if r and r[0] == 1:
        return True, '커밋 없음', '', ''
    if not r or r[0] != 0:
        return failed(('rev-parse',), r)
    head = r[1].strip()
    r = git_run(cwd, 'rev-parse', '--abbrev-ref', 'HEAD')
    if not r or r[0] != 0:
        return failed(('rev-parse',), r)
    branch = r[1].strip()
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


def roster_task(hub, name):
    """0.7 까지 agents.json task 에 적던 T 번호."""
    d = read_json(os.path.join(hub, 'agents.json'))
    v = ((d or {}).get('task') or {}).get(name) if isinstance(d, dict) else None
    return str(v.get('task') or '') if isinstance(v, dict) else ''


def verify_record(hub, cwd, t):
    spec = next((d.get('verify') for d in map(read_json, record_paths(hub, cwd, t) if t else [])
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


def close_record(r, rows, hub, gitnote, branch, head):
    name, sid, cwd = str(r.get('name')), str(r.get('sessionId') or ''), str(r.get('cwd') or '')
    t = (task_name(name) or {}).get('task') or roster_task(hub, name)
    path = server.transcript_path(sid, cwd) if sid else None
    who = caller(rows)
    msgs = received(path, name)
    mine = sum(1 for m in msgs if who and m['from'] == who)
    now, started = time.time(), r.get('startedAt')
    started = started / 1000 if isinstance(started, (int, float)) else None
    last = os.path.getmtime(path) if path else None
    return {'closed_at': iso(now), 'task': t, 'name': name, 'id': r.get('id'), 'sessionId': sid, 'cwd': cwd,
            'branch': branch, 'head': head, 'git': gitnote,
            'started_at': iso(started) if started else '', 'last_activity_at': iso(last) if last else '',
            'elapsed_s': round(now - started) if started else None,
            'active_s': round(last - started) if started and last else None,
            'tokens': server.claude_tokens(path), 'messages_in': len(msgs), 'from_caller': mine, 'caller': who,
            'redirects': max((mine if who else len(msgs)) - 1, 0), 'verify': verify_record(hub, cwd, t),
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
    ok, why, _, _ = git_safety(r.get('cwd'))
    if not ok:
        raise Refuse(why)
    if r.get('state') != 'done':
        code, out, err = claude(['stop', sid])
        sys.stdout.write(out)
        if code != 0:
            raise Fail('claude stop %s 이 실패했다: %s' % (sid, err.strip()[:300]))
    ok, why, branch, head = git_safety(r.get('cwd'))   # 멈추는 사이 커밋했을 수 있다
    if not ok:
        raise Refuse(why + '. 세션은 멈춰 두었다(claude attach %s 로 다시 연다)' % sid)
    path = os.path.join(hub, STATE, 'closed.jsonl')
    try:
        append_once(path, close_record(r, rows, hub, why, branch, head))
    except OSError as e:
        raise Fail('기록을 남기지 못해 지우지 않았다. 세션은 멈춰 두었다(claude attach %s 로 다시 연다): %s' % (sid, e))
    code, out, err = claude(['rm', sid])
    sys.stdout.write(out)
    sys.stderr.write(err)
    if code != 0:
        raise Fail('claude rm %s 이 실패했다. 기록은 남겼다(%s). 위 출력을 사용자에게 보인다' % (sid, path))
    print('lk: %s 를 닫았다(%s). 기록 %s' % (name, why, path))
    return 0


def main(argv=None, claude=run_claude):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if '--' in argv:
        i = argv.index('--')
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog='lk', description='lanekeeper 작업 세션 띄우기와 닫기')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sp = sub.add_parser('spawn', help='claude --bg 로 작업 세션을 띄운다')
    sp.add_argument('--name', required=True, help='task-T<YYYYMMDD>-<NN>-<주제>')
    sp.add_argument('--cwd', required=True, help='세션을 열 저장소(허브 폴더에서 잘못 띄우지 않게 꼭 준다)')
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
