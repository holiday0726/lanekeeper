---
name: update
description: lanekeeper 새 판을 받고 이미 만든 허브 폴더의 규칙 문서와 설정을 새 틀에 맞춘다. 플러그인을 갱신하고, 판을 비교하고, 허브에 들어갈 변경을 미리 보여 주고, 사용자가 확인하면 백업한 뒤 반영한다. 현황판, 명단, 결정 같은 사용자 데이터는 건드리지 않는다.
argument-hint: "[허브 폴더 경로]"
disable-model-invocation: true
---

# lanekeeper 업데이트

사용자가 `/lanekeeper:update` 를 불렀다.
아래 순서대로 진행하고, 각 단계의 명령과 출력을 사용자에게 보여 준다.
한 단계가 실패하면 거기서 멈추고 무엇이 실패했는지 알린다.
사용자가 5단계에서 반영하겠다고 답하기 전에는 허브 폴더와 사용자 설정에 아무것도 쓰지 않는다.

## 1. 지금 판과 설정값 보기

```
claude plugin list --json
claude plugin configure lanekeeper@lanekeeper --json
```

`lanekeeper@` 로 시작하는 항목의 `version` 이 지금 판이다.
플러그인 이름이 `lanekeeper@lanekeeper` 가 아니면 이 항목의 `id` 를 아래 명령에 쓴다.
설정값 `python` 을 아래 `<PY>` 로 쓰고, `hub_dir` 는 3단계의 기본값으로 둔다.
`python` 이 비어 있으면 `/lanekeeper:setup` 을 먼저 부르라고 알리고 멈춘다.
Windows 에서 `<PY>` 는 `python.exe` 절대 경로이니 `"<PY>"` 처럼 따옴표로 감싸고, PowerShell 에서는 앞에 `&` 를 붙인다(`& "<PY>" ...`).

## 2. 플러그인 새 판 받기

```
claude plugin marketplace list --json
```

`lanekeeper` 마켓플레이스의 `source` 가 `directory` 면 받은 폴더를 로컬 마켓플레이스로 붙인 설치다(README "손으로 설치하기").
이때는 그 `path` 에서 `git pull --ff-only` 할지 사용자에게 먼저 묻고, 답한 때에만 돌린다.
이 설치도 플러그인은 `plugins/cache/` 아래 사본으로 돌아가니, `git pull` 만으로는 바뀌지 않는다.

이어서 아래 두 명령을 돌린다.
플러그인 사본만 바꾸고 허브 폴더와 설정은 건드리지 않는다.

```
claude plugin marketplace update lanekeeper
claude plugin update lanekeeper@lanekeeper
```

`claude plugin list --json` 을 다시 돌려 새 `version` 과 `installPath` 를 읽는다.
아래 `<ROOT>` 는 이 새 `installPath` 다.
`${CLAUDE_PLUGIN_ROOT}` 는 이 세션이 처음 읽은 옛 판을 가리키니 쓰지 않는다.
새 판은 `plugins/cache/` 아래 새 판 번호 폴더에 생기고 옛 판 폴더도 남는다.
이 세션의 훅과 이 스킬 본문은 옛 판 그대로이고, 새 판은 6단계에서 다시 열 때 올라온다.
판이 같으면 이미 최신이라고 알리고, 허브가 그 판에 맞는지 보러 다음 단계로 간다.

## 3. 허브 폴더 정하기

인자가 있으면 그 경로를 쓰고, 없으면 1단계의 `hub_dir` 를 쓴다.
둘 다 없으면 사용자에게 묻는다.

## 4. 미리 보기

```
<PY> "<ROOT>/scripts/update_hub.py" "<허브 폴더>"
```

이 명령은 아무 파일도 쓰지 않는다.
출력의 각 줄은 판정으로 시작하고, 바뀔 파일 아래에는 diff 가 붙는다.

| 판정 | 뜻 | 반영하면 |
|---|---|---|
| `same` | 이미 새 틀과 같다 | 그대로 |
| `keep` | 사용자가 고쳤고 틀은 그대로다 | 그대로 |
| `create` | 허브에 없는 틀 파일 | 새로 복사 |
| `replace` | 사용자가 고치지 않았고 틀이 바뀌었다 | 새 틀로 바꿈 |
| `merge` | 둘 다 바뀌었고 겹치지 않는다(`CLAUDE.md`, `COORDINATION.md`) | 사용자 줄을 두고 틀 변경만 넣음 |
| `addkeys` | 설정 JSON 에 기준본 뒤 새 틀에서 생긴 최상위 키가 없다 | 그 키만 더함. 나머지는 손으로 |
| `conflict` | 둘 다 같은 곳을 바꿨다 | 손대지 않음. 손으로 |
| `unknown` | 0.6.0 까지 만든 허브라 기준본이 없고 새 틀과 다르다 | 손대지 않음. 손으로 |
| `data` | 현황판, 명단, 결정, dev 점유 같은 사용자 데이터 | 손대지 않음 |
| `merge`, `kept` | 사용자 설정(`settings.json`)에 더할 키, 이미 있는 키 | 없는 키만 더함 |

