"""lk spawn, lk close 시험: python3 -m pytest tests/test_lk.py

claude 는 부르지 않는다. lk.run_claude 를 가짜로 바꿔 끼우고, git 은 임시 폴더의 진짜 저장소로 돈다.
"""
import json
import os
import subprocess
import sys
import zlib

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import lk  # noqa: E402
import server  # noqa: E402  lk 가 dashboard 를 경로에 넣는다

REAL_RUN_PASEO = getattr(lk, 'run_paseo', None)   # 시험은 lk.run_paseo 를 가짜로 바꿔 끼운다(paseo 고정물)

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t', GIT_COMMITTER_NAME='t',
               GIT_COMMITTER_EMAIL='t@t', GIT_CONFIG_NOSYSTEM='1')


def git(repo, *args):
    r = subprocess.run(['git', '-C', str(repo)] + list(args), capture_output=True, text=True, env=GIT_ENV)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class Claude:
    """claude agents, --bg, stop, rm 만 흉내 낸다. calls 에 부른 인자를 남긴다."""

    def __init__(self, rows=(), rm_fails=False, stop_fails=False, rm_keeps=False, on_stop=None):
        self.rows, self.calls, self.rm_fails, self.stop_fails = [dict(r) for r in rows], [], rm_fails, stop_fails
        self.rm_keeps, self.on_stop = rm_keeps, on_stop

    def __call__(self, args, cwd=None):
        self.calls.append((list(args), cwd))
        if args[:2] == ['agents', '--json']:
            rows = self.rows if '--all' in args else [r for r in self.rows if r.get('state') != 'done']
            return 0, json.dumps(rows), ''
        if args[0] == '--bg':
            name = args[args.index('--name') + 1]
            self.rows.append({'name': name, 'id': 'abcd1234', 'sessionId': 'abcd1234-0000', 'cwd': cwd,
                              'state': 'working', 'kind': 'background', 'startedAt': 1794600000000})
            return 0, 'backgrounded · abcd1234 · %s\n  claude attach abcd1234    open in this terminal\n' % name, ''
        if args[0] == 'stop':
            if self.stop_fails:
                return 1, '', 'cannot stop %s\n' % args[1]
            for r in self.rows:
                if r.get('id') == args[1]:
                    r['state'] = 'done'
            if self.on_stop:
                self.on_stop()
            return 0, 'stopped %s\n' % args[1], ''
        if args[0] == 'rm':
            if self.rm_fails:
                return 1, '', 'not safe: unpushed commits\n'
            if not self.rm_keeps:                     # rm_keeps: 0 을 돌려주고 행을 남기는 경우
                self.rows = [r for r in self.rows if r.get('id') != args[1]]
            return 0, 'removed %s\n' % args[1], ''
        return 1, '', 'unknown'

    def did(self, word):
        return [a for a, _ in self.calls if a and a[0] == word]


def task(name, state='working', **kw):
    return dict({'name': name, 'id': kw.pop('id', name[-8:]), 'sessionId': name + '-sid', 'cwd': '/x', 'state': state,
                 'kind': 'background', 'startedAt': 1794600000000}, **kw)


class Paseo:
    """paseo ls, run, inspect, stop, archive 만 흉내 낸다(0.15.1 의 --json 출력 꼴). calls 에 부른 인자를 남긴다.

    rows 는 보관한 세션까지 든 Paseo 저장소다. missing 은 paseo 가 없는 PC(CI), fails 는 그 하위 명령이 실패하는 경우.
    running_after_stop: stop 뒤 inspect 몇 번까지 running 으로 남는지(True 는 계속). 0.15.1 의 stop 은 cancel 이 실패해도
    경고만 찍고 0 이다. run_cwd: run 이 --cwd 와 다른 폴더에 띄웠다고 돌려줄 때.
    """

    def __init__(self, rows=(), missing=False, fails=(), keeps_archive=False, running_after_stop=0, workspaces=(),
                 run_cwd=None):
        self.rows, self.calls, self.missing, self.fails = [dict(r) for r in rows], [], missing, set(fails)
        self.keeps_archive, self.running_after_stop, self.workspaces = keeps_archive, running_after_stop, list(workspaces)
        self.run_cwd, self.still = run_cwd, 0

    def __call__(self, args):
        self.calls.append(list(args))
        if self.missing:
            return 127, '', 'paseo 를 찾지 못했다'
        if args[0] in self.fails:
            return 1, '', json.dumps({'error': {'code': 'X', 'message': '%s boom' % args[0]}})
        if args[:2] == ['workspace', 'ls']:
            return 0, json.dumps(self.workspaces), ''
        if args[0] == 'ls':
            rows = self.rows if '--all' in args else [r for r in self.rows if not r.get('archived')]
            return 0, json.dumps([{'id': r['id'], 'shortId': r['id'][:7], 'name': r['name'],
                                   'provider': '%s/%s' % (r['provider'], r['model']), 'thinking': 'auto',
                                   'status': r['status'], 'cwd': r['cwd'], 'created': '1 minutes ago'} for r in rows]), ''
        if args[0] == 'run':
            opt = lambda k: args[args.index(k) + 1] if k in args else None  # noqa: E731
            r = {'id': 'p%07d-0000-4000-8000-000000000000' % (len(self.rows) + 1), 'name': opt('--title'),
                 'provider': opt('--provider'), 'model': opt('--model') or '-', 'status': 'running',
                 'cwd': self.run_cwd or opt('--cwd'), 'archived': False}
            self.rows.append(r)
            return 0, json.dumps({'agentId': r['id'], 'status': 'running', 'provider': r['provider'], 'cwd': r['cwd'],
                                  'title': r['name']}), 'Created workspace wks_1 - x\n'
        hit = [r for r in self.rows if r['id'] == args[1] or r['id'][:7] == args[1]]
        if not hit:
            return 1, '', json.dumps({'error': {'code': 'AGENT_NOT_FOUND', 'message': 'Agent not found: ' + args[1]}})
        r = hit[0]
        if args[0] == 'inspect':
            if r['status'] == 'running' and self.still is not True:   # 첫 차례나 멈춘 run 은 still 번 뒤 끝난다
                if self.still > 0:
                    self.still -= 1
                else:
                    r['status'] = 'idle'
            return 0, json.dumps({'Id': r['id'], 'Name': r['name'], 'Provider': r['provider'], 'Model': r['model'],
                                  'Status': r['status'], 'Archived': r['archived'], 'Mode': 'full-access', 'Cwd': r['cwd'],
                                  'CreatedAt': '2026-11-26T01:00:00.000Z', 'UpdatedAt': '2026-11-26T01:30:00.000Z',
                                  'LastUsage': {'InputTokens': 5, 'OutputTokens': 7, 'CachedTokens': 11, 'CostUsd': 0},
                                  'Worktree': None, 'ParentAgentId': None}), ''
        if args[0] == 'stop':
            r['status'] = 'running' if self.running_after_stop else 'idle'
            self.still = self.running_after_stop
            return 0, '', ''
        if args[0] == 'archive':
            if r['status'] == 'running' and '--force' not in args:
                return 1, '', json.dumps({'error': {'code': 'AGENT_RUNNING', 'message': 'currently running'}})
            r['archived'] = not self.keeps_archive
            return 0, json.dumps({'agentId': r['id'], 'archivedAt': '2026-11-26T02:00:00.000Z'}), ''
        return 1, '', 'unknown'

    def did(self, word):
        return [a for a in self.calls if a and a[0] == word]


def ptask(name, **kw):
    """Paseo 세션 행(보관하지 않음)."""
    return dict({'id': kw.pop('id', '%08x-0000-4000-8000-000000000000' % zlib.crc32(name.encode())), 'name': name,
                 'provider': 'codex', 'model': 'gpt-6.2-sol', 'status': 'idle', 'cwd': '/x', 'archived': False}, **kw)


@pytest.fixture(autouse=True)
def paseo(monkeypatch):
    """실제 Paseo 데몬을 건드리지 않게 모든 시험에 가짜 paseo 를 끼운다. Paseo 세션이 없는 PC 와 같다."""
    p = Paseo()
    monkeypatch.setattr(lk, 'run_paseo', p)
    monkeypatch.setattr(lk, 'sleep', lambda s: None, raising=False)   # stop 뒤 기다림을 건너뛴다
    return p


