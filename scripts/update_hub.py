#!/usr/bin/env python3
"""허브 폴더 갱신: python3 scripts/update_hub.py <허브 폴더> [--apply] [--accept 이름 ...] [--restore 백업 폴더] [--config-dir 폴더]

/lanekeeper:update 스킬이 부른다. 인자가 허브 폴더뿐이면 미리 보기이고 아무 파일도 쓰지 않는다.
허브 파일, 기준본(<허브>/.lanekeeper/base/, setup 이나 지난 update 가 남긴 틀 사본), 이 판의 틀을 셋이 비교한다.

규칙 문서와 설정(MANAGED) 판정:
  create    허브에 없다. 새 틀을 복사한다.
  same      이미 새 틀과 같다.
  keep      사용자가 고쳤고 틀은 그대로다. 손대지 않는다.
  replace   사용자가 고치지 않았고 틀이 바뀌었다. 새 틀로 바꾼다.
  merge     둘 다 바뀌었고 git merge-file 이 충돌 없이 합쳤다(md 만). 합친 결과를 쓴다.
  addkeys   설정 JSON 에 기준본 뒤 새 틀에서 생긴 최상위 키가 없다. 그 키만 더하고 나머지 차이는 손으로 본다.
  conflict  둘 다 바뀌었고 자동으로 못 합친다. 손대지 않고 틀이 바뀐 곳을 보여 준다.
  unknown   기준본이 없고(0.6.0 까지 만든 허브) 새 틀과 다르다. 손대지 않고 허브와 새 틀의 차이를 보여 준다.
사용자 데이터(그 밖의 틀: STATUS.md, agents.json, decisions.json, dev-occupancy.json): 없을 때만 만든다.
  data      손대지 않는다. JSON 이면 새 틀에 있고 허브에 없는 최상위 키를 note 로 알린다.
사용자 설정(<설정 폴더>/settings.json): setup_hub.py 의 merge_user_settings 로 없는 키만 더한다.

--apply    위 판정대로 쓴다. 쓰기 전에 <허브>/.lanekeeper/backup-<시각>/ 에 바뀔 파일과 손으로 볼 파일, 기준본을 백업한다.
--accept   손으로 합쳤거나 그대로 두기로 한 파일의 기준본을 새 틀로 적는다. 다음부터 그 뒤에 바뀐 것만 보인다.
--restore  백업 폴더대로 허브를 되돌린다(새로 만든 파일 지우기, 기준본 포함). 사용자 설정은 settings.json.bak-<시각> 으로 손으로 되돌린다.
마지막 줄은 스킬이 읽는 JSON 이다: {"hub_dir", "version", "applied", "changed", "base": 적을 기준본 수, "manual": [...], "backup"}
"""
import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from setup_hub import BASE, REPO, at, config_dir, load, merge_user_settings, native, put, say, slash, sources  # noqa: E402

MANAGED = {'CLAUDE.md', 'COORDINATION.md', '.claude/settings.json', 'supervisor.settings.json'}
STATE = '.lanekeeper'
MANUAL = ('addkeys', 'conflict', 'unknown')


