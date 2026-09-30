#!/usr/bin/env python3
"""daily → Slack 저녁 보고 본문 렌더러 (/scrum pm --post).

규칙은 기계적이다 — 모델이 세부 불릿을 보고에 끌고 들어오는 것을 막는 게 목적이다.
  - 프로젝트 절(## 헤딩)의 **최상위 번호 항목 첫 줄**만 가져온다. 들여쓴 세부 불릿은 나가지 않는다.
  - `## 개인` 과 프로젝트가 아닌 절(아침/저녁 스크럼·스크럼·회의)은 건너뛴다.
  - 굵게·wikilink·마크다운 링크·코드 표기·[진행]/[이월]/[완료]·줄 끝 ⏰ 는 벗기고, 숫자는 그대로 둔다.
  - 프로젝트 순서는 daily 에 나온 순서. --order "A,B" 를 주면 그 순서가 먼저, 나머지는 뒤에.
  - 프로젝트 사이에 빈 줄을 넣는다 — Slack 의 markdown 변환이 목록을 이어 붙이지 않게.

사용: scrum_render.py daily/YYYY-MM-DD.md [--order "A,B,C"] [--check]
  --check  본문 대신 형식 위반만 보고한다. 위반이 있으면 exit 1.
"""
import re
import sys
from pathlib import Path

SKIP = {"개인", "아침 스크럼", "저녁 스크럼", "스크럼", "회의"}
ITEM = re.compile(r"^(\d+)\.\s+(.*)$")
MAX_TITLE = 90


def clean(s):
    s = re.sub(r"\s*→\s*\[\[[^\]]+\]\]\s*$", "", s)             # 끝의 "→ [[교훈 노트]]" 는 통째로
    s = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", s)      # [[a|b]] → b
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)                 # [[a]] → a
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", s) # [t](url) → t
    s = re.sub(r"\*\*|__|`", "", s)
    s = re.sub(r"\[(진행|완료|이월)\]\s*", "", s)
    s = re.sub(r"\s*⏰\s*\d{2}-\d{2}(\s+\d{2}:\d{2})?\s*$", "", s)
    s = re.sub(r"\s*(→|⏰)\s*$", "", s)
    return re.sub(r"\s{2,}", " ", s).strip(" -—·")


def parse(text):
    """## 헤딩 → 줄 목록. frontmatter 와 첫 헤딩 앞은 버린다."""
    sections, cur = {}, None
    for ln in text.splitlines():
        m = re.match(r"^## (.+?)\s*$", ln)
        if m:
            cur = m.group(1).strip()
            sections.setdefault(cur, [])
            continue
        if cur is not None:
            sections[cur].append(ln)
    return sections


def titles(lines):
    out, problems = [], []
    for ln in lines:
        if ln.startswith((" ", "\t")):
            continue
        m = ITEM.match(ln)
        if not m:
            continue
        t = clean(m.group(2))
        if not t:
            continue
        if len(t) > MAX_TITLE:
            problems.append(f"제목이 {MAX_TITLE}자를 넘는다(세부가 제목에 섞였을 가능성): {t[:60]}…")
        out.append(t)
    return out, problems


def render(text, order=()):
    sections = parse(text)
    names = [n for n in sections if n not in SKIP]
    first = [n for n in order if n in names]
    names = first + [n for n in names if n not in first]
    blocks, problems = [], []
    for name in names:
        items, probs = titles(sections[name])
        problems += [f"[{name}] {p}" for p in probs]
        if items:
            blocks.append("\n".join([name] + [f"{i}. {t}" for i, t in enumerate(items, 1)]))
    return "\n\n".join(blocks), problems


def main(argv):
    args, order, check = [], (), False
    it = iter(argv)
    for a in it:
        if a == "--check":
            check = True
        elif a == "--order":
            order = tuple(x.strip() for x in next(it, "").split(",") if x.strip())
        elif a.startswith("--"):
            print(f"알 수 없는 옵션: {a}", file=sys.stderr)
            return 2
        else:
            args.append(a)
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    p = Path(args[0]).expanduser()
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        print(f"daily 를 읽을 수 없다: {e}", file=sys.stderr)
        return 2
    body, problems = render(text, order)
    for pr in problems:
        print(f"⚠️ {pr}", file=sys.stderr)
    if check:
        return 1 if problems else 0
    if not body:
        print("⚠️ 보고할 항목이 없다(프로젝트 절에 번호 항목 0개)", file=sys.stderr)
        return 1
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
