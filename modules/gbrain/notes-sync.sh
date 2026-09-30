#!/bin/zsh
# ~/notes → gbrain 동기화. ~/notes 의 post-commit 훅이 백그라운드로 부르고, /brain sync 가 앞에서 부른다.
# 커밋된 변경만 읽는다(gbrain sync 는 git 기준). 중복 실행 잠금 + 단계별 데드라인 — 멈춘 채 남지 않는다.
#   NOTES_NO_SYNC=1 이면 아무것도 안 한다.
[ -n "${NOTES_NO_SYNC:-}" ] && exit 0
# 물려받은 PATH 가 먼저 — 훅·launchd 처럼 PATH 가 최소인 환경을 위해 bun·brew 경로를 뒤에 채운다
export PATH="${PATH:+$PATH:}$HOME/.bun/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
KIT="$HOME/.claude/notes-kit"; SOURCE="${NOTES_GBRAIN_SOURCE:-notes}"
LOCK="$KIT/.sync.lock"; LOG="$KIT/logs/sync-$(date +%Y-%m).log"
mkdir -p "$KIT/logs"
if ! mkdir "$LOCK" 2>/dev/null; then
  # 30분 넘은 잠금은 죽은 실행이 남긴 것 — 걷고 진행
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then rmdir "$LOCK"; mkdir "$LOCK" || exit 0
  else echo "$(date '+%F %T') skip: 다른 동기화가 도는 중" >> "$LOG"; exit 0; fi
fi
T=$(mktemp -t notessync)
trap '/bin/rmdir "$LOCK" 2>/dev/null; rm -f "$T"' EXIT
command -v gbrain >/dev/null || { echo "$(date '+%F %T') gbrain 없음 — skip" >> "$LOG"; exit 0; }

# 명령 하나를 데드라인 안에서 돌린다. 출력은 파이프가 아니라 임시 파일로 받는다 —
# `cmd | tail &` 이면 $! 가 tail 이라 kill 이 본 명령을 못 죽이고 고아로 남긴다.
run() { local dl=$1; shift; local what=$1; shift
  "$@" > "$T" 2>&1 & local p=$!; local d=$((SECONDS+dl))
  while kill -0 $p 2>/dev/null && [ $SECONDS -lt $d ]; do sleep 2; done
  if kill -0 $p 2>/dev/null; then
    kill $p 2>/dev/null; echo "!! $what 데드라인 ${dl}s 초과 — kill"
    local k=$((SECONDS+10)); while kill -0 $p 2>/dev/null && [ $SECONDS -lt $k ]; do sleep 1; done
    kill -9 $p 2>/dev/null
  fi
}
{
  echo "=== $(date '+%F %T') sync start"
  run 600 sync gbrain sync --source "$SOURCE" --no-pull --no-embed --yes
  grep -E "imported|Synced|complete|rror" "$T" | grep -v -i upgrade
  run 300 extract gbrain extract --stale --source-id "$SOURCE"
  head -1 "$T"
  if curl -s -m 3 localhost:11434/api/tags >/dev/null; then
    run 900 embed gbrain embed --stale
    grep -E "Embedded|rror" "$T"
  else echo "ollama 꺼짐 — embed 건너뜀(다음 동기화 때 --stale 로 따라잡는다)"; fi
  echo "=== $(date '+%F %T') done"
} >> "$LOG" 2>&1
