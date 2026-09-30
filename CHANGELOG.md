# 변경 기록

## v2.1 — 2026-10-01

- **세션 간 착수 표시**: 여러 세션이 `/next` 에서 같은 `▶ 지금` 을 집던 문제. `/next claim` 으로 표시하면 다른 세션의 `/next` 에선 `🔒 <세션 이름>` 으로 빠진다. 표시는 `~/.claude/notes-kit/claims/` 에 있고(git 커밋 없음), 주인 세션이 끝나면 저절로 풀린다(hook 없음 — 주인 PID 와 그 시작 시각으로 판정).
- **항목 식별을 번호에서 키/제목 머리로**: `/next done` 이 번호로 지우면, 다른 세션이 그사이 번호를 다시 매겼을 때 엉뚱한 줄이 지워졌다. 이제 `claim.py done` 이 지울 줄 원문을 돌려주고 그 줄을 지운다.
- `/next` 보기는 큐를 직접 읽지 않고 `claim.py show` 로 한다 — 게이트·착수 판정이 스크립트에서 기계적으로 나온다.

올라올 때: `git pull && zsh install.sh update`. 새 세션부터 적용된다.

## v2 — 2026-09-30

모듈식으로 바꿨다. `zsh install.sh <모듈>` 로 필요한 것만 켜고, `git pull && zsh install.sh update` 로 업데이트한다.

- **새 모듈**: `scrum`(아침·저녁 스크럼·주간 보고, Slack 보고), `entities`(사람·프로젝트·결정 페이지 + RESOLVER), `procs`(세션이 띄운 프로세스 회수), `gbrain`(노트 의미 검색 + `/brain`).
- **`/next sync`**: Jira MCP 가 있으면 큐의 티켓 상태를 대조하고 새 티켓을 "미배치"로 보여 준다. 없으면 daily `[이월]` 대조만.
- **`/log`**: `entities` 가 켜져 있으면 결정·사람·프로젝트의 새 사실도 옮긴다. 커밋할 때 `git add -A` 를 쓰지 않는다.
- **설치 스크립트**: 키트 파일은 달라졌으면 백업 후 교체, 노트·CLAUDE.md 는 덮지 않는다. 노트 위치를 기억한다.

**v1(zip)에서 올라올 때**: `zsh install.sh core` 한 번. `~/.claude/commands/log.md`·`next.md` 는 `.bak-<시각>` 으로 백업되고 새 것으로 바뀐다 — 직접 고쳐 둔 게 있으면 백업에서 옮긴다. `~/notes` 안 파일은 그대로다.

## v1 — 2026-09-16

`/log`·`/next` 단순판, `~/notes` 구조, CLAUDE.md 규칙 4줄.
