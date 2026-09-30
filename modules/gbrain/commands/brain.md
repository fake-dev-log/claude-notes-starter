---
description: "노트 검색 인덱스(gbrain) 유지보수. 사용: /brain sync | /brain check"
allowed-tools: Bash, Read, Grep, Glob
---
# /brain $ARGUMENTS

`~/notes` 를 gbrain 이 검색할 수 있게 유지한다. 평소엔 `~/notes` 커밋마다 post-commit 훅이 백그라운드로 동기화하므로 손댈 일이 없다 — 이 커맨드는 확인과 복구용이다.

## `/brain sync` — 지금 동기화
1. `~/notes` 에 커밋 안 된 변경이 있으면 먼저 알린다 — gbrain 은 **커밋된 것만** 읽는다. 커밋할지는 사용자가 정한다.
2. `zsh ~/.claude/notes-kit/notes-sync.sh` 를 앞에서 돌리고, `~/.claude/notes-kit/logs/sync-YYYY-MM.log` 의 마지막 실행 블록을 보여 준다.
3. `gbrain sources status` 로 notes 소스의 LAG·EMBED·FAILS 를 한 줄로 요약한다. `ollama 꺼짐` 이 찍혔으면 Ollama 를 켜고 다시 치라고 알린다.

## `/brain check` — 점검
1. 끊긴 링크: `python3 ~/.claude/notes-kit/check_links.py ~/notes`. 있으면 파일별로 보여 주고, 고칠지(대상 페이지를 만들지·링크를 고칠지) 묻는다 — 자동으로 고치지 않는다.
2. 인덱스 상태: `gbrain sources status`. EMBED 가 100% 가 아니면 `gbrain embed --stale`, FAILS 가 있으면 `gbrain sync --source notes` 출력의 오류 줄을 보여 준다.
3. 검색 표본: 최근 daily 제목 하나로 `gbrain search "<제목 일부>"` 를 돌려 그 daily 가 상위에 나오는지 본다. 안 나오면 동기화가 멈춘 것이다.

## 하지 않는 것
- `gbrain sources remove`·`purge` 같은 삭제 명령은 치지 않는다 — 필요하면 사용자에게 명령을 알려 준다.
- 노트 내용을 고치지 않는다. 이 커맨드는 인덱스만 다룬다.