@pytest.fixture(autouse=True)
def projects(tmp_path, monkeypatch):
    """transcript 폴더(~/.claude/projects 대신). lk close 는 세션이 일한 곳을 여기서 찾는다."""
    p = tmp_path / 'projects'
    p.mkdir()
    monkeypatch.setattr(server, 'PROJECTS', str(p))
    return p


def trail(projects, sid, *cwds, states=()):
    """세션 transcript: cwd 가 차례로 바뀐 기록과 worktree-state 기록(states: worktreeSession 값들, None 은 나옴)."""
    lines = [{'type': 'user', 'cwd': str(c), 'message': {'content': 'x'}} for c in cwds]
    lines += [{'type': 'worktree-state', 'worktreeSession': s} for s in states]
    d = projects / '-x'
    d.mkdir(parents=True, exist_ok=True)
    with open(d / (sid + '.jsonl'), 'a', encoding='utf-8') as f:
        f.write(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in lines))


def entered(path, branch, orig):
    return {'originalCwd': str(orig), 'worktreePath': str(path), 'worktreeBranch': branch, 'worktreeName': 'w'}


@pytest.fixture
def hub(tmp_path):
    h = tmp_path / 'hub'
    h.mkdir()
    (h / 'agents.json').write_text('{"resident": {"hub": {"lane": "HUB"}}}', encoding='utf-8')
    return h


@pytest.fixture
def repo(tmp_path):
    remote, r = tmp_path / 'remote.git', tmp_path / 'repo'
    subprocess.run(['git', 'init', '-q', '--bare', str(remote)], check=True, env=GIT_ENV)
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(r)], check=True, env=GIT_ENV)
    (r / 'a.txt').write_text('a\n')
    git(r, 'add', '.')
    git(r, 'commit', '-qm', 'a')
    git(r, 'remote', 'add', 'origin', str(remote))
    git(r, 'push', '-q', 'origin', 'main')
    return r


def spawn(claude, *args):
    return lk.main(['spawn'] + list(args), claude=claude)


@pytest.mark.parametrize('name,ok', [
    ('task-T20261114-09-lanes-split', True),
    ('task-T20261114-09-x-supervisor', True),
    ('task-T20261114-123-bump071', True),
    ('task-lanes-split', False),                      # T 번호 없음(0.7 까지의 이름)
    ('task-T2026111-09-x', False),                    # 날짜 일곱 자리
    ('task-T20261340-09-x', False),                   # 없는 날짜
    ('task-T20261114-9-x', False),                    # 번호 한 자리
    ('task-T20261114-09', False),                     # 주제 없음
    ('task-T20261114-09-Lanes', False),               # 대문자
    ('task-T20261114-09-x--y', False),
    ('T20261114-09-x', False),
    ('task-T20261114-09-x; rm -rf /', False),
])
def test_name_rule(name, ok):
    assert bool(lk.task_name(name)) == ok
    if ok:
        assert lk.task_name(name)['task'] == 'T-' + name.split('-T')[1][:8] + '-' + name.split('-')[2]


def test_spawn_runs_claude_and_saves_verify(hub, repo, capsys):
    c = Claude([task('hub', kind='interactive', id=None)])
    code = spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261114-09-a', '--effort', 'xhigh',
                 '--verify', 'python3 -m pytest', '--verify', 'claude plugin validate --strict .', '--', '--model', 'm')
    out = capsys.readouterr().out
    assert code == 0
    assert c.did('--bg') == [['--bg', '--name', 'task-T20261114-09-a', '--effort', 'xhigh', '--model', 'm']]
    assert [cwd for a, cwd in c.calls if a[0] == '--bg'] == [str(repo)]
    assert 'backgrounded · abcd1234' in out, '대시보드가 띄운 세션을 잇는 줄을 그대로 내보낸다'
    rec = json.loads((hub / '.lanekeeper' / 'tasks' / 'T-20261114-09.json').read_text(encoding='utf-8'))
    assert rec['task'] == 'T-20261114-09' and rec['verify'] == ['python3 -m pytest', 'claude plugin validate --strict .']
    assert [s['id'] for s in rec['sessions']] == ['abcd1234'] and rec['sessions'][0]['name'] == 'task-T20261114-09-a'
    common = os.path.join(str(repo), git(repo, 'rev-parse', '--git-common-dir'))
    assert json.loads(open(os.path.join(common, 'lanekeeper', 'tasks', 'T-20261114-09.json'), encoding='utf-8').read()) == rec, \
        '워커가 git rev-parse --git-common-dir 로 찾을 사본'
    assert not git(repo, 'status', '--porcelain'), '작업 트리에는 쓰지 않는다'

    c.rows = [r for r in c.rows if r['name'] == 'hub']
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261114-09-b') == 0
    rec = json.loads((hub / '.lanekeeper' / 'tasks' / 'T-20261114-09.json').read_text(encoding='utf-8'))
    assert rec['verify'] == ['python3 -m pytest', 'claude plugin validate --strict .'], '--verify 없이 띄우면 앞 것을 둔다'
    assert [s['name'] for s in rec['sessions']] == ['task-T20261114-09-a', 'task-T20261114-09-b']


def test_spawn_refuses_bad_name(hub, repo, capsys):
    c = Claude()
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-lanes-split') == 2
    assert 'task-T' in capsys.readouterr().err and not c.did('--bg')


def test_spawn_limit_counts_task_sessions_only(hub, repo, capsys):
    live = [task('task-T20261114-%02d-x' % i) for i in range(1, 8)]
    others = [task('hub', kind='interactive', id=None), task('WF1', state='blocked'), task('designer'),
              dict(task('x'), name=None), task('task-T20261113-01-old', state='done')]
    c = Claude(live + others)
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261114-20-y') == 0, '7개면 띄운다'
    c.rows.append(task('task-T20261114-21-z', state='blocked'))   # 막혀 있어도 떠 있는 세션이다
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261114-22-w') == 2
    err = capsys.readouterr().err
    assert '8' in err and 'task-T20261114-21-z' in err and 'WF1' not in err
    assert len(c.did('--bg')) == 1
    os.environ['LANEKEEPER_MAX_TASKS'] = '10'
    try:
        assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261114-22-w') == 0, '상한은 사용자 설정'
    finally:
        del os.environ['LANEKEEPER_MAX_TASKS']


def test_spawn_refuses_live_duplicate(hub, repo, capsys):
    c = Claude([task('task-T20261114-09-a')])
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261114-09-a') == 2
    assert not c.did('--bg')


def test_spawn_claude_failure_writes_nothing(hub, repo):
    fail = lambda args, cwd=None: (0, '[]', '') if args[0] == 'agents' else (1, '', 'boom')  # noqa: E731
    assert spawn(fail, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261114-09-a') == 1
    assert not (hub / '.lanekeeper' / 'tasks').exists()


def test_hub_dir_resolution(hub, tmp_path, monkeypatch):
    monkeypatch.delenv('LANEKEEPER_HUB_DIR', raising=False)
    (hub / 'reports').mkdir()
    assert lk.hub_dir('', str(hub / 'reports')) == str(hub), 'cwd 에서 위로 올라가며 찾는다'
    other = tmp_path / 'other'
    other.mkdir()
    assert lk.hub_dir('', str(other)) is None
    monkeypatch.setenv('LANEKEEPER_HUB_DIR', str(hub))
    assert lk.hub_dir('', str(other)) == str(hub)
    assert lk.hub_dir(str(other), str(hub)) == str(other), '--hub 가 앞선다'


# lk close
def transcript(projects, sid, lines):
    d = projects / '-x'
    d.mkdir(parents=True, exist_ok=True)
    (d / (sid + '.jsonl')).write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in lines), encoding='utf-8')


def peer(frm, mid, text, t='2026-11-14T05:00:00Z'):
    return {'type': 'user', 'timestamp': t, 'origin': {'kind': 'peer', 'name': frm, 'msg_id': mid},
            'message': {'content': '<cross-session-message from="uds:/s" from-name="%s">%s</cross-session-message>' % (frm, text)}}


