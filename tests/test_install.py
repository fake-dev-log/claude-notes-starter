"""install.sh 검사 — 매번 빈 임시 HOME 에서 돌린다. 실제 ~/.claude·~/notes 는 건드리지 않는다.

PATH 는 /usr/bin:/bin 만 준다 — gbrain·ollama·claude 가 안 보이게 해서 gbrain 모듈의 '선행 도구 없음' 경로를 탄다.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = os.environ.get("INSTALL_SH", str(ROOT / "install.sh"))


class Install(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="kittest-home-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.claude = self.home / ".claude"
        self.notes = self.home / "notes"

    def run_install(self, *args, env=None):
        e = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"}
        e.update(env or {})
        r = subprocess.run(["/bin/zsh", INSTALL, *args], capture_output=True, text=True, env=e, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def read(self, p):
        return Path(p).read_text(encoding="utf-8")

    # ---- happy path
    def test_list_without_args(self):
        code, out = self.run_install()
        self.assertEqual(code, 0, out)
        for m in ("core", "scrum", "entities", "procs", "gbrain"):
            self.assertIn(m, out)
        self.assertFalse(self.claude.exists())          # 목록만 — 아무것도 안 만든다

    def test_core_fresh_install(self):
        (self.claude).mkdir()
        (self.claude / "CLAUDE.md").write_text("# 내 규칙\n- 기존 줄\n", encoding="utf-8")
        code, out = self.run_install("core")
        self.assertEqual(code, 0, out)
        self.assertIn("add     ~/notes/README.md", out)       # 경로는 ~ 표기로 보인다(\~ 가 새면 안 된다)
        self.assertNotIn("\\~", out)
        for p in ("notes/README.md", "notes/queue.md", ".claude/commands/log.md", ".claude/commands/next.md"):
            self.assertTrue((self.home / p).exists(), p)
        self.assertTrue((self.notes / "daily").is_dir())
        md = self.read(self.claude / "CLAUDE.md")
        self.assertTrue(md.startswith("# 내 규칙\n- 기존 줄\n\n## 기록 루프"))
        self.assertIn("~/notes/daily/", self.read(self.claude / "commands/log.md"))
        self.assertEqual(self.read(self.claude / "notes-kit/modules").split(), ["core"])

    def test_rerun_is_idempotent(self):
        self.run_install("core", "scrum", "entities")
        before = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        code, out = self.run_install("core", "scrum", "entities")
        self.assertEqual(code, 0, out)
        self.assertNotRegex(out, r"(?m)^(add|update) ")
        after = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        md = self.read(self.claude / "CLAUDE.md")
        self.assertEqual(md.count("## 기록 루프"), 1)
        self.assertEqual(self.read(self.notes / "README.md").count("## 스크럼 설정"), 1)

    def test_all_modules_listed_as_installed(self):
        self.run_install("scrum")
        _, out = self.run_install()
        self.assertRegex(out, r"✓ core")
        self.assertRegex(out, r"✓ scrum")
        self.assertNotRegex(out, r"✓ gbrain")

    # ---- 업그레이드 (v1 → v2)
    def test_changed_kit_file_is_backed_up_then_replaced(self):
        cmd = self.claude / "commands"
        cmd.mkdir(parents=True)
        (cmd / "log.md").write_text("v1 내용\n", encoding="utf-8")
        code, out = self.run_install("core")
        self.assertEqual(code, 0, out)
        self.assertIn("update", out)
        baks = list(cmd.glob("log.md.bak-*"))
        self.assertEqual(len(baks), 1)
        self.assertEqual(self.read(baks[0]), "v1 내용\n")
        self.assertIn("# /log", self.read(cmd / "log.md"))

    def test_user_notes_never_overwritten(self):
        self.notes.mkdir()
        (self.notes / "queue.md").write_text("## 내 큐\n1. 지우면 안 됨\n", encoding="utf-8")
        (self.notes / "README.md").write_text("# 내 README\n", encoding="utf-8")
        self.run_install("core", "scrum")
        self.assertEqual(self.read(self.notes / "queue.md"), "## 내 큐\n1. 지우면 안 됨\n")
        readme = self.read(self.notes / "README.md")
        self.assertTrue(readme.startswith("# 내 README\n"))           # 원문 유지
        self.assertIn("## 스크럼 설정", readme)                        # 절만 덧붙음

    # ---- 노트 위치
    def test_custom_notes_path_is_substituted_and_remembered(self):
        code, out = self.run_install("core", env={"NOTES": str(self.home / "Documents/n")})
        self.assertEqual(code, 0, out)
        log = self.read(self.claude / "commands/log.md")
        self.assertIn("~/Documents/n/daily/", log)
        self.assertNotIn("~/notes/", log)
        self.assertIn("~/Documents/n", self.read(self.claude / "CLAUDE.md"))
        self.assertFalse(self.notes.exists())
        # 두 번째 실행은 NOTES 없이도 같은 위치
        self.run_install("scrum")
        self.assertIn("~/Documents/n/", self.read(self.claude / "commands/scrum.md"))
        self.assertTrue((self.home / "Documents/n/weekly").is_dir())

    def test_literal_tilde_notes_path(self):
        self.run_install("core", env={"NOTES": "~/x/notes"})
        self.assertTrue((self.home / "x/notes/daily").is_dir())
        self.assertFalse((Path.cwd() / "~").exists())

    # ---- 의존·실패
    def test_module_without_core_pulls_core(self):
        code, out = self.run_install("entities")
        self.assertEqual(code, 0, out)
        self.assertIn("core 가 먼저", out)
        self.assertTrue((self.claude / "commands/log.md").exists())
        self.assertTrue((self.notes / "RESOLVER.md").exists())
        self.assertEqual(self.read(self.claude / "notes-kit/modules").split(), ["core", "entities"])

    def test_unknown_module_changes_nothing(self):
        code, out = self.run_install("core", "nope")
        self.assertEqual(code, 1)
        self.assertIn("모르는 모듈: nope", out)
        self.assertFalse(self.claude.exists())
        self.assertFalse(self.notes.exists())

    def test_update_without_record_fails(self):
        code, out = self.run_install("update")
        self.assertEqual(code, 1)
        self.assertIn("core 부터", out)

    def test_update_reinstalls_recorded_modules(self):
        self.run_install("core", "scrum")
        (self.claude / "commands/scrum.md").unlink()
        code, out = self.run_install("update")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.claude / "commands/scrum.md").exists())
        self.assertFalse((self.claude / "commands/brain.md").exists())

    # ---- procs: settings.json 병합
    def test_procs_merges_hooks_preserving_existing(self):
        self.claude.mkdir()
        orig = {"model": "x", "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        (self.claude / "settings.json").write_text(json.dumps(orig), encoding="utf-8")
        code, out = self.run_install("procs")
        self.assertEqual(code, 0, out)
        d = json.loads(self.read(self.claude / "settings.json"))
        self.assertEqual(d["model"], "x")
        starts = [h["command"] for g in d["hooks"]["SessionStart"] for h in g["hooks"]]
        ends = [h["command"] for g in d["hooks"]["SessionEnd"] for h in g["hooks"]]
        self.assertEqual(starts[0], "echo mine")
        self.assertTrue(starts[1].endswith('session_procs.py" start'))
        self.assertTrue(ends[0].endswith('session_procs.py" end'))
        self.assertEqual(len(list(self.claude.glob("settings.json.bak-*"))), 1)
        # 다시 돌려도 hook 이 늘지 않는다
        self.run_install("procs")
        d2 = json.loads(self.read(self.claude / "settings.json"))
        self.assertEqual(d, d2)

    def test_procs_refuses_broken_settings(self):
        self.claude.mkdir()
        (self.claude / "settings.json").write_text("{ 깨진", encoding="utf-8")
        code, out = self.run_install("procs")
        self.assertNotEqual(code, 0)
        self.assertIn("JSON 이 아니다", out)
        self.assertEqual(self.read(self.claude / "settings.json"), "{ 깨진")
        self.assertNotIn("procs", self.read(self.claude / "notes-kit/modules").split())

    # ---- gbrain: 선행 도구가 없을 때
    def test_gbrain_without_tools_installs_files_and_guides(self):
        self.notes.mkdir()
        subprocess.run(["git", "init", "-q", str(self.notes)], check=True)
        code, out = self.run_install("gbrain")
        self.assertEqual(code, 0, out)
        self.assertIn("선행 도구가 없다", out)
        self.assertTrue((self.claude / "commands/brain.md").exists())
        self.assertTrue(os.access(self.claude / "notes-kit/notes-sync.sh", os.X_OK))
        hook = self.notes / ".git/hooks/post-commit"
        self.assertTrue(os.access(hook, os.X_OK))
        self.run_install("gbrain")
        self.assertEqual(self.read(hook).count("notes-sync.sh"), 1)

    def test_gbrain_without_git_skips_hook(self):
        code, out = self.run_install("gbrain")
        self.assertEqual(code, 0, out)
        self.assertIn("git repo 가 아니다", out)
        self.assertFalse((self.notes / ".git").exists())

    def test_existing_post_commit_hook_is_appended_not_replaced(self):
        self.notes.mkdir()
        subprocess.run(["git", "init", "-q", str(self.notes)], check=True)
        hook = self.notes / ".git/hooks/post-commit"
        hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        self.run_install("gbrain")
        text = self.read(hook)
        self.assertTrue(text.startswith("#!/bin/sh\necho mine\n"))
        self.assertIn("notes-sync.sh", text)

    def test_notes_sync_noop_when_disabled_or_missing_gbrain(self):
        self.run_install("gbrain")
        sync = self.claude / "notes-kit/notes-sync.sh"
        e = {"HOME": str(self.home), "PATH": "/usr/bin:/bin"}
        r = subprocess.run(["/bin/zsh", str(sync)], env=dict(e, NOTES_NO_SYNC="1"), capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.claude / "notes-kit/logs").exists())
        r = subprocess.run(["/bin/zsh", str(sync)], env=e, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        logs = list((self.claude / "notes-kit/logs").glob("sync-*.log"))
        self.assertIn("gbrain 없음", self.read(logs[0]))
        self.assertFalse((self.claude / "notes-kit/.sync.lock").exists())   # 잠금이 남지 않는다


STUB_OLLAMA = """#!/bin/sh
# 실물처럼 줄마다 내보낸다 — 앞에서 grep -q 가 끝나면 뒤 줄에서 SIGPIPE 를 맞는다
[ "$1" = list ] || exit 1
echo "NAME              ID              SIZE      MODIFIED"
echo "bge-m3:latest     790764642607    1.2 GB    3 weeks ago"
sleep 0.3
echo "other:latest      000000000000    4.7 GB    4 months ago"
"""
STUB_GBRAIN = """#!/bin/sh
echo "gbrain $*" >> "$HOME/calls.log"
case "$1 $2" in
  "init "*) mkdir -p "$HOME/.gbrain" && echo '{}' > "$HOME/.gbrain/config.json" ;;
  "sources add") echo "$3" > "$HOME/.gbrain/sources" ;;
  "sources list") echo "default 0"; sleep 0.3; [ -e "$HOME/.gbrain/sources" ] && echo "$(cat "$HOME/.gbrain/sources") 2" ;;
