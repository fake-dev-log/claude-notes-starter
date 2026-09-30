"""modules/procs/session_procs.py 검사 — 더미 node 프로세스에 세션 env 를 심어 회수·보고를 본다.

session_procs 는 SESSION_PROCS_TEST_MARKER 가 든 프로세스만 보므로 실제 다른 세션의 dev 서버는 건드리지 않는다.
SESSION_PROCS 환경변수로 대상 스크립트를 바꿀 수 있다 — 한 번 깨서 빨간불을 확인할 때 쓴다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCS = os.environ.get("SESSION_PROCS", str(ROOT / "modules" / "procs" / "session_procs.py"))
TMP_HOME = tempfile.mkdtemp(prefix="procstest-home-")


def tearDownModule():
    shutil.rmtree(TMP_HOME, ignore_errors=True)


NODE = shutil.which("node")
MARKER = f"procstest-{os.getpid()}-{time.time_ns()}"   # session_procs 가 이 마커가 든 프로세스만 보게 한다


@unittest.skipUnless(NODE, "node 필요")
class SessionProcs(unittest.TestCase):
    """더미 node 프로세스에 세션 env 를 심어 회수·보고를 본다. 더미는 30초 뒤 스스로 끝난다(자체 데드라인)."""

    def setUp(self):
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)

    def spawn(self, sid, claude_pid, marker):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID=sid, CLAUDE_PID=str(claude_pid))
        p = subprocess.Popen([NODE, "-e", "setTimeout(()=>{},30000)", marker, MARKER], env=env)
        self.procs.append(p)
        return p

    def dead_pid(self):
        p = subprocess.Popen(["true"])
        p.wait()
        return p.pid

    def run_procs(self, mode, sid):
        env = dict(os.environ, HOME=TMP_HOME, SESSION_PROCS_TEST_MARKER=MARKER)
        r = subprocess.run([sys.executable, PROCS, mode], input=json.dumps({"session_id": sid, "reason": "test"}),
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_end_reaps_only_own_dev_processes(self):
        sid = f"test-{os.getpid()}-{time.time_ns()}"
        mine = self.spawn(sid, os.getpid(), "vite")
        other = self.spawn(sid + "-other", os.getpid(), "vite")          # 다른 세션 → 살아야 한다
        not_dev = self.spawn(sid, os.getpid(), "notes-sync")            # 같은 세션이지만 DEV 아님 → 살아야 한다
        time.sleep(0.5)
        self.run_procs("end", sid)
        mine.wait(timeout=5)
        self.assertIsNotNone(mine.poll())
        self.assertIsNone(other.poll())
        self.assertIsNone(not_dev.poll())

    def test_start_reports_dead_session_leftovers(self):
        sid = f"test-{os.getpid()}-{time.time_ns()}"
        orphan = self.spawn(sid, self.dead_pid(), "vite")
        live = self.spawn(sid + "-live", os.getpid(), "vite")          # 살아 있는 세션 것 → 보고 안 함
        time.sleep(0.5)
        out = self.run_procs("start", "new-session")
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(f"pid {orphan.pid}", ctx)
        self.assertNotIn(f"pid {live.pid}", ctx)


if __name__ == "__main__":
    unittest.main()
