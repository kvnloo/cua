#!/usr/bin/env python3
"""OWN-20 packet verifier (stdlib only). Run from anywhere; exit 0 only when every check passes.

1. Recomputes the per-row table, the scope classification and every reported timing from raw/
   (re-imports analyze.py) and compares them with the committed own-20-summary.json.
2. Checks every pre-registered block (schedule.json) has raw data, ran the expected Driver
   (sha256 + version read inside the session), kept every attempted mutation, and stayed within
   <= 10 measured mutations per lock acquisition.
3. Checks the quiet-lane receipts: raw/lock-ledger.jsonl has one EXCLUSIVE quiet-timed receipt per
   block (label own20-<block_id>) whose [acquired, released] interval contains the block's own
   start/end wall times; with --ledger <quiet-lane-ledger.jsonl> every copied receipt must also
   appear verbatim in the live ledger. Count-only controls (D1, G1) have shared receipts.
4. Checks PREREG order: the PREREG commit time precedes the first counted mutation, and (with git)
   PREREG.json at that commit equals the packet's PREREG.json.
5. Checks the README states the recomputed verdict for every scope and the disposition.
6. Privacy: no absolute local paths, home directories, host name or secret-looking tokens in any
   packet file (gz decompressed) and (with git) in any commit of the branch since the base.
"""

from __future__ import annotations

import datetime as dt
import gzip
import importlib.util
import json
import re
import socket
import subprocess
import sys
from pathlib import Path

PKT = Path(__file__).resolve().parent
RAW = PKT / "raw"
BASE_SHA = "352507b6c03162ab286b21d5ed509125cc3daece"
DRIVER_SHA256 = "8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3"
DRIVER_VERSION = "cua-driver 0.32.0"
failures: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)


def utc(s: str) -> int:
    return int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.timezone.utc).timestamp() * 1e9)


def git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(PKT), *args], capture_output=True, text=True, check=True).stdout
    except (subprocess.SubprocessError, OSError):
        return None


spec = importlib.util.spec_from_file_location("own20_analyze", PKT / "analyze.py")
analyze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze)
schedule = json.loads((PKT / "schedule.json").read_text())
block_ids = [b["block_id"] for b in schedule]

# 1. recompute
census_raw = RAW / "blocks"
rows, summary = analyze.run(census_raw)
committed = json.loads((PKT / "summaries" / "own-20-summary.json").read_text())
recomputed = json.loads(json.dumps(summary, sort_keys=True))
for key in ("per_row", "classification", "listener_timing_retained", "mutations_attempted", "mutations_failed",
            "driver_sha256", "driver_versions", "blocks"):
    check(recomputed.get(key) == committed.get(key), f"recompute: {key} matches own-20-summary.json")

# 2. blocks
present = sorted(p.name for p in census_raw.iterdir() if p.is_dir())
check(present == sorted(block_ids), f"every pre-registered block has a raw dir ({len(present)}/{len(block_ids)})")
check(summary["driver_sha256"] == [DRIVER_SHA256], "driver sha256 read inside every session")
check(summary["driver_versions"] == [DRIVER_VERSION], "driver version read inside every session")
batch = [json.loads(x) for x in (RAW / "batch.jsonl").read_text().splitlines() if x.strip()] \
    if (RAW / "batch.jsonl").exists() else []
check(len(batch) == len(block_ids), f"batch.jsonl has one line per block ({len(batch)})")
check(all(b.get("hostless") == "1" for b in batch), "every block launched under hostless (batch.jsonl)")
times = {}
for bid in block_ids:
    recs = analyze.load_jsonl(census_raw / bid / "mutations.jsonl")
    start = next((r for r in recs if r.get("event") == "block_start"), None)
    end = next((r for r in recs if r.get("event") == "block_end"), None)
    muts = [r for r in recs if r.get("event") == "mutation"]
    btype = start["block_type"] if start else None
    expect = None
    if btype:
        planned = {"text_v1": 10, "text_v2": 10, "focus_v1": 10, "focus_v2": 10, "selection_v1": 10,
                   "selection_v2": 10, "checkbox_v1": 10, "checkbox_v2": 10, "child_pts": 10, "child_stp": 10,
                   "recreate": 10, "window": 10, "process_v1": 9, "process_v2": 9, "registry": 10, "noop": 10,
                   "decoy": 10, "listener_cycle": 10}
        expect = planned[btype]
    check(start is not None and end is not None and len(muts) == expect and len(muts) <= 10,
          f"{bid}: block complete, {len(muts)} mutations kept (planned {expect}, <= 10 per acquisition)")
    if start and end:
        times[bid] = (start["w_ns"], end["w_ns"])

# 3. receipts
ledger = [json.loads(x) for x in (RAW / "lock-ledger.jsonl").read_text().splitlines() if x.strip()]
live = None
if "--ledger" in sys.argv:
    live = set(Path(sys.argv[sys.argv.index("--ledger") + 1]).read_text().splitlines())
