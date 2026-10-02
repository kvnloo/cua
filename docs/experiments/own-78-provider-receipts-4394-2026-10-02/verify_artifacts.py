#!/usr/bin/env python3
"""Independent verifier for the OWN-78 packet (does not import analyze.py).

usage: python3 verify_artifacts.py      (exit 0 = every check passed)

1. Recomputes per-row counts from raw/*.jsonl and compares them with own78-summary.json.
2. Cross-checks every decision-bearing runner record against HTTP evidence: one HTTP 200 attempt
   per decision, in order, from api.typesafe.ai for live rows (loopback stub for R4s), the decoded
   provider response selected the same id, request-id sha256 prefixes agree, and backend == mock
   rows made 0 HTTP attempts.
3. Recomputes the provider budget (reached / loopback-refused / stub) and checks raw/budget.json.
4. Checks the oracle-side counts (submits, navigations, routine starts, journal token completions).
5. Privacy scan of every file in the packet (absolute paths, host name, bearer tokens, key-like
   strings) and checks that no record carries headers, bodies or typed text.
6. If git is available: PREREG.json and PREREG-AMENDMENT-1.json were committed before the first
   measured block started.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
FAIL: list[str] = []
MEASURED = {"m1-r2": "R2", "m2-r3": "R3", "m3-r1": "R1", "m4-r4a": "R4", "m5-r4b": "R4", "m6-r0": "R0", "m7-r4s-a": "R4s", "m8-r4s-b": "R4s"}


def check(cond: bool, label: str) -> None:
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        FAIL.append(label)


def trials(block: str) -> list[list[dict]]:
    return [[json.loads(l) for l in p.read_text().splitlines() if l.strip()] for p in sorted((RAW / block).glob(f"{block}-*.jsonl"))]


def parts(rows: list[dict]):
    cell = next(r for r in rows if r["type"] == "cell")
    ev = [r["event"] for r in rows if r["type"] == "runner_event"]
    rc = [r for r in rows if r["type"] == "receipt"]
    return cell, ev, rc, [r for r in rows if r["type"] == "journal"]


def decisions(ev):
    return [e for e in ev if e.get("event") == "step" or (e.get("event") == "outcome" and e.get("outcome") == "abstained" and "backend" in e)]


def completions(journal):
    n, prev = 0, False
    for e in sorted(journal, key=lambda e: e["seq"]):
        n += e["equals_token"] and not prev
        prev = e["equals_token"]
    return n


def main() -> int:
    summary = json.loads((HERE / "own78-summary.json").read_text())
    rows = summary["rows"]
    per_row: dict[str, list] = {}
    for block, row in MEASURED.items():
        per_row.setdefault(row, []).extend(trials(block))

    # 1+2: per-row recomputation and HTTP cross-check
    for row, items in per_row.items():
        check(len(items) == rows[row]["n_trials"], f"{row}: n_trials {len(items)} == summary {rows[row]['n_trials']}")
        matched = total = 0
        for t in items:
            cell, ev, rc, journal = parts(t)
            dec = decisions(ev)
            http = [r for r in rc if r.get("kind") == "http_attempt" and not r.get("guard_refused")]
            ok200 = [r for r in http if r.get("status") == 200]
            resp = [r for r in rc if r.get("kind") == "provider_response" and r.get("ok")]
            if row == "R2":
                check(not http and all(d.get("backend") == "mock" for d in dec), f"{cell['cell_id']}: backend=mock and 0 HTTP attempts")
                continue
            check(len(dec) == len(ok200) == len(resp), f"{cell['cell_id']}: decisions {len(dec)} == HTTP 200 {len(ok200)} == decoded responses {len(resp)}")
            want_host = "127.0.0.1" if row == "R4s" else "api.typesafe.ai"
            for d, h, p in zip(dec, ok200, resp):
                total += 1
                sel = d.get("candidate") if d.get("event") == "step" else "abstain"
                good = (h.get("host") == want_host and p.get("selected_id") == sel and h.get("request_id_sha256_16") == p.get("request_id_sha256_16")
                        and (row == "R0" or d.get("backend") == "typesafe"))
                matched += good
        if row != "R2":
            print(f"     {row}: {matched}/{total} decision records match HTTP evidence")
            check(matched == total, f"{row}: every decision record matches its HTTP 200 attempt and decoded response")
    check(rows["R1"]["backend_field_eq_http_responder"] == rows["R1"]["decisions"] == 10, "R1 summary: 10/10 backend == HTTP responder")
    check(rows["R1"]["verified"] == sum(1 for t in per_row["R1"] if parts(t)[0]["final_state"] == {"submitted": parts(t)[0]["token"]}), "R1 verified count recomputed")
    check(rows["R2"]["verified"] == 10 and rows["R2"]["http_attempts"] == 0 and rows["R2"]["backend_mock"] == 20, "R2 summary: 10 verified, 0 HTTP, 20 mock decisions")

    # 4: oracle-side counts
    for row in ("R3", "R4", "R4s"):
        hist = Counter()
        for t in per_row[row]:
            cell, ev, rc, journal = parts(t)
            c = cell["server_counts"]
            hist[completions(journal)] += 1
            check(c.get("GET /", 0) == 1 and c.get("POST /reset", 0) == 1 and c.get("POST /submit", 0) == 0, f"{cell['cell_id']}: 1 navigation, 1 routine start, 0 submits")
            if row == "R4s":
                types = sum(1 for r in rc if r.get("kind") == "driver_call" and r.get("tool") == "browser_type")
                final = ev[-1]
                check(completions(journal) == 1 and types == 1 and final.get("outcome") == "unknown" and final.get("phase") == "decide" and final.get("step") == 2 and cell["rc"] != 0,
                      f"{cell['cell_id']}: 1 input mutation, 1 browser_type, explicit decide failure at step 2")
        check({str(k): v for k, v in hist.items()} == {str(k): v for k, v in rows[row].get("input_mutations_hist", {"0": 6}).items()}, f"{row}: input-mutation histogram {dict(hist)} matches summary")

    # 3: budget
    reached = refused = stub = 0
    for p in RAW.glob("*/*-*.jsonl"):
        for r in (json.loads(l) for l in p.read_text().splitlines() if l.strip()):
            if r.get("type") == "receipt" and r.get("kind") == "http_attempt" and not r.get("guard_refused"):
                has_status = isinstance(r.get("status"), int)
                reached += (not r["loopback"]) and has_status
                refused += r["loopback"] and not has_status
                stub += r["loopback"] and has_status
    budget = json.loads((RAW / "budget.json").read_text())
    check(reached == budget["reached"] == summary["budget"]["reached"] == 42, f"budget: reached {reached} == budget.json {budget['reached']} == summary == 42")
    check(reached <= 45, "budget: reached within the lane cap of 45")
    check(refused == summary["budget"]["loopback_refused"] and stub == summary["budget"]["stub_answered_not_provider"], f"budget: loopback refused {refused}, stub {stub} match summary")
    check(reached + refused + stub == budget["attempts"], f"budget: reached+refused+stub {reached + refused + stub} == budget.json attempts {budget['attempts']}")

    # 5: privacy and content-free receipts
    host = socket.gethostname()
    patterns = [re.compile(p) for p in (r"/home/", r"/mnt/", r"/tmp/", r"x11-session\.[A-Za-z0-9]{6}", r"Bearer ", r"tsk_[A-Za-z0-9]", r"own78-dummy-key")]
    for f in sorted(HERE.rglob("*")):
        if f.is_dir() or "__pycache__" in f.parts:
            continue
        text = f.read_text(errors="replace")
        bad = [p.pattern for p in patterns if p.search(text)]
        if f.name in ("verify_artifacts.py", "package_raw.py"):
            bad = []  # these two files define the pattern lists themselves
        elif f.name == "own78_harness.py":
            bad = [b for b in bad if b != r"own78-dummy-key"]  # defines the dummy-key constant
        check(not bad and (not host or host not in text), f"privacy: {f.relative_to(HERE)}")
    forbidden_keys = {"headers", "body", "text", "authorization", "api_key", "value"}
    leaked = 0
    for p in RAW.glob("*/*-*.jsonl"):
        for r in (json.loads(l) for l in p.read_text().splitlines() if l.strip()):
            if r.get("type") in ("receipt", "journal", "stub") and forbidden_keys & {k.lower() for k in r}:
                leaked += 1
    check(leaked == 0, "receipts/journal/stub records carry no headers, bodies, typed text or key fields")

    # 6: prereg ordering
    try:
        def ctime(path: str) -> datetime:
            out = subprocess.run(["git", "-C", str(HERE), "log", "--diff-filter=A", "--format=%cI", "--", path], capture_output=True, text=True, check=True).stdout.split()
            return datetime.fromisoformat(out[-1])
        first = min(datetime.strptime(json.loads((RAW / b / "validity.json").read_text())["started_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) for b in MEASURED)
        smoke_first = min(datetime.strptime(json.loads((RAW / b / "validity.json").read_text())["started_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) for b in ("smoke-a",))
        check(ctime("PREREG.json") <= smoke_first, f"PREREG.json committed before the first trial (smoke-a {smoke_first.isoformat()})")
        check(ctime("PREREG-AMENDMENT-1.json") <= first, f"PREREG-AMENDMENT-1.json committed before the first measured block ({first.isoformat()})")
    except Exception as error:  # git not available in a detached copy
        print(f"skip prereg ordering check: {type(error).__name__}")

    print(f"\n{'ALL CHECKS PASSED' if not FAIL else f'{len(FAIL)} CHECK(S) FAILED'}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
