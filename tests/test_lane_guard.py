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
from lane_guard import bash_targets, check, read_lanes  # noqa: E402


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


# 외부 리뷰(T-20261114-09)가 통과한다고 적은 범주를 다시 만든 목록. 리뷰 원문 21개가 아니라 범주마다 변형 둘 이상.
# WEB 워커(C:\p\web)가 API 레인(/c/p/api)에 쓰려는 명령. (범주, 명령, 막아야 하나)
BYPASS = [
    ('리다이렉트', 'echo x > /c/p/api/a.txt', True),
    ('리다이렉트', 'printf x >> ../api/a.txt', True),
    ('cd 뒤 리다이렉트', 'cd /c/p/api && echo x > a.txt', True),
    ('cd 뒤 리다이렉트', 'cd ../api; echo x > a.txt', True),
    ('cp', 'cp a.txt /c/p/api/', True),
    ('cp', 'cp -t ../api a.txt', True),
    ('히어독', "cat > /c/p/api/n.md <<'EOF'\nhi\nEOF", True),
    ('히어독', 'cd ../api && cat <<EOF > n.md\nhi\nEOF', True),
    ('cd 뒤 git commit', 'cd ../api; git commit -am x', True),
    ('cd 뒤 git commit', 'cd /c/p/api && git add -A && git commit -m x', True),
    ('git -C', 'git -C /c/p/api commit -am x', True),
    ('git -C', 'git -C ../api commit -am x', True),
    ('git -C', 'git -C ../api push origin HEAD', True),
    ('git -C', 'git --work-tree=/c/p/api --git-dir=/c/p/api/.git checkout -- .', True),
    ('rm', 'rm -rf /c/p/api/src', True),
    ('rm', 'cd ../api && rm -rf build', True),
    ('rm', 'rm -rf /c/p', True),                                   # 레인 루트를 품은 상위 폴더
    ('rm', 'find /c/p/api -name "*.pyc" -delete', True),
    ('touch', 'touch /c/p/api/x', True),
    ('touch', 'cd ../api; touch x', True),
    ('dd of=', 'dd if=/dev/zero of=/c/p/api/blob bs=1 count=1', True),
    ('dd of=', 'cd ../api && dd of=blob < /dev/null', True),
    ('patch -d', 'patch -d /c/p/api -p1 < fix.diff', True),
    ('patch -d', 'patch --directory=../api -p1 -i fix.diff', True),
    ('patch -d', 'cd ../api && patch -p1 < fix.diff', True),
    ('mv 원본', 'mv /c/p/api/a.py /tmp/', True),
    ('괄호 안 cd', '(cd ../api && mkdir new)', True),
    ('변수(문서에 적은 한계)', 'd=/c/p/api; touch $d/x', False),
    ('변수(문서에 적은 한계)', 'touch "${API}/x"', False),
    ('bash -c(문서에 적은 한계)', "bash -c 'touch /c/p/api/x'", False),
    ('bash -c(문서에 적은 한계)', "sh -c 'cd /c/p/api && git commit -am x'", False),
    ('읽기는 통과', 'git -C /c/p/api status', False),
    ('읽기는 통과', 'git -C ../api log --oneline -5', False),
    ('읽기는 통과', 'cd ../api && git diff && git branch -a', False),
    ('읽기는 통과', 'git -C /c/p/api fetch', False),
    ('자기 레인은 통과', 'git commit -am x && rm -rf build && touch y', False),
]


@pytest.mark.parametrize('kind,cmd,want', BYPASS, ids=['%s: %s' % (k, c.splitlines()[0]) for k, c, _ in BYPASS])
def test_bypass_table(kind, cmd, want):
    assert bool(check(B(cmd, r'C:\p\web'), HUBN, '', nt=True, roster=NT_ROSTER)) == want


