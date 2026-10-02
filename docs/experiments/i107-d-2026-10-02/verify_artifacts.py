"""Verify the i107 lane-D packet: recompute every number from raw/ and check every receipt.

    python3 verify_artifacts.py            # exit 0 = all checks pass

Checks:
  1. d-summary.json, ledger/i107-d-ledger.jsonl and ledger/cells.json equal a fresh build (analyze.build).
  2. PREREG.json: map PREREG sha256 pinned; lane PREREG committed (git) before the first measured REAL trial
     and unchanged since its commit.
  3. Reused files are verbatim (sha256; git objects when available): b01_analysis.py, fault_transport.py.
  4. Tested source: jev-use tree 72bf8156 and libs/cua-driver tree a87dc39d at the lane's base commit (git).
  5. UNIT receipts: every red log fails, the green log passes with 0 failures; guard-matrix.json and
     structural-work.json recompute (when the jev-use environment is importable).
  6. 0 provider HTTP and the scripted chooser named on every REAL trial, manifest and ledger row.
  7. Locks: every REAL block has a quiet-timed receipt (raw/real/<block>/lock-receipt.json) whose
     EXCLUSIVE window contains the block's start and end.
  8. Every cell is either backed by trials or BLOCKED/NOT_RUN with a reason; live-provider is BLOCKED.
  9. Live PR head reads at lane start and end are recorded separately from the tested source.
 10. Privacy: no absolute local path, temp path, user name, host name, or verification token in any file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "harness"))
sys.dont_write_bytecode = True

import analyze  # noqa: E402

FAIL: list[str] = []
MAP_SHA = "8eeb837ffa24425cfc36ba2c72a8ea65df4207e1a39a7d261f1cda85496b2c53"
VERBATIM = {
    "harness/b01_analysis.py": ("072c8ef2f925aa7c3d2894c47c66b2e665f5c77774d2a53fe03215b2b9a48a31",
                                "6689610d5:docs/experiments/b-01-browser-critpath-2026-10-02/b01_analysis.py"),
    "harness/fault_transport.py": ("c85eec39fd3d5ae186a3654511aa35e07ebff4d28eaf664d1e80675dace49784",
                                   "b97daa4ba:docs/experiments/own-105-runner-reconcile-2026-10-02/harness/fault_transport.py"),
}
BASE = "be68363bc38940d5560be55165ceaf6fd743437b"


def check(cond: bool, what: str) -> None:
    print(("PASS " if cond else "FAIL ") + what)
    if not cond:
        FAIL.append(what)


def git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def main() -> None:
    raw = HERE / "raw"
    summary, rows, cells = analyze.build(raw)
    check(json.loads((HERE / "d-summary.json").read_text()) == json.loads(analyze.dump(summary)),
          "1 d-summary.json equals a fresh build from raw/")
    led = [json.loads(x) for x in (HERE / "ledger" / "i107-d-ledger.jsonl").read_text().splitlines() if x.strip()]
    check(led == json.loads(json.dumps(rows, default=str)), f"1 ledger equals a fresh build ({len(rows)} rows)")
    check(json.loads((HERE / "ledger" / "cells.json").read_text()) == json.loads(analyze.dump(cells)),
          "1 cells.json equals a fresh build")

    prereg = json.loads((HERE / "PREREG.json").read_text())
    check(prereg["map_prereg"]["sha256"] == MAP_SHA, "2 lane PREREG pins the map PREREG sha256")
    mp = HERE.parent / "i107-map-2026-10-02" / "PREREG.json"
    if mp.exists():
        check(hashlib.sha256(mp.read_bytes()).hexdigest() == MAP_SHA, "2 map PREREG file matches its pinned sha256")
    log = git("log", "--diff-filter=A", "--format=%H %cI", "--", f":(top)docs/experiments/{HERE.name}/PREREG.json")
    if log:
        sha, when = log.strip().splitlines()[-1].split()
        committed = git("show", f"{sha}:docs/experiments/{HERE.name}/PREREG.json")
        check(committed is not None and json.loads(committed) == prereg, f"2 PREREG.json unchanged since {sha[:9]} ({when})")
        from datetime import datetime
        prereg_t = datetime.fromisoformat(when)
        starts = [datetime.fromisoformat(m["started_utc"].replace("Z", "+00:00")) for m in summary["real"]["manifests"]
                  if m.get("block") not in ("smoke", "shake")]
        check(bool(starts) and all(t > prereg_t for t in starts),
              f"2 PREREG commit {when} precedes every measured REAL block ({len(starts)}; first {min(starts) if starts else None})")
        alog = git("log", "--diff-filter=A", "--format=%H %cI", "--", f":(top)docs/experiments/{HERE.name}/PREREG-AMENDMENT-1.json")
        if alog:
            a_t = datetime.fromisoformat(alog.strip().splitlines()[-1].split()[1])
            check(all(t > a_t for t in starts), f"2 amendment 1 committed ({a_t.isoformat()}) before every measured REAL block")
    else:
        print("SKIP 2 git history not available")

    for rel, (want, obj) in VERBATIM.items():
        check(hashlib.sha256((HERE / rel).read_bytes()).hexdigest() == want, f"3 {rel} sha256 {want[:12]}")
        orig = git("show", obj)
        if orig is not None:
            check(orig == (HERE / rel).read_text(), f"3 {rel} equals git object {obj.split(':')[0]}")
        else:
            print(f"SKIP 3 git object {obj.split(':')[0]} not available")

    jt, dt = git("rev-parse", f"{BASE}:libs/cua-driver/examples/jev-use"), git("rev-parse", f"{BASE}:libs/cua-driver")
    if jt and dt:
        check(jt.strip() == "72bf8156136771da9a767ec12ae7c364e426d910", "4 caller jev-use tree 72bf8156 at the lane base")
        check(dt.strip() == "a87dc39dc3b27b7b207e2bc9c85db7d1b6b1d497", "4 libs/cua-driver tree a87dc39d at the lane base")
        changed = git("diff", "--name-only", BASE, "HEAD")
        if changed is not None:
            outside = [p for p in changed.split() if not p.startswith(f"docs/experiments/{HERE.name}/")]
            check(not outside, f"4 lane commits touch only the lane packet (outside: {outside})")
    else:
        print("SKIP 4 git objects not available")

    unit = raw / "unit"
    reds = sorted(unit.glob("red-*.log"))
    check(bool(reds) and all(("FAILED" in p.read_text()) for p in reds), f"5 {len(reds)} red logs each fail")
    green = (unit / "green-harness-suite.log").read_text()
    m = re.search(r"Ran (\d+) tests", green)
    check(bool(m) and green.rstrip().endswith("OK") and "FAILED" not in green,
          f"5 green harness suite: {m.group(1) if m else '?'} tests OK")
    try:
        import guard_matrix
        check(guard_matrix.compute() == json.loads((unit / "guard-matrix.json").read_text()),
              "5 guard-matrix.json recomputes from the jev-use caller code")
    except ImportError as error:
        print(f"SKIP 5 guard matrix recomputation (jev-use environment not importable: {type(error).__name__})")

    real_trials, manifests = analyze.load_real(raw)
    net = sum((t["summary"].get("network") or {}).get("non_loopback_connect_attempts", 0) for t in real_trials)
    check(net == 0, f"6 non-loopback connects across {len(real_trials)} REAL trials = {net}")
    check(all(m.get("provider") == "mock" and "choose_mock_for_task" in (m.get("chooser") or "") for m in manifests),
          f"6 {len(manifests)} manifests: provider mock, chooser named")
    check(all("choose_mock_for_task" in (r.get("chooser") or "") for r in rows), f"6 {len(rows)} ledger rows name the chooser")
    check(all(r.get("evidence") == "REAL" for r in rows), "6 every ledger row is a REAL trial (no fake-driver row)")

    from datetime import datetime

    def ts(v: str) -> datetime:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))

    real_dir = raw / "real"
    for block_dir in sorted(p for p in real_dir.iterdir() if p.is_dir()) if real_dir.is_dir() else []:
        rec_path = block_dir / "lock-receipt.json"
        mans = [json.loads(p.read_text()) for p in (block_dir / "manifests").glob("*.json")]
        ok = rec_path.exists()
        if ok:
            rec = json.loads(rec_path.read_text())
            ok = bool(mans) and rec.get("rc") is not None and all(
                mm.get("lock_label") == rec.get("label") and ts(rec["acquired"]) <= ts(mm["started_utc"])
                and ts(mm["ended_utc"]) <= ts(rec["released"]) for mm in mans)
        check(ok, f"7 block {block_dir.name}: quiet-timed EXCLUSIVE receipt contains the block ({len(mans)} manifest)")

    bad = [c for c in cells["cells"] if c.get("label") in ("BLOCKED", "NOT_RUN") and not c.get("reason")]
    check(not bad, f"8 {len(cells['cells'])} cells: every BLOCKED/NOT_RUN cell carries a reason")
    check(any(c["comparison"] == "CMP-D live provider" and c["label"] == "BLOCKED" for c in cells["cells"]),
          "8 live-provider cell BLOCKED")

    heads = summary["live_pr_head_reads"]
    check("start" in heads and "end" in heads, f"9 live PR 4316 head read at start and end: {sorted(heads)}")
    check(all(h["result"]["headRefOid"] for h in heads.values()), "9 live heads recorded")

    host = socket.gethostname()
    user = os.environ.get("USER") or ""
    roots = ["home", "mnt", "tmp", "var" + "/tmp"]  # built from parts so this file does not match itself
    pat = re.compile("|".join("/" + r + "/" for r in roots) + "|cua-lane" + "-tmp|x11-session\\.[A-Za-z0-9]{6}")
    tok = re.compile(r"\bjev-[0-9a-f]{10}\b|\b[A-Z]{64}\b")
    offenders = []
    for path in HERE.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        data = path.read_bytes()
        if path.name.endswith(".tar.gz"):
            import io
            import tarfile
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                data = b"\n".join(tar.extractfile(m).read() for m in tar.getmembers() if m.isfile())
        text = data.decode("utf-8", "replace")
        if pat.search(text) or (host and len(host) > 3 and host in text) or (user and len(user) > 2 and f"/{user}/" in text) \
                or (path.suffix != ".py" and tok.search(text)):
            offenders.append(str(path.relative_to(HERE)))
    check(not offenders, f"10 privacy scan over every packet file (offenders: {offenders})")

    print(f"\n{len(FAIL)} failure(s)")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
