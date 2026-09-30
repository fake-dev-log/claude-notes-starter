#!/usr/bin/env python3
"""큐 착수 표시(claim) — 여러 Claude Code 세션이 /next 에서 같은 항목을 집지 않게 한다.

    claim.py show <프로젝트> | --all       큐 절을 착수 상태와 함께 보여 준다 (▶ 지금 · ✋ 내가 착수 · 🔒 다른 세션 · ⏳ 게이트)
    claim.py claim <프로젝트> <항목> [--force]   착수 표시. exit 3 = 다른 살아 있는 세션이 잡고 있다
    claim.py release <프로젝트> <항목> [--force] 표시 해제
    claim.py done <프로젝트> <항목>             표시 해제 + 큐에서 지울 그 줄을 출력한다 (줄은 /next 가 지운다)
    claim.py list [--json]                   살아 있는 착수 표시 전부
    claim.py key <항목 문장>                  항목 식별자(정규화 결과)

<항목> = 큐 번호 · 티켓 키 · 제목 머리(` — ` 앞). 무엇으로 주든 **지금 큐 파일**에서 그 항목을 찾아 식별자로 바꾼다 —
식별자는 번호가 아니라 키/제목 머리라서, 다른 세션이 큐를 다시 매겨도 표시가 항목을 따라간다.

설계
  - 표시는 git 이 아니라 ~/.claude/notes-kit/claims/ 의 JSON 파일이다 — 커밋이 없고 노트에 흔적이 남지 않는다.
  - 표시의 수명 = 주인 세션이 살아 있는 동안. 주인은 Bash 도구 환경의 CLAUDE_CODE_SESSION_ID · CLAUDE_PID 로 정한다.
    읽을 때마다 CLAUDE_PID 가 살아 있는지 + 그 프로세스의 시작 시각이 표시 때와 같은지 본다(PID 재사용에 속지 않게).
    죽었으면 표시는 없는 것으로 치고 지운다 — 세션을 끝내면 release 를 안 해도 풀린다. TTL 은 없다.
  - 쓰기는 claims/.lock 에 flock 을 잡고 읽고·판정하고·쓴다 — 동시에 claim 해도 하나만 이긴다.
exit: 0 · 1 인자·항목 오류 · 2 큐 파일 없음 · 3 남이 착수 중 · 4 세션 신원 없음(Claude Code 밖)
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
KIT = HOME / ".claude" / "notes-kit"
CLAIMS = KIT / "claims"
SESSIONS = HOME / ".claude" / "sessions"
KEY_HEAD = re.compile(r"^([A-Za-z][A-Za-z0-9]*-\d+)(?=$|[\s:·,)(])")
ITEM = re.compile(r"^(\d+)\.\s+(.*)$")
GATE = re.compile(r"⏰\s*(\d{2})-(\d{2})")


class Fail(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------- 항목

def norm(text):
    """티켓 키가 앞에 있으면 키(대문자), 없으면 제목 머리(` — ` 앞, 공백 정규화, 대소문자 무시)."""
    s = unicodedata.normalize("NFC", text or "").strip()
    s = re.sub(r"^\d+\.\s+", "", s)
    s = re.sub(r"\*\*|`", "", s)
    s = re.sub(r"^\[(진행|이월|완료)\]\s*", "", s).strip()
    m = KEY_HEAD.match(s)
    if m:
        return m.group(1).upper()
    s = re.split(r"\s+[—–]\s+", s, maxsplit=1)[0]
    s = re.sub(r"\s*⏰.*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        raise Fail(1, "항목이 비었다 — 번호·티켓 키·제목 머리 중 하나를 준다")
    return s.casefold()


def queue_path():
    if os.environ.get("NOTES_QUEUE"):
        return Path(os.environ["NOTES_QUEUE"]).expanduser()
    p = KIT / "notes-path"
    notes = Path(p.read_text().strip()) if p.exists() and p.read_text().strip() else HOME / "notes"
    return notes / "queue.md"


def sections(text):
    """## 헤딩 → [(번호, 줄 원문)] (번호 항목만. 불릿·인용·빈 줄은 뺀다)"""
    out, cur = {}, None
    for ln in text.splitlines():
        m = re.match(r"^## (.+?)\s*$", ln)
        if m:
            cur = m.group(1).strip()
            out.setdefault(cur, [])
            continue
        if cur is not None:
            im = ITEM.match(ln)
            if im:
                out[cur].append((int(im.group(1)), ln))
    return out


