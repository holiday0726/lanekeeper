"""레인 쓰기 강제 훅 시험: python3 -m pytest tests/test_lane_guard.py

경로 판정은 Windows 꼴(nt=True)도 문자열로 시험한다. 훅 실행은 cp949 입출력으로 돌려 Windows 한국어 로캘을 흉내 낸다.
"""
import json
import os
import subprocess
import sys

import pytest

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'hooks')
sys.path.insert(0, HOOKS)
from hubpath import inside, native, norm  # noqa: E402
from lane_guard import bash_targets, check  # noqa: E402


def W(f, cwd, tool='Write', key='file_path'):
    return {'tool_name': tool, 'tool_input': {key: f}, 'cwd': cwd}


def B(cmd, cwd):
    return {'tool_name': 'Bash', 'tool_input': {'command': cmd}, 'cwd': cwd}


def M(to, cwd):
    return {'tool_name': 'SendMessage', 'tool_input': {'to': to, 'message': 'x'}, 'cwd': cwd}


# 허브 폴더 보호(예전 hub_only_write 와 같은 판정). (이름, 막아야 하나, 훅 입력, hub_dir, CLAUDE_PROJECT_DIR)
NT_HUB = [
    ('워커가 허브 파일', True, W(r'C:\Users\Me\hub\STATUS.md', r'C:\work\repo'), r'C:\Users\Me\hub', ''),
    ('대소문자 다름', True, W(r'c:\users\me\HUB\status.md', r'C:\work\repo'), r'C:\Users\Me\hub', ''),
    ('슬래시 섞임', True, W('C:/Users/Me\\hub/agents.json', 'C:/work'), 'C:\\Users\\Me\\hub\\', ''),
    ('Git Bash 꼴 설정', True, W(r'C:\Users\Me\hub\STATUS.md', r'C:\work'), '/c/Users/Me/hub', ''),
    ('Git Bash 꼴 파일', True, W('/c/users/me/hub/x.md', r'C:\work'), r'C:\Users\Me\hub', ''),
    ('cygdrive 꼴', True, W('/cygdrive/C/Users/Me/hub/x.md', r'C:\work'), r'C:\Users\Me\hub', ''),
    ('.. 로 들어감', True, W(r'C:\work\..\Users\Me\hub\x.md', r'C:\work'), r'C:\Users\Me\hub', ''),
    ('상대 경로', True, W(r'..\hub\x.md', r'C:\Users\Me\repo'), r'C:\Users\Me\hub', ''),
    ('NotebookEdit', True, W(r'C:\Users\Me\hub\n.ipynb', r'C:\work', 'NotebookEdit', 'notebook_path'), r'C:\Users\Me\hub', ''),
    ('UNC 경로', True, W(r'\\srv\share\hub\x.md', r'C:\work'), r'\\SRV\share\hub', ''),
    ('허브 자신', False, W(r'C:\Users\Me\hub\STATUS.md', r'C:\Users\Me\hub'), r'C:\Users\Me\hub', ''),
    ('허브 하위 폴더에서', False, W(r'C:\Users\Me\hub\STATUS.md', r'c:\users\me\hub\reports'), r'C:\Users\Me\hub', ''),
    ('허브가 cd 한 뒤', False, W(r'C:\Users\Me\hub\STATUS.md', r'C:\work'), r'C:\Users\Me\hub', r'C:\Users\Me\hub'),
    ('워커가 허브로 cd', True, W(r'C:\Users\Me\hub\STATUS.md', r'C:\Users\Me\hub'), r'C:\Users\Me\hub', r'C:\work'),
    ('이름만 비슷한 폴더', False, W(r'C:\Users\Me\hub2\x.md', r'C:\work'), r'C:\Users\Me\hub', ''),
    ('다른 드라이브', False, W(r'D:\Users\Me\hub\x.md', r'C:\work'), r'C:\Users\Me\hub', ''),
    ('허브 밖 파일', False, W(r'C:\work\a.py', r'C:\work'), r'C:\Users\Me\hub', ''),
    ('hub_dir 비어 있음', False, W(r'C:\Users\Me\hub\x.md', r'C:\work'), '', ''),
    ('파일 경로 없음', False, {'tool_name': 'Write', 'tool_input': {}, 'cwd': r'C:\work'}, r'C:\Users\Me\hub', ''),
]
POSIX_HUB = [
    ('워커가 허브 파일', True, W('/home/u/hub/STATUS.md', '/home/u/repo'), '/home/u/hub', ''),
    ('끝 슬래시 설정', True, W('/home/u/hub/a.json', '/home/u/repo'), '/home/u/hub/', ''),
    ('.. 로 들어감', True, W('/home/u/repo/../hub/a', '/home/u/repo'), '/home/u/hub', ''),
    ('허브 자신', False, W('/home/u/hub/STATUS.md', '/home/u/hub'), '/home/u/hub', ''),
    ('이름만 비슷한 폴더', False, W('/home/u/hub2/a', '/home/u/repo'), '/home/u/hub', ''),
    ('Linux 는 대소문자 구별', False, W('/home/u/HUB/a', '/home/u/repo'), '/home/u/hub', ''),
    ('Linux 는 /c 를 드라이브로 보지 않음', False, W('/c/hub/a', '/home/u/repo'), 'C:/hub', ''),
]