def usage(mid, i, o, cr, cw):
    return {'type': 'assistant', 'timestamp': '2026-11-14T05:01:00Z', 'message': {'id': mid, 'usage': {
        'input_tokens': i, 'output_tokens': o, 'cache_read_input_tokens': cr, 'cache_creation_input_tokens': cw}}}


@pytest.fixture
def worker(repo, tmp_path, monkeypatch):
    """repo 의 worktree 에서 일한 세션 하나와 그 transcript. 허브(hub-sid)가 lk close 를 부른다."""
    wt = tmp_path / 'repo' / '.claude' / 'worktrees' / 'w'
    git(repo, 'worktree', 'add', '-q', '-b', 'feat', str(wt))
    (wt / 'b.txt').write_text('b\n')
    git(wt, 'add', '.')
    git(wt, 'commit', '-qm', 'b')
    projects = tmp_path / 'projects'
    monkeypatch.setattr(server, 'PROJECTS', str(projects))
    monkeypatch.setenv('CLAUDE_CODE_SESSION_ID', 'hub-sid')
    transcript(projects, 'w-sid', [
        peer('hub', 'm1', '[배정] T-20261114-09 할 일'),
        peer('hub', 'm1', '[배정] T-20261114-09 할 일'),          # 대기열에 들어갔다가 전달되며 두 번 남은 같은 메시지
        peer('hub', 'm2', '[배정 보완] 이것도'),
        peer('hub', 'm3', '테스트도 돌려'),
        peer('web', 'm4', '[보고] 다른 레인 답'),
        usage('a1', 10, 20, 1000, 5), usage('a1', 10, 20, 1000, 5), usage('a2', 1, 2, 300, 0)])
    gd = git(wt, 'rev-parse', '--git-dir')
    os.makedirs(os.path.join(wt, gd, 'lanekeeper'), exist_ok=True)
    with open(os.path.join(wt, gd, 'lanekeeper', 'verify.jsonl'), 'w', encoding='utf-8') as f:
        f.write(json.dumps({'task': 'T-20261114-09', 'cmd': 'pytest', 'exit': 0, 'head': 'abc'}) + '\n')
    rows = [task('task-T20261114-09-w', id='w1234567', sessionId='w-sid', cwd=str(wt), startedAt=1794600000000),
            task('hub', kind='interactive', id=None, sessionId='hub-sid', state=None)]
    return wt, rows


def close(claude, hub, key):
    return lk.main(['close', '--hub', str(hub), key], claude=claude)


def closed(hub):
    p = hub / '.lanekeeper' / 'closed.jsonl'
    return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()] if p.exists() else []


def test_close_refuses_unpushed_branch(hub, worker, capsys):
    wt, rows = worker
    c = Claude(rows)
    assert close(c, hub, 'task-T20261114-09-w') == 2
    assert '원격' in capsys.readouterr().err
    assert not c.did('stop') and not c.did('rm') and closed(hub) == []


def test_close_refuses_dirty_tree(hub, worker, capsys):
    wt, rows = worker
    git(wt, 'push', '-q', 'origin', 'feat')
    (wt / 'new.py').write_text('x\n')                # 커밋하지 않은 새 파일
    c = Claude(rows)
    assert close(c, hub, 'w1234567') == 2
    err = capsys.readouterr().err
    assert 'new.py' in err and '그 세션이 만든 변경이면 커밋하고 push' in err
    assert '세션과 무관한 사용자 파일이면 커밋하지 말고 .git/info/exclude' in err and '사용자에게 확인' in err
    assert not c.did('stop') and not c.did('rm')


def test_close_pushed_records_then_removes(hub, worker, capsys):
    wt, rows = worker
    git(wt, 'push', '-q', 'origin', 'feat')
    (hub / '.lanekeeper' / 'tasks').mkdir(parents=True)
    (hub / '.lanekeeper' / 'tasks' / 'T-20261114-09.json').write_text(json.dumps({'task': 'T-20261114-09', 'verify': ['pytest']}))
    c = Claude(rows)
    assert close(c, hub, 'task-T20261114-09-w') == 0, capsys.readouterr()
    assert [a[0] for a, _ in c.calls if a[0] in ('stop', 'rm')] == ['stop', 'rm']
    assert c.did('rm') == [['rm', 'w1234567']], '--discard-unpushed 같은 옵션은 넘기지 않는다'
    [r] = closed(hub)
    assert r['task'] == 'T-20261114-09' and r['name'] == 'task-T20261114-09-w' and r['sessionId'] == 'w-sid'
    assert r['branch'] == 'feat' and r['head'] == git(wt, 'rev-parse', 'HEAD') and 'refs/remotes/origin/feat' in r['git']
    assert r['tokens']['total'] == 10 + 20 + 5 + 1 + 2 and r['tokens']['cacheRead'] == 1300, r['tokens']
    assert r['messages_in'] == 4 and r['from_caller'] == 3 and r['redirects'] == 2 and r['caller'] == 'hub', r
    assert r['verify'] == {'spec': ['pytest'], 'runs': [{'task': 'T-20261114-09', 'cmd': 'pytest', 'exit': 0, 'head': 'abc'}]}
    assert r['started_at'].startswith('2026-') and r['elapsed_s'] >= 0


def test_close_merged_into_main(hub, worker):
    wt, rows = worker
    repo = wt.parents[2]
    git(repo, 'merge', '-q', '--ff-only', 'feat')   # 원격에는 없고 main 에 들어감
    c = Claude(rows)
    assert close(c, hub, 'task-T20261114-09-w') == 0
    assert 'main' in closed(hub)[0]['git']


def test_close_non_git_folder(hub, tmp_path, projects):
    d = tmp_path / 'plain'
    d.mkdir()
    trail(projects, 'task-T20261114-09-p-sid', d)
    c = Claude([task('task-T20261114-09-p', id='p1234567', cwd=str(d))])
    assert close(c, hub, 'task-T20261114-09-p') == 0
    assert closed(hub)[0]['git'] == 'git 저장소 아님'


@pytest.mark.parametrize('rows,key,word', [
    ([task('WF1', id='r1234567')], 'WF1', 'task-'),
    ([task('task-T20261114-09-a', id='a1111111'), task('task-T20261114-09-a', id='a2222222')], 'task-T20261114-09-a', 'id'),
    ([], 'task-T20261114-09-a', '없'),
    ([task('task-T20261114-09-i', kind='interactive', id=None)], 'task-T20261114-09-i', 'background'),
])
def test_close_refuses(hub, rows, key, word, capsys):
    c = Claude(rows)
    assert close(c, hub, key) == 2
    assert word in capsys.readouterr().err and not c.did('stop') and not c.did('rm')


def test_close_rm_failure_and_retry(hub, tmp_path, capsys, projects):
    d = tmp_path / 'plain'
    d.mkdir()
    trail(projects, 'task-T20261114-09-p-sid', d)
    rows = [task('task-T20261114-09-p', id='p1234567', cwd=str(d))]
    c = Claude(rows, rm_fails=True)
    assert close(c, hub, 'p1234567') == 1
    assert 'not safe' in capsys.readouterr().err and len(closed(hub)) == 1
    c.rm_fails = False
    assert close(c, hub, 'p1234567') == 0
    assert len(closed(hub)) == 1, '다시 닫아도 같은 세션 줄을 두 번 쓰지 않는다'


def test_bin_wrapper_runs_lk():
    """bin/lk(sh)가 Python 을 찾아 lk.py 까지 간다. 이름 검사에서 멈추니 claude 는 부르지 않는다."""
    import shutil
    sh = shutil.which('bash') or shutil.which('sh')
    if not sh or 'system32' in sh.lower():   # Windows 의 WSL bash 는 Git Bash 가 아니다
        pytest.skip('Git Bash 나 sh 없음')
    r = subprocess.run([sh, os.path.join(ROOT, 'bin', 'lk'), 'spawn', '--cwd', '.', '--name', 'task-bad'], capture_output=True,
                       timeout=60)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert 'task-T' in r.stderr.decode('utf-8', 'replace')


