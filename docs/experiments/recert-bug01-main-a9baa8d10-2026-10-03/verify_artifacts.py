"""RECERT-BUG01 artifact verifier.

Checks, from the packet alone (plus git when run inside the repo):
  1. harness/ files are blob-identical to MANIFEST.json (git blob ids recomputed here);
  2. recert-bug01-summary.json == analyze_recert.py recomputed from raw/;
  3. the pre-registered gates and dispositions recompute to what the summary and README state;
  4. every Driver session-env sha256 equals the PREREG binary hashes for its arm;
  5. every measured REAL block lies inside a RECERT-BUG01 SHARED ledger window (raw/locks/ledger.jsonl),
     and the PREREG commit precedes the first measured trial (git, when available);
  6. every cited commit exists (git, when available) and the replay patch-ids match;
  7. privacy scan: no absolute local paths, host name or secret-shaped strings in the packet.
Exit 0 only when all checks pass.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import analyze_recert  # noqa: E402

FAIL: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("ok   " if ok else "FAIL ") + msg)
    if not ok:
        FAIL.append(msg)


def blob_id(p: Path) -> str:
    data = p.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def main() -> None:
    # 1 harness identity
    man = json.loads((HERE / "harness" / "MANIFEST.json").read_text())
    for f in man["files"]:
        check(blob_id(HERE / f["file"]) == f["blob"], f"blob-identical {f['file']}")

    # 2 summary recompute
    summary = json.loads((HERE / "recert-bug01-summary.json").read_text())
    re_sum = analyze_recert.main(HERE)
    check(json.loads(json.dumps(re_sum, sort_keys=True)) == summary, "summary recomputes from raw/")

    # 3 gates / dispositions
    g = re_sum["gates"]
    readme = (HERE / "README.md").read_text()
    check(f"**A: {g['A_disposition']}" in readme, f"README states A = {g['A_disposition']}")
    check(f"**B: {g['B_disposition']}" in readme, f"README states B = {g['B_disposition']}")
    a = re_sum["part_a"]
    check(f"background {a['m9']['T_mislabel']}/20" in readme or f"{a['m9']['T_mislabel']}/20" in readme, "README cites the M9 mislabel count")
    check(g["E4"]["duplicate_dispatches"] == 0 and g["E4"]["b_transport_errors"] == 0, "E4: 0 duplicate dispatches, 0 transport errors")

    # 4 binary hashes
    prereg = json.loads((HERE / "PREREG.json").read_text())
    want = {k: prereg["binaries"][k]["sha256"] for k in ("M9", "M9i", "MF9")}
    for b, key in (("m9", "M9"), ("mf9", "MF9")):
        check(a[b]["driver_sha256"] == [want[key]], f"part A {b} sha256 == PREREG {key}")
        check(re_sum["part_a_decoy"][b]["driver_sha256"] == [want[key]], f"decoy {b} sha256 == PREREG {key}")
        check(a[b]["counter_env_set"] == [False], f"part A {b}: counter variable unset")
    for name, v in re_sum["part_b"].items():
        key = "M9i" if name.startswith("m9i-") else "M9"
        check(v["driver_sha256"] == want[key], f"part B {name} sha256 == PREREG {key}")

    # 5 lock windows
    ledger = [json.loads(x) for x in (HERE / "raw" / "locks" / "ledger.jsonl").read_text().splitlines() if x.strip()]
    wins = [(ts(r["acquired"]), ts(r["released"]), r["label"]) for r in ledger if r.get("lane") == "RECERT-BUG01" and r.get("mode") == "shared"]

    def inside(t0: float, t1: float) -> bool:
        return any(w0 - 1.0 <= t0 and t1 <= w1 + 1.0 for w0, w1, _ in wins)

    blocks = []
    for p in sorted((HERE / "raw" / "part-a").glob("*/*-block-0*.json")):
        if "harness-error" in p.name:
            continue
        m = json.loads(p.read_text())
        blocks.append((m["t_start_ms"] / 1000, m["t_end_ms"] / 1000, str(p.relative_to(HERE))))
    for p in sorted((HERE / "raw" / "part-a-decoy").glob("*/session-env.json")):
        e = json.loads(p.read_text())
        blocks.append((ts(e["t_start_utc"]), ts(e["t_end_utc"]), str(p.relative_to(HERE))))
    for p in sorted((HERE / "raw" / "part-b").glob("*/calls.jsonl")):
        for line in p.read_text().splitlines():
            r = json.loads(line)
            if r.get("event") == "block":
                blocks.append((r["t_start_ms"] / 1000, r["t_end_ms"] / 1000, str(p.relative_to(HERE))))
    bad = [b for b in blocks if not inside(b[0], b[1])]
    check(bool(blocks) and not bad, f"{len(blocks)} measured blocks inside SHARED ledger windows" + (f" (outside: {bad[:3]})" if bad else ""))
    first = min(b[0] for b in blocks) if blocks else None
    pre_first = git("log", "--reverse", "--format=%H %ct", "--", "PREREG.json")
    if pre_first:
        sha, ct = pre_first.splitlines()[0].split()
        check(first is not None and int(ct) < first, f"PREREG first commit {sha[:9]} precedes the first measured block")
    else:
        print("skip PREREG-order check (no git)")

    # 6 commits + patch-ids
    if git("rev-parse", "--git-dir"):
        prov = json.loads((HERE / "provenance.json").read_text())
        for sha in prov["commits_cited"]:
            check(git("cat-file", "-e", sha + "^{commit}") is not None, f"commit exists {sha[:12]}")
        for orig, rep in prov["replays"].items():
            pa = subprocess.run(f"git -C {HERE} show {orig} | git patch-id --stable", shell=True, capture_output=True, text=True).stdout.split()
            pb = subprocess.run(f"git -C {HERE} show {rep['commit']} | git patch-id --stable", shell=True, capture_output=True, text=True).stdout.split()
            same = bool(pa) and bool(pb) and pa[0] == pb[0]
            check(same == rep["patch_id_equal"], f"patch-id {orig[:9]} vs {rep['commit'][:9]} equal={same}")
    else:
        print("skip commit checks (no git)")

    # 7 privacy
    roots = "|".join("/" + r + "/" for r in ("home", "mnt", "tmp", "root", "var/tmp"))  # built, so this file holds no literal path
    pat = re.compile("(" + roots + r"|BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
    hits = []
    import socket
    host = socket.gethostname()
    for p in sorted(HERE.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            txt = p.read_text(errors="replace")
            for m in pat.finditer(txt):
                ctx = txt[max(0, m.start() - 20): m.end() + 20]
                if "(?:home|mnt" in ctx:
                    continue
                hits.append(f"{p.relative_to(HERE)}: {m.group(0)}")
            if host and len(host) > 2 and re.search(r"\b" + re.escape(host) + r"\b", txt):
                hits.append(f"{p.relative_to(HERE)}: <host name>")
    check(not hits, "privacy scan" + (f" hits={hits[:5]}" if hits else ""))
    print("RESULT:", "PASS" if not FAIL else f"FAIL ({len(FAIL)})")
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    main()
