---
name: setup
description: lanekeeper 를 설치한 뒤 한 번 돌리는 설치 마무리. Python 경로를 찾고, 허브 폴더를 만들어 규칙 틀과 설정 예시를 복사하고, 사용자 설정에 필요한 키를 합치고, 플러그인 설정값 python 과 hub_dir 를 넣고, 사용자가 원하면 addy-skills 를 설치한다.
argument-hint: "[허브 폴더 경로]"
disable-model-invocation: true
---

# lanekeeper 설치 마무리

사용자가 `/lanekeeper:setup` 을 불렀다.
아래 순서대로 진행하고, 각 단계의 명령과 출력을 사용자에게 보여 준다.
한 단계가 실패하면 거기서 멈추고 무엇이 실패했는지 알린다.

이 플러그인 폴더는 `${CLAUDE_PLUGIN_ROOT}` 이다.
이 문자열이 경로로 바뀌지 않고 그대로 보이면 `claude plugin list --json` 에서 `lanekeeper@` 로 시작하는 항목의 `installPath` 를 대신 쓴다.

## 1. Python 찾기

Windows 인지 먼저 본다(Bash 에서 `uname -s` 가 `MINGW`, `MSYS`, `CYGWIN` 으로 시작하거나 PowerShell 을 쓰는 경우).

Windows 에서는 아래를 차례로 돌려 처음 성공한 것을 쓴다.

```
py -3 -c "import sys;print(sys.version_info[:2]>=(3,8), sys.executable)"
python -c "import sys;print(sys.version_info[:2]>=(3,8), sys.executable)"
```

Linux 와 macOS 에서는 이것을 돌린다.

```
python3 -c "import sys;print(sys.version_info[:2]>=(3,8), sys.executable)"
```

첫 낱말이 `True` 가 아니거나 명령이 없으면 멈추고, Python 3.8 이상을 설치한 뒤 다시 부르라고 알린다.
Windows 의 `python` 이 Microsoft Store 설치 안내만 띄우고 끝나는 경우도 없는 것으로 본다.

설정값 `python` 은 이렇게 정한다.

- Windows: 출력의 둘째 칸(`sys.executable`)에서 역슬래시를 `/` 로 바꾼 절대 경로.
  훅은 셸을 거치지 않고 이 값을 그대로 실행한다.
- Linux, macOS: `python3`

아래에서 `<PY>` 는 이 단계에서 성공한 명령(`py -3`, `python`, `python3`)을 뜻한다.

## 2. 허브 폴더 정하기

인자가 있으면 그 경로를 허브 폴더로 쓴다.
없으면 사용자에게 묻는다.
기본값은 홈 폴더 아래 `hub` 이고, Windows 는 `C:/Users/<사용자>/hub` 꼴로 보여 준다.
허브 폴더는 허브 세션을 여는 폴더이고, 나중에 다른 세션은 이 폴더의 파일을 고치지 못한다는 것을 함께 알린다.

## 3. 허브 폴더 만들기와 사용자 설정 합치기

```
<PY> "${CLAUDE_PLUGIN_ROOT}/scripts/setup_hub.py" "<허브 폴더>"
```

스크립트가 하는 일은 이렇다.
다시 돌려도 결과가 같다.

- 허브 폴더를 만들고 `templates/hub/*` 와 `examples/hub.settings.json`(`.claude/settings.json` 으로), `examples/supervisor.settings.json` 을 복사한다.
  있는 파일은 덮지 않는다.
- 사용자 설정 `settings.json` 에 `examples/user.settings.json` 의 키(`crossSessionInbound`) 가 없으면 더한다.
  `model` 같은 다른 설정은 건드리지 않는다.
  있는 값은 그대로 두고, 쓰기 전에 `settings.json.bak-<시각>` 으로 백업한다.
- `agents.json` 의 `resident.hub.cwd` 가 비어 있으면 허브 폴더 경로를 넣는다.

출력의 각 줄은 `created`, `exists`, `merged`, `kept`, `backup`, `filled` 로 시작한다.
`kept` 줄은 기존 값을 그대로 둔 것이니 사용자에게 보여 주고, 예시 값으로 바꾸고 싶으면 직접 고치라고 알린다.
마지막 줄은 JSON 이고, 그 `hub_dir` 를 다음 단계의 설정값으로 쓴다.
사용자 설정이 JSON 으로 읽히지 않는다는 오류로 끝나면 아무것도 바뀌지 않았다.
그 파일을 사용자가 고친 뒤 다시 부르라고 알린다.

## 4. 플러그인 설정값 넣기

먼저 지금 값을 본다.

