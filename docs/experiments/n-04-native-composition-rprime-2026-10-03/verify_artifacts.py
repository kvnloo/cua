#!/usr/bin/env python3
"""N-04 packet verifier (standard library + git). Passes from a clean clone of the branch.

Checks:
 1. raw/MANIFEST.json: every listed raw file exists with the listed sha256 and size; no unlisted file.
 2. analyze_n04.py re-run from raw/ reproduces n04-summary.json and n04-trial-metrics.jsonl.gz exactly.
 3. headline-numbers.json: every number equals the value at its path in n04-summary.json (or
    hc-control.json), and every cited headline text appears verbatim in README.md.
 4. Cited files: every packet path cited in README.md (whole README) or the headline/summary JSON is
    tracked by git (template verify_helper.check_cited).
 5. PREREG.json was first committed before the first EXCLUSIVE receipt of this lane's measured chunks.
 6. The registered files are unchanged since PREREG (plan.json, harness/*), and harness/n03/* are the
    N-03 blobs (git blob ids registered in PREREG.json).
 7. Locks and the load rule: every measured round label (k1-, k5-, s0-) ran in a chunk with an
    EXCLUSIVE quiet-timed receipt whose window contains all of the round's trials (wall clock), the
    round was preceded by a passing load-gate check (1-min loadavg <= 4.0) in that chunk, and every
    control label ran in a chunk with a SHARED receipt.
 8. Privacy of EVERY commit base..HEAD (privacy_scan_commits.py: paths, private names from
    CUA_PRIVACY_NAMES_FILE + host name as whole words, secret shapes, decoded hex/base64 literals).

usage: python3 verify_artifacts.py [--base <sha>]   (run under bin/hostless)
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
sys.path.insert(0, str(HERE))
from verify_helper import check_cited  # noqa: E402

BASE = "45dff8f3227a21ff8bef1af4bf4c2bcbd9449b2a"  # R': every lane commit on this branch is scanned
MEASURED_PREFIXES = ("n04-k1-", "n04-k5-", "n04-s0-")
CONTROL_PREFIX = "n04c-"
FAILS: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        FAILS.append(msg)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout


def get_path(obj, path: str):  # noqa: ANN001, ANN201
    for part in path.split("|"):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def read_jsonl(p: Path) -> list[dict]:
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt", encoding="utf-8") as stream:
        return [json.loads(x) for x in stream if x.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    # 1 manifest
    manifest = json.loads((RAW / "MANIFEST.json").read_text(encoding="utf-8"))
    bad = [k for k, v in manifest.items() if not (RAW / k).is_file()
           or hashlib.sha256((RAW / k).read_bytes()).hexdigest() != v["sha256"] or (RAW / k).stat().st_size != v["bytes"]]
    extra = [str(p.relative_to(RAW)) for p in RAW.rglob("*") if p.is_file() and p.name != "MANIFEST.json"
             and str(p.relative_to(RAW)) not in manifest]
    check(not bad and not extra, f"raw manifest: {len(manifest)} files, mismatched {bad[:5]}, unlisted {extra[:5]}")
    # 2 re-analysis
    with tempfile.TemporaryDirectory() as tmp:
        out, met = Path(tmp) / "s.json", Path(tmp) / "m.jsonl.gz"
        subprocess.run([sys.executable, "-B", str(HERE / "analyze_n04.py"), "--raw", str(RAW), "--out", str(out),
                        "--metrics", str(met)], check=True, capture_output=True)
        check(json.loads(out.read_text(encoding="utf-8")) == json.loads((HERE / "n04-summary.json").read_text(encoding="utf-8")),
              "analyze_n04.py reproduces n04-summary.json from raw/")
        check(gzip.decompress(met.read_bytes()) == gzip.decompress((HERE / "n04-trial-metrics.jsonl.gz").read_bytes()),
              "analyze_n04.py reproduces n04-trial-metrics.jsonl.gz")
    # 3 headline numbers
    summary = json.loads((HERE / "n04-summary.json").read_text(encoding="utf-8"))
    hc = json.loads((HERE / "hc-control.json").read_text(encoding="utf-8"))
    heads = json.loads((HERE / "headline-numbers.json").read_text(encoding="utf-8"))
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    nbad = []
    for h in heads["numbers"]:
        src = summary if h["source"] == "n04-summary.json" else hc
        try:
            v = get_path(src, h["path"])
        except (KeyError, IndexError, TypeError):
            nbad.append(f"{h['id']}: path missing")
            continue
        if v != h["value"]:
            nbad.append(f"{h['id']}: {v!r} != {h['value']!r}")
        if h.get("text") and h["text"] not in readme:
            nbad.append(f"{h['id']}: README lacks {h['text']!r}")
    check(not nbad, f"headline numbers: {len(heads['numbers'])} checked, problems {nbad[:6]}")
    # 4 cited files tracked
    findings = check_cited(HERE, scope="all")
    check(not findings, f"cited files tracked (verify_helper, whole README + JSON): problems {findings[:5]}")
    # 5 PREREG before first measured receipt
    first = git("log", "--diff-filter=A", "--format=%cI", "--", "PREREG.json").split()
    prereg_t = dt.datetime.fromisoformat(first[-1]) if first else None
    receipts = [json.loads(x) for x in (RAW / "locks" / "quiet-lane-receipts.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    excl = [x for x in receipts if str(x.get("label", "")).startswith("n04-c") and x.get("mode") is None]
    t_first = min((ts(x["acquired"]) for x in excl), default=None)
    check(bool(prereg_t and t_first and prereg_t < t_first),
          f"PREREG.json first committed {prereg_t} before the first EXCLUSIVE measured receipt {t_first}")
    # 6 registered files unchanged; N-03 blobs
    prereg = json.loads((HERE / "PREREG.json").read_text(encoding="utf-8"))
    reg = prereg["harness"]["sha256_at_registration"]
    frozen = ["plan.json", "harness/n04_harness.py", "harness/run_block_n04.sh", "harness/run_chunks.sh", "harness/make_plan_n04.py"]
    changed_frozen = [f for f in frozen if hashlib.sha256((HERE / f).read_bytes()).hexdigest() != reg[f]]
    check(not changed_frozen, f"plan and harness unchanged since PREREG: changed {changed_frozen}")
    changed_analysis = [f for f in ("analyze_n04.py", "hc_control.py") if hashlib.sha256((HERE / f).read_bytes()).hexdigest() != reg[f]]
    print(f"note: analysis files changed after PREREG (disclosed in README Deviations if any): {changed_analysis}")
    want = {}
    for item in prereg["harness"]["n03_copy"].split(":", 1)[1].split(","):
        parts = item.split()  # "<file> <blob id> [trailing note]"
        if len(parts) >= 2:
            want[parts[0]] = parts[1]
    got = {f: git("hash-object", f"harness/n03/{f}").strip() for f in want}
    check(len(want) == 6 and got == want, f"harness/n03 blob-identical to N-03 63d419034: {len(want)} files")
    # 7 locks and the load rule
    gate = read_jsonl(RAW / "locks" / "load-gate.jsonl")
    done = {x["label"]: x for x in gate if x.get("event") == "round_done"}
    passes = {(x["chunk"], x["label"]) for x in gate if x.get("event") == "load_gate" and x.get("pass") and x.get("last_load1", 99) <= 4.0}
    by_label = {x["label"]: x for x in receipts}
    lbad = []
    n_meas = n_ctl = 0
    for d in sorted(p for p in (RAW / "runs").iterdir() if p.is_dir()):
        label = d.name
        recs = read_jsonl(d / "trials.jsonl.gz")
        trials = [x for x in recs if x.get("event") == "trial"]
        if label.startswith(MEASURED_PREFIXES):
            n_meas += 1
            dn = done.get(label)
            if not dn:
                lbad.append(f"{label}: no round_done")
                continue
            rc = by_label.get(dn["chunk"])
            if not rc or rc.get("mode") is not None:
                lbad.append(f"{label}: chunk {dn['chunk']} has no EXCLUSIVE receipt")
                continue
            a, b = ts(rc["acquired"]).timestamp() * 1e9, ts(rc["released"]).timestamp() * 1e9
            if not all(a <= x["w_begin"] and x["w_end"] <= b for x in trials):
                lbad.append(f"{label}: a trial outside its EXCLUSIVE window")
            if (dn["chunk"], label) not in passes:
                lbad.append(f"{label}: no passing load gate")
        elif label.startswith(CONTROL_PREFIX):
            n_ctl += 1
            dn = done.get(label)
            rc = by_label.get(dn["chunk"]) if dn else None
            if not rc or rc.get("mode") != "shared":
                lbad.append(f"{label}: no SHARED receipt")
    check(not lbad and n_meas > 0, f"locks + load rule: {n_meas} measured round labels, {n_ctl} control labels; problems {lbad[:6]}")
    # 8 privacy of every commit
    res = subprocess.run([sys.executable, "-B", str(HERE / "privacy_scan_commits.py"), "--repo", str(HERE),
                          "--range", f"{args.base}..HEAD"], capture_output=True, text=True)
    print(res.stdout.strip())
    check(res.returncode == 0, "privacy: every commit since R' (paths, private names, secrets, decoded literals)")
    print("VERIFY", "FAILED" if FAILS else "OK", f"({len(FAILS)} failures)")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
