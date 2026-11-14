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

    def __init__(self, rows=(), rm_fails=False):
        self.rows, self.calls, self.rm_fails = [dict(r) for r in rows], [], rm_fails

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
            for r in self.rows:
                if r.get('id') == args[1]:
                    r['state'] = 'done'
            return 0, 'stopped %s\n' % args[1], ''
        if args[0] == 'rm':
            if self.rm_fails:
                return 1, '', 'not safe: unpushed commits\n'
            self.rows = [r for r in self.rows if r.get('id') != args[1]]
            return 0, 'removed %s\n' % args[1], ''
        return 1, '', 'unknown'

    def did(self, word):
        return [a for a, _ in self.calls if a and a[0] == word]


def task(name, state='working', **kw):
    return dict({'name': name, 'id': kw.pop('id', name[-8:]), 'sessionId': name + '-sid', 'cwd': '/x', 'state': state,
                 'kind': 'background', 'startedAt': 1794600000000}, **kw)


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


def test_close_non_git_folder(hub, tmp_path):
    d = tmp_path / 'plain'
    d.mkdir()
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


def test_close_rm_failure_and_retry(hub, tmp_path, capsys):
    d = tmp_path / 'plain'
    d.mkdir()
    rows = [task('task-T20261114-09-p', id='p1234567', cwd=str(d))]
    c = Claude(rows, rm_fails=True)
    assert close(c, hub, 'p1234567') == 1
    assert 'not safe' in capsys.readouterr().err and len(closed(hub)) == 1
    c.rm_fails = False
    assert close(c, hub, 'p1234567') == 0
    assert len(closed(hub)) == 1, '다시 닫아도 같은 세션 줄을 두 번 쓰지 않는다'