def test_close_refuses_when_git_fails(hub, worker, tmp_path, monkeypatch, capsys):
    """git 이 없거나 실패하면 안전한지 모르니 거부한다. 폴더 위로 .git 이 없을 때만 git 저장소가 아니라고 본다."""
    wt, rows = worker
    git(wt, 'push', '-q', 'origin', 'feat')
    empty = tmp_path / 'nogit'
    empty.mkdir()
    monkeypatch.setenv('PATH', str(empty))
    c = Claude(rows)
    assert close(c, hub, 'task-T20261114-09-w') == 2
    assert 'git' in capsys.readouterr().err and not c.did('stop')
    plain = tmp_path / 'plain'
    plain.mkdir()
    assert lk.git_safety(str(plain))[:2] == (True, 'git 저장소 아님'), 'git 이 없어도 .git 이 없으면 저장소가 아니다'


def test_close_refuses_when_status_fails(hub, worker, monkeypatch):
    wt, rows = worker
    git(wt, 'push', '-q', 'origin', 'feat')
    (wt / 'b.txt').write_text('changed\n')
    real = lk.git_run
    monkeypatch.setattr(lk, 'git_run', lambda cwd, *a: (128, '', 'boom') if a[:1] == ('status',) else real(cwd, *a))
    c = Claude(rows)
    assert close(c, hub, 'task-T20261114-09-w') == 2 and not c.did('stop')


def test_close_repo_root_with_other_worktrees(hub, worker, capsys, projects):
    """저장소 루트 세션: 다른 세션의 .claude/worktrees 는 내 변경이 아니다. 루트 밖 하위 폴더 변경은 본다."""
    wt, rows = worker
    repo = wt.parents[2]
    trail(projects, 'r-sid', repo)
    c = Claude([task('task-T20261114-09-root', id='r1234567', sessionId='r-sid', cwd=str(repo))])
    assert close(c, hub, 'task-T20261114-09-root') == 0, capsys.readouterr()
    (repo / 'sub').mkdir()
    (repo / 'a.txt').write_text('changed\n')
    assert lk.git_safety(str(repo / 'sub'))[0] is False, '하위 폴더에서 열어도 저장소 전체 변경을 본다'


def test_spawn_needs_cwd(hub, repo, capsys):
    c = Claude()
    assert spawn(c, '--hub', str(hub), '--name', 'task-T20261114-09-a') == 2
    assert '--cwd' in capsys.readouterr().err and not c.calls


def test_hub_dir_placeholder_ignored(hub, monkeypatch):
    monkeypatch.setenv('LANEKEEPER_HUB_DIR', '<허브 폴더>')
    assert lk.hub_dir('', str(hub)) == str(hub), '채우지 않은 자리표시는 없는 것으로 본다'


def test_close_record_failure_keeps_session(hub, tmp_path, capsys, projects):
    d = tmp_path / 'plain'
    d.mkdir()
    trail(projects, 'task-T20261114-09-p-sid', d)
    (hub / '.lanekeeper').write_text('a file, so no folder', encoding='utf-8')
    c = Claude([task('task-T20261114-09-p', id='p1234567', cwd=str(d))])
    assert close(c, hub, 'p1234567') == 1
    assert '기록' in capsys.readouterr().err and not c.did('rm'), '기록을 못 남기면 지우지 않는다'


def test_close_when_stop_fails(hub, tmp_path, capsys, projects):
    """stop 이 실패해도 그 세션이 이미 떠 있지 않으면(끝난 세션) 닫는다. 떠 있으면 지우지 않는다."""
    d = tmp_path / 'plain'
    d.mkdir()
    trail(projects, 'task-T20261114-09-p-sid', d)
    trail(projects, 'task-T20261114-09-q-sid', d)
    c = Claude([task('task-T20261114-09-p', id='p1234567', cwd=str(d), state='done')], stop_fails=True)
    assert close(c, hub, 'p1234567') == 0 and c.did('rm') == [['rm', 'p1234567']]
    c = Claude([task('task-T20261114-09-q', id='q1234567', cwd=str(d), state='working')], stop_fails=True)
    assert close(c, hub, 'q1234567') == 1
    assert 'stop' in capsys.readouterr().err and not c.did('rm')


# 0.8.0 리뷰(T-20261116-01) P1: claude agents 의 cwd 는 띄운 폴더다. 세션이 EnterWorktree 로 옮겨 간 곳은 transcript 에 있다
NAME = 'task-T20261116-06-w'


@pytest.fixture
def moved(repo, projects):
    """저장소 루트(main, push 됨)에서 띄워 .claude/worktrees/w(브랜치 feat)로 옮겨 간 세션. 행의 cwd 는 루트다."""
    wt = repo / '.claude' / 'worktrees' / 'w'
    git(repo, 'worktree', 'add', '-q', '-b', 'feat', str(wt))
    (wt / 'b.txt').write_text('b\n')
    git(wt, 'add', '.')
    git(wt, 'commit', '-qm', 'b')
    trail(projects, 'm-sid', repo, wt, states=[entered(wt, 'feat', repo)])
    return repo, wt, [task(NAME, id='m1234567', sessionId='m-sid', cwd=str(repo))]


def test_close_looks_at_entered_worktree(hub, moved, capsys):
    """리뷰 A: 루트는 깨끗하고 push 됐지만 세션 worktree 에 push 안 한 커밋이 있다. 예전에는 닫았다."""
    repo, wt, rows = moved
    c = Claude(rows)
    assert close(c, hub, NAME) == 2
    err = capsys.readouterr().err
    assert 'feat' in err and str(wt.name) in err and not c.did('stop') and not c.did('rm') and closed(hub) == []
    git(wt, 'push', '-q', 'origin', 'feat')
    (wt / 'c.txt').write_text('uncommitted\n')
    assert close(c, hub, NAME) == 2 and 'c.txt' in capsys.readouterr().err and not c.did('stop')


def test_close_ignores_launch_root_after_move(hub, moved, capsys):
    """리뷰 B, C: worktree 는 push 됐다. 띄운 폴더 루트에 사용자 파일이 있고 main 이 원격보다 앞서도 닫는다."""
    repo, wt, rows = moved
    git(wt, 'push', '-q', 'origin', 'feat')
    gd = git(wt, 'rev-parse', '--git-dir')
    os.makedirs(os.path.join(wt, gd, 'lanekeeper'), exist_ok=True)
    with open(os.path.join(wt, gd, 'lanekeeper', 'verify.jsonl'), 'w', encoding='utf-8') as f:
        f.write(json.dumps({'task': 'T-20261116-06', 'cmd': 'pytest', 'exit': 0}) + '\n')
    (repo / '.claude').mkdir(exist_ok=True)
    (repo / '.claude' / 'settings.local.json.bak-202611141027').write_text('{}\n')
    git(repo, 'commit', '-q', '--allow-empty', '-m', 'local main only')
    c = Claude(rows)
    assert close(c, hub, NAME) == 0, capsys.readouterr()
    [r] = closed(hub)
    assert r['branch'] == 'feat' and r['head'] == git(wt, 'rev-parse', 'HEAD') and 'origin/feat' in r['git'], r
    assert lk.same(r['workdir'], str(wt)) and r['cwd'] == str(repo)
    assert [p['branch'] for p in r['places']] == ['feat']
    assert r['verify']['runs'] == [{'task': 'T-20261116-06', 'cmd': 'pytest', 'exit': 0}], '검증 기록은 worktree git 폴더에서'


def test_close_refuses_without_transcript(hub, repo, capsys):
    c = Claude([task(NAME, id='n1234567', sessionId='no-such', cwd=str(repo))])
    assert close(c, hub, NAME) == 2
    assert 'transcript' in capsys.readouterr().err and not c.did('stop')


def test_close_checks_every_entered_worktree(hub, moved, projects, capsys):
    """worktree 를 둘 거쳤으면 둘 다 본다. 앞의 것에 남은 커밋이 있으면 거부한다."""
    repo, wt, rows = moved
    wt2 = repo / '.claude' / 'worktrees' / 'w2'
    git(repo, 'worktree', 'add', '-q', '-b', 'feat2', str(wt2), 'main')
    git(wt2, 'push', '-q', 'origin', 'feat2')
    trail(projects, 'm-sid', wt2, states=[None, entered(wt2, 'feat2', repo)])
    c = Claude(rows)
    assert close(c, hub, NAME) == 2 and 'feat ' in capsys.readouterr().err
    git(wt, 'push', '-q', 'origin', 'feat')
    assert close(c, hub, NAME) == 0, capsys.readouterr()
    r = closed(hub)[0]
    assert r['branch'] == 'feat2' and sorted(p['branch'] for p in r['places']) == ['feat', 'feat2'], r


