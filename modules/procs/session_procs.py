#!/usr/bin/env python3
"""Claude Code SessionStart/SessionEnd 프로세스 점검 — "띄운 것은 내가 끈다" 를 규칙이 아니라 장치로.

  end    세션이 끝날 때, 그 세션이 띄운 dev 서버·watcher·jest 를 회수한다(TERM → 3초 → KILL).
         귀속은 프로세스 환경변수 CLAUDE_CODE_SESSION_ID 로 한다 — Bash 도구가 자식에게 물려주고,
         고아(PPID 1)가 돼도 남는다. node 계열은 `ps -E` 로 보이지만 zsh·sleep 같은 시스템 바이너리는
         안 보인다(macOS) → 셸 무한 루프는 이 hook 으로 못 잡는다.
         DEV 패턴에 맞는 것만 죽인다 — 같은 세션 id 를 물려받았어도 스스로 끝나는 작업(동기화 스크립트 등)은
         건드리지 않는다(도중에 죽이면 잠금이 남는다).
  start  새 세션에 알린다: ① 죽은 세션(CLAUDE_PID 가 없는)이 남긴 dev 프로세스 ② CPU 50% 넘게 10분 이상 도는 내 프로세스.
         죽이지 않는다 — 어느 작업 것인지 보고 판단하는 건 세션(과 사용자) 몫이다.

왜: 긴 세션이 띄운 dev 서버·watcher 가 세션이 끝난 뒤에도 몇 시간씩 CPU 를 먹는 일이 반복됐다.
    포트가 비어 있어도 감시자(부모 프로세스)는 포트를 안 잡아서 "정리 완료"로 착각하기 쉽다.
실패해도 exit 0 (fail-open) — 오류는 ~/.claude/logs/session_procs.log.
테스트: python3 -m unittest discover -s tests -v  (repo 루트)
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

LOG = Path.home() / ".claude" / "logs" / "session_procs.log"
DEV = re.compile(
    r"\bvite\b|\bnest(?:\.js)?\s+start\b|--watch\b|\bjest\b|\bjest-worker\b|webpack(?:-dev-server)?\s+serve"
    r"|\bnext\s+dev\b|\bnodemon\b|\bts-node-dev\b|\btsx\s+watch\b|\bstorybook\b|\bhttp-server\b|\blive-server\b"
    r"|\b(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:dev|start:dev|serve)\b|\bdev:(?:api|web|server|client)\b")
ENV_SID = re.compile(r"\bCLAUDE_CODE_SESSION_ID=([\w-]+)")
ENV_PID = re.compile(r"\bCLAUDE_PID=(\d+)")


def log(msg):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(f"{time.strftime('%F %T')} {msg}\n")
    except Exception:
        pass


def ps(*args):
    return subprocess.run(["ps", *args], capture_output=True, text=True, timeout=10).stdout


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def dev_candidates():
    """내 uid 의 DEV 패턴 프로세스 → [(pid, etime, command)]
    SESSION_PROCS_TEST_MARKER 가 있으면 그 문자열이 든 프로세스만 본다 — 테스트(특히 세션 필터를 지운 변이)가
    실제 다른 세션의 dev 서버를 죽이지 못하게 하는 울타리다. hook 실행 환경에는 이 변수가 없다."""
    marker = os.environ.get("SESSION_PROCS_TEST_MARKER")
    out = []
    for line in ps("-U", str(os.getuid()), "-o", "pid=,etime=,command=", "-ww").splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and DEV.search(parts[2]) and (not marker or marker in parts[2]):
            out.append((int(parts[0]), parts[1], parts[2]))
    return out


def env_of(pid):
    """(session_id, claude_pid) — 환경이 안 보이면 (None, None)"""
    txt = ps("-E", "-ww", "-o", "command=", "-p", str(pid))
    s, p = ENV_SID.search(txt), ENV_PID.search(txt)
    return (s.group(1) if s else None, int(p.group(1)) if p else None)


def cwd_of(pid):
    try:
        out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                             capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"^n(.+)$", out, re.M)
        return m.group(1) if m else "?"
    except Exception:
        return "?"


def short(cmd, n=90):
    cmd = re.sub(r"\s+", " ", cmd)
    return cmd if len(cmd) <= n else cmd[:n] + "…"


def reap(session_id, grace=3.0):
    me = {os.getpid(), os.getppid()}
    targets = [(pid, cmd) for pid, _, cmd in dev_candidates()
               if pid not in me and env_of(pid)[0] == session_id]
    for pid, cmd in targets:
        try:
            os.kill(pid, signal.SIGTERM)
            log(f"TERM {session_id[:8]} pid={pid} {short(cmd)}")
        except ProcessLookupError:
            pass
    deadline = time.time() + grace
    while time.time() < deadline and any(alive(p) for p, _ in targets):
        time.sleep(0.2)
    killed = []
    for pid, cmd in targets:
        if alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
                log(f"KILL {session_id[:8]} pid={pid} (TERM 무시)")
            except ProcessLookupError:
                pass
        killed.append(pid)
    return killed


def report():
    lines = []
    for pid, etime, cmd in dev_candidates():
        sid, cpid = env_of(pid)
        if cpid and not alive(cpid):
            lines.append(f"- pid {pid} · {etime} · 세션 {sid[:8] if sid else '?'}(종료됨) · cwd {cwd_of(pid)} · {short(cmd)}")
    hot = []
    for line in ps("-U", str(os.getuid()), "-o", "pid=,pcpu=,etime=,command=", "-ww").splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        pid, pcpu, etime, cmd = int(parts[0]), float(parts[1]), parts[2], parts[3]
        long_run = "-" in etime or etime.count(":") == 2 or (etime.count(":") == 1 and int(etime.split(":")[0]) >= 10)
        if pcpu > 50 and long_run and pid != os.getpid():
            hot.append(f"- pid {pid} · CPU {pcpu:.0f}% · {etime} · {short(cmd)}")
    out = []
    if lines:
        out.append(f"[session_procs] 종료된 Claude 세션이 남긴 dev 프로세스 {len(lines)}개:\n" + "\n".join(lines[:10]))
    if hot:
        out.append(f"[session_procs] CPU 50% 넘게 10분 이상 도는 내 프로세스 {len(hot)}개:\n" + "\n".join(hot[:10]))
    if out:
        out.append("이 세션 워크스페이스 것이면 회수하고(`ps -p <pid> -o args=` 로 확인 후 그 PID 만), "
                   "다른 워크스페이스 것이면 건드리지 말고 사용자에게 보고한다.")
    return "\n\n".join(out)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    try:
        if mode == "end":
            sid = data.get("session_id")
            if sid:
                n = reap(sid)
                if n:
                    log(f"END {sid[:8]} reason={data.get('reason')} 회수 {len(n)}개")
        elif mode == "start":
            ctx = report()
            if ctx:
                log(f"START {str(data.get('session_id'))[:8]} 보고:\n{ctx}")
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                         "additionalContext": ctx}}, ensure_ascii=False))
    except Exception as e:                            # fail-open
        log(f"ERROR {mode}: {e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