for bid in block_ids:
    rec = [r for r in ledger if r.get("label") == f"own20-{bid}"]
    timing = analyze.is_timing_block(bid)  # AMENDMENT-1: seq 1-18 quiet-timed, seq 19-54 count-only shared
    kind_ok = ("pid" in rec[0] and "mode" not in rec[0]) if timing and rec else (bool(rec) and rec[0].get("mode") == "shared")
    ok = len(rec) == 1 and kind_ok and bid in times \
        and utc(rec[0]["acquired"]) <= times[bid][0] and times[bid][1] <= utc(rec[0]["released"])
    check(ok, f"{bid}: one {'EXCLUSIVE quiet-timed' if timing else 'shared count-only'} receipt whose interval contains the block")
prov0 = json.loads((PKT / "provenance.json").read_text())
am = prov0["amendment_commit"]
after = [times[b][0] for b in block_ids if b in times and int(b[1:3]) >= am["first_affected_seq"]]
check(bool(after) and am["committer_epoch"] * 1_000_000_000 < min(after),
      "AMENDMENT-1 committed before every block it governs")
done_before = [b for b in block_ids if b in times and int(b[1:3]) < am["first_affected_seq"]]
check(all(times[b][1] < am["committer_epoch"] * 1_000_000_000 for b in done_before),
      f"blocks run before AMENDMENT-1 ({len(done_before)}) finished before its commit")
shown_am = git("show", f'{am["sha"]}:docs/experiments/own-20-atspi-invalidation-census-2026-10-02/AMENDMENT-1.json')
if shown_am is not None:
    check(shown_am == (PKT / "AMENDMENT-1.json").read_text(), "AMENDMENT-1.json unchanged since its commit")
for label in ("own20-D1-default-off", "own20-G1-chrome-gate"):
    check(any(r.get("label") == label and r.get("mode") == "shared" for r in ledger), f"{label}: shared-lock receipt")
if live is not None:
    copied = [x for x in (RAW / "lock-ledger.jsonl").read_text().splitlines() if '"pid"' in x]
    check(all(x in live for x in copied), f"all {len(copied)} quiet-timed receipts appear verbatim in the live ledger")

# 4. PREREG order
prov = json.loads((PKT / "provenance.json").read_text())
pre = prov["prereg_commit"]
first = min(t[0] for t in times.values())
check(pre["committer_epoch"] * 1_000_000_000 < first, "PREREG committed before the first counted mutation")
shown = git("show", f'{pre["sha"]}:docs/experiments/own-20-atspi-invalidation-census-2026-10-02/PREREG.json')
if shown is not None:
    check(shown == (PKT / "PREREG.json").read_text(), "PREREG.json unchanged since its commit")
    ct = git("show", "-s", "--format=%ct", pre["sha"])
    check(ct is not None and int(ct.strip()) == pre["committer_epoch"], "PREREG commit time matches provenance")

# 5. README
readme = (PKT / "README.md").read_text()
for scope, c in summary["classification"].items():
    check(f"`{scope}`" in readme and c["verdict"] in readme, f"README states {scope} = {c['verdict']}")
check("Disposition" in readme and "**#20: KEEP.**" in readme, "README states the disposition")
spec_r = importlib.util.spec_from_file_location("own20_render", PKT / "render_tables.py")
render = importlib.util.module_from_spec(spec_r)
spec_r.loader.exec_module(render)
m = re.search(r"<!-- GENERATED:BEGIN[^>]*-->\n(.*?)<!-- GENERATED:END -->", readme, re.S)
check(m is not None and m.group(1) == render.render(recomputed), "README generated tables equal render_tables.py output for the recomputed summary")

# 6. privacy
host = socket.gethostname().split(".")[0]
patterns = [
    (re.compile(r"/home/[A-Za-z0-9_.-]+"), "home path"),
    (re.compile(r"/mnt/[A-Za-z0-9_.-]+"), "mount path"),
    (re.compile(r"/Users/[A-Za-z0-9_.-]+"), "macOS home path"),
    (re.compile(r"/tmp/[A-Za-z0-9_.-]+"), "tmp path"),
    (re.compile(r"(?i)(api[_-]?key|secret|token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{24,}"), "secret assignment"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "secret-looking key"),
]
if len(host) >= 3:
    patterns.append((re.compile(rf"\b{re.escape(host)}\b"), "host name"))
for path in sorted(PKT.rglob("*")):
    if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
        continue
    data = path.read_bytes()
    text = (gzip.decompress(data) if path.suffix == ".gz" else data).decode("utf-8", errors="replace")
    hits = [(label, m.group(0)) for rx, label in patterns for m in rx.finditer(text)]
    check(not hits, f"privacy: {path.relative_to(PKT)}" + (f" -> {hits[:3]}" if hits else ""))
log = git("log", "-p", "--format=%H%n%an <%ae>%n%B", f"{BASE_SHA}..HEAD")
if log is not None:
    commits = git("rev-list", f"{BASE_SHA}..HEAD")
    hits = [(label, m.group(0)) for rx, label in patterns for m in rx.finditer(log) if label != "secret assignment"]
    check(not hits, f"privacy: every commit of the branch since the base ({len(commits.split())} commits)"
          + (f" -> {hits[:3]}" if hits else ""))

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