`data` 줄에 `새 틀에 있는 키가 없음` 이 붙으면 그 키를 손으로 더할지 사용자에게 알린다(예: 0.6.0 의 `agents.json` `lanes`).
`<ROOT>/CHANGELOG.md` 에서 1단계 판보다 새 절을 요약해 함께 보여 준다.
판이 같았으면 맨 위 절만 보여 준다.
마지막 줄 JSON 의 `changed` 와 `base` 가 0 이고 `manual` 이 비어 있으면 허브가 이미 새 판에 맞으니 6단계로 간다.
`changed` 와 `manual` 은 비었는데 `base` 만 있으면 바뀔 파일은 없고 기준본만 처음 적는 것이다. 그렇게 알리고 5단계로 간다.

## 5. 확인 뒤 반영

반영할지 사용자에게 묻는다.
기본은 반영하지 않는다.
사용자가 반영하겠다고 답한 때에만 돌린다.

```
<PY> "<ROOT>/scripts/update_hub.py" "<허브 폴더>" --apply
```

쓰기 전에 `<허브 폴더>/.lanekeeper/backup-<시각>/` 에 바뀔 파일과 손으로 볼 파일, 기준본을 백업한다.
`backup` 줄의 경로를 사용자에게 알린다.

마지막 줄 JSON 의 `manual` 에 있는 파일은 손으로 본다.
파일마다 무엇을 넣을지 제안하고 사용자가 고른 것만 고친다.

- `conflict`: 미리 보기의 `old/` 에서 `new/` 로 가는 diff 가 새 틀이 바꾼 곳이다. 사용자 파일의 같은 자리에 그 변경을 어떻게 넣을지 보여 준다.
- `unknown`: `hub/` 에서 `new/` 로 가는 diff 에는 사용자가 쓴 줄도 섞여 있다. `<...>` 를 채운 줄, 레인 표, 인터페이스 표, 변경 로그 행, 사용자가 더한 규칙은 사용자 것으로 보고 남긴다. CHANGELOG 의 틀 변경과 맞는 줄만 새 틀 쪽 변경으로 제안한다.
- `addkeys`: 최상위 키는 이미 더했다. 남은 차이(예: `permissions` 의 새 줄)는 보여 주기만 하고, 권한을 늘리는 줄은 하나씩 사용자가 고르게 한다.

허브 폴더의 파일은 허브 세션만 고칠 수 있다(레인 쓰기 보호 훅).
이 세션이 허브 세션이 아니면 고칠 내용을 정리해 보여 주고, 허브 세션에서 고치라고 알린다.

손으로 다 넣었거나 그대로 두기로 한 파일은 기준본을 새 틀로 적는다.

```
<PY> "<ROOT>/scripts/update_hub.py" "<허브 폴더>" --accept <파일 이름 ...>
```

파일 이름은 `manual` 에 나온 그대로 쓴다(예: `CLAUDE.md`, `.claude/settings.json`).
`--apply` 없이 `replace`, `merge`, `create` 판정인 파일을 주면 그 틀 변경이 다음부터 안 보이게 되므로 스크립트가 멈춘다.
`--accept` 하지 않은 파일은 다음 미리 보기에 다시 나온다.

## 6. 되돌리는 법과 마지막 안내

사용자에게 아래를 알린다.

1. 되돌리기: 5단계 `backup` 줄의 폴더로 반영 전 상태로 돌린다.
   반영 뒤 손으로 고친 것도 되돌아가고, 새로 만든 파일은 지우고, 기준본도 돌린다.
   백업 폴더는 남는다.

   ```
   <PY> "<ROOT>/scripts/update_hub.py" "<허브 폴더>" --restore "<백업 폴더>"
   ```

   사용자 설정은 이 명령이 돌리지 않는다.
   5단계에서 `settings.json.bak-<시각>` 이 나왔으면 그 파일을 `settings.json` 으로 되돌린다.
2. 새 판은 Claude Code 를 다시 열거나 `/reload-plugins` 를 입력해야 올라온다.
3. 이미 떠 있는 대시보드는 옛 판 화면을 계속 보여 준다.
   허브 세션을 다시 열 때 세션 시작 메시지가 판이 다르다고 알리면 그 안내대로 서버를 끄고 다시 연다(README "업데이트").
4. `claude plugin configure lanekeeper@lanekeeper --json` 을 다시 돌려 새 판에서 값이 비어 있는 필수 설정이 있으면 그 이름과 이 명령을 알린다.