def test_hub_git_reads_lanes():
    assert not check(B('git -C /c/p/web status && git -C /c/p/web log -3', HUBN), HUBN, nt=True, roster=NT_ROSTER)
    assert check(B('git -C /c/p/web commit -am x', HUBN), HUBN, nt=True, roster=NT_ROSTER)
    assert check(B('git commit -am x', r'C:\p\web'), HUBN, HUBN, nt=True, roster=NT_ROSTER), '허브가 레인으로 cd 해 둔 셸'


# lanes 를 못 읽으면 허브 폴더 밖 쓰기를 모두 막는다. 허브 폴더 안은 원래대로(허브만)
BROKEN = (None, 'C:/Users/Me/hub/lanes.json', 'JSON 이 아님')


@pytest.mark.parametrize('name,want,inp', [
    ('워커가 자기 저장소', True, W(r'C:\p\web\a.py', r'C:\p\web')),
    ('워커가 아무 곳', True, B('touch /c/tmp/x', r'C:\p\web')),
    ('워커가 허브 파일', True, W(HUBN + r'\STATUS.md', r'C:\p\web')),
    ('허브가 허브 파일(고칠 수 있어야 함)', False, W(HUBN + r'\lanes.json', HUBN)),
    ('허브가 밖', True, W(r'C:\p\web\a.py', HUBN)),
    ('/dev/null 은 그대로', False, B('ls > /dev/null', r'C:\p\web')),
    ('쓰기 아닌 Bash', False, B('git status && ls', r'C:\p\web')),
])
def test_broken_lanes_block(name, want, inp):
    why = check(inp, HUBN, nt=True, roster={}, lanes=BROKEN)
    assert bool(why) == want
    if want and 'STATUS' not in str(inp):
        assert 'lanes.json' in why and '허브' in why


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if isinstance(text, str) else json.dumps(text, ensure_ascii=False), encoding='utf-8')


# nipa 허브의 agents.json 모양: lanes 없음, 허브 lane 이 소문자, T 번호 없는 task 이름
NIPA_AGENTS = {'_note': 'x', 'resident': {'hub': {'lane': 'hub', 'cwd': '/h'}, 'WF1': {'lane': 'WF1', 'cwd': '/w', 'note': 'n'}},
               'task': {'task-lanekeeper-update': {'lane': 'lanekeeper', 'task': 'T-20261113-04'}}}


def test_read_lanes(tmp_path):
    hub = tmp_path
    assert read_lanes(str(hub)) == ({}, '', ''), '둘 다 없으면 레인 없음'
    write(hub / 'agents.json', NIPA_AGENTS)
    assert read_lanes(str(hub)) == ({}, str(hub / 'agents.json'), ''), 'nipa 모양은 레인 없음이지 깨짐이 아님'
    write(hub / 'agents.json', dict(NIPA_AGENTS, lanes={'WEB': ['~/web']}))
    assert read_lanes(str(hub)) == ({'WEB': ['~/web']}, str(hub / 'agents.json'), ''), '0.7 까지의 자리'
    write(hub / 'lanes.json', {'_note': 'x', 'lanes': {'API': '~/api'}})
    assert read_lanes(str(hub)) == ({'API': '~/api'}, str(hub / 'lanes.json'), ''), 'lanes.json 이 있으면 그것만'
    write(hub / 'lanes.json', {'lanes': {}})
    assert read_lanes(str(hub))[0] == {}
    for bad in ('{broken', '[1]', '{"_note": "lanes 키 없음"}', '{"lanes": ["WEB"]}', '{"lanes": {"A": 3}}',
                '{"lanes": {"A": ["~/a", 3]}}'):
        write(hub / 'lanes.json', bad)
        lanes, where, why = read_lanes(str(hub))
        assert lanes is None and where == str(hub / 'lanes.json') and why, bad
    (hub / 'lanes.json').unlink()
    write(hub / 'agents.json', '{"resident": ')
    lanes, where, why = read_lanes(str(hub))
    assert lanes is None and where == str(hub / 'agents.json') and why, 'lanes.json 이 없을 때 깨진 agents.json'
    write(hub / 'agents.json', {'lanes': 'WEB'})
    assert read_lanes(str(hub))[0] is None