def test_close_vanished_worktree_checks_branch(hub, moved, capsys):
    """옮겨 간 worktree 폴더가 없어졌으면 그 브랜치를 본다. 브랜치도 없으면 잃을 것이 없다."""
    repo, wt, rows = moved
    git(repo, 'worktree', 'remove', '--force', str(wt))
    c = Claude(rows)
    assert close(c, hub, NAME) == 2 and 'feat' in capsys.readouterr().err, '브랜치 feat 는 push 안 됨'
    git(repo, 'push', '-q', 'origin', 'feat')
    assert close(c, hub, NAME) == 0, capsys.readouterr()


def test_close_vanished_worktree_without_branch(hub, moved, capsys):
    repo, wt, rows = moved
    git(repo, 'worktree', 'remove', '--force', str(wt))
    git(repo, 'branch', '-D', 'feat')
    assert close(Claude(rows), hub, NAME) == 0, capsys.readouterr()


def test_close_rechecks_after_stop(hub, moved, capsys):
    repo, wt, rows = moved
    git(wt, 'push', '-q', 'origin', 'feat')
    c = Claude(rows, on_stop=lambda: (wt / 'late.txt').write_text('x\n'))
    assert close(c, hub, NAME) == 2
    assert 'late.txt' in capsys.readouterr().err and c.did('stop') and not c.did('rm')


def test_close_reports_row_left_after_rm(hub, moved, capsys):
    """claude rm 이 0 을 돌려줬는데 행이 남으면(worktree 를 남긴 경우) 실패로 알린다."""
    repo, wt, rows = moved
    git(wt, 'push', '-q', 'origin', 'feat')
    c = Claude(rows, rm_keeps=True)
    assert close(c, hub, NAME) == 1
    assert '남아' in capsys.readouterr().err and len(closed(hub)) == 1


def test_close_never_moved_uses_spawn_snapshot(hub, repo, projects, capsys):
    """옮겨 가지 않은 세션은 띄운 폴더를 본다. lk spawn 때 이미 있던 사용자 파일과 그때의 HEAD 는 세션 것이 아니다."""
    (repo / '.orca').mkdir()
    (repo / '.orca' / 'x').write_text('user\n')
    git(repo, 'commit', '-q', '--allow-empty', '-m', 'user local commit')    # main 이 원격보다 앞섬
    c = Claude()
    assert spawn(c, '--hub', str(hub), '--name', NAME, '--cwd', str(repo)) == 0
    trail(projects, 'abcd1234-0000', repo)
    assert close(c, hub, NAME) == 0, capsys.readouterr()
    assert '띄울 때' in closed(hub)[0]['git']


def test_close_never_moved_new_file_refused(hub, repo, projects, capsys):
    (repo / '.orca').mkdir()
    (repo / '.orca' / 'x').write_text('user\n')
    c = Claude()
    assert spawn(c, '--hub', str(hub), '--name', NAME, '--cwd', str(repo)) == 0
    trail(projects, 'abcd1234-0000', repo)
    (repo / 'work.py').write_text('session work\n')
    assert close(c, hub, NAME) == 2
    err = capsys.readouterr().err
    assert 'work.py' in err and '.git/info/exclude' in err and '사용자에게 확인' in err
    (repo / 'work.py').unlink()
    (repo / 'a.txt').write_text('changed\n')
    git(repo, 'commit', '-qam', 'session commit')
    assert close(c, hub, NAME) == 2 and '원격' in capsys.readouterr().err, '세션이 루트에서 한 커밋은 push 해야 닫는다'


def test_close_never_moved_without_snapshot_is_strict(hub, repo, projects, capsys):
    (repo / '.orca').mkdir()
    (repo / '.orca' / 'x').write_text('user\n')
    trail(projects, 'n-sid', repo)
    c = Claude([task(NAME, id='n1234567', sessionId='n-sid', cwd=str(repo))])
    assert close(c, hub, NAME) == 2
    err = capsys.readouterr().err
    assert '.orca' in err and 'info/exclude' in err


def other_repo(tmp_path):
    """사용자 파일이 늘 있는 다른 저장소 루트(nipa WF1 처럼). transcript 의 cwd 는 셸을 따라 여기로 올 수 있다."""
    o = tmp_path / 'other'
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(o)], check=True, env=GIT_ENV)
    (o / 'user.bak').write_text('x\n')
    return o


def test_close_moved_session_ending_elsewhere(hub, moved, projects, tmp_path, capsys):
    """worktree 에서 일하고 셸이 마지막에 다른 저장소(WF1/out 같은 곳)에 있었다. 그 저장소는 보지 않는다."""
    repo, wt, rows = moved
    git(wt, 'push', '-q', 'origin', 'feat')
    o = other_repo(tmp_path)
    trail(projects, 'm-sid', o / '.', o)
    assert close(Claude(rows), hub, NAME) == 0, capsys.readouterr()
    r = closed(hub)[0]
    assert r['branch'] == 'feat' and lk.same(r['workdir'], str(wt)), r
    assert [p['branch'] for p in r['places']] == ['feat']


def test_close_never_moved_session_ending_elsewhere(hub, repo, projects, tmp_path, capsys):
    """옮겨 가지 않은 세션은 마지막 cwd 가 어디든 띄운 폴더를 본다. 루트에 push 안 한 커밋이 있으면 거부한다."""
    git(repo, 'commit', '-q', '--allow-empty', '-m', 'session work in root')
    plain = tmp_path / 'plain'
    plain.mkdir()
    trail(projects, 'n-sid', repo, plain)
    c = Claude([task(NAME, id='n1234567', sessionId='n-sid', cwd=str(repo))])
    assert close(c, hub, NAME) == 2 and '원격' in capsys.readouterr().err and not c.did('stop')
    git(repo, 'push', '-q', 'origin', 'main')
    assert close(c, hub, NAME) == 0, capsys.readouterr()
    r = closed(hub)[0]
    assert lk.same(r['workdir'], str(repo)) and r['branch'] == 'main', r


def test_close_back_in_launch_repo_checks_both(hub, moved, projects, capsys):
    """worktree 에 들어갔다 나와 띄운 저장소에서 끝나면 둘 다 본다."""
    repo, wt, rows = moved
    git(wt, 'push', '-q', 'origin', 'feat')
    trail(projects, 'm-sid', repo, states=[None])
    git(repo, 'commit', '-q', '--allow-empty', '-m', 'after exit, in root')
    assert close(Claude(rows), hub, NAME) == 2 and 'main' in capsys.readouterr().err
    git(repo, 'push', '-q', 'origin', 'main')
    assert close(Claude(rows), hub, NAME) == 0, capsys.readouterr()
    r = closed(hub)[0]
    assert lk.same(r['workdir'], str(repo)) and sorted(p['branch'] for p in r['places']) == ['feat', 'main'], r


def test_session_places_reads_tool_results(tmp_path):
    """EnterWorktree 결과(toolUseResult.worktreePath)와 relocated 만 있어도 옮겨 간 곳으로 본다."""
    p = tmp_path / 't.jsonl'
    lines = [{'type': 'user', 'cwd': '/r'}, {'type': 'relocated', 'relocatedCwd': '/r/.claude/worktrees/a'},
             {'type': 'user', 'toolUseResult': {'worktreePath': '/r/.claude/worktrees/b', 'worktreeBranch': 'wb'}},
             {'type': 'user', 'cwd': '/r/.claude/worktrees/b/src'}]
    p.write_text(''.join(json.dumps(x) + '\n' for x in lines), encoding='utf-8')
    s = lk.session_places(str(p))
    assert s['launch'] == '/r' and s['last'] == '/r/.claude/worktrees/b/src'
    assert [(w['path'], w['branch']) for w in s['entered']] == [('/r/.claude/worktrees/a', ''),
                                                               ('/r/.claude/worktrees/b', 'wb')]