esac
exit 0
"""
STUB_CLAUDE = """#!/bin/sh
echo "claude $*" >> "$HOME/calls.log"
case "$1 $2" in
  "mcp get") [ -e "$HOME/.mcp-gbrain" ] ;;
  "mcp add") touch "$HOME/.mcp-gbrain" ;;
esac
"""


class GbrainWithTools(unittest.TestCase):
    """선행 도구가 있을 때의 한 번짜리 설정 — 실물 대신 stub 으로 호출 순서·인자·재실행 안전만 본다."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="kittest-gb-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.bin = self.home / "stubbin"
        self.bin.mkdir()
        for name, body in (("ollama", STUB_OLLAMA), ("gbrain", STUB_GBRAIN), ("claude", STUB_CLAUDE)):
            p = self.bin / name
            p.write_text(body, encoding="utf-8")
            p.chmod(0o755)
        notes = self.home / "notes"
        notes.mkdir()
        subprocess.run(["git", "init", "-q", str(notes)], check=True)

    def run_install(self, *args):
        e = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin", "LANG": "en_US.UTF-8"}
        r = subprocess.run(["/bin/zsh", INSTALL, *args], capture_output=True, text=True, env=e, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def calls(self):
        p = self.home / "calls.log"
        return p.read_text().splitlines() if p.exists() else []

    def test_first_run_inits_registers_and_connects(self):
        code, out = self.run_install("gbrain")
        self.assertEqual(code, 0, out)
        self.assertNotIn("임베딩 모델이 없다", out)     # SIGPIPE 오판 회귀 방지
        c = self.calls()
        init = [x for x in c if x.startswith("gbrain init")]
        self.assertEqual(len(init), 1)
        self.assertIn("--pglite", init[0])
        self.assertIn("ollama:bge-m3", init[0])
        self.assertIn(f"gbrain sources add notes --path {self.home}/notes --name notes", c)
        self.assertIn(f"claude mcp add gbrain -s user -- {self.bin}/gbrain serve", c)
        self.assertTrue(any(x.startswith("gbrain sync --source notes") for x in c))   # 첫 동기화

    def test_rerun_does_not_reinit_or_readd(self):
        self.run_install("gbrain")
        (self.home / "calls.log").unlink()
        code, out = self.run_install("gbrain")
        self.assertEqual(code, 0, out)
        c = self.calls()
        self.assertFalse([x for x in c if x.startswith(("gbrain init", "gbrain sources add", "claude mcp add"))], c)
        self.assertIn("same    gbrain 소스 notes", out)            # sources list 도 SIGPIPE 오판 없이
        self.assertIn("same    claude MCP gbrain", out)

    def test_existing_brain_is_left_alone(self):
        (self.home / ".gbrain").mkdir()
        (self.home / ".gbrain/config.json").write_text("{}")
        code, out = self.run_install("gbrain")
        self.assertEqual(code, 0, out)
        self.assertIn("기존 gbrain 브레인", out)
        self.assertFalse([x for x in self.calls() if x.startswith(("gbrain init", "gbrain sources add"))])

    def test_missing_embedding_model_stops_before_init(self):
        (self.bin / "ollama").write_text("#!/bin/sh\necho NAME ID\n")
        code, out = self.run_install("gbrain")
        self.assertEqual(code, 0, out)
        self.assertIn("ollama pull bge-m3", out)
        self.assertFalse([x for x in self.calls() if x.startswith("gbrain init")])


if __name__ == "__main__":
    unittest.main()
