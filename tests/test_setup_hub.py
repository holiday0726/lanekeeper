#!/usr/bin/env python3
"""허브 설치 스크립트 시험: python3 -m pytest tests/test_setup_hub.py

임시 폴더와 가짜 HOME(HOME, USERPROFILE 둘 다)으로만 돈다. 진짜 ~/.claude 는 읽지도 쓰지도 않는다.
출력은 cp949 로 받아 Windows 한국어 로캘을 흉내 낸다.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SCRIPT = os.path.join(REPO, 'scripts', 'setup_hub.py')
TEMPLATES = sorted(os.listdir(os.path.join(REPO, 'templates', 'hub')))


def run(home, hub, *extra, ok=True):
    env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_CONFIG_DIR'}
    env.update(HOME=home, USERPROFILE=home, PYTHONIOENCODING='cp949')
    r = subprocess.run([sys.executable, SCRIPT, hub] + list(extra), env=env, capture_output=True, timeout=30)
    out, err = r.stdout.decode('cp949'), r.stderr.decode('cp949', 'replace')
    assert (r.returncode == 0) == ok, (r.returncode, out, err)
    return out, err


def snapshot(root):
    """root 아래 모든 파일의 경로와 내용."""
    files = {}
    for d, _, names in os.walk(root):
        for n in names:
            p = os.path.join(d, n)
            with open(p, 'rb') as f:
                files[os.path.relpath(p, root)] = f.read()
    return files


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)


# 1. 처음 설치: 사용자 설정 파일이 없는 가짜 HOME
def test_first_install_and_rerun():
    tmp = tempfile.mkdtemp()
    home, hub = os.path.join(tmp, 'home'), os.path.join(tmp, '내 허브')
    os.makedirs(home)
    out, _ = run(home, hub)
    summary = json.loads(out.splitlines()[-1])
    assert summary['changed'] > 0, summary
    assert summary['hub_dir'] == (hub.replace('\\', '/') if os.name == 'nt' else hub), summary
    for n in TEMPLATES:
        assert os.path.isfile(os.path.join(hub, n)), n
    assert load(os.path.join(hub, '.claude', 'settings.json')) == load(os.path.join(REPO, 'examples', 'hub.settings.json'))
    assert os.path.isfile(os.path.join(hub, 'supervisor.settings.json'))
    assert not os.path.exists(os.path.join(hub, 'user.settings.json'))
    user = os.path.join(home, '.claude', 'settings.json')
    assert load(user) == load(os.path.join(REPO, 'examples', 'user.settings.json'))
    assert glob.glob(user + '.bak-*') == [], '없던 파일은 백업할 것이 없음'
    assert load(os.path.join(hub, 'agents.json'))['resident']['hub'] == {'lane': 'HUB', 'cwd': summary['hub_dir']}

    # 2. 다시 돌리면 바뀐 것이 없다
    before = snapshot(tmp)
    out, _ = run(home, hub)
    assert json.loads(out.splitlines()[-1])['changed'] == 0, out
    assert 'created' not in out and 'merged' not in out and 'backup' not in out, out
    assert snapshot(tmp) == before, '두 번째 실행이 파일을 바꿈'


# 3. 기존 사용자 설정: 있는 값은 두고 없는 키만 더하고, 쓰기 전에 백업
def test_merge_user_settings():
    tmp = tempfile.mkdtemp()
    home, hub = os.path.join(tmp, 'home'), os.path.join(tmp, 'hub')
    orig = '{\n  "model": "sonnet",\n  "theme": "dark",\n  "env": {"A": "1"}\n}\n'
    user = os.path.join(home, '.claude', 'settings.json')
    write(user, orig)
    out, _ = run(home, hub)
    got = load(user)
    assert got['model'] == 'sonnet' and got['theme'] == 'dark' and got['env'] == {'A': '1'}, got
    assert got['crossSessionInbound'] == 'accept', got
    baks = glob.glob(user + '.bak-*')
    assert len(baks) == 1 and open(baks[0], encoding='utf-8').read() == orig, baks
    assert list(got) == ['model', 'theme', 'env', 'crossSessionInbound'], '키 순서 유지'
    before = snapshot(tmp)
    run(home, hub)
    assert snapshot(tmp) == before, '합친 뒤 다시 돌리면 백업도 새로 만들지 않음'


# 3b. model 이 없는 사용자 설정에 model 을 넣지 않는다 (기본 모델을 바꾸지 않음)
def test_no_model_added():
    tmp = tempfile.mkdtemp()
    home, hub = os.path.join(tmp, 'home'), os.path.join(tmp, 'hub')
    user = os.path.join(home, '.claude', 'settings.json')
    write(user, '{"theme": "dark"}\n')
    run(home, hub)
    assert load(user) == {'theme': 'dark', 'crossSessionInbound': 'accept'}, load(user)
    shutil.rmtree(tmp, ignore_errors=True)
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, 'home'))
    run(os.path.join(tmp, 'home'), os.path.join(tmp, 'hub'))
    assert 'model' not in load(os.path.join(tmp, 'home', '.claude', 'settings.json')), '새 설정 파일에도 model 없음'


# 4. 허브 폴더에 이미 있는 파일과 채워진 agents.json 은 덮지 않는다
def test_keeps_existing_files():
    tmp = tempfile.mkdtemp()
    home, hub = os.path.join(tmp, 'home'), os.path.join(tmp, 'hub')
    write(os.path.join(hub, 'STATUS.md'), '내 현황\n')
    roster = {'resident': {'hub': {'lane': 'HUB', 'cwd': '/elsewhere'}}, 'task': {'w1': {}}}
    write(os.path.join(hub, 'agents.json'), json.dumps(roster))
    write(os.path.join(hub, '.claude', 'settings.json'), '{"model": "x"}')
    run(home, hub)
    assert open(os.path.join(hub, 'STATUS.md'), encoding='utf-8').read() == '내 현황\n'
    assert load(os.path.join(hub, 'agents.json')) == roster
    assert load(os.path.join(hub, '.claude', 'settings.json')) == {'model': 'x'}
    assert os.path.isfile(os.path.join(hub, 'COORDINATION.md')), '없는 파일은 채움'


# 5. 사용자 설정이 JSON 으로 안 읽히면 아무것도 쓰지 않고 멈춘다
def test_broken_user_settings_stops():
    tmp = tempfile.mkdtemp()
    home, hub = os.path.join(tmp, 'home'), os.path.join(tmp, 'hub')
    user = os.path.join(home, '.claude', 'settings.json')
    write(user, '{ "model": "x", // 주석\n}')
    before = snapshot(tmp)
    run(home, hub, ok=False)
    assert snapshot(tmp) == before and not os.path.exists(hub)


# 6. 설정 폴더는 --config-dir, CLAUDE_CONFIG_DIR 순으로 고른다
def test_config_dir_choice():
    tmp = tempfile.mkdtemp()
    home, hub, cfg = (os.path.join(tmp, d) for d in ('home', 'hub', 'cfg'))
    os.makedirs(home)
    run(home, hub, '--config-dir', cfg)
    assert os.path.isfile(os.path.join(cfg, 'settings.json')) and not os.path.exists(os.path.join(home, '.claude'))
    env_cfg = os.path.join(tmp, 'envcfg')
    os.environ['CLAUDE_CONFIG_DIR'] = env_cfg
    try:
        r = subprocess.run([sys.executable, SCRIPT, hub], env=dict(os.environ, HOME=home, USERPROFILE=home),
                           capture_output=True, timeout=30)
    finally:
        del os.environ['CLAUDE_CONFIG_DIR']
    assert r.returncode == 0 and os.path.isfile(os.path.join(env_cfg, 'settings.json')), r.stderr
    assert not os.path.exists(os.path.join(home, '.claude'))


# 7. 허브 경로가 파일이면 멈춘다
def test_hub_path_is_file():
    tmp = tempfile.mkdtemp()
    write(os.path.join(tmp, 'hub'), 'x')
    _, err = run(os.path.join(tmp, 'home'), os.path.join(tmp, 'hub'), ok=False)
    assert not os.path.exists(os.path.join(tmp, 'home')), '멈출 때 사용자 설정도 쓰지 않음'


# 8. Windows 에서 /c/Users/... 꼴 허브 경로는 C:/Users/... 로 푼다 (Windows 에서만)
def test_windows_bash_path():
    if os.name == 'nt':
        tmp = tempfile.mkdtemp()
        hub = os.path.join(tmp, 'hub')
        bash_form = '/' + hub[0].lower() + hub[2:].replace('\\', '/')
        out, _ = run(os.path.join(tmp, 'home'), bash_form)
        assert json.loads(out.splitlines()[-1])['hub_dir'].casefold() == hub.replace('\\', '/').casefold(), out
        assert os.path.isfile(os.path.join(hub, 'agents.json'))