@pytest.mark.parametrize('name,want,inp,hub,project', NT_HUB, ids=[c[0] for c in NT_HUB])
def test_hub_nt(name, want, inp, hub, project):
    assert bool(check(inp, hub, project, nt=True, roster={})) == want


@pytest.mark.skipif(os.name == 'nt', reason='POSIX 표는 realpath 를 쓴다')
@pytest.mark.parametrize('name,want,inp,hub,project', POSIX_HUB, ids=[c[0] for c in POSIX_HUB])
def test_hub_posix(name, want, inp, hub, project):
    assert bool(check(inp, hub, project, nt=False, roster={})) == want


def test_path_helpers():
    assert native('/c/Users/x', nt=True) == 'c:/Users/x' and native('/c/Users/x', nt=False) == '/c/Users/x'
    assert inside(norm('C:/', nt=True), norm('C:/', nt=True)) and inside('c:/a', 'c:/')


# 레인 경로. Windows 꼴 설정과 Git Bash 꼴 파일을 섞는다
NT_ROSTER = {'resident': {'hub': {'lane': 'HUB'}, 'web-main': {'lane': 'WEB'}},
             'lanes': {'WEB': [r'C:\p\web'], 'API': ['/c/p/api', r'C:\p\web\vendor\api'], 'DOC': 'docs'}}
HUBN = r'C:\Users\Me\hub'
NT_LANE = [
    ('자기 레인', False, W(r'C:\p\web\a.py', r'C:\p\web'), ''),
    ('자기 레인 worktree', False, W(r'C:\p\web\.claude\worktrees\x\a.py', r'C:\p\web\.claude\worktrees\x'), ''),
    ('worktree 에서 다른 레인', True, W(r'C:\p\api\a.py', r'C:\p\web\.claude\worktrees\x'), ''),
    ('다른 레인', True, W(r'c:\P\API\a.py', r'C:\p\web'), ''),
    ('Git Bash 꼴 대상', True, W('/c/p/api/a.py', r'C:\p\web'), ''),
    ('겹친 경로는 깊은 쪽이 주인', True, W(r'C:\p\web\vendor\api\x.py', r'C:\p\web'), ''),
    ('깊은 레인 세션이 자기 경로', False, W(r'C:\p\web\vendor\api\x.py', r'C:\p\web\vendor\api'), ''),
    ('이름만 비슷한 폴더', False, W(r'C:\p\api2\a.py', r'C:\p\web'), ''),
    ('레인 없는 세션이 레인 경로', True, W(r'C:\p\web\a.py', r'C:\other'), ''),
    ('레인 없는 세션이 밖', False, W(r'C:\other\a.py', r'C:\other'), ''),
    ('허브가 레인 저장소', True, W(r'C:\p\web\a.py', HUBN), ''),
    ('상대 경로 레인(허브 기준)', True, W(r'C:\Users\Me\hub\docs\a.md', r'C:\p\web'), ''),
    ('CLAUDE_PROJECT_DIR 이 우선', False, W(r'C:\p\api\a.py', r'C:\p\web'), r'C:\p\api'),
    ('Bash 리다이렉트', True, B(r'echo x > C:\\p\\api\\a.txt', r'C:\p\web'), ''),
    ('Bash 자기 레인 리다이렉트', False, B('echo x >> notes.txt', r'C:\p\web'), ''),
    ('Bash cd 뒤 상대 경로', True, B('cd /c/p/api && echo x > a.txt', r'C:\p\web'), ''),
    ('Bash 2>&1 은 대상 아님', False, B('make 2>&1 | tee build.log', r'C:\p\web'), ''),
    ('Bash /dev/null', False, B('ls > /dev/null', r'C:\p\web'), ''),
]


@pytest.mark.parametrize('name,want,inp,project', NT_LANE, ids=[c[0] for c in NT_LANE])
def test_lane_nt(name, want, inp, project):
    assert bool(check(inp, HUBN, project, nt=True, roster=NT_ROSTER)) == want


