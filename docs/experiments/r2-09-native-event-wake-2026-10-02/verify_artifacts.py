#!/usr/bin/env python3
"""R2-09 packet verifier (stdlib only; run from anywhere inside the repo).

Checks:
 1. PREREG.json was committed before the first measured trial and is unchanged
    since that commit; the measurement commit is an ancestor of HEAD and is
    the only libs/ change on the branch since the N-01R base.
 2. Every packet file and every raw/ path the README cites is tracked in git.
 3. Every measured block's meta row names the Driver sha256 recorded in
    provenance.json, and every block ran under a quiet-lane lock receipt
    (raw/lock-ledger.jsonl).
 4. analyze.py re-run on raw/ reproduces r209-summary.json exactly.
 5. Every number listed in README_NUMBERS.json (path into the summary +
    value) equals the summary value and is quoted in the README.
 6. Privacy: no absolute local path, user name or host name in any packet
    file (derived at run time, never hard-coded).
"""

from __future__ import annotations

import gzip
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAIL: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, check=False).stdout.strip()


def rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def main() -> None:
    prov = json.loads((HERE / "provenance.json").read_text(encoding="utf-8"))
    rel = HERE.relative_to(Path(git("rev-parse", "--show-toplevel")))
    # 1. pre-registration order
    prereg_sha = prov["prereg_commit"]["sha"]
    prereg_time = datetime.fromisoformat(git("show", "-s", "--format=%cI", prereg_sha))
    first_ns = None
    measured = sorted(p for p in (HERE / "raw").glob("r209-*/trials.jsonl.gz"))
    for path in measured:
        for r in rows(path):
            if r.get("event") == "trial" and r.get("w_begin"):
                first_ns = r["w_begin"] if first_ns is None else min(first_ns, r["w_begin"])
    first = datetime.fromtimestamp(first_ns / 1e9, tz=timezone.utc) if first_ns else None
    check(first is not None and prereg_time < first,
          f"PREREG commit {prereg_sha[:9]} ({prereg_time.isoformat()}) precedes the first measured trial ({first})")
    diff = subprocess.run(["git", "diff", "--quiet", prereg_sha, "HEAD", "--", str(rel / "PREREG.json")],
                          cwd=HERE).returncode
    check(diff == 0, "PREREG.json unchanged since its commit")
    mc = prov["measurement_commit"]
    check(subprocess.run(["git", "merge-base", "--is-ancestor", mc, "HEAD"], cwd=HERE).returncode == 0,
          f"measurement commit {mc[:9]} is an ancestor of HEAD")
    libs = git("diff", "--name-only", prov["base_commit"], "HEAD", "--", ":(top)libs")
    check(libs.splitlines() == ["libs/cua-driver/rust/crates/platform-linux/src/atspi/native.rs"],
          f"only native.rs changed under libs/ since the base ({libs.splitlines()})")
    libs_after = git("diff", "--name-only", mc, "HEAD", "--", ":(top)libs")
    check(libs_after == "", "no libs/ change after the measurement commit")
    # 2. tracked files
    tracked = set(git("ls-files", "--full-name", ".").splitlines())
    for p in sorted(HERE.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            r = str(p.relative_to(HERE.parent.parent.parent))
            check(r in tracked, f"tracked: {p.relative_to(HERE)}") if r not in tracked else None
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    cited = set(re.findall(r"`(raw/[^`\s]+)`", readme))
    for c in sorted(cited):
        prefix = re.split(r"[<*]", c)[0]
        hits = [t for t in tracked if t.startswith(str(rel / prefix)) or (prefix.endswith("/") and t.startswith(str(rel) + "/" + prefix))]
        check(bool(hits), f"README-cited path tracked: {c}")
    untracked = [str(p.relative_to(HERE)) for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                 and str(p.relative_to(HERE.parent.parent.parent)) not in tracked]
    check(not untracked, f"every packet file tracked ({len(untracked)} untracked: {untracked[:5]})")
    # 3. driver sha + lock receipts
    ledger = [json.loads(x) for x in (HERE / "raw" / "lock-ledger.jsonl").read_text().splitlines() if x.strip()]
    receipts = {x["label"]: x for x in ledger}
    groups = {}
    gpath = HERE / "raw" / "groups.jsonl"
    for x in (json.loads(y) for y in gpath.read_text().splitlines() if y.strip()) if gpath.exists() else []:
        if "blocks" in x:
            groups[x["group"]] = x["blocks"].split()

    def iso_ns(s: str) -> int:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1e9)

    for path in measured:
        trial_rows = list(rows(path))
        meta = next(r for r in trial_rows if r.get("event") == "meta")
        check(meta.get("driver_sha256") == prov["driver"]["sha256"], f"{path.parent.name}: driver sha256")
        label = path.parent.name
        receipt = receipts.get(f"r2-09-{label}")
        if receipt is None:
            block = meta.get("block")
            receipt = next((receipts.get(f"r2-09-r209-group-{g}") for g, bs in groups.items() if block in bs
                            and receipts.get(f"r2-09-r209-group-{g}")), None)
        inside = False
        if receipt:
            t0 = min(r["w_begin"] for r in trial_rows if r.get("event") == "trial")
            t1 = max(r["w_end"] for r in trial_rows if r.get("event") == "trial")
            inside = iso_ns(receipt["acquired"]) <= t0 and t1 <= iso_ns(receipt["released"])
        check(bool(receipt) and inside, f"{label}: inside an exclusive quiet-timed receipt window")
    # 4. reproduce the summary
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        s_path, m_path = Path(tmp) / "s.json", Path(tmp) / "m.jsonl"
        measured_raw = Path(tmp) / "raw"
        measured_raw.mkdir()
        for path in measured:
            (measured_raw / path.parent.name).mkdir()
            (measured_raw / path.parent.name / path.name).symlink_to(path)
        subprocess.run([sys.executable, str(HERE / "analyze.py"), str(measured_raw), str(s_path), str(m_path)],
                       check=True, capture_output=True)
        check(json.loads(s_path.read_text()) == json.loads((HERE / "r209-summary.json").read_text()),
              "analyze.py reproduces r209-summary.json")
        with gzip.open(HERE / "r209-trial-metrics.jsonl.gz", "rt", encoding="utf-8") as stream:
            check(stream.read() == m_path.read_text(), "analyze.py reproduces r209-trial-metrics.jsonl.gz")
    # 5. README numbers present in the summary
    summary = json.loads((HERE / "r209-summary.json").read_text())
    for item in json.loads((HERE / "README_NUMBERS.json").read_text())["numbers"]:
        node = summary
        for key in item["path"]:
            node = node[key] if isinstance(node, dict) else node[int(key)]
        check(node == item["value"], f"README number {item['path']} == {item['value']} (summary {node})")
        check(str(item["value"]) in readme, f"README quotes {item['value']}") if item.get("quoted", True) else None
    # 6. privacy
    host = socket.gethostname()
    user = os.environ.get("USER") or Path.home().name
    pats = [re.compile("/" + "mnt" + r"/[A-Za-z0-9_]"), re.compile("/" + "home" + r"/[A-Za-z0-9_]"), re.compile("/" + "run/user" + r"/\d")]
    if host:
        pats.append(re.compile(r"\b" + re.escape(host) + r"\b"))
    if user:
        pats.append(re.compile(r"\b" + re.escape(user) + r"\b"))
    bad = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        data = gzip.open(p, "rt", encoding="utf-8", errors="replace").read() if p.suffix == ".gz" \
            else p.read_text(encoding="utf-8", errors="replace")

        for rx in pats:
            if rx.search(data):
                bad.append(f"{p.relative_to(HERE)}: {rx.pattern}")
    check(not bad, f"privacy scan ({bad[:5]})")
    print(f"\n{'PASS' if not FAIL else 'FAIL'}: {len(FAIL)} failed checks")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
