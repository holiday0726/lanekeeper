#!/usr/bin/env python3
"""대시보드 열기 훅 시험: python3 tests/test_open_dashboard.py

임시 허브 폴더와 빈 포트로 훅을 실제로 돌린다. 허브 밖에서는 아무것도 띄우지 않고, 허브에서는 서버를 떼어 띄우며
(훅이 바로 끝나야 한다), 떠 있으면 다시 띄우지 않는지 본다. 띄운 서버는 로그의 pid 로만 끈다.
"""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
HOOK = os.path.join(REPO, 'hooks', 'open_dashboard.py')

tmp = tempfile.mkdtemp()
hub, work, data = (os.path.join(tmp, d) for d in ('hub', 'work', 'data'))
shutil.copytree(os.path.join(REPO, 'templates', 'hub'), hub)
os.makedirs(work)
with socket.socket() as s:
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
url = 'http://127.0.0.1:%d' % port
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


HINT = '. 다른 PC 에서 볼 때는 README 의 "다른 PC 에서 보기"'


def hook(project, **extra):
    env = dict(os.environ, CLAUDE_PLUGIN_OPTION_HUB_DIR=hub, CLAUDE_PLUGIN_OPTION_DASHBOARD_PORT=str(port),
               CLAUDE_PLUGIN_OPTION_ORCA='false', CLAUDE_PROJECT_DIR=project, CLAUDE_PLUGIN_DATA=data,
               PYTHONIOENCODING='cp949')
    env.update(extra)
    env = {k: v for k, v in env.items() if v is not None}   # None 은 설정하지 않은 값: 환경변수로 오지 않는다
    payload = json.dumps({'hook_event_name': 'SessionStart', 'source': 'startup', 'cwd': project}).encode()
    t = time.time()
    r = subprocess.run([sys.executable, HOOK], input=payload, env=env, capture_output=True, timeout=30)
    assert r.returncode == 0, r.stderr.decode('utf-8', 'replace')
    return r.stdout.decode('utf-8'), time.time() - t


def get(path):
    with opener.open(url + path, timeout=3) as r:
        return json.load(r)


out, _ = hook(work)
assert out == '', '허브 밖 세션에서는 조용히 끝나야 함: ' + out
try:
    get('/')
    raise AssertionError('허브 밖 세션이 서버를 띄웠음')
except OSError:
    pass

pid = None
try:
    out, took = hook(hub)
    msg = json.loads(out)['systemMessage']
    assert msg == '대시보드 %s 떠 있음' % url + HINT, msg
    assert took < 10, '훅이 서버 출력 파이프를 물고 기다렸음: %.1f 초' % took
    log = open(os.path.join(data, 'dashboard-%d.log' % port), encoding='utf-8').read()
    pid = int(re.search(r'pid (\d+)', log).group(1))
    st = get('/api/status')
    assert os.path.samefile(st['path'], os.path.join(hub, 'STATUS.md')), st.get('path')
    assert st['text'].startswith('# 현황판')
    assert get('/api/dev')['items'] == [] and get('/api/decisions')['error'] == ''

    out, took = hook(os.path.join(hub, 'reports'))   # 허브 하위 폴더에서 다시 열기: 떠 있으니 다시 띄우지 않는다
    assert json.loads(out)['systemMessage'] == '대시보드 %s 떠 있음' % url + HINT and took < 3, (out, took)
    assert len(re.findall(r'pid \d+', open(os.path.join(data, 'dashboard-%d.log' % port), encoding='utf-8').read())) == 1

    # orca 설정을 두지 않으면 기본 켬이지만, orca 명령이 없으면 Orca 이야기는 없다
    bare = os.path.join(tmp, 'bare')
    os.makedirs(bare)
    msg = json.loads(hook(hub, CLAUDE_PLUGIN_OPTION_ORCA=None, PATH=bare)[0])['systemMessage']
    assert msg == '대시보드 %s 떠 있음' % url + HINT, msg

    # orca 명령이 있는데 탭을 못 열면 실패를 알리되 SSH 를 가정하지 않는다
    fake = os.path.join(tmp, 'fake')
    os.makedirs(fake)
    with open(os.path.join(fake, 'orca'), 'w') as f:
        f.write('#!/bin/sh\necho \'{"ok": false}\'\n')
    os.chmod(os.path.join(fake, 'orca'), 0o755)
    with open(os.path.join(fake, 'orca.bat'), 'w') as f:
        f.write('@echo {"ok": false}\n')
    msg = json.loads(hook(hub, CLAUDE_PLUGIN_OPTION_ORCA=None, PATH=fake + os.pathsep + bare)[0])['systemMessage']
    assert 'Orca 탭 열기 실패' in msg and 'SSH' not in msg and msg.endswith(HINT), msg

    # 업데이트 전에 띄운 서버(0.4.1 이하는 판 머리글이 없다)가 포트를 쥐고 있으면 다시 띄우지 않고 끄라고 알린다
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port2 = s.getsockname()[1]
    old = subprocess.Popen([sys.executable, '-m', 'http.server', str(port2), '--bind', '127.0.0.1', '--directory', tmp],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                opener.open('http://127.0.0.1:%d/' % port2, timeout=1).close()
                break
            except OSError:
                time.sleep(0.1)
        msg = json.loads(hook(hub, CLAUDE_PLUGIN_OPTION_DASHBOARD_PORT=str(port2))[0])['systemMessage']
        assert '떠 있음, 다만 플러그인' in msg and '다른 판(0.4.1 이하)' in msg and msg.endswith(HINT), msg
        assert not os.path.exists(os.path.join(data, 'dashboard-%d.log' % port2)), '떠 있는 포트에 서버를 또 띄웠음'
    finally:
        old.terminate()
        old.wait()
finally:
    if pid:
        os.kill(pid, signal.SIGTERM)
    shutil.rmtree(tmp, ignore_errors=True)
print('ok')