def read(path):
    """비교용 글. 없으면 None. CRLF 와 BOM 은 떼고 읽는다."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8-sig') as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def obj(text):
    try:
        v = json.loads(text or '')
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def merge3(hub, base, new):
    """git merge-file 로 세 갈래 병합. 충돌이 있거나 git 이 없으면 None."""
    git = shutil.which('git')
    if not git:
        return None
    with tempfile.TemporaryDirectory() as d:
        paths = [os.path.join(d, n) for n in ('hub', 'base', 'new')]
        for p, t in zip(paths, (hub, base, new)):
            write(p, t)
        r = subprocess.run([git, 'merge-file', '-p'] + paths, capture_output=True)
    return r.stdout.decode('utf-8') if r.returncode == 0 else None


def plan(rel, hub, base, new):
    """(판정, 허브에 쓸 글 또는 None, 보여 줄 (앞, 뒤, 앞 이름, 뒤 이름) 또는 None, 덧붙일 말)"""
    if hub is None:
        return 'create', new, None, ''
    if rel not in MANAGED:
        want, cur = obj(new), obj(hub)
        miss = [k for k in want or {} if cur is not None and k not in cur and not k.startswith('_')]
        return 'data', None, None, (': 새 틀에 있는 키가 없음 ' + ', '.join(miss)) if miss else ''
    if hub == new:
        return 'same', None, None, ''
    if base is not None and new == base:
        return 'keep', None, None, ''
    if base is not None and hub == base:
        return 'replace', new, (hub, new, 'hub', 'new'), ''
    manual = 'unknown' if base is None else 'conflict'
    shown = (hub, new, 'hub', 'new') if base is None else (base, new, 'old', 'new')
    if rel.endswith('.json'):
        cur, want, old = obj(hub), obj(new), obj(base)
        add = [k for k in want or {} if cur is not None and old is not None and k not in cur and k not in old]
        if add:  # setup 의 사용자 설정 합치기와 같은 규칙. 기준본에 있던 키는 사용자가 지운 것이니 다시 넣지 않는다
            cur.update((k, want[k]) for k in add)
            return 'addkeys', json.dumps(cur, ensure_ascii=False, indent=2) + '\n', shown, ': ' + ', '.join(add)
        return manual, None, shown, ''
    if base is not None:
        merged = merge3(hub, base, new)
        if merged is not None:
            return 'merge', merged, (hub, merged, 'hub', 'merged'), ''
    return manual, None, shown, ''


def show(rel, a, b, la, lb):
    for line in difflib.unified_diff(a.splitlines(True), b.splitlines(True), la + '/' + rel, lb + '/' + rel):
        sys.stdout.write(line if line.endswith('\n') else line + '\n')


def backup(hub, files, created):
    root = at(hub, STATE + '/backup-' + time.strftime('%Y%m%d-%H%M%S'))
    d, n = root, 1
    while os.path.exists(d):  # 같은 초에 두 번 돌려도 앞 백업을 덮지 않는다
        n += 1
        d = '%s-%d' % (root, n)
    for rel in files:
        put(at(hub, rel), at(d, 'files/' + rel))
    if os.path.isdir(at(hub, BASE)):
        shutil.copytree(at(hub, BASE), at(d, 'base'))
    with open(os.path.join(d, 'manifest.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'files': files, 'created': created}, f, ensure_ascii=False, indent=2)
    say('backup', slash(d))
    return d


def restore(hub, d):
    man = load(os.path.join(d, 'manifest.json'))  # 백업 폴더가 아니면 여기서 멈춘다
    for rel in man['created']:
        if os.path.exists(at(hub, rel)):
            os.remove(at(hub, rel))
            say('removed', slash(at(hub, rel)))
    for rel in man['files']:
        put(at(d, 'files/' + rel), at(hub, rel))
        say('restored', slash(at(hub, rel)))
    shutil.rmtree(at(hub, BASE), ignore_errors=True)
    if os.path.isdir(at(d, 'base')):
        shutil.copytree(at(d, 'base'), at(hub, BASE))
    say('restored', slash(at(hub, BASE)))


def main(argv=None):
    ap = argparse.ArgumentParser(description='lanekeeper 허브 폴더를 새 틀에 맞춘다. 기본은 미리 보기')
    ap.add_argument('hub', help='허브 폴더 경로')
    ap.add_argument('--apply', action='store_true', help='판정대로 쓴다(쓰기 전에 백업)')
    ap.add_argument('--accept', nargs='+', default=[], metavar='이름', help='기준본을 새 틀로 적을 파일(예: CLAUDE.md)')
    ap.add_argument('--restore', metavar='백업 폴더', help='이 백업대로 되돌린다')
    ap.add_argument('--config-dir', help='Claude 설정 폴더. 기본은 CLAUDE_CONFIG_DIR 또는 ~/.claude')
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(errors='backslashreplace')  # Windows cp949 콘솔에서 못 찍는 글자로 죽지 않게
    hub = os.path.abspath(native(a.hub))
    if not os.path.isfile(os.path.join(hub, 'agents.json')):
        sys.exit('허브 폴더가 아닙니다(agents.json 없음): %s\n새로 만들 때는 /lanekeeper:setup 을 씁니다.' % hub)
    if a.restore:
        return restore(hub, os.path.abspath(native(a.restore)))
    bad = [n for n in a.accept if n not in MANAGED]
    if bad:
        sys.exit('--accept 는 %s 중에서 고릅니다: %s' % (', '.join(sorted(MANAGED)), ', '.join(bad)))

    changed = merge_user_settings(config_dir(a.config_dir), dry=not a.apply)  # 설정이 깨져 있으면 허브를 건드리기 전에 멈춘다
    todo, manual, bases, lost = [], [], [], []
    for src, rel in sources():
        new = read(src)
        hub_text, base = read(at(hub, rel)), read(at(hub, BASE + '/' + rel))
        tag, text, shown, extra = plan(rel, hub_text, base, new)
        say(tag, slash(at(hub, rel)) + extra)
        if shown and not a.apply:
            show(rel, *shown)
        if text is not None:
            todo.append((rel, text, hub_text is None))
            if rel in a.accept and tag not in MANUAL and not a.apply:
                lost.append(rel)
        if tag in MANUAL and rel not in a.accept:
            manual.append(rel)
        elif rel in MANAGED and tag not in ('keep', 'data') and base != new:
            bases.append((rel, new))  # 기준본은 사용자가 새 틀까지 본 파일만 올린다
    changed += len(todo)
    if lost:  # 기준본만 올리면 그 틀 변경이 다음부터 안 보인다
        sys.exit('--accept 는 손으로 볼 파일(addkeys, conflict, unknown)에 씁니다. 이 파일은 --apply 로 반영합니다: ' + ', '.join(lost))

    bdir = None
    if a.apply and (todo or manual):
        bdir = backup(hub, [r for r, _, new_file in todo if not new_file] + manual,
                       [r for r, _, new_file in todo if new_file])
    if a.apply:
        for rel, text, _ in todo:
            write(at(hub, rel), text)
    if a.apply or a.accept:
        for rel, new in bases:
            if a.apply or rel in a.accept:
                write(at(hub, BASE + '/' + rel), new)
                say('base', rel)
    for rel in manual:
        say('manual', '%s: 손으로 합친 뒤(또는 그대로 두기로 하면) --accept %s' % (slash(at(hub, rel)), rel))
    print(json.dumps({'hub_dir': slash(hub), 'version': load(os.path.join(REPO, '.claude-plugin', 'plugin.json'))['version'],
                      'applied': a.apply, 'changed': changed, 'base': len(bases), 'manual': manual,
                      'backup': bdir and slash(bdir)}))


if __name__ == '__main__':
    main()
