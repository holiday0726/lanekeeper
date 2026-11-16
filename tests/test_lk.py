"""lk spawn, lk close 시험: python3 -m pytest tests/test_lk.py

claude 는 부르지 않는다. lk.run_claude 를 가짜로 바꿔 끼우고, git 은 임시 폴더의 진짜 저장소로 돈다.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import lk  # noqa: E402
import server  # noqa: E402  lk 가 dashboard 를 경로에 넣는다

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
    assert '커밋' in capsys.readouterr().err and not c.did('stop')


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
    assert close(c, hub, NAME) == 2 and 'work.py' in capsys.readouterr().err
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
