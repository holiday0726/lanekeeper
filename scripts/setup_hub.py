#!/usr/bin/env python3
"""허브 폴더 설치: python3 scripts/setup_hub.py <허브 폴더> [--config-dir <Claude 설정 폴더>]

/lanekeeper:setup 스킬이 부른다. 다시 돌려도 결과가 같다.
1. 허브 폴더를 만들고 templates/hub/* 와 설정 예시 둘을 복사한다. 있는 파일은 덮지 않는다.
   복사한 파일은 <허브>/.lanekeeper/base/ 에도 남긴다. update_hub.py 가 다음 판과 비교할 기준본이다.
2. 사용자 설정(<설정 폴더>/settings.json)에 examples/user.settings.json 의 키 중 없는 것만 더한다. 쓰기 전에 백업한다.
3. agents.json 의 resident.hub.cwd 가 비어 있으면 허브 폴더 경로를 넣는다.
설정 폴더는 --config-dir, CLAUDE_CONFIG_DIR, ~/.claude 순으로 정한다.
마지막 줄은 스킬이 읽는 JSON 이다: {"hub_dir": ..., "python": ..., "changed": 바뀐 수}
"""
import argparse
import json
import os
import shutil
import sys
import time

if sys.version_info < (3, 8):
    sys.exit('Python 3.8 이상이 필요합니다: ' + sys.version.split()[0])

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'hooks'))
from hubpath import NT, native  # noqa: E402  훅과 같은 규칙으로 ~ 와 /c/x 꼴을 푼다

BASE = '.lanekeeper/base'  # 허브 안에 남기는 기준본 폴더


def slash(p):
    return p.replace('\\', '/') if NT else p


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def dump(path, data):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def say(tag, msg):
    print('%-8s %s' % (tag, msg))


def sources():
    """허브에 복사하는 (원본 절대 경로, 허브 안 상대 경로 '/' 꼴) 목록."""
    tpl = os.path.join(REPO, 'templates', 'hub')
    pairs = [(os.path.join(tpl, n), n) for n in sorted(os.listdir(tpl))]
    return pairs + [(os.path.join(REPO, 'examples', 'hub.settings.json'), '.claude/settings.json'),
                    (os.path.join(REPO, 'examples', 'supervisor.settings.json'), 'supervisor.settings.json')]


def at(root, rel):
    return os.path.join(root, *rel.split('/'))


def put(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)


def copy_files(hub):
    changed = 0
    for src, rel in sources():
        dst = at(hub, rel)
        if os.path.exists(dst):
            say('exists', slash(dst))
            continue
        put(src, dst)
        put(src, at(hub, BASE + '/' + rel))
        say('created', slash(dst))
        changed += 1
    return changed


def config_dir(arg):
    return os.path.abspath(os.path.expanduser(arg or os.environ.get('CLAUDE_CONFIG_DIR') or os.path.join('~', '.claude')))


def merge_user_settings(config_dir, dry=False):
    """examples/user.settings.json 의 키 중 없는 것만 더한다. dry 면 무엇을 더할지만 찍는다."""
    path = os.path.join(config_dir, 'settings.json')
    want = load(os.path.join(REPO, 'examples', 'user.settings.json'))
    cur = load(path) if os.path.exists(path) else {}  # JSON 이 깨져 있으면 여기서 멈추고 아무것도 쓰지 않는다
    if not isinstance(cur, dict):
        sys.exit('사용자 설정이 JSON 객체가 아닙니다: ' + path)
    add = [k for k in want if k not in cur]
    for k in want:
        if k in cur:
            say('kept', '%s: %s = %s' % (slash(path), k, json.dumps(cur[k], ensure_ascii=False)))
    if dry:
        for k in add:
            say('merge', '%s: %s = %s' % (slash(path), k, json.dumps(want[k], ensure_ascii=False)))
        return len(add)
    if not add:
        return 0
    if os.path.exists(path):
        bak = '%s.bak-%s' % (path, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copyfile(path, bak)
        say('backup', slash(bak))
    else:
        os.makedirs(config_dir, exist_ok=True)
    cur.update((k, want[k]) for k in add)
    dump(path, cur)
    for k in add:
        say('merged', '%s: %s = %s' % (slash(path), k, json.dumps(want[k], ensure_ascii=False)))
    return 1


def fill_roster(hub):
    path = os.path.join(hub, 'agents.json')
    data = load(path)
    entry = data.setdefault('resident', {}).setdefault('hub', {'lane': 'HUB'})
    if entry.get('cwd'):
        say('kept', '%s: resident.hub.cwd = %s' % (slash(path), entry['cwd']))
        return 0
    entry['cwd'] = slash(hub)
    dump(path, data)
    say('filled', '%s: resident.hub.cwd = %s' % (slash(path), entry['cwd']))
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description='lanekeeper 허브 폴더 설치')
    ap.add_argument('hub', help='허브 폴더 경로')
    ap.add_argument('--config-dir', help='Claude 설정 폴더. 기본은 CLAUDE_CONFIG_DIR 또는 ~/.claude')
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(errors='backslashreplace')  # Windows cp949 콘솔에서 못 찍는 글자로 죽지 않게
    hub = os.path.abspath(native(a.hub))
    if os.path.exists(hub) and not os.path.isdir(hub):
        sys.exit('허브 경로가 폴더가 아닙니다: ' + hub)
    changed = merge_user_settings(config_dir(a.config_dir))  # 사용자 설정이 깨져 있으면 허브 폴더도 건드리기 전에 멈춘다
    changed += copy_files(hub) + fill_roster(hub)
    print(json.dumps({'hub_dir': slash(hub), 'python': slash(sys.executable), 'changed': changed}))


if __name__ == '__main__':
    main()
