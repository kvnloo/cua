"""Re-verify the stack-smoke packet from its own files (stdlib only). Prints RESULT PASS|FAIL.

Checks
 1. manifest: every file listed in SHA256SUMS exists and matches.
 2. PREREG commit precedes the first measured run (git commit time vs drive ledger), when git is available.
 3. oracle independence: every run's verdict is re-derived from the fixture state files with the PREREG rule.
 4. summary regrade: harness/analyze.py over raw/ reproduces summary.json's gate verdicts and key counts.
 5. bench regrade: cold/warm stats in bench/bench_summary.json are recomputed from bench/raw/*.json.
 6. scan: no local absolute paths, host name or secret-looking strings in any packet file.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAIL: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def manifest() -> None:
    lines = (HERE / "SHA256SUMS").read_text().splitlines()
    bad = 0
    for line in lines:
        h, rel = line.split(None, 1)
        p = HERE / rel.strip()
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
            bad += 1
            print("   mismatch:", rel)
    check(bad == 0 and len(lines) > 0, f"manifest: {len(lines)} files, {bad} mismatches")


def prereg_order() -> None:
    ledger = [json.loads(x) for x in (HERE / "raw" / "drive-ledger.jsonl").read_text().splitlines() if x.strip()]
    first = min(r["started"] for r in ledger if r["run_id"].startswith("m"))
    try:
        out = subprocess.run(["git", "log", "--format=%ct", "--diff-filter=A", "--", "PREREG.json"], cwd=HERE,
                             capture_output=True, text=True, timeout=20).stdout.split()
    except Exception:
        out = []
    if not out:
        print("skip PREREG order: no git history available")
        return
    check(int(out[-1]) < first, f"PREREG committed ({out[-1]}) before first measured run ({int(first)})")


def oracle_rederive() -> None:
    n = bad = 0
    for rd in sorted((HERE / "raw" / "runs").iterdir()):
        run = json.loads((rd / "run.json").read_text())
        o = json.loads((rd / "oracle.json").read_text())
        try:
            before = json.loads((rd / "fixture" / "state.before.json").read_text())
            after = json.loads((rd / "fixture" / "state.after.json").read_text())
        except Exception:
            bad += o.get("verdict") != "unknown"
            n += 1
            continue
        if run["task"] == "gtk3":
            v = "pass" if after.get("agreed") is True and after.get("counter") == 0 and after.get("size") == "none" \
                and after.get("note_saved") is None else "fail"
        else:
            v = "pass" if after.get("submitted") == run["token"] else "fail"
        n += 1
        bad += v != o.get("verdict")
    check(bad == 0 and n > 0, f"oracle re-derived from fixture state for {n} runs, {bad} disagreements")


def regrade() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "summary.json"
        subprocess.run([sys.executable, str(HERE / "harness" / "analyze.py"), str(HERE / "raw"), str(HERE / "plan.json"),
                        str(HERE / "raw" / "drive-ledger.jsonl"), str(out)], check=True, capture_output=True, timeout=300)
        a, b = json.loads(out.read_text()), json.loads((HERE / "summary.json").read_text())
    for k in ("H1_join", "H2_persistence", "H4_fail_open"):
        check(a[k]["pass"] == b[k]["pass"], f"regrade {k}.pass == {b[k]['pass']}")
    for k in ("tool_sequence_identical", "pairs_complete", "oracle_discordant_on_only_pass", "oracle_discordant_off_only_pass"):
        check(a["H3b_paired"][k] == b["H3b_paired"][k], f"regrade H3b.{k} == {b['H3b_paired'][k]}")
    check(a["outcomes"] == b["outcomes"], "regrade outcome cells identical")
    check(a["executed"] == b["executed"] == b["planned"], f"all {b['planned']} planned runs present")


def bench() -> None:
    bs = HERE / "bench" / "bench_summary.json"
    if not bs.exists():
        print("skip bench: no bench_summary.json")
        return
    s = json.loads(bs.read_text())
    for name, row in s["backends"].items():
        if row.get("evidence") != "BENCHMARK":
            continue
        raw = json.loads((HERE / "bench" / "raw" / f"{name}.json").read_text())
        warm = [r["latency_ms"] for r in raw["rows"][1:] if r["status"] == "ok"]
        cold = raw["rows"][0].get("cold_ms_from_process_start")
        p50 = statistics.median(warm) if warm else None
        check(abs((row["warm_latency_ms_p50"] or 0) - (p50 or 0)) < 1e-6 and abs((row["cold_ms"] or 0) - (cold or 0)) < 1e-6,
              f"bench regrade {name}: cold {cold and round(cold)} ms, warm p50 {p50 and round(p50, 2)} ms (n={len(warm)})")


def scan() -> None:
    host = re.escape(socket.gethostname())  # the verifying machine's own name, never written into the packet
    pat = re.compile(r"/mnt/|/home/|/workspace/|/tmp/claude|sk-[A-Za-z0-9]{16,}|hf_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}"
                     + (f"|\\b{host}\\b" if host else ""))
    hits = []
    for p in HERE.rglob("*"):
        if p.is_file() and p.name != "verify_artifacts.py":
            t = p.read_text(encoding="utf-8", errors="replace")
            hits += [f"{p.relative_to(HERE)}: {m.group(0)}" for m in pat.finditer(t)]
    for h in hits[:20]:
        print("   ", h)
    check(not hits, f"scan: {len(hits)} local-path/host/secret hits")


if __name__ == "__main__":
    manifest()
    prereg_order()
    oracle_rederive()
    regrade()
    bench()
    scan()
    print("RESULT", "PASS" if not FAIL else "FAIL")
    sys.exit(1 if FAIL else 0)