# P2: 상주 세션 띄우기
@pytest.fixture
def roster_hub(hub, repo):
    (hub / 'agents.json').write_text(json.dumps({'resident': {
        'hub': {'lane': 'hub', 'cwd': str(hub)}, 'WF1': {'lane': 'WF1', 'cwd': str(repo)}}}), encoding='utf-8')
    return hub


def test_spawn_resident(roster_hub, repo, capsys):
    c = Claude([task('task-T20261116-0%d-a' % i, id='t%07d' % i) for i in range(8)])   # 작업 세션 상한이 차 있다
    assert spawn(c, '--hub', str(roster_hub), '--resident', 'WF1', '--', '--model', 'm') == 0, capsys.readouterr()
    [(args, cwd)] = [x for x in c.calls if x[0][0] == '--bg']
    assert args == ['--bg', '--name', 'WF1', '--effort', 'high', '--model', 'm'] and cwd == str(repo)
    assert '상주' in capsys.readouterr().out
    assert not (roster_hub / '.lanekeeper' / 'tasks').exists(), '상주 세션은 T 번호 기록을 남기지 않는다'


@pytest.mark.parametrize('args,word', [
    (['--resident', 'designer'], 'resident'),                            # 명부에 없는 이름
    (['--resident', 'wf1'], 'resident'),                                 # 대소문자가 다른 이름
    (['--resident', 'hub'], '허브'),                                      # 허브는 사용자가 띄운다
    (['--resident', 'task-T20261116-06-x'], '--name'),
    (['--resident', 'WF1', '--verify', 'pytest'], '--verify'),
    (['--resident', 'WF1', '--name', 'task-T20261116-06-x'], '하나'),
    ([], '하나'),
])
def test_spawn_resident_refuses(roster_hub, args, word, capsys):
    c = Claude()
    assert spawn(c, '--hub', str(roster_hub), *args) == 2
    assert word in capsys.readouterr().err and not [a for a, _ in c.calls if a[0] == '--bg']


def test_spawn_resident_refuses_live_duplicate(roster_hub, capsys):
    c = Claude([task('WF1', id='r1234567', kind='background')])
    assert spawn(c, '--hub', str(roster_hub), '--resident', 'WF1') == 2
    assert 'WF1' in capsys.readouterr().err and not [a for a, _ in c.calls if a[0] == '--bg']


def test_spawn_resident_cwd_override(roster_hub, tmp_path, capsys):
    other = tmp_path / 'other'
    other.mkdir()
    c = Claude()
    assert spawn(c, '--hub', str(roster_hub), '--resident', 'WF1', '--cwd', str(other)) == 0
    assert [cwd for a, cwd in c.calls if a[0] == '--bg'] == [str(other)]
    assert '명부' in capsys.readouterr().err, '명부의 cwd 와 다르면 알린다'


# Paseo 엔진(codex, antigravity): lk 가 paseo run 으로 띄우고 paseo stop, archive 로 닫는다
PNAME = 'task-T20261126-01-p'


def test_spawn_codex_runs_paseo(hub, repo, paseo, capsys):
    c = Claude([task('hub', kind='interactive', id=None)])
    code = spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex', '--model', 'gpt-6.2-sol',
                 '--verify', 'python3 -m pytest -q')
    out = capsys.readouterr().out
    assert code == 0, out
    assert not c.did('--bg'), 'claude 세션은 띄우지 않는다'
    assert paseo.did('ls') == [['ls', '--global', '--json']], '--global 이 없으면 지금 폴더 범위만 나온다'
    [run] = paseo.did('run')
    assert run[:-1] == ['run', '--no-wait', '--json', '--title', PNAME, '--provider', 'codex', '--model', 'gpt-6.2-sol',
                        '--mode', 'full-access', '--cwd', str(repo)]
    assert run[-1] == lk.WAIT_PROMPT and '허브' in run[-1], '첫 배정은 허브가 paseo send 로 보낸다. 지시문은 대기 한 줄뿐'
    pid = paseo.rows[0]['id']
    assert pid in out and PNAME in out
    rec = json.loads((hub / '.lanekeeper' / 'tasks' / 'T-20261126-01.json').read_text(encoding='utf-8'))
    assert rec['verify'] == ['python3 -m pytest -q']
    [s] = rec['sessions']
    assert (s['name'], s['id'], s['engine'], s['model'], s['cwd']) == (PNAME, pid, 'codex', 'gpt-6.2-sol', str(repo))
    assert s['git_at_spawn'] == {'head': git(repo, 'rev-parse', 'HEAD'), 'dirty': []}
    common = os.path.join(str(repo), git(repo, 'rev-parse', '--git-common-dir'))
    assert json.loads(open(os.path.join(common, 'lanekeeper', 'tasks', 'T-20261126-01.json'), encoding='utf-8').read()) == rec


def test_spawn_antigravity_and_effort(hub, repo, paseo, capsys):
    c = Claude()
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'antigravity',
                 '--model', 'gemini-4-neon-high') == 0, capsys.readouterr()
    [run] = paseo.did('run')
    assert run[run.index('--provider') + 1] == 'antigravity' and run[run.index('--mode') + 1] == 'full-access'
    assert '--thinking' not in run, '--effort 를 주지 않으면 provider 기본값'
    paseo.rows.clear()
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'antigravity', '--effort', 'xhigh') == 2
    assert '모델' in capsys.readouterr().err and len(paseo.did('run')) == 1, 'antigravity 는 thinking 이 없다. 모델 id 로 고른다'
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex', '--effort', 'xhigh') == 0
    run = paseo.did('run')[-1]
    assert run[run.index('--thinking') + 1] == 'xhigh', 'codex 는 --effort 를 thinking 으로 넘긴다'
    assert '--model' not in run, '--model 이 없으면 provider 기본 모델'


def wks(wid, cwd, isolation='local', background=False):
    return {'workspaceId': wid, 'project': 'repo', 'name': 'main', 'isolation': isolation, 'cwd': str(cwd),
            'background': background}


def test_spawn_paseo_reuses_folder_workspace(hub, repo, tmp_path, paseo):
    """paseo run 은 --workspace 가 없으면 부를 때마다 workspace 를 새로 만든다(0.15.1 실측). 같은 폴더의 local workspace 를 쓴다."""
    paseo.workspaces = [wks('wks_other', tmp_path), wks('wks_wt', repo, isolation='worktree'),
                        wks('wks_bg', repo, background=True), wks('wks_repo', repo), wks('wks_repo2', repo)]
    assert spawn(Claude(), '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex') == 0
    run = paseo.did('run')[0]
    assert run[run.index('--workspace') + 1] == 'wks_repo' and run[run.index('--cwd') + 1] == str(repo)
    paseo.rows, paseo.workspaces = [], [wks('wks_other', tmp_path)]
    assert spawn(Claude(), '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex') == 0
    assert '--workspace' not in paseo.did('run')[1], '없으면 paseo 가 만든다'
    paseo.rows, paseo.fails = [], {'workspace'}
    assert spawn(Claude(), '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex') == 0, \
        'workspace 목록을 못 읽어도 띄운다'
    assert '--workspace' not in paseo.did('run')[2]


def test_spawn_paseo_passes_extra_args(hub, repo, paseo):
    assert spawn(Claude(), '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex',
                 '--', '--label', 'k=v') == 0
    run = paseo.did('run')[0]
    assert run[-3:-1] == ['--label', 'k=v'] and run[-1] == lk.WAIT_PROMPT


def test_spawn_limit_counts_claude_and_paseo(hub, repo, paseo, capsys):
    c = Claude([task('task-T20261126-%02d-c' % i) for i in range(1, 5)] + [task('hub', kind='interactive', id=None)])
    paseo.rows = [ptask('task-T20261126-%02d-x' % i) for i in range(11, 14)] + [
        ptask('hub', provider='claude'), ptask('task-T20261125-01-old', archived=True)]
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261126-20-y', '--engine', 'codex') == 0, \
        '4 + 3 이면 띄운다(보관한 세션, task- 아닌 세션은 세지 않는다)'
    for engine in ('codex', 'claude'):
        assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261126-21-z', '--engine', engine) == 2
        err = capsys.readouterr().err
        assert '8' in err and 'task-T20261126-01-c' in err and 'task-T20261126-20-y' in err, err
    assert not c.did('--bg') and len(paseo.did('run')) == 1


