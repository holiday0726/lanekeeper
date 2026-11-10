#!/usr/bin/env python3
"""레인 정의로 허브 세션의 permissions.deny 줄을 만든다: python3 scripts/lane_deny.py <허브 폴더>

<허브 폴더>/agents.json 의 "lanes" 경로마다 "Edit(<경로>/**)" 를 찍는다. 파일은 고치지 않는다.
출력을 허브 폴더 .claude/settings.json 의 permissions.deny 에 붙여 넣는다.
권한 규칙에서 / 로 시작하는 경로는 설정 파일 기준이라, 절대 경로는 //경로 로, Windows 드라이브는 //c/Users/... 꼴로 쓴다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'hooks'))
from hubpath import native  # noqa: E402
from lane_guard import read_roster  # noqa: E402


def rule(path, hub):
    p = path.strip().replace('\\', '/').rstrip('/')
    if p.startswith('~'):
        return 'Edit(%s/**)' % p
    p = native(p).replace('\\', '/')
    m = re.match(r'([A-Za-z]):/(.*)', p)
    if m:
        return 'Edit(//%s/%s/**)' % (m.group(1).lower(), m.group(2))
    if not p.startswith('/'):
        p = os.path.normpath(os.path.join(native(hub), p)).replace('\\', '/')
        m = re.match(r'([A-Za-z]):/(.*)', p)
        if m:
            return 'Edit(//%s/%s/**)' % (m.group(1).lower(), m.group(2))
    return 'Edit(//%s/**)' % p.lstrip('/')


def rules(hub):
    lanes = read_roster(hub).get('lanes')
    out = []
    for paths in lanes.values() if isinstance(lanes, dict) else ():
        for p in [paths] if isinstance(paths, str) else paths if isinstance(paths, list) else []:
            if isinstance(p, str) and p.strip() and rule(p, hub) not in out:
                out.append(rule(p, hub))
    return out


def main(argv):
    if len(argv) != 1:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding='utf-8')
    out = rules(argv[0])
    if not out:
        sys.exit('agents.json 의 "lanes" 가 비어 있습니다: ' + os.path.join(native(argv[0]), 'agents.json'))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main(sys.argv[1:])
