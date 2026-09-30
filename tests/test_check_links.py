"""modules/gbrain/check_links.py 검사."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = os.environ.get("CHECK_LINKS", str(ROOT / "modules" / "gbrain" / "check_links.py"))


def notes(files):
    d = tempfile.mkdtemp(prefix="notes-")
    for rel, text in files.items():
        p = Path(d) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


def run(*args):
    r = subprocess.run([sys.executable, CHECK, *args], capture_output=True, text=True, timeout=10)
    return r.returncode, r.stdout, r.stderr


class CheckLinks(unittest.TestCase):
    def test_all_links_resolve(self):
        d = notes({
            "people/홍길동.md": "---\ntype: person\naliases: [Gildong, 'gd']\n---\n# 홍길동\n",
            "daily/2026-09-30.md": "[[홍길동]] [[Gildong]] [[gd|길동]] [[홍길동#지금]] [[people/홍길동]]\n",
        })
        code, out, _ = run(d)
        self.assertEqual(code, 0, out)
        self.assertIn("끊긴 링크 0개", out)

    def test_broken_link_reported(self):
        d = notes({"daily/2026-09-30.md": "1. 작업 → [[없는 교훈]]\n"})
        code, out, _ = run(d)
        self.assertEqual(code, 1)
        self.assertIn("daily/2026-09-30.md: [[없는 교훈]]", out)
        self.assertIn("끊긴 링크 1개", out)

    def test_code_is_ignored(self):
        d = notes({"README.md": "형식 예: `[[YYYY-MM-DD]]`\n\n```markdown\n→ [[제목]]\n```\n"})
        code, out, _ = run(d)
        self.assertEqual(code, 0, out)

    def test_hidden_dirs_ignored(self):
        d = notes({".obsidian/x.md": "[[없음]]\n", "a.md": "ok\n"})
        self.assertEqual(run(d)[0], 0)

    def test_missing_dir(self):
        code, _, err = run("/nonexistent/notes-dir")
        self.assertEqual(code, 2)
        self.assertIn("없다", err)

    def test_empty_notes(self):
        code, out, _ = run(notes({}))
        self.assertEqual(code, 0)
        self.assertIn("0개", out)


if __name__ == "__main__":
    unittest.main()
