"""허브 폴더와 레인 경로 판정, 작업 세션 이름 규칙. 두 훅(lane_guard, open_dashboard), scripts, 대시보드가 같이 쓴다.

Windows 경로는 문자열로만 다뤄 Linux 에서도 시험할 수 있다: 역슬래시와 / 를 같게, 대소문자를 무시,
Git Bash 꼴 /c/Users 와 Cygwin 꼴 /cygdrive/c/Users 를 c:/Users 로 본다.
"""
import os
import posixpath
import re
from datetime import datetime

NT = os.name == 'nt'
DRIVE = re.compile(r'/(?:cygdrive/)?([A-Za-z])(?=/|$)')
TASK_NAME = re.compile(r'task-T(\d{8})-(\d{2,3})-([a-z0-9]+(?:-[a-z0-9]+)*)')


def task_name(name):
    """작업 세션 이름 task-T<YYYYMMDD>-<NN>-<주제> 를 {'task': 'T-YYYYMMDD-NN', 'topic': 주제} 로. 아니면(없는 날짜 포함) None.

    lk spawn 이 이 꼴만 띄우고, 대시보드는 이름에서 T 번호를 읽는다. 주제는 영어 소문자, 숫자, 하이픈 하나씩이다.
    """
    m = TASK_NAME.fullmatch(str(name or ''))
    if not m:
        return None
    try:
        datetime.strptime(m.group(1), '%Y%m%d')
    except ValueError:
        return None
    return {'task': 'T-%s-%s' % (m.group(1), m.group(2)), 'topic': m.group(3)}


def native(p, nt=NT):
    """설정값을 이 OS 가 여는 경로로: ~ 를 풀고, Windows 에서는 /c/x 를 c:/x 로."""
    p = os.path.expanduser((p or '').strip())
    if nt:
        p = p.replace('\\', '/')
        m = DRIVE.match(p)
        if m:
            p = m.group(1) + ':' + p[m.end():]
    return p


def norm(p, nt=NT, base=''):
    """비교용 경로. 상대 경로는 base 기준. Linux 는 심볼릭 링크까지 푼다(realpath)."""
    p = native(p, nt)
    if nt:
        if base and not re.match(r'[A-Za-z]:/|/', p):
            p = native(base, nt).rstrip('/') + '/' + p
        return posixpath.normpath(p).casefold()
    return os.path.realpath(os.path.join(native(base, nt), p) if base else p)


def inside(path, root):
    """norm() 을 거친 두 경로에서 path 가 root 이거나 그 아래인지. C:/hub2 는 C:/hub 아래가 아니다."""
    return path == root or path.startswith(root.rstrip('/') + '/')
