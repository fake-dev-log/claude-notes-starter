"""core/claim.py 검사 — 가짜 Claude 세션(= 살아 있는 sleep 프로세스의 PID)을 여럿 만들어 착수 표시를 본다.

매 테스트는 빈 임시 HOME 에서 돈다. CLAIM 환경변수로 대상 스크립트를 바꿀 수 있다 — 한 번 깨서 빨간불을 확인할 때 쓴다.
"""
import concurrent.futures as cf
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAIM = os.environ.get("CLAIM", str(ROOT / "core" / "claim.py"))
GATE = (dt.date.today() + dt.timedelta(days=30)).strftime("%m-%d")   # 늘 30일 뒤 — 해가 바뀌어도 게이트 전

QUEUE = """# 큐

## api
> jql: project = ABC
> synced: 2026-09-30
1. ABC-12 주문 목록 커서 페이지네이션 — 인덱스부터
2. **로그 정리** — worker 재시도 상한
3. 모바일 호출 확인 ⏰ {gate}
- 잔여: 불릿은 항목이 아니다

## web
1. 로그인 한글 깨짐

## 비어 있음

## 보류
- 당분간 안 할 것
""".replace("{gate}", GATE)


class Claim(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="claimtest-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        (self.home / "notes").mkdir()
        self.queue = self.home / "notes" / "queue.md"
        self.queue.write_text(QUEUE, encoding="utf-8")
        (self.home / ".claude" / "sessions").mkdir(parents=True)
        self.procs = []
        self.addCleanup(self.kill_all)

    def kill_all(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)

    def session(self, name):
        """살아 있는 가짜 Claude 세션 — (세션 id, pid). 60초 뒤 스스로 끝난다."""
        p = subprocess.Popen(["sleep", "60"])
        self.procs.append(p)
        sid = f"{name}-{p.pid}-session"
        (self.home / ".claude" / "sessions" / f"{p.pid}.json").write_text(json.dumps({"name": name, "sessionId": sid}))
        return sid, p.pid

    def run_claim(self, who, *args, extra=None):
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"}
        if who:
            env.update(CLAUDE_CODE_SESSION_ID=who[0], CLAUDE_PID=str(who[1]))
        env.update(extra or {})
        r = subprocess.run([sys.executable, CLAIM, *args], capture_output=True, text=True, env=env, timeout=30)
        return r.returncode, r.stdout, r.stderr

    # ---- happy
    def test_other_session_sees_lock_and_gets_next_item(self):
        a, b = self.session("alpha"), self.session("beta")
        self.assertEqual(self.run_claim(a, "claim", "api", "1")[0], 0)
        code, out, _ = self.run_claim(b, "show", "api")
        self.assertEqual(code, 0)
        self.assertIn("▶ 지금  2. **로그 정리**", out)
        self.assertIn("🔒 1. ABC-12", out)
        self.assertIn("alpha", out)
        _, out, _ = self.run_claim(a, "show", "api")
        self.assertIn("✋ 1. ABC-12", out)
        self.assertIn("▶ 지금  2.", out)

    def test_number_key_and_head_resolve_to_same_item(self):
        a, b = self.session("alpha"), self.session("beta")
        self.run_claim(a, "claim", "api", "abc-12")                      # 키(대소문자 무시)
        for arg in ("1", "ABC-12", "ABC-12 주문 목록 커서 페이지네이션"):
            self.assertEqual(self.run_claim(b, "claim", "api", arg)[0], 3, arg)
        self.run_claim(a, "claim", "api", "로그 정리")                     # 제목 머리(굵게·꼬리 무시)
        self.assertEqual(self.run_claim(b, "claim", "api", "2")[0], 3)

    def test_lock_follows_item_after_renumbering(self):
        a, b = self.session("alpha"), self.session("beta")
        self.run_claim(a, "claim", "api", "2")
        # 다른 세션이 맨 위에 항목을 넣고 번호를 다시 매겼다
        self.queue.write_text(QUEUE.replace("1. ABC-12", "1. 새 급한 일\n2. ABC-12").replace("2. **로그", "3. **로그")
                              .replace("3. 모바일", "4. 모바일"), encoding="utf-8")
        _, out, _ = self.run_claim(b, "show", "api")
        self.assertIn("🔒 3. **로그 정리**", out)
        self.assertIn("▶ 지금  1. 새 급한 일", out)

    def test_release_and_done(self):
        a, b = self.session("alpha"), self.session("beta")
        self.run_claim(a, "claim", "api", "1")
        self.assertEqual(self.run_claim(a, "release", "api", "1")[0], 0)
        self.assertEqual(self.run_claim(b, "claim", "api", "1")[0], 0)
        code, out, _ = self.run_claim(b, "done", "api", "ABC-12")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "1. ABC-12 주문 목록 커서 페이지네이션 — 인덱스부터")   # 지울 줄 그대로
        self.assertEqual(self.run_claim(a, "claim", "api", "1")[0], 0)

    def test_claim_twice_is_idempotent(self):
        a = self.session("alpha")
        self.run_claim(a, "claim", "api", "1")
        code, out, _ = self.run_claim(a, "claim", "api", "1")
        self.assertEqual(code, 0)
        self.assertIn("이미 내 착수", out)

    def test_show_all_skips_hold_section(self):
        a = self.session("alpha")
        self.run_claim(a, "claim", "web", "1")
        _, out, _ = self.run_claim(self.session("beta"), "show", "--all")
        self.assertIn("## api\n▶ 지금  1. ABC-12", out)
        self.assertIn("## web\n▶ 지금  없음", out)
        self.assertIn(f"⏳ 가장 이른 게이트 {GATE}", out)
        self.assertNotIn("## 보류", out)

    # ---- failure
    def test_other_session_is_refused_then_force(self):
        a, b = self.session("alpha"), self.session("beta")
        self.run_claim(a, "claim", "api", "1")
        code, _, err = self.run_claim(b, "claim", "api", "1")
        self.assertEqual(code, 3)
        self.assertIn("alpha", err)
        self.assertEqual(self.run_claim(b, "release", "api", "1")[0], 3)          # 남의 것은 못 푼다
        code, out, _ = self.run_claim(b, "claim", "api", "1", "--force")
        self.assertEqual(code, 0)
        self.assertIn("뺏음: alpha", out)

    def test_no_session_identity(self):
        code, _, err = self.run_claim(None, "claim", "api", "1")
        self.assertEqual(code, 4)
        self.assertIn("세션 신원", err)
        self.assertEqual(self.run_claim(None, "show", "api")[0], 0)              # 보기는 신원 없이도 된다

    def test_unknown_item_project_and_missing_queue(self):
        a = self.session("alpha")
        self.assertEqual(self.run_claim(a, "claim", "api", "9")[0], 1)
        self.assertEqual(self.run_claim(a, "claim", "api", "없는 제목")[0], 1)
        code, _, err = self.run_claim(a, "claim", "없는절", "1")
        self.assertEqual(code, 1)
        self.assertIn("있는 절", err)
        self.queue.unlink()
        self.assertEqual(self.run_claim(a, "show", "api")[0], 2)

    def test_bad_args(self):
        a = self.session("alpha")
        self.assertEqual(self.run_claim(a)[0], 1)
        self.assertEqual(self.run_claim(a, "claim", "api")[0], 1)
        self.assertEqual(self.run_claim(a, "nope")[0], 1)

    # ---- edge
    def test_dead_owner_frees_item(self):
        a, b = self.session("alpha"), self.session("beta")
        self.run_claim(a, "claim", "api", "1")
        self.procs[0].kill()
        self.procs[0].wait()
        _, out, _ = self.run_claim(b, "show", "api")
        self.assertIn("▶ 지금  1. ABC-12", out)
        self.assertEqual(self.run_claim(b, "claim", "api", "1")[0], 0)
        self.assertEqual(len(list((self.home / ".claude/notes-kit/claims").glob("*.json"))), 1)   # 죽은 표시는 지워졌다

    def test_reused_pid_is_not_trusted(self):
        a, b = self.session("alpha"), self.session("beta")
        self.run_claim(a, "claim", "api", "1")
        f = next((self.home / ".claude/notes-kit/claims").glob("*.json"))
        c = json.loads(f.read_text())
        c["started"] = "Mon Jan  1 00:00:00 2001"      # 같은 PID 지만 다른 프로세스
        f.write_text(json.dumps(c))
        self.assertEqual(self.run_claim(b, "claim", "api", "1")[0], 0)

    def test_concurrent_claims_have_one_winner(self):
        sessions = [self.session(f"s{i}") for i in range(8)]
        with cf.ThreadPoolExecutor(8) as ex:
            codes = list(ex.map(lambda s: self.run_claim(s, "claim", "api", "1",
                                                         extra={"CLAIM_TEST_RACE_SLEEP": "0.2"})[0], sessions))
        self.assertEqual(sorted(codes), [0] + [3] * 7)

    def test_done_after_line_already_removed(self):
        a = self.session("alpha")
        self.run_claim(a, "claim", "api", "로그 정리")
        self.queue.write_text(QUEUE.replace("2. **로그 정리** — worker 재시도 상한\n", ""), encoding="utf-8")
        code, out, _ = self.run_claim(a, "done", "api", "로그 정리")
        self.assertEqual(code, 0)
        self.assertIn("이미 없다", out)
        self.assertEqual(self.run_claim(a, "list")[1], "")

    def test_key_normalization(self):
        def key(s):
            return self.run_claim(None, "key", s)[1].strip()
        self.assertEqual(key("3. **abc-12** 무엇 — 꼬리"), "ABC-12")
        self.assertEqual(key("[이월] 로그  정리 — 꼬리 ⏰ 10-02"), "로그 정리")
        self.assertEqual(key(f"모바일 호출 확인 ⏰ {GATE}"), "모바일 호출 확인")
        self.assertEqual(key("Café 정리"), key("café 정리"))                 # NFC

    def test_empty_section(self):
        _, out, _ = self.run_claim(None, "show", "비어 있음")
        self.assertIn("▶ 지금  없음", out)
        self.assertIn("번호 항목 0개", out)


if __name__ == "__main__":
    unittest.main()