@pytest.mark.parametrize('engine', ['claude', 'codex'])
def test_spawn_refuses_duplicate_across_engines(hub, repo, paseo, engine, capsys):
    paseo.rows = [ptask(PNAME)]
    c = Claude()
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', engine) == 2
    assert PNAME in capsys.readouterr().err and not c.did('--bg') and not paseo.did('run')
    paseo.rows, c.rows = [], [task(PNAME)]
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', engine) == 2
    assert not c.did('--bg') and not paseo.did('run')


def test_spawn_claude_without_paseo(hub, repo, paseo, capsys):
    """paseo 가 없는 PC(CI)에서 claude 엔진은 그대로다. codex 와 antigravity 는 거부한다."""
    paseo.missing = True
    c = Claude()
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261126-02-a') == 0
    assert c.did('--bg') == [['--bg', '--name', 'task-T20261126-02-a', '--effort', 'high']], 'claude 인자는 바뀌지 않는다'
    assert 'paseo' not in capsys.readouterr().err, '없는 것은 알리지 않는다'
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex') == 2
    assert 'paseo' in capsys.readouterr().err and len(c.did('--bg')) == 1


def test_spawn_when_paseo_ls_fails(hub, repo, paseo, capsys):
    paseo.fails = {'ls'}
    c = Claude()
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261126-02-a') == 0, 'claude 엔진은 막지 않는다'
    assert 'paseo ls' in capsys.readouterr().err, '세지 못한 것은 알린다'
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex') == 1
    assert 'paseo ls' in capsys.readouterr().err and not paseo.did('run')


def test_spawn_paseo_run_failure_writes_nothing(hub, repo, paseo, capsys):
    paseo.fails = {'run'}
    assert spawn(Claude(), '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex') == 1
    assert 'paseo run' in capsys.readouterr().err
    assert not (hub / '.lanekeeper' / 'tasks').exists()


@pytest.mark.parametrize('args,word', [
    (['--engine', 'gemini', '--name', PNAME, '--cwd', '.'], 'engine'),
    (['--engine', 'codex', '--resident', 'WF1'], 'resident'),
    (['--engine', 'antigravity', '--name', PNAME, '--cwd', '.', '--effort', 'high'], '모델'),
])
def test_spawn_engine_refuses(roster_hub, paseo, args, word, capsys):
    c = Claude()
    assert spawn(c, '--hub', str(roster_hub), *args) == 2
    assert word in capsys.readouterr().err and not c.did('--bg') and not paseo.did('run')


def test_spawn_claude_model_flag(hub, repo):
    c = Claude()
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261126-02-a', '--model', 'opus') == 0
    assert c.did('--bg') == [['--bg', '--name', 'task-T20261126-02-a', '--effort', 'high', '--model', 'opus']]


def test_run_paseo_drops_caller_env(monkeypatch):
    """허브가 Paseo 세션이면 PASEO_AGENT_ID 가 물려 온다. 두면 paseo run 이 --cwd 대신 허브 폴더에 허브의 자식으로 띄운다."""
    seen = {}

    def fake_run(argv, **kw):
        seen['argv'], seen['env'] = argv, kw.get('env')
        return subprocess.CompletedProcess(argv, 0, '[]', '')

    monkeypatch.setattr(lk.shutil, 'which', lambda n: '/bin/' + n)
    monkeypatch.setattr(lk.subprocess, 'run', fake_run)
    monkeypatch.setenv('PASEO_AGENT_ID', 'hub-agent')
    monkeypatch.setenv('PASEO_WORKSPACE_ID', 'wks_hub')
    monkeypatch.setenv('PASEO_HOME', '/h/.paseo')
    code, out, _ = REAL_RUN_PASEO(['ls', '--json'])
    assert code == 0 and seen['argv'] == ['/bin/paseo', 'ls', '--json']
    assert 'PASEO_AGENT_ID' not in seen['env'] and 'PASEO_WORKSPACE_ID' not in seen['env']
    assert seen['env']['PASEO_HOME'] == '/h/.paseo'
    monkeypatch.setattr(lk.shutil, 'which', lambda n: None)
    assert REAL_RUN_PASEO(['ls'])[0] == 127, 'paseo 가 없으면 127'


@pytest.fixture
def spawned(hub, repo, paseo):
    """lk spawn --engine codex 로 repo 에 띄운 Paseo 세션의 id."""
    assert spawn(Claude(), '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex',
                 '--model', 'gpt-6.2-sol', '--verify', 'pytest') == 0
    return paseo.rows[0]['id']