@pytest.mark.parametrize('cmd,want', [
    ('echo a > x', ['x']),
    ('echo a>>x; echo b &> y', ['x', 'y']),
    ('cmd 2>/dev/null >out', ['/dev/null', 'out']),
    ('cat a | tee -a l1 l2', ['l1', 'l2']),
    ("sed -i 's/a/b/' f1 f2", ['f1', 'f2']),
    ("sed -i.bak -e 's/a/b/' -e 's/c/d/' f1", ['f1']),
    ("sed 's/a/b/' f1", []),
    ('cp -r a b dest/', ['dest/']),
    ('mv -t dest a b', ['dest']),
    ('cp --target-directory=d a', ['d']),
    ('sudo FOO=1 tee x', ['x']),
    ('git commit -m "a > b"', []),
    ('echo "unclosed', []),
    ('cat < in > out', ['out']),
])
def test_bash_targets(cmd, want):
    assert [p for p, _ in bash_targets(cmd)] == want


def test_bash_cd_base():
    assert bash_targets('cd sub && cd deeper && echo > f') == [('f', 'sub/deeper')]


def test_message_hub_only():
    r = NT_ROSTER
    on = dict(nt=True, roster=r, message_hub_only=True)
    assert check(M('api-main', r'C:\p\web'), HUBN, **on)
    assert not check(M('hub', r'C:\p\web'), HUBN, **on)
    assert not check(M('hub [3fa9c1]', r'C:\p\web'), HUBN, **on)
    assert not check(M('uds:/run/x.sock', r'C:\p\web'), HUBN, **on)
    assert not check(M('main', r'C:\p\web'), HUBN, **on)
    assert not check(M('web-main', HUBN), HUBN, **on), '허브는 누구에게나 보낸다'
    assert not check(M('api-main', r'C:\p\web'), HUBN, nt=True, roster=r), '설정이 꺼져 있으면 막지 않는다'


def run(tmp, inp, project, *args, hub_dir=None):
    env = dict(os.environ, CLAUDE_PLUGIN_OPTION_HUB_DIR=str(tmp / 'hub') if hub_dir is None else hub_dir,
               CLAUDE_PROJECT_DIR=str(project), PYTHONIOENCODING='cp949')
    env.pop('CLAUDE_PLUGIN_OPTION_LANE_MESSAGE_HUB_ONLY', None)
    payload = json.dumps(inp, ensure_ascii=False).encode('utf-8')   # Claude Code 는 UTF-8 로 보낸다
    r = subprocess.run([sys.executable, os.path.join(HOOKS, 'lane_guard.py'), *args], input=payload, env=env,
                       capture_output=True)
    return r.returncode, r.stderr.decode('utf-8')


def test_hook_process(tmp_path):
    hub, web, api = tmp_path / 'hub', tmp_path / 'web', tmp_path / 'api'
    for d in (hub, web, api):
        d.mkdir()
    (hub / 'agents.json').write_text(json.dumps({'resident': {'hub': {'lane': 'HUB'}},
                                                 'lanes': {'WEB': [str(web)], 'API': [str(api)]}}), encoding='utf-8')
    code, err = run(tmp_path, W(str(hub / '현황.md'), str(web)), web)
    assert code == 2 and '허브만' in err
    code, err = run(tmp_path, W(str(api / 'a.py'), str(web)), web)
    assert code == 2 and 'API' in err and '허브에 요청' in err
    assert run(tmp_path, W(str(web / 'a.py'), str(web)), web) == (0, '')
    assert run(tmp_path, W(str(hub / 'STATUS.md'), str(hub)), hub) == (0, '')
    assert run(tmp_path, B('echo x > %s' % (api / 'a'), str(web)), web)[0] == 2
    assert run(tmp_path, W(str(hub / 'STATUS.md'), str(web)), web, hub_dir='') == (0, '')
    assert run(tmp_path, M('someone', str(web)), web)[0] == 0
    assert run(tmp_path, M('someone', str(web)), web, 'true')[0] == 2
    (hub / 'agents.json').write_text('{broken', encoding='utf-8')
    assert run(tmp_path, W(str(api / 'a.py'), str(web)), web) == (0, ''), '깨진 agents.json 이면 허브 폴더만 지킨다'
    if os.name != 'nt':   # Windows 는 심볼릭 링크를 만들려면 관리자 권한이 필요하다
        os.symlink(hub, web / 'hub-link')
        assert run(tmp_path, W(str(web / 'hub-link' / 'STATUS.md'), str(web)), web)[0] == 2


def test_lane_deny(tmp_path):
    sys.path.insert(0, os.path.join(HOOKS, '..', 'scripts'))
    from lane_deny import rule, rules
    assert rule('~/p/web/', '/h') == 'Edit(~/p/web/**)'
    assert rule('C:\\p\\web', '/h') == 'Edit(//c/p/web/**)'
    if os.name != 'nt':
        assert rule('/srv/web', '/h') == 'Edit(//srv/web/**)'
        assert rule('docs', '/h') == 'Edit(//h/docs/**)'
    (tmp_path / 'agents.json').write_text(json.dumps({'lanes': {'A': ['~/a', '~/a/'], 'B': '~/b', 'C': 3}}))
    assert rules(str(tmp_path)) == ['Edit(~/a/**)', 'Edit(~/b/**)']
