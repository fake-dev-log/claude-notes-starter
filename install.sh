#!/bin/zsh
# claude-notes-starter 설치·업데이트.
#   zsh install.sh                      모듈 목록
#   zsh install.sh core [scrum …]       설치 (다시 돌리면 업데이트)
#   zsh install.sh update               설치했던 모듈 전부 다시 (git pull 뒤에)
#   NOTES=~/Documents/notes zsh install.sh core    노트 위치 바꾸기 — 처음 설치 때 한 번. 이후엔 기억한다.
#
# 덮어쓰기 규칙
#   키트 파일(~/.claude/commands 의 커맨드, ~/.claude/notes-kit 의 스크립트) — 내용이 다르면 .bak-<시각> 으로 백업하고 교체.
#   노트(~/notes 안)·~/.claude/CLAUDE.md — 덮지 않는다. 파일이 없으면 만들고, 절이 없으면 끝에 덧붙인다.
set -euo pipefail
HERE=${0:A:h}
CLAUDE_HOME=$HOME/.claude
KIT=$CLAUDE_HOME/notes-kit
CMD=$CLAUDE_HOME/commands
CLAUDE_MD=$CLAUDE_HOME/CLAUDE.md
STAMP=$(date +%Y%m%d-%H%M%S)
ALL=(core scrum entities procs gbrain)
typeset -A DESC=(
  core     "/log · /next(+ 세션 간 착수 표시) — 기록 루프 (필수)"
  scrum    "/scrum am|pm|weekly [--post] — daily 로 스크럼·주간 보고 초안, Slack 보고"
  entities "사람·프로젝트·결정 페이지 + RESOLVER — /log·/scrum 이 새 사실을 옮긴다"
  procs    "세션이 띄운 dev 서버·watcher 를 세션 종료 때 회수 (SessionStart/End hook)"
  gbrain   "노트 의미 검색(gbrain, 로컬 PGLite + Ollama) + /brain sync|check"
)

if [[ -n ${NOTES:-} ]]; then NOTES=${NOTES/#\~/$HOME}
elif [[ -s $KIT/notes-path ]]; then NOTES=$(<$KIT/notes-path)
else NOTES=$HOME/notes; fi
NOTES_T=${NOTES/#$HOME/\~}          # 커맨드 문서에 박을 표기 (~/notes)

TILDE='~'
say() { printf '%-7s %s\n' "$1" "${2//$HOME/$TILDE}"; }
render() { sed -e "s#~/notes#${NOTES_T}#g" "$1"; }

put_kit() {   # 키트 파일: 없으면 추가, 같으면 그대로, 다르면 백업 후 교체
  local src=$1 dst=$2 mode=${3:-644} tmp
  mkdir -p "${dst:h}"
  tmp=$(mktemp "${dst:h}/.tmp.XXXXXX")
  render "$src" > "$tmp"; chmod "$mode" "$tmp"
  if [[ ! -e $dst ]]; then mv "$tmp" "$dst"; say add "$dst"
  elif cmp -s "$tmp" "$dst"; then rm -f "$tmp"; say same "$dst"
  else cp -p "$dst" "$dst.bak-$STAMP"; mv "$tmp" "$dst"; say update "$dst  (이전 것 → ${dst:t}.bak-$STAMP)"; fi
}

put_user() {  # 노트 파일: 없을 때만
  local src=$1 dst=$2
  mkdir -p "${dst:h}"
  if [[ -e $dst ]]; then say skip "$dst (이미 있음 — 덮지 않는다)"
  else render "$src" > "$dst"; say add "$dst"; fi
}

append_section() {  # 파일 끝에 절 덧붙이기. 같은 헤딩 줄이 이미 있으면 skip
  local file=$1 src=$2 head
  head=$(grep -m1 '^## ' "$src")
  mkdir -p "${file:h}"
  if grep -qxF -- "$head" "$file" 2>/dev/null; then say skip "$file ← '$head' (이미 있음)"; return; fi
  { [[ -s $file ]] && echo; render "$src" | sed '/./,$!d'; } >> "$file"
  say add "$file ← '$head'"
}

record() { mkdir -p "$KIT"; touch "$KIT/modules"; grep -qxF "$1" "$KIT/modules" || echo "$1" >> "$KIT/modules"; }

m_core() {
  mkdir -p "$NOTES/daily" "$NOTES/lessons"
  put_user "$HERE/core/notes/README.md" "$NOTES/README.md"
  put_user "$HERE/core/notes/queue.md"  "$NOTES/queue.md"
  put_kit "$HERE/core/commands/log.md"  "$CMD/log.md"
  put_kit "$HERE/core/commands/next.md" "$CMD/next.md"
  put_kit "$HERE/core/claim.py"         "$KIT/claim.py"
  append_section "$CLAUDE_MD" "$HERE/core/CLAUDE.snippet.md"
  mkdir -p "$KIT"; print -r -- "$NOTES" > "$KIT/notes-path"
}

m_scrum() {
  mkdir -p "$NOTES/weekly"
  put_kit "$HERE/modules/scrum/commands/scrum.md" "$CMD/scrum.md"
  put_kit "$HERE/modules/scrum/scrum_render.py"   "$KIT/scrum_render.py"
  append_section "$NOTES/README.md" "$HERE/modules/scrum/notes.snippet.md"
}

m_entities() {
  mkdir -p "$NOTES"/{people,projects,decisions,meetings}
  put_user "$HERE/modules/entities/RESOLVER.md" "$NOTES/RESOLVER.md"
  append_section "$NOTES/README.md" "$HERE/modules/entities/notes.snippet.md"
  append_section "$CLAUDE_MD" "$HERE/modules/entities/CLAUDE.snippet.md"
}

m_procs() {
  put_kit "$HERE/modules/procs/session_procs.py" "$KIT/hooks/session_procs.py"
  local r
  r=$(/usr/bin/python3 - "$CLAUDE_HOME/settings.json" "$KIT/hooks/session_procs.py" "$STAMP" <<'PY'
import json, os, shutil, sys
path, script, stamp = sys.argv[1:]
try:
    d = json.load(open(path)) if os.path.exists(path) and os.path.getsize(path) else {}
except ValueError as e:
    print(f"error settings.json 이 JSON 이 아니다({e}) — 손대지 않았다"); sys.exit(0)
hooks = d.setdefault("hooks", {})
changed = False
for ev, arg in (("SessionStart", "start"), ("SessionEnd", "end")):
    cmd = f'/usr/bin/python3 "{script}" {arg}'
    groups = hooks.setdefault(ev, [])
    if any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
        continue
    groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 15}]})
    changed = True