@pytest.mark.parametrize('cmd,want', [
    ('echo a > x', ['x']),
    ('echo a>>x; echo b &> y', ['x', 'y']),
    ('cmd 2>/dev/null >out', ['/dev/null', 'out']),
    ('cat a | tee -a l1 l2', ['l1', 'l2']),
    ("sed -i 's/a/b/' f1 f2", ['f1', 'f2']),
    ("sed -i.bak -e 's/a/b/' -e 's/c/d/' f1", ['f1']),
    ("sed 's/a/b/' f1", []),
    ('cp -r a b dest/', ['dest/']),
    ('mv -t dest a b', ['dest', 'a', 'b']),                           # mv 는 원본도 지운다
    ('mv a b c/', ['c/', 'a', 'b']),
    ('cp --target-directory=d a', ['d']),
    ('sudo FOO=1 tee x', ['x']),
    ('git commit -m "a > b"', ['.']),                                  # git 쓰기 명령의 대상은 저장소 폴더
    ('rm -rf build dist', ['build', 'dist']),
    ('rm -- -odd', ['-odd']),
    ('rmdir d; unlink l', ['d', 'l']),
    ('touch -r ref.txt new', ['new']),
    ('mkdir -p -m 755 a/b', ['a/b']),
    ('truncate -s 0 f', ['f']),
    ('ln -s target link', ['link']),
    ('ln -s /x/target', ['.']),
    ('chmod 644 f g', ['f', 'g']),
    ('dd if=/dev/zero of=/x/y bs=1', ['/x/y']),
    ('patch -d /x -p1 < p.diff', ['/x']),
    ('patch --directory=/x -p1 -i p.diff', ['/x']),
    ('patch -p1 < p.diff', ['.']),
    ('patch -p 1 a.c p.diff', ['a.c']),
    ('patch -o out.c a.c p.diff', ['out.c']),
    ("find /x -name '*.pyc' -delete", ['/x']),
    ('find -L . a -type f -delete', ['.', 'a']),
    ("find /x -name '*.pyc'", []),
    ('timeout 30 rm -rf x', ['x']),
    ('nice -n 5 touch y', ['y']),
    ('git -C /x commit -m y', ['/x']),
    ('git -C a -C b commit', ['a/b']),
    ('git -C a -C /b commit', ['/b']),
    ('git --no-pager -c core.pager=cat -C /x push', ['/x']),
    ('git --git-dir=/x/.git --work-tree=/x add .', ['/x']),
    ('git --git-dir /x/.git reset --hard', ['/x/.git']),
    ('git clone --depth 1 url /x/y', ['/x/y']),
    ('git init', ['.']),
    ('git -C /x stash', ['/x']),
    ('git -C /x branch -D old', ['/x']),
    ('git -C /x branch new', ['/x']),
    ('git -C /x tag v1', ['/x']),
    ('git -C /x config user.name me', ['/x']),
    ('git -C /x remote add o url', ['/x']),
    ('git -C /x worktree add ../w', ['/x']),
    ('git -C /x status', []),
    ('git -C /x log --oneline -5', []),
    ('git --no-pager -C /x diff HEAD~1', []),
    ('git -C /x fetch origin', []),
    ('git -C /x rev-parse --abbrev-ref HEAD', []),
    ('git -C /x branch -a', []),
    ('git -C /x branch -r --contains HEAD', []),
    ('git -C /x branch --list "feat*"', []),
    ('git -C /x tag -l "v*"', []),
    ('git -C /x stash list', []),
    ('git -C /x worktree list', []),
    ('git -C /x remote -v', []),
    ('git -C /x config --get user.name', []),
    ('git -C /x config user.name', []),
    ('git --version', []),
    ('d=/x; touch $d/y', ['$d/y']),                                    # 변수는 풀지 않는다(문서에 적은 한계)
    ("bash -c 'touch /x/y'", []),                                      # bash -c 안은 보지 않는다(문서에 적은 한계)
    ('echo "unclosed', []),
    ('cat < in > out', ['out']),
    ('cp a b\ncat /home/u/hub/COORDINATION.md', ['b']),              # a new line ends a command
    ("cat > out <<'EOF'\nif a > b: pass\nEOF", ['out']),             # a heredoc body is not a command
    ('python3 - <<EOF\nprint(1 > 0)\nEOF\necho x > after', ['after']),
    ('echo "a\nb" > q', ['q']),                                        # a new line inside quotes stays
    ("cat <<EOF > empty\nEOF\ntee -a log", ['empty', 'log']),         # empty heredoc, redirect on the opening line
])
def test_bash_targets(cmd, want):
    assert [t[0] for t in bash_targets(cmd)] == want


