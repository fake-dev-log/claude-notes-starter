# claude-notes-starter

Claude Code 를 터미널에서 쓰는 사람을 위한 **기록 루프** 키트. 사람이 손으로 쓰는 글자는 0 이다 — Claude 가 쓰고, 다음 세션의 Claude 가 읽는다.

```
작업 한 덩어리 끝 ──▶ /log ──▶ 세션 끊기 ──▶ 새 세션 ──▶ /next ──▶ 작업 …
                      │                                    ▲
                      └── ~/notes/daily/YYYY-MM-DD.md ──────┘
                          ~/notes/queue.md
```

기록이 멈추는 이유는 대개 도구가 아니라 **쓰기 귀찮고, 읽는 사람이 없어서**다. 여기서는 Claude 가 쓰고 Claude 가 읽는다. Obsidian 은 쓰는 도구가 아니라 Claude 가 쓴 걸 **사람이 훑어보는 뷰어**다.

## 모듈

`core` 만으로 시작한다. 나머지는 **막히는 지점이 생겼을 때** 하나씩 켠다 — 처음부터 다 켜면 남의 규칙을 한꺼번에 떠안게 된다.

| 모듈 | 무엇 | 이럴 때 켠다 | 필요한 것 |
|---|---|---|---|
| `core` | `/log` · `/next` · 기록 규칙 4줄 | 처음부터 | Claude Code |
| `scrum` | `/scrum am\|pm\|weekly` — daily 로 아침 우선순위·저녁 정리·주간 보고 초안. `--post` 면 Slack 에 보고 | 스크럼·주간 보고를 매일 손으로 쓰고 있을 때 | (선택) Slack·Google Calendar·Jira MCP |
| `entities` | 사람·프로젝트·결정·회의 페이지 + `RESOLVER.md`(어디에 쓸지 규칙) | "그 사람이 뭐라고 했더라", "그때 왜 그렇게 정했더라"가 daily 뒤지기로 안 풀릴 때 | — |
| `procs` | 세션이 띄운 dev 서버·watcher 를 세션 종료 때 회수, 새 세션에 잔여 프로세스 보고 | 세션을 여러 개 돌리고, 끝난 세션의 서버가 남아 있던 적이 있을 때 | macOS, `/usr/bin/python3` |
| `gbrain` | 노트 의미 검색(로컬 PGLite + Ollama 임베딩) + MCP 연결 + 커밋마다 자동 동기화 + `/brain sync\|check` | 노트가 수백 장이 되어 grep 으로 안 찾아질 때 | [gbrain](https://github.com/garrytan/gbrain)(bun), Ollama `bge-m3`, `~/notes` 가 git repo |

Jira 대조(`/next sync`)는 모듈이 아니라 `core` 에 들어 있다 — Jira MCP 가 연결돼 있고 큐 절에 `> jql:` 줄이 있으면 동작하고, 없으면 daily 대조만 한다.

## 설치

```bash
git clone <이 repo> && cd claude-notes-starter
zsh install.sh                 # 모듈 목록 (✓ = 설치됨)
zsh install.sh core            # 시작
zsh install.sh scrum entities  # 나중에 하나씩
# 노트 위치를 바꾸려면 처음 한 번: NOTES=~/Documents/notes zsh install.sh core
```

그다음:
1. Obsidian → "Open folder as vault" → `~/notes`.
2. (권장) `cd ~/notes && git init && git add -A && git commit -m init`. repo 면 `/log` 가 커밋까지 한다. `gbrain` 모듈은 repo 가 필요하다.
3. **새** Claude Code 세션에서 작업하고 `/log`. 그게 첫 daily 다.

## 업데이트

```bash
git pull && zsh install.sh update     # 설치했던 모듈 전부 다시
```

| 무엇 | 다시 설치하면 |
|---|---|
| 키트 파일 — `~/.claude/commands/{log,next,scrum,brain}.md`, `~/.claude/notes-kit/` | 내용이 다르면 `.bak-<시각>` 으로 백업하고 교체. 커맨드를 직접 고쳐 썼다면 백업에서 옮긴다 |
| 노트 — `~/notes` 안 파일 | **덮지 않는다.** 없을 때만 만들고, 새 절은 끝에 덧붙인다 |
| `~/.claude/CLAUDE.md` | 덮지 않는다. 같은 헤딩의 절이 없을 때만 끝에 덧붙인다 |
| `~/.claude/settings.json` (`procs`) | hook 두 줄이 없을 때만 넣는다. 넣기 전에 백업 |

## 첫 2주

- **세션 하나에 작업 하나.** 끝나면 `/log`, 그리고 `/exit`. 긴 세션은 compaction 뒤 앞부분을 잃는다 — 기록이 있으면 끊어도 손해가 없다.
- **새 세션은 `/next` 로 시작.** "어제 뭐 하다 말았지"를 Claude 가 답한다.
- daily 는 읽기만 한다. 고치고 싶으면 Claude 에게 시킨다.
- 2주 뒤 daily 를 훑어보고, 가장 자주 막힌 지점에 맞는 모듈을 하나 켠다.

## 모듈별 메모

**scrum** — `--post` 는 항상 초안을 보여 주고 확인을 받은 뒤 보낸다. 채널·보고 형식은 `~/notes/README.md` `## 스크럼 설정` 에 적히고, 형식은 그 채널에 내가 올려 온 최근 게시물을 읽어 따른다. 저녁 보고 본문은 `scrum_render.py` 가 daily 의 제목 줄만 기계적으로 뽑는다(세부 불릿·`## 개인` 은 나가지 않는다).

**entities** — 페이지는 "다시 볼 사람", "세 번 넘게 나온 프로젝트"일 때만 만든다. 옛 사실은 지우지 않고 `status: superseded` 로 표시한다(`RESOLVER.md` 정정 절차).

**procs** — 세션이 끝날 때 그 세션이 띄운 것만 끈다(프로세스 환경변수의 세션 id 로 귀속). 다른 세션 것은 보고만 한다. 셸 무한 루프는 못 잡는다 — 루프에는 종료 조건을 넣는다.

**gbrain** — `install.sh gbrain` 이 선행 도구를 확인하고, 없으면 설치 명령만 알려 준다. 다 있으면 `gbrain init --pglite`(서버 없는 로컬 파일 DB) → 소스 `notes` 등록 → `claude mcp add gbrain -s user` → 첫 동기화까지 한다. 이미 쓰던 gbrain 브레인이 있으면 건드리지 않고 명령만 알려 준다. 이후엔 `~/notes` 커밋마다 post-commit 훅이 백그라운드로 동기화한다(`NOTES_NO_SYNC=1` 로 끈다). 검증한 gbrain 버전은 `v0.54.1.1`.

```bash
brew install oven-sh/bun/bun && bun install -g github:garrytan/gbrain#v0.54.1.1
brew install --cask ollama && ollama pull bge-m3      # 임베딩 모델 1.2GB, 로컬에서만 돈다
zsh install.sh gbrain
```

## 테스트

```bash
python3 -m unittest discover -s tests -v
```

표준 라이브러리만. 설치 테스트는 매번 빈 임시 HOME 에서 돈다(실제 `~/.claude`·`~/notes` 는 건드리지 않는다). `procs` 테스트는 `node` 가 있어야 돈다.

## 라이선스

MIT
