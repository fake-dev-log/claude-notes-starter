"""modules/scrum/scrum_render.py 검사. 실행: python3 -m unittest discover -s tests -v (repo 루트)"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDER = os.environ.get("SCRUM_RENDER", str(ROOT / "modules" / "scrum" / "scrum_render.py"))

DAILY = """---
type: daily
date: 2026-09-30
---

## 아침 스크럼
1. 이건 나가면 안 된다

## api
1. **ABC-12 주문 목록 페이지네이션 — 커서 방식으로 교체** → [[2026-09-30 인덱스 없는 정렬은 느리다]]
   - 🔴 세부는 나가면 안 된다 2.1s → 40ms
2. [이월] `worker` 재시도 상한 정리 ⏰ 10-02
3. [[결제 모듈|결제]] 로그 정리 — [문서](https://example.com/x)

## 개인
1. 개인 일은 나가면 안 된다

## web
1. 로그인 화면 한글 깨짐 수정 (UTF-8 → 한글 1,234건 확인)

## 회의
1. 회의도 나가면 안 된다
"""


def run(*args, text=None):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "2026-09-30.md"
        if text is not None:
            p.write_text(text, encoding="utf-8")
        argv = [str(p) if a == "{daily}" else a for a in args]
        r = subprocess.run([sys.executable, RENDER, *argv], capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout, r.stderr


class Render(unittest.TestCase):
    def test_titles_only_in_daily_order(self):
        code, out, err = run("{daily}", text=DAILY)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "\n".join([
            "api",
            "1. ABC-12 주문 목록 페이지네이션 — 커서 방식으로 교체",
            "2. worker 재시도 상한 정리",
            "3. 결제 로그 정리 — 문서",
            "",
            "web",
            "1. 로그인 화면 한글 깨짐 수정 (UTF-8 → 한글 1,234건 확인)",
        ]))

    def test_details_personal_and_meta_sections_never_leak(self):
        _, out, _ = run("{daily}", text=DAILY)
        for leak in ("세부", "개인 일", "아침", "회의도", "[[", "**", "`", "⏰", "[이월]"):
            self.assertNotIn(leak, out)

    def test_order_option_puts_named_first(self):
        _, out, _ = run("{daily}", "--order", "web, 없는프로젝트", text=DAILY)
        self.assertTrue(out.startswith("web\n1. "))
        self.assertIn("\n\napi\n1. ", out)

    def test_blank_line_between_projects(self):
        # Slack markdown 변환이 목록을 이어 붙이지 않게 하는 장치 — 빠지면 번호가 이어진다
        _, out, _ = run("{daily}", text=DAILY)
        self.assertIn("\n\nweb\n", out)

    def test_long_title_warns_and_check_fails(self):
        long = "## api\n1. " + "가" * 91 + "\n"
        code, out, err = run("{daily}", text=long)
        self.assertEqual(code, 0)
        self.assertIn("90자", err)
        code, out, err = run("{daily}", "--check", text=long)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_exactly_90_chars_is_fine(self):
        code, _, err = run("{daily}", "--check", text="## api\n1. " + "가" * 90 + "\n")
        self.assertEqual(code, 0, err)

    def test_no_items_is_an_error(self):
        code, out, err = run("{daily}", text="---\ntype: daily\n---\n\n## 개인\n1. x\n\n## api\n- 불릿만\n")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("0개", err)

    def test_empty_file(self):
        code, out, _ = run("{daily}", text="")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_missing_file_and_bad_args(self):
        self.assertEqual(run("{daily}")[0], 2)          # 파일을 만들지 않았다
        self.assertEqual(run()[0], 2)
        self.assertEqual(run("{daily}", "--nope", text=DAILY)[0], 2)

    def test_tab_indented_details_skipped(self):
        _, out, _ = run("{daily}", text="## api\n1. 제목\n\t2. 탭 들여쓴 하위 번호\n")
        self.assertEqual(out.strip(), "api\n1. 제목")


if __name__ == "__main__":
    unittest.main()