def test_bash_cd_base():
    assert bash_targets('cd sub && cd deeper && echo > f') == [('f', 'sub/deeper', False)]
    assert bash_targets('cd ../api; git commit -am x') == [('.', '../api', False)]
    assert bash_targets('pushd /x && touch f') == [('f', '/x', False)]
    assert bash_targets('(cd /x && ls); touch f') == [('f', '', False)], '괄호 안 cd 는 밖으로 이어지지 않는다'
    assert bash_targets('rm -rf a; mv b c') == [('a', '', True), ('c', '', False), ('b', '', True)]


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
    # bash 는 따옴표 없는 역슬래시를 지우므로 Windows 에서도 명령 안의 경로는 / 로 쓴다
    assert run(tmp_path, B('echo x > %s' % str(api / 'a').replace('\\', '/'), str(web)), web)[0] == 2
    assert run(tmp_path, W(str(hub / 'STATUS.md'), str(web)), web, hub_dir='') == (0, '')
    assert run(tmp_path, M('someone', str(web)), web)[0] == 0
    assert run(tmp_path, M('someone', str(web)), web, 'true')[0] == 2
    (hub / 'agents.json').write_text('{broken', encoding='utf-8')
    code, err = run(tmp_path, W(str(web / 'a.py'), str(web)), web)
    assert code == 2 and 'agents.json' in err, 'lanes.json 이 없을 때 깨진 agents.json 이면 허브 폴더 밖 쓰기를 막는다'
    assert run(tmp_path, W(str(hub / 'STATUS.md'), str(hub)), hub) == (0, ''), '허브는 허브 폴더를 고칠 수 있다'
    (hub / 'lanes.json').write_text(json.dumps({'lanes': {'WEB': [str(web)], 'API': [str(api)]}}), encoding='utf-8')
    assert run(tmp_path, W(str(web / 'a.py'), str(web)), web) == (0, ''), 'lanes.json 이 있으면 명부가 깨져도 레인 보호가 남는다'
    assert run(tmp_path, W(str(api / 'a.py'), str(web)), web)[0] == 2
    (hub / 'lanes.json').write_text('{"lanes": {"WEB": [', encoding='utf-8')
    code, err = run(tmp_path, W(str(web / 'a.py'), str(web)), web)
    assert code == 2 and 'lanes.json' in err
    (hub / 'lanes.json').write_text('{"lanes": {}}', encoding='utf-8')
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
    (tmp_path / 'agents.json').write_text(json.dumps({'lanes': {'A': ['~/a', '~/a/'], 'B': '~/b'}}))
    assert rules(str(tmp_path)) == ['Edit(~/a/**)', 'Edit(~/b/**)'], '0.7 까지의 자리(agents.json)'
    (tmp_path / 'lanes.json').write_text(json.dumps({'lanes': {'C': ['~/c']}}))
    assert rules(str(tmp_path)) == ['Edit(~/c/**)'], 'lanes.json 이 있으면 그것만'
    (tmp_path / 'lanes.json').write_text('{"lanes": {"C": 3}}')
    with pytest.raises(SystemExit):
        rules(str(tmp_path))
