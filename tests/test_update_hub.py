#!/usr/bin/env python3
"""허브 갱신 스크립트 시험: python3 -m pytest tests/test_update_hub.py

setup_hub.py 로 임시 폴더에 허브를 만든 뒤, 기준본과 허브 파일을 옛 틀처럼 고쳐 새 판을 받은 상황을 흉내 낸다.
가짜 HOME(HOME, USERPROFILE 둘 다)으로만 돈다. 출력은 cp949 로 받아 Windows 한국어 로캘을 흉내 낸다.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_setup_hub import REPO, load, snapshot, write  # noqa: E402

SETUP = os.path.join(REPO, 'scripts', 'setup_hub.py')
UPDATE = os.path.join(REPO, 'scripts', 'update_hub.py')
DATA = ['STATUS.md', 'agents.json', 'decisions.json', 'dev-occupancy.json']
DROP = '- 이력을 git 으로 남기지 않는다면'  # 옛 CLAUDE.md 틀에 없던 줄로 친다
DROP_C = '- 허브는 일을 맡길 때 작업 세션을 새로 열 수 있다.'  # 옛 COORDINATION.md 틀에 없던 줄로 친다


def run(home, script, *args, ok=True):
    env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_CONFIG_DIR'}
    env.update(HOME=home, USERPROFILE=home, PYTHONIOENCODING='cp949')
    r = subprocess.run([sys.executable, script] + list(args), env=env, capture_output=True, timeout=30)
    out, err = r.stdout.decode('cp949'), r.stderr.decode('cp949', 'replace')
    assert (r.returncode == 0) == ok, (r.returncode, out, err)
    return out


def update(home, hub, *args, ok=True):
    out = run(home, UPDATE, hub, *args, ok=ok)
    return out, (json.loads(out.splitlines()[-1]) if ok else None)


def tag_of(out, hub, rel):
    """출력에서 허브 파일 rel 의 판정."""
    want = os.path.join(hub, *rel.split('/')).replace('\\', '/')
    for line in out.splitlines():
        tag, _, rest = line.partition(' ')
        if rest.strip().split(': ')[0] == want:
            return tag


def text(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def template(rel):
    return text(os.path.join(REPO, 'templates', 'hub', rel))


def without(t, prefix):
    return ''.join(line for line in t.splitlines(True) if not line.startswith(prefix))


def make_hub():
    tmp = tempfile.mkdtemp()
    home, hub = os.path.join(tmp, 'home'), os.path.join(tmp, '내 허브')
    write(os.path.join(home, '.claude', 'settings.json'), '{"crossSessionInbound": "accept"}\n')
    run(home, SETUP, hub)
    return tmp, home, hub


def old(hub, rel, base, mine=None):
    """옛 판에서 만든 허브 흉내: 기준본은 base, 허브 파일은 mine(없으면 base 그대로). base 가 None 이면 기준본을 지운다."""
    b = os.path.join(hub, '.lanekeeper', 'base', *rel.split('/'))
    if base is None:
        os.remove(b)
    else:
        write(b, base)
    write(os.path.join(hub, *rel.split('/')), base if mine is None else mine)


def user_data(hub):
    """사용자가 쓴 데이터 파일. agents.json 은 0.6.0 전처럼 lanes 키가 없다."""
    write(os.path.join(hub, 'STATUS.md'), '# 현황판\n\n- 내 일 진행 중\n')
    write(os.path.join(hub, 'agents.json'), json.dumps({'resident': {'hub': {'lane': 'HUB', 'cwd': hub}}, 'task': {'w1': {}}}))
    write(os.path.join(hub, 'decisions.json'), '{"items": [{"id": "D-1", "status": "open"}]}\n')
    write(os.path.join(hub, 'dev-occupancy.json'), '{"items": [], "updated_at": "2026-11-13T09:00"}\n')
    return {n: open(os.path.join(hub, n), 'rb').read() for n in DATA}


def backups(hub):
    d = os.path.join(hub, '.lanekeeper')
    return sorted(n for n in os.listdir(d) if n.startswith('backup-'))


# setup 이 복사한 파일마다 기준본을 남긴다
def test_setup_records_base():
    _, _, hub = make_hub()
    for n in os.listdir(os.path.join(REPO, 'templates', 'hub')):
        assert text(os.path.join(hub, '.lanekeeper', 'base', n)) == template(n), n
    assert text(os.path.join(hub, '.lanekeeper', 'base', '.claude', 'settings.json')) == text(
        os.path.join(REPO, 'examples', 'hub.settings.json'))


# 1. 미리 보기는 가짜 HOME 까지 아무것도 바꾸지 않는다
def test_preview_changes_nothing():
    tmp, home, hub = make_hub()
    write(os.path.join(home, '.claude', 'settings.json'), '{"theme": "dark"}\n')  # crossSessionInbound 없음
    t = template('CLAUDE.md')
    old(hub, 'CLAUDE.md', without(t, DROP))
    os.remove(os.path.join(hub, 'decisions.json'))
    before = snapshot(tmp)
    out, s = update(home, hub)
    assert snapshot(tmp) == before, '미리 보기가 파일을 바꿈'
    assert tag_of(out, hub, 'CLAUDE.md') == 'replace' and tag_of(out, hub, 'decisions.json') == 'create', out
    assert '+' + DROP in out, '바뀔 줄을 보여 줌'
    assert 'crossSessionInbound' in out and 'merge ' in out, '사용자 설정에 더할 키도 보여 줌'
    assert s['applied'] is False and s['changed'] == 3 and s['backup'] is None, s


# 2. 반영: 바뀐 틀만 들어가고 사용자 데이터와 사용자가 채운 줄은 남는다. 다시 돌리면 바뀐 것이 없다
def test_apply_updates_templates_and_keeps_user_data():
    tmp, home, hub = make_hub()
    data = user_data(hub)
    t, c = template('CLAUDE.md'), template('COORDINATION.md')
    old(hub, 'CLAUDE.md', without(t, DROP))  # 사용자가 안 고침 -> replace
    row = '| 2026-11-13 | WEB | 로그인 API 추가 | HUB | 완료 |\n'
    c_old = without(c, DROP_C)
    c_mine = c_old.replace('| `<레인>` | `<저장소 또는 폴더>` | `<상주 세션 이름, 금지 규칙>` |',
                           '| WEB | ~/projects/web | web 세션 |') + row
    old(hub, 'COORDINATION.md', c_old, c_mine)  # 둘 다 고침, 다른 곳 -> merge
    settings = os.path.join(hub, '.claude', 'settings.json')
    write(settings, text(settings).replace('<레인 저장소 1>', 'web'))  # 사용자가 고침, 틀은 그대로 -> keep
    mine_settings = text(settings)

    out, s = update(home, hub, '--apply')
    assert tag_of(out, hub, 'CLAUDE.md') == 'replace' and tag_of(out, hub, 'COORDINATION.md') == 'merge', out
    assert tag_of(out, hub, '.claude/settings.json') == 'keep', out
    assert text(os.path.join(hub, 'CLAUDE.md')) == t
    got = text(os.path.join(hub, 'COORDINATION.md'))
    assert DROP_C in got and '| WEB | ~/projects/web | web 세션 |' in got and got.endswith(row), got[-300:]
    assert '<<<<<<<' not in got
    assert text(settings) == mine_settings
    for n in DATA:
        assert open(os.path.join(hub, n), 'rb').read() == data[n], n + ' 사용자 데이터가 바뀜'
    assert '새 틀에 있는 키가 없음 lanes' in out, 'agents.json 에 lanes 가 없다고 알림'
    for n in ('CLAUDE.md', 'COORDINATION.md'):
        assert text(os.path.join(hub, '.lanekeeper', 'base', n)) == template(n), n + ' 기준본을 새 틀로'
    assert s['applied'] and s['changed'] == 2 and s['manual'] == [] and s['backup'], s

    before, n_backups = snapshot(tmp), len(backups(hub))
    out, s = update(home, hub, '--apply')
    assert s['changed'] == 0 and s['backup'] is None, out
    assert snapshot(tmp) == before and len(backups(hub)) == n_backups, '두 번째 반영이 파일을 바꿈'


# 3. 같은 곳을 둘 다 고쳤거나 기준본이 없으면 손대지 않고, --accept 뒤에는 keep 이 된다
def test_conflict_and_unknown_left_alone():
    tmp, home, hub = make_hub()
    t = template('CLAUDE.md')
    mine = t.replace('# 허브\n', '# 우리 허브\n', 1)
    old(hub, 'CLAUDE.md', t.replace('# 허브\n', '# 허브(옛)\n', 1), mine)  # 같은 줄을 둘 다 고침
    sup = os.path.join(hub, 'supervisor.settings.json')
    sup_mine = text(sup).replace('Bash(git push origin *)', 'Bash(git push github *)')
    old(hub, 'supervisor.settings.json', None, sup_mine)  # 0.6.0 까지 만든 허브: 기준본 없음

    out, s = update(home, hub)
    assert tag_of(out, hub, 'CLAUDE.md') == 'conflict' and tag_of(out, hub, 'supervisor.settings.json') == 'unknown', out
    assert '-# 허브(옛)' in out and '+# 허브' in out, 'conflict 는 틀이 바뀐 곳(옛 틀 -> 새 틀)을 보여 줌'
    out, s = update(home, hub, '--apply')
    out2, s2 = update(home, hub, '--apply')
    assert text(os.path.join(hub, 'CLAUDE.md')) == mine and text(sup) == sup_mine, '손대지 않음'
    assert s['manual'] == ['CLAUDE.md', 'supervisor.settings.json'], s
    assert s['backup'] and s2['backup'] and s['backup'] != s2['backup'], '손으로 볼 파일이 있으면 매번 따로 백업'
    assert not os.path.exists(os.path.join(hub, '.lanekeeper', 'base', 'supervisor.settings.json')), '검토 전에는 기준본을 적지 않음'

    out, s = update(home, hub, '--accept', 'CLAUDE.md', 'supervisor.settings.json')
    assert s['manual'] == [], s
    out, s = update(home, hub)
    assert tag_of(out, hub, 'CLAUDE.md') == 'keep' and tag_of(out, hub, 'supervisor.settings.json') == 'keep', out
    update(home, hub, '--accept', 'STATUS.md', ok=False)


# 4. 설정 JSON: 새 틀에서 생긴 최상위 키만 더하고, 사용자가 지운 키는 다시 넣지 않고, 깨진 JSON 을 쓰지 않는다
def test_settings_json_adds_only_new_keys():
    tmp, home, hub = make_hub()
    rel = '.claude/settings.json'
    new = json.loads(text(os.path.join(REPO, 'examples', 'hub.settings.json')))
    base = {k: v for k, v in new.items() if k != 'effortLevel'}  # 옛 틀에는 effortLevel 이 없었다
    mine = {k: v for k, v in base.items() if k != 'model'}  # 사용자가 model 을 지웠다
    mine['permissions'] = dict(mine['permissions'], deny=['Edit(~/projects/web/**)'])
    old(hub, rel, json.dumps(base, ensure_ascii=False, indent=2) + '\n', json.dumps(mine, ensure_ascii=False, indent=2) + '\n')
    out, s = update(home, hub, '--apply')
    assert tag_of(out, hub, rel) == 'addkeys' and 'effortLevel' in out, out
    got = load(os.path.join(hub, '.claude', 'settings.json'))
    assert got['effortLevel'] == new['effortLevel'] and 'model' not in got, got
    assert got['permissions']['deny'] == ['Edit(~/projects/web/**)'], '중첩 값은 사용자 것 그대로'
    assert s['manual'] == [rel], '나머지 차이는 손으로 봄'


# 5. 백업에서 되돌리면 백업 폴더 밖의 허브가 반영 전과 바이트까지 같다(새로 만든 파일 지우기와 기준본 포함)
def test_backup_and_restore():
    tmp, home, hub = make_hub()
    user_data(hub)
    t, c = template('CLAUDE.md'), template('COORDINATION.md')
    old(hub, 'CLAUDE.md', without(t, DROP))
    old(hub, 'COORDINATION.md', without(c, DROP_C), without(c, DROP_C) + '| 2026-11-13 | WEB | x | HUB | 완료 |\n')
    old(hub, 'supervisor.settings.json', None, text(os.path.join(hub, 'supervisor.settings.json')) + ' ')
    os.remove(os.path.join(hub, 'dev-occupancy.json'))

    def hub_files():
        return {k: v for k, v in snapshot(hub).items() if not k.startswith(os.path.join('.lanekeeper', 'backup-'))}

    before = hub_files()
    out, s = update(home, hub, '--apply')
    assert s['changed'] == 3 and s['backup'], out
    write(os.path.join(hub, 'supervisor.settings.json'), '{"손으로": "합침"}\n')  # 반영 뒤 손으로 합친 것도 되돌아가야 한다
    assert hub_files() != before
    run(home, UPDATE, hub, '--restore', s['backup'])
    assert hub_files() == before, '되돌린 뒤 다름'
    assert os.path.isdir(s['backup']), '백업은 남김'


# 6. 허브가 아닌 폴더에서는 아무것도 쓰지 않고 멈춘다
def test_not_a_hub():
    tmp = tempfile.mkdtemp()
    home, hub = os.path.join(tmp, 'home'), os.path.join(tmp, 'empty')
    os.makedirs(hub)
    before = snapshot(tmp)
    update(home, hub, '--apply', ok=False)
    assert snapshot(tmp) == before