def commit_on_branch(repo, branch, push):
    """codex 는 띄운 checkout 에서 브랜치를 바꿔 일하기도 한다(T-20261117-01)."""
    git(repo, 'checkout', '-q', '-b', branch)
    (repo / 'b.txt').write_text('b\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'b')
    if push:
        git(repo, 'push', '-q', 'origin', branch)


def test_close_paseo_pushed_records_then_archives(hub, repo, paseo, spawned, capsys):
    commit_on_branch(repo, 'feat', push=True)
    c = Claude([task('hub', kind='interactive', id=None, sessionId='hub-sid', state=None)])
    assert close(c, hub, PNAME) == 0, capsys.readouterr()
    assert not c.did('stop') and not c.did('rm'), 'claude 세션 명령은 부르지 않는다'
    assert [a[0] for a in paseo.calls if a[0] in ('stop', 'archive')] == ['stop', 'archive']
    assert paseo.did('stop') == [['stop', spawned]] and paseo.did('archive')[0][:2] == ['archive', spawned]
    assert paseo.rows[0]['archived'] and not paseo.did('delete'), '지우지 않고 보관한다'
    [r] = closed(hub)
    assert (r['engine'], r['task'], r['name'], r['id'], r['sessionId']) == ('codex', 'T-20261126-01', PNAME, spawned, spawned)
    assert r['provider'] == 'codex/gpt-6.2-sol' and r['cwd'] == str(repo) and r['workdir'] == str(repo)
    assert r['branch'] == 'feat' and r['head'] == git(repo, 'rev-parse', 'HEAD') and 'refs/remotes/origin/feat' in r['git']
    assert r['tokens'] is None, '모르는 토큰은 비워 둔다'
    assert r['paseo_last_usage'] == {'InputTokens': 5, 'OutputTokens': 7, 'CachedTokens': 11, 'CostUsd': 0}
    assert r['verify']['spec'] == ['pytest'] and r['started_at'] == lk.iso(lk.stamp('2026-11-26T01:00:00.000Z'))
    assert r['last_activity_at'] == lk.iso(lk.stamp('2026-11-26T01:30:00Z')) and r['active_s'] == 1800


def test_close_paseo_refuses_unpushed(hub, repo, paseo, spawned, capsys):
    commit_on_branch(repo, 'feat', push=False)
    assert close(Claude(), hub, PNAME) == 2
    assert '원격' in capsys.readouterr().err
    assert not paseo.did('stop') and not paseo.did('archive') and closed(hub) == []


def test_close_paseo_dirty_and_snapshot(hub, repo, paseo, capsys):
    (repo / 'user.txt').write_text('사용자 파일\n', encoding='utf-8')   # 띄우기 전부터 있던 사용자 파일
    assert spawn(Claude(), '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex') == 0
    (repo / 'new.py').write_text('x\n')                # 세션이 만든 커밋하지 않은 파일
    assert close(Claude(), hub, PNAME) == 2
    assert 'new.py' in capsys.readouterr().err and not paseo.did('stop')
    (repo / 'new.py').unlink()
    assert close(Claude(), hub, PNAME) == 0, '띄울 때 있던 변경은 뺀다'
    assert '띄울 때' in closed(hub)[0]['git']


def test_close_paseo_rechecks_after_stop(hub, repo, paseo, spawned, capsys):
    def stop_then_write(args):
        r = paseo(args)
        if args[0] == 'stop':
            (repo / 'late.py').write_text('x\n')        # 멈추기 전 마지막 차례에 쓴 파일
        return r

    assert lk.main(['close', '--hub', str(hub), PNAME], claude=Claude(), paseo=stop_then_write) == 2
    err = capsys.readouterr().err
    assert 'late.py' in err and 'paseo send' in err and not paseo.did('archive') and closed(hub) == []


def test_close_paseo_archive_failure_and_retry(hub, repo, paseo, spawned, capsys):
    paseo.fails = {'archive'}
    assert close(Claude(), hub, PNAME) == 1
    assert 'archive' in capsys.readouterr().err and len(closed(hub)) == 1, '보관 전에 기록을 남긴다'
    paseo.fails = set()
    assert close(Claude(), hub, spawned[:7]) == 0, 'shortId 로도 닫는다'
    assert len(closed(hub)) == 1, '다시 닫아도 같은 세션 줄을 두 번 쓰지 않는다'


def test_close_paseo_reports_not_archived(hub, repo, paseo, spawned, capsys):
    paseo.keeps_archive = True
    assert close(Claude(), hub, PNAME) == 1
    assert '보관' in capsys.readouterr().err and len(closed(hub)) == 1


def test_close_paseo_waits_for_stop(hub, repo, paseo, spawned, capsys):
    """paseo stop 은 cancel 이 실패해도 0 이다. 다시 검사는 run 이 끝난 뒤라야 뜻이 있으니 running 이 풀릴 때까지 기다린다."""
    paseo.running_after_stop = 3
    assert close(Claude(), hub, PNAME) == 0, capsys.readouterr()
    assert '--force' in paseo.did('archive')[0] and paseo.rows[0]['archived']
    assert len([a for a in paseo.did('inspect')]) >= 5, '처음 한 번, 멈춘 뒤 running 셋과 idle 하나'


def test_close_paseo_still_running_after_stop(hub, repo, paseo, spawned, capsys):
    paseo.running_after_stop = True
    assert close(Claude(), hub, PNAME) == 1
    err = capsys.readouterr().err
    assert '돈다' in err and spawned in err
    assert not paseo.did('archive') and closed(hub) == [], '도는 세션은 기록하지도 보관하지도 않는다'


def test_close_paseo_stop_fails(hub, repo, paseo, spawned, capsys):
    paseo.fails = {'stop'}
    paseo.rows[0]['status'] = 'idle'
    assert close(Claude(), hub, PNAME) == 0, '멈출 것이 없던(이미 쉬는) 세션이면 닫는다'
    assert len(closed(hub)) == 1


def test_close_paseo_record_failure_keeps_session(hub, tmp_path, paseo, capsys):
    d = tmp_path / 'plain'
    d.mkdir()
    paseo.rows = [ptask(PNAME, cwd=str(d))]
    (hub / '.lanekeeper').write_text('a file, so no folder', encoding='utf-8')
    assert close(Claude(), hub, PNAME) == 1
    assert '기록' in capsys.readouterr().err and not paseo.did('archive'), '기록을 못 남기면 보관하지 않는다'


@pytest.mark.parametrize('claude_rows,paseo_rows,key,word', [
    ([task(PNAME)], [ptask(PNAME)], PNAME, 'id'),                          # 두 엔진에 같은 이름
    ([], [ptask('hub', provider='claude')], 'hub', 'task-'),              # 상주(허브) Paseo 세션
    ([], [ptask(PNAME, archived=True)], PNAME, '없'),                       # 이미 보관함
])
def test_close_paseo_refuses(hub, paseo, claude_rows, paseo_rows, key, word, capsys):
    paseo.rows = paseo_rows
    c = Claude(claude_rows)
    assert close(c, hub, key) == 2
    assert word in capsys.readouterr().err
    assert not c.did('stop') and not paseo.did('stop') and not paseo.did('archive')


def test_close_paseo_non_git_folder(hub, tmp_path, paseo):
    d = tmp_path / 'plain'
    d.mkdir()
    paseo.rows = [ptask(PNAME, cwd=str(d), provider='antigravity', model='gemini-4-neon-high')]
    assert close(Claude(), hub, PNAME) == 0
    [r] = closed(hub)
    assert r['git'] == 'git 저장소 아님' and r['engine'] == 'antigravity' and r['task'] == 'T-20261126-01'


@pytest.mark.parametrize('extra', [['--workspace', 'wks_x'], ['--new-workspace', 'worktree'], ['--worktree', 'w'],
                                   ['--cwd', '/elsewhere'], ['--workspace=wks_x'], ['--title', 'other']])
def test_spawn_paseo_refuses_placement_args(hub, repo, paseo, extra, capsys):
    """폴더와 workspace, 제목은 lk 가 정한다. worktree 에서 일할 세션은 worktree 를 만들어 --cwd 로 준다."""
    assert spawn(Claude(), '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex', '--', *extra) == 2
    assert '--cwd' in capsys.readouterr().err and not paseo.did('run')


def test_spawn_paseo_records_where_paseo_put_it(hub, repo, tmp_path, paseo, capsys):
    other = tmp_path / 'other'
    other.mkdir()
    paseo.run_cwd = str(other)
    assert spawn(Claude(), '--hub', str(hub), '--cwd', str(repo), '--name', PNAME, '--engine', 'codex') == 0
    assert str(other) in capsys.readouterr().err
    [s] = json.loads((hub / '.lanekeeper' / 'tasks' / 'T-20261126-01.json').read_text(encoding='utf-8'))['sessions']
    assert s['cwd'] == str(other) and s['git_at_spawn'] is None, '다른 폴더의 띄울 때 상태를 빼지 않는다'


def test_spawn_limit_keeps_claude_row_count(hub, repo, paseo, capsys):
    """claude 쪽은 예전처럼 행 수로 센다(lk 밖에서 같은 이름으로 둘 띄운 경우). Paseo 행은 claude 에 없는 이름만 더한다."""
    dup = [task('task-T20261126-01-c', id='a1'), task('task-T20261126-01-c', id='a2')]
    c = Claude(dup + [task('task-T20261126-%02d-c' % i) for i in range(2, 8)])
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261126-20-y') == 2, '행 8개면 거부'
    assert '8' in capsys.readouterr().err
    c.rows = c.rows[1:]
    paseo.rows = [ptask('task-T20261126-01-c')]
    assert spawn(c, '--hub', str(hub), '--cwd', str(repo), '--name', 'task-T20261126-20-y') == 0, \
        'claude 7개와 같은 이름의 Paseo 행은 7개로 센다'


def test_close_when_paseo_ls_fails(hub, paseo, capsys):
    paseo.fails = {'ls'}
    assert close(Claude(), hub, PNAME) == 2
    err = capsys.readouterr().err
    assert '찾지 못했다' in err and '세지' not in err


def test_close_paseo_unknown_model(hub, tmp_path, paseo):
    d = tmp_path / 'plain'
    d.mkdir()
    paseo.rows = [ptask(PNAME, cwd=str(d), model='-')]   # 0.15.1 inspect 는 모델을 모르면 "-"
    assert close(Claude(), hub, PNAME) == 0
    assert closed(hub)[0]['provider'] == 'codex'


@pytest.mark.parametrize('what', ['inspect', 'cwd'])
def test_close_paseo_without_inspect(hub, paseo, what, capsys):
    paseo.rows = [ptask(PNAME, cwd='' if what == 'cwd' else '/x')]
    if what == 'inspect':
        paseo.fails = {'inspect'}
    assert close(Claude(), hub, PNAME) == (1 if what == 'inspect' else 2)
    assert 'inspect' in capsys.readouterr().err and not paseo.did('stop')


def test_run_paseo_timeout_is_not_missing(monkeypatch):
    """paseo 가 없을 때만 127 이다. 시간을 넘기거나 돌리지 못하면 실패로 본다(claude 엔진은 알리고 띄운다)."""
    def boom(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 120)

    monkeypatch.setattr(lk.shutil, 'which', lambda n: '/bin/' + n)
    monkeypatch.setattr(lk.subprocess, 'run', boom)
    code, _, err = REAL_RUN_PASEO(['ls'])
    assert code not in (0, 127) and err