def read_queue():
    p = queue_path()
    try:
        return sections(p.read_text(encoding="utf-8"))
    except OSError:
        raise Fail(2, f"큐 파일이 없다: {p}")


def resolve(project, arg):
    """(식별자, 큐 줄) — 번호·키·제목 머리로 지금 큐에서 항목 하나를 찾는다."""
    secs = read_queue()
    if project not in secs:
        raise Fail(1, f"큐에 '## {project}' 절이 없다 (있는 절: {', '.join(secs) or '없음'})")
    items = secs[project]
    if arg.strip().isdigit():
        hit = [ln for n, ln in items if n == int(arg)]
    else:
        want = norm(arg)
        hit = [ln for _, ln in items if norm(ln) == want]
    if not hit:
        raise Fail(1, f"'## {project}' 에서 '{arg}' 항목을 못 찾았다 — /next 로 지금 큐를 다시 본다")
    if len(hit) > 1:
        raise Fail(1, f"'{arg}' 에 맞는 항목이 {len(hit)}개다 — 티켓 키나 더 긴 제목 머리를 준다")
    return norm(hit[0]), hit[0]


def gate_of(line, today):
    """줄의 첫 ⏰ MM-DD 가 오늘 뒤면 그 날짜, 아니면 None. 6개월 넘게 앞이면 작년 날짜로 본다."""
    m = GATE.search(line)
    if not m:
        return None
    try:
        d = dt.date(today.year, int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None
    if (d - today).days > 183:
        d = d.replace(year=d.year - 1)
    return d if d > today else None


# ---------------------------------------------------------------- 세션

def proc_start(pid):
    try:
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                           timeout=5, env=dict(os.environ, LC_ALL="C"))
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def alive(pid, started):
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    except (TypeError, ValueError):
        return False
    now = proc_start(pid)
    return started is None or now is None or now == started   # 시작 시각이 다르면 PID 가 재사용된 것


def me():
    sid, pid = os.environ.get("CLAUDE_CODE_SESSION_ID"), os.environ.get("CLAUDE_PID")
    if not sid or not pid or not pid.isdigit():
        raise Fail(4, "세션 신원이 없다(CLAUDE_CODE_SESSION_ID·CLAUDE_PID) — Claude Code 세션의 Bash 도구에서 부른다")
    return {"session": sid, "pid": int(pid), "started": proc_start(pid), "name": session_name(pid, sid)}


def session_name(pid, sid):
    try:
        d = json.loads((SESSIONS / f"{pid}.json").read_text())
        if d.get("name"):
            return d["name"]
    except (OSError, ValueError):
        pass
    return f"{Path(os.getcwd()).name or 'session'}-{sid[:4]}"


# ---------------------------------------------------------------- 저장

class Store:
    def __enter__(self):
        CLAIMS.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(CLAIMS / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)

    @staticmethod
    def path(project, key):
        return CLAIMS / (hashlib.sha1(f"{project}\0{key}".encode()).hexdigest()[:20] + ".json")

    def get(self, project, key):
        """살아 있는 표시만. 주인이 죽은 표시는 지우고 None."""
        p = self.path(project, key)
        try:
            c = json.loads(p.read_text())
        except (OSError, ValueError):
            return None
        if not alive(c.get("pid"), c.get("started")):
            p.unlink(missing_ok=True)
            return None
        return c

    def put(self, c):
        p = self.path(c["project"], c["key"])
        if os.environ.get("CLAIM_TEST_RACE_SLEEP"):   # 테스트 전용 — 판정과 쓰기 사이를 벌려 경합을 재현한다
            time.sleep(float(os.environ["CLAIM_TEST_RACE_SLEEP"]))
        tmp = p.with_suffix(f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(c, ensure_ascii=False))
        os.replace(tmp, p)

    def drop(self, project, key):
        self.path(project, key).unlink(missing_ok=True)

    def all(self):
        out = []
        for p in sorted(CLAIMS.glob("*.json")):
            try:
                c = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            if alive(c.get("pid"), c.get("started")):
                out.append(c)
            else:
                p.unlink(missing_ok=True)
        return out