if changed:
    if os.path.exists(path):
        shutil.copy2(path, f"{path}.bak-{stamp}")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=2); f.write("\n")
    os.replace(tmp, path)
print("add" if changed else "same")
PY
)
  case $r in
    add)  say add  "$CLAUDE_HOME/settings.json ← SessionStart·SessionEnd hook (이전 것 → settings.json.bak-$STAMP)" ;;
    same) say same "$CLAUDE_HOME/settings.json (hook 이미 있음)" ;;
    *)    say error "$r"; return 1 ;;
  esac
  append_section "$CLAUDE_MD" "$HERE/modules/procs/CLAUDE.snippet.md"
}

m_gbrain() {
  put_kit "$HERE/modules/gbrain/notes-sync.sh"     "$KIT/notes-sync.sh" 755
  put_kit "$HERE/modules/gbrain/check_links.py"    "$KIT/check_links.py"
  put_kit "$HERE/modules/gbrain/commands/brain.md" "$CMD/brain.md"
  # 노트 커밋마다 백그라운드 동기화
  local hook=$NOTES/.git/hooks/post-commit
  if [[ ! -d $NOTES/.git ]]; then
    say skip "post-commit 훅 — ${NOTES_T} 가 git repo 가 아니다(cd ${NOTES_T} && git init 후 다시)"
  elif grep -qs 'notes-sync.sh' "$hook"; then say same "$hook"
  else
    [[ -s $hook ]] || print -r -- '#!/bin/sh' > "$hook"
    print -r -- '[ -z "$NOTES_NO_SYNC" ] && (zsh "$HOME/.claude/notes-kit/notes-sync.sh" >/dev/null 2>&1 &)' >> "$hook"
    chmod +x "$hook"; say add "$hook ← notes-sync"
  fi
  # 한 번만 하는 설정 — 선행 도구가 없으면 안내만 하고 넘어간다
  local miss=()
  command -v gbrain >/dev/null || miss+=("gbrain:  brew install oven-sh/bun/bun && bun install -g github:garrytan/gbrain#v0.54.1.1")
  command -v ollama >/dev/null || miss+=("ollama:  brew install --cask ollama  (앱을 한 번 켠다)")
  if (( ${#miss} )); then
    say todo "선행 도구가 없다 — 설치 후 'zsh install.sh gbrain' 을 다시:"; printf '          %s\n' "${miss[@]}"; return 0
  fi
  # 출력을 먼저 받는다 — `ollama list | grep -q` 는 grep 이 먼저 끝나면 ollama 가 SIGPIPE 로 죽고,
  # pipefail 때문에 모델이 있어도 '없다'로 판정된다(실측)
  local out
  out=$(ollama list 2>/dev/null) || true
  if [[ $'\n'$out != *$'\n'bge-m3* ]]; then
    say todo "임베딩 모델이 없다 — 'ollama pull bge-m3' (1.2GB) 후 'zsh install.sh gbrain' 을 다시"; return 0
  fi
  if [[ -e $HOME/.gbrain/config.json ]]; then
    out=$(gbrain sources list 2>/dev/null) || true
    if [[ $out == *notes* ]]; then say same "gbrain 소스 notes"
    else say todo "기존 gbrain 브레인이 있어 건드리지 않았다 — 직접: gbrain sources add notes --path \"$NOTES\""; fi
  else
    say run "gbrain init --pglite (로컬 파일 DB, 서버 없음)"
    # 출력이 길다 — 실패할 때만 끝부분을 보인다
    if ! out=$(gbrain init --pglite --embedding-model ollama:bge-m3 --embedding-dimensions 1024 --non-interactive 2>&1); then
      say error "gbrain init 실패:"; print -r -- "$out" | tail -8; return 1; fi
    if ! out=$(gbrain sources add notes --path "$NOTES" --name notes 2>&1); then
      say error "gbrain sources add 실패:"; print -r -- "$out" | tail -8; return 1; fi
    say add "gbrain 소스 notes → ${NOTES_T}"
  fi
  if command -v claude >/dev/null; then
    if claude mcp get gbrain >/dev/null 2>&1; then say same "claude MCP gbrain"
    else claude mcp add gbrain -s user -- "$(command -v gbrain)" serve >/dev/null && say add "claude MCP gbrain (user scope)"; fi
  else say todo "claude CLI 가 PATH 에 없다 — 직접: claude mcp add gbrain -s user -- $(command -v gbrain) serve"; fi
  if [[ -d $NOTES/.git ]]; then
    say run "첫 동기화"; NOTES_NO_SYNC= zsh "$KIT/notes-sync.sh"
    grep -v -i upgrade "$KIT/logs/sync-$(date +%Y-%m).log" | tail -3 | sed 's/^/          /'
  fi
  return 0
}

usage() {
  print "claude-notes-starter — 모듈 (✓ = 설치됨, 노트: ${NOTES_T})\n"
  local m mark
  for m in $ALL; do
    mark=" "; grep -qsxF "$m" "$KIT/modules" && mark="✓"
    printf '  %s %-9s %s\n' "$mark" "$m" "$DESC[$m]"
  done
  print "\n  zsh install.sh core scrum      설치 (다시 돌리면 업데이트)\n  zsh install.sh update          설치했던 모듈 전부 다시"
}

(( $# )) || { usage; exit 0; }
want=()
if [[ $1 == update ]]; then
  [[ -s $KIT/modules ]] || { print "설치된 모듈 기록이 없다 — zsh install.sh core 부터"; exit 1; }
  want=("${(@f)$(<$KIT/modules)}")
else
  for m in "$@"; do (( ${ALL[(Ie)$m]} )) || { print "모르는 모듈: $m"; usage; exit 1; }; done
  want=("$@")
fi
# core 는 모든 모듈의 바탕 — 설치된 적 없으면 먼저
if ! (( ${want[(Ie)core]} )) && ! grep -qsxF core "$KIT/modules"; then print "core 가 먼저 필요하다 — 같이 설치한다"; want=(core $want); fi

for m in $ALL; do
  (( ${want[(Ie)$m]} )) || continue
  print "\n[$m]"; m_$m; record "$m"
done

print "\n완료. 새 Claude Code 세션부터 적용된다."
if (( ${want[(Ie)core]} )) && [[ ! -d $NOTES/.git ]]; then
  print "  • Obsidian → Open folder as vault → ${NOTES_T}\n  • (권장) cd ${NOTES_T} && git init && git add -A && git commit -m init — repo 면 /log 가 커밋까지 한다"
fi
