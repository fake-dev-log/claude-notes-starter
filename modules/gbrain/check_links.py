#!/usr/bin/env python3
"""~/notes 의 끊긴 [[링크]] 를 찾는다 (/brain check).

대상 이름 = 파일명(확장자 뺀 것) 또는 frontmatter aliases. 코드 블록·인라인 코드 안의 [[…]] 는 무시한다.
[[a|표시]] 는 a, [[a#절]] 은 a 로 본다. 출력: "파일: [[대상]]" 한 줄씩, 끝에 합계. 끊긴 링크가 있으면 exit 1.
사용: check_links.py [노트 경로]   (기본 ~/notes)
"""
import re
import sys
from pathlib import Path

LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
INLINE = re.compile(r"`[^`\n]*`")
ALIASES = re.compile(r"^aliases:\s*\[(.*?)\]\s*$", re.M)


def names(root):
    out = set()
    for p in root.rglob("*.md"):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        out.add(p.stem)
        head = p.read_text(encoding="utf-8", errors="ignore")[:2000]
        if head.startswith("---"):
            m = ALIASES.search(head.split("\n---", 1)[0])
            if m:
                out.update(a.strip().strip("'\"") for a in m.group(1).split(",") if a.strip())
    return out


def broken(root):
    known = names(root)
    out = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        text = INLINE.sub("", FENCE.sub("", p.read_text(encoding="utf-8", errors="ignore")))
        for m in LINK.finditer(text):
            target = m.group(1).strip()
            if target and Path(target).name not in known and target not in known:
                out.append((str(rel), target))
    return out


def main(argv):
    root = Path(argv[0] if argv else "~/notes").expanduser()
    if not root.is_dir():
        print(f"노트 폴더가 없다: {root}", file=sys.stderr)
        return 2
    rows = broken(root)
    for f, t in rows:
        print(f"{f}: [[{t}]]")
    print(f"끊긴 링크 {len(rows)}개")
    return 1 if rows else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
