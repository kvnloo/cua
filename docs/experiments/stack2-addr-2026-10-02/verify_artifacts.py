"""Re-verify the stack2-addr packet from its own files (stdlib only). Prints RESULT PASS|FAIL.

Checks
 1. manifest: every file listed in SHA256SUMS exists and matches.
 2. PREREG / CONFIRM_PREREG / CONFIRM2_PREREG commits precede the first run of their sets (git commit time vs drive ledger), when git is available.
 3. oracle independence: every run's verdict is re-derived from the fixture state files with the PREREG rule.
 4. tool metrics: each run_summary.json 'tools' block is recomputed from that run's tool_calls.jsonl.
 5. summary regrade: harness/analyze.py over raw/ reproduces summary.json's gates, cells and pair tables.
 6. contract: contract/tools_list_properties.json shows element_index absent on 0.32.0 and present on 0.21.0.
 7. scan: no local absolute paths, host name or secret-looking strings in any packet file.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import socket
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


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


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
    ledger = jl(HERE / "raw" / "drive-ledger.jsonl")
    for name, prefixes in (("PREREG.json", "ml"), ("CONFIRM_PREREG.json", "c"), ("CONFIRM2_PREREG.json", "d")):
        first = min(r["started"] for r in ledger if r["run_id"][0] in prefixes)
        try:
            out = subprocess.run(["git", "log", "--format=%ct", "--diff-filter=A", "--", name], cwd=HERE,
                                 capture_output=True, text=True, timeout=20).stdout.split()
        except Exception:
            out = []
        if not out:
            print(f"skip {name} order: no git history available")
            continue
        check(int(out[-1]) < first, f"{name} committed ({out[-1]}) before its first run ({int(first)})")


def oracle_rederive() -> None:
    n = bad = 0
    for rd in sorted((HERE / "raw" / "runs").iterdir()):
        run = json.loads((rd / "run.json").read_text())
        if not (rd / "oracle.json").exists():
            n += 1
            bad += not (rd / "HARNESS_INCIDENT.txt").exists()
            continue
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


def tool_metrics() -> None:
    spec = importlib.util.spec_from_file_location("extract", HERE / "harness" / "extract.py")
    ex = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ex)
    n = bad = 0
    for rd in sorted((HERE / "raw" / "runs").iterdir()):
        s = json.loads((rd / "run_summary.json").read_text())
        rows = jl(rd / "tool_calls.jsonl")
        n += 1
        if ex.tool_metrics(rows) != s["tools"]:
            bad += 1
            print("   tools mismatch:", rd.name)
    check(bad == 0 and n > 0, f"tool metrics recomputed from tool_calls.jsonl for {n} runs, {bad} mismatches")


def regrade() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "summary.json"
        subprocess.run([sys.executable, str(HERE / "harness" / "analyze.py"), str(HERE / "raw"), str(HERE / "plan.json"),
                        str(HERE / "raw" / "drive-ledger.jsonl"), str(out)], check=True, capture_output=True, timeout=300)
        a, b = json.loads(out.read_text()), json.loads((HERE / "summary.json").read_text())
    for k in ("H1_contract", "H2_element_reach", "H4_authority", "legacy_0_21_0"):
        check(a[k]["pass"] == b[k]["pass"], f"regrade {k}.pass == {b[k]['pass']}")
    check(a["H3_task_success"] == b["H3_task_success"], "regrade H3 pair tables identical")
    check(a["cells"] == b["cells"], "regrade cells identical")
    check(a["executed"] == b["executed"] == b["planned"], f"all {b['planned']} planned runs executed")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "confirm.json"
        subprocess.run([sys.executable, str(HERE / "harness" / "analyze_confirm.py"), str(HERE / "raw"),
                        str(HERE / "plan_confirm.json"), str(HERE / "raw" / "drive-ledger.jsonl"), str(HERE / "summary.json"),
                        str(out)], check=True, capture_output=True, timeout=300)
        a, b = json.loads(out.read_text()), json.loads((HERE / "confirm_summary.json").read_text())
    check(a == b, f"regrade confirm_summary.json identical ({b['executed']}/{b['planned']} runs)")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "confirm2.json"
        subprocess.run([sys.executable, str(HERE / "harness" / "analyze_confirm.py"), str(HERE / "raw"),
                        str(HERE / "plan_confirm2.json"), str(HERE / "raw" / "drive-ledger.jsonl"), str(HERE / "summary.json"),
                        str(out)], check=True, capture_output=True, timeout=300)
        a, b = json.loads(out.read_text()), json.loads((HERE / "confirm2_summary.json").read_text())
    check(a == b, f"regrade confirm2_summary.json identical ({b['executed']}/{b['planned']} runs)")


def contract() -> None:
    c = json.loads((HERE / "contract" / "tools_list_properties.json").read_text())
    ok = all("element_index" not in c["cua_driver_0_32_0"][t] and "element_token" in c["cua_driver_0_32_0"][t]
             and "element_index" in c["cua_driver_0_21_0"][t] for t in ("click", "double_click", "scroll", "set_value"))
    ok = ok and not any(k in c[v]["drag"] for v in ("cua_driver_0_32_0", "cua_driver_0_21_0") for k in ("from_element", "element_token"))
    check(ok, "contract: 0.32.0 token-only on click/double_click/scroll/set_value; 0.21.0 lists element_index; no element drag")


def scan() -> None:
    host = re.escape(socket.gethostname())
    pat = re.compile(r"(?<![\w>.-])(/mnt/|/home/|/workspace/)|/tmp/claude|sk-[A-Za-z0-9]{16,}|hf_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}"
                     + (f"|\\b{host}\\b" if host else ""))
    hits = []
    for p in HERE.rglob("*"):
        if p.is_file() and p.name != "verify_artifacts.py" and "__pycache__" not in p.parts:
            t = p.read_text(encoding="utf-8", errors="replace")
            hits += [f"{p.relative_to(HERE)}: {m.group(0)}" for m in pat.finditer(t)]
    for h in hits[:20]:
        print("   ", h)
    check(not hits, f"scan: {len(hits)} local-path/host/secret hits")


if __name__ == "__main__":
    manifest()
    prereg_order()
    oracle_rederive()
    tool_metrics()
    regrade()
    contract()
    scan()
    print("RESULT", "PASS" if not FAIL else "FAIL")
    sys.exit(1 if FAIL else 0)