def ago(ts):
    m = int((time.time() - ts) // 60)
    return f"{m}분 전" if m < 60 else f"{m // 60}시간 전"


# ---------------------------------------------------------------- 명령

def cmd_claim(project, arg, force=False):
    who = me()
    key, line = resolve(project, arg)
    with Store() as st:
        cur = st.get(project, key)
        if cur and cur["session"] == who["session"]:
            print(f"이미 내 착수: {line}")
            return 0
        if cur and not force:
            raise Fail(3, f"🔒 {cur['name']} 가 착수 중({ago(cur['at'])}) — 다른 항목을 고른다. "
                          f"그 세션이 끝난 게 확실할 때만 --force")
        st.put({"project": project, "key": key, "line": line, "session": who["session"], "pid": who["pid"],
                "started": who["started"], "name": who["name"], "at": time.time()})
    print(f"✋ 착수: {line}" + (f"  (뺏음: {cur['name']})" if cur else ""))
    return 0


def cmd_release(project, arg, force=False, done=False):
    who = me()
    try:
        key, line = resolve(project, arg)
    except Fail as e:
        if not done or e.code != 1:
            raise
        key, line = norm(arg), None           # done: 줄이 이미 지워졌으면 표시만 푼다
    with Store() as st:
        cur = st.get(project, key)
        if cur and cur["session"] != who["session"] and not force:
            raise Fail(3, f"🔒 {cur['name']} 의 착수다 — 내 것이 아니면 풀지 않는다(확실하면 --force)")
        st.drop(project, key)
    if done:
        print(line if line else f"(큐에 '{arg}' 줄이 이미 없다 — 표시만 풀었다)")
    else:
        print(f"해제: {line}")
    return 0


def cmd_show(project=None, all_=False):
    secs = read_queue()
    today = dt.date.today()
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    with Store() as st:
        claims = {(c["project"], c["key"]): c for c in st.all()}
    names = [n for n in secs if n != "보류"] if all_ else [project]
    if not all_ and project not in secs:
        raise Fail(1, f"큐에 '## {project}' 절이 없다 (있는 절: {', '.join(secs) or '없음'})")
    for name in names:
        rows, now_pick, gates = [], None, []
        for _, ln in secs[name]:
            c = claims.get((name, norm(ln)))
            g = gate_of(ln, today)
            if c and c["session"] == sid:
                rows.append(f"✋ {ln}  (내가 착수)")
            elif c:
                rows.append(f"🔒 {ln}  ({c['name']}, {ago(c['at'])})")
            elif g:
                rows.append(f"⏳ {ln}")
                gates.append((g, ln))
            else:
                if now_pick is None:
                    now_pick = ln
                rows.append(f"   {ln}")
        if all_:
            print(f"## {name}")
            print(f"▶ 지금  {now_pick}" if now_pick else "▶ 지금  없음")
            if gates:
                g, ln = min(gates)
                print(f"⏳ 가장 이른 게이트 {g:%m-%d}  {ln}")
            print()
            continue
        print(f"▶ 지금  {now_pick}" if now_pick else "▶ 지금  없음 — 전부 착수 중·게이트 전이거나 절이 비었다")
        print("\n".join(rows) if rows else "(번호 항목 0개)")
    return 0


def cmd_list(as_json=False):
    with Store() as st:
        cs = st.all()
    if as_json:
        print(json.dumps(cs, ensure_ascii=False))
    else:
        for c in cs:
            print(f"{c['project']}\t{c['line']}\t{c['name']}\t{ago(c['at'])}")
    return 0


def main(argv):
    force = "--force" in argv
    args = [a for a in argv if a not in ("--force", "--json", "--all")]
    try:
        if not args:
            print(__doc__, file=sys.stderr)
            return 1
        op = args[0]
        if op == "show":
            if "--all" in argv:
                return cmd_show(all_=True)
            if len(args) != 2:
                raise Fail(1, "사용: claim.py show <프로젝트> | --all")
            return cmd_show(args[1])
        if op in ("claim", "release", "done"):
            if len(args) < 3:
                raise Fail(1, f"사용: claim.py {op} <프로젝트> <번호|키|제목 머리>")
            project, arg = args[1], " ".join(args[2:])
            if op == "claim":
                return cmd_claim(project, arg, force)
            return cmd_release(project, arg, force, done=(op == "done"))
        if op == "list":
            return cmd_list("--json" in argv)
        if op == "key" and len(args) >= 2:
            print(norm(" ".join(args[1:])))
            return 0
        raise Fail(1, f"모르는 명령: {op}")
    except Fail as e:
        print(str(e), file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