```
claude plugin configure lanekeeper@lanekeeper --json
```

`inputs` 의 `python` 이나 `hub_dir` 에 이미 다른 값이 있으면 바꿀지 사용자에게 묻는다.
플러그인 이름이 `lanekeeper@lanekeeper` 가 아니면 `claude plugin list --json` 에서 찾은 이름을 쓴다.

값을 넣는다.
JSON 의 값은 한 줄 문자열이어야 하고, 경로에 `"` 가 있으면 `\"` 로 바꾼다.
`hub_dir` 는 3단계 마지막 줄의 값을 `\uXXXX` 이스케이프를 풀지 않고 그대로 넣는다.
그래야 PowerShell 5.1 처럼 파이프를 ASCII 로 보내는 셸에서도 한글 경로가 깨지지 않는다.
`python` 값에 ASCII 밖 글자가 있으면 같은 꼴(`\uXXXX`)로 바꿔 넣는다.

Bash:

```
printf '%s' '{"python":"<1단계 값>","hub_dir":"<3단계 hub_dir>"}' | claude plugin configure lanekeeper@lanekeeper --values-stdin
```

PowerShell:

```
'{"python":"<1단계 값>","hub_dir":"<3단계 hub_dir>"}' | claude plugin configure lanekeeper@lanekeeper --values-stdin
```

`Configuration saved` 가 보이면 된 것이다.
`dashboard_port`, `orca`, `git_message_check` 는 넣지 않는다.
비워 두면 기본값(4990, 켬, 꺼짐)을 쓴다.

## 5. addy-skills 설치(선택)

```
claude plugin list --json
```

`addy-skills@` 로 시작하는 항목이 있으면 건너뛴다.
없으면 설치할지 사용자에게 묻고, 기본은 설치하지 않는다.
허브 규칙 틀의 `CLAUDE.md` "스킬 쓰는 때" 절이 이 플러그인의 스킬을 부르는데, 설치하지 않으면 허브가 그 절을 건너뛴다고 함께 알린다.
사용자가 설치하겠다고 답한 때에만 아래를 돌린다.

```
claude plugin install addy-skills --marketplace holiday0726/Addy-skills
```

## 6. 마지막 안내

사용자에게 아래를 알린다.

1. 설정값은 Claude Code 를 다시 열어야 적용된다.
   지금 세션을 닫는다.
2. 허브 폴더에서 세션을 연다(`cd <허브 폴더>` 뒤 `claude`).
   `대시보드 http://127.0.0.1:4990 떠 있음` 으로 시작하는 줄이 보이면 브라우저로 연다.
   다른 PC 의 브라우저로 볼 때는 아래 "다른 PC 에서 대시보드 보기" 를 알린다.
3. 허브 세션 안에서 `/rename hub` 를 입력한다.
   대시보드는 `agents.json` 의 `hub` 세션을 허브로 본다.
4. 손으로 채울 자리: `.claude/settings.json` 의 `<레인 저장소>` 자리, `supervisor.settings.json` 의 `autoMode.allow`, `CLAUDE.md` 와 `COORDINATION.md` 의 `<...>` 자리.

3단계에서 `kept` 가 나온 키와 4단계에서 바꾸지 않은 값이 있으면 여기서 다시 짚는다.

## 다른 PC 에서 대시보드 보기

사용자가 어떤 클라이언트로 붙어 있는지 짐작하지 않는다.
SSH 라고 단정하지 말고, 아래 세 경우를 그대로 알린다.
README 의 "다른 PC 에서 보기"(영어판 "Viewing from another PC") 절과 같은 내용이다.

- 같은 PC 면 `http://127.0.0.1:<포트>` 를 그대로 연다.
- 포트를 전달해 주는 클라이언트(VS Code 나 Cursor 의 Remote, Orca)면 전달된 같은 번호의 `http://127.0.0.1:<포트>` 를 연다.
  대시보드는 Host 가 `127.0.0.1:<포트>`, `localhost:<포트>` 인 요청만 받으므로 PC 쪽 포트가 다르면 `bad host` 가 난다.
- Paseo 처럼 포트를 전달하지 않으면 PC 에서 `ssh -N -L <포트>:127.0.0.1:<포트> <사용자>@<호스트>` 를 띄워 둔 채 `http://127.0.0.1:<포트>` 를 연다.
  Windows PowerShell 도 같은 명령이다.

`0.0.0.0` 으로 열거나 공개 터널 서비스를 권하지 않는다.
대시보드에는 인증이 없어 주소에 닿는 누구나 세션 대화 기록과 로그를 읽는다.
