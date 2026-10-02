"""Active-C admissibility: classify every get_browser_state call in the A traces.

kvnloo/cua#107 lane CSHADOW, PREREG ``arms.C_active``. A Driver read may be
replaced by mirror state only if it is none of:

  (a) a ref-minting snapshot before a mutation,
  (b) a binding/revalidation read,
  (c) a post-effect verification read,
  (d) a #105 reconciliation read.

Input: the B-01 measured trial archive (REAL traces of the jev-use run.py step
loop on the same ``libs/cua-driver`` tree as the i107 tested source; B-01 is
PENDING, numbers reproduced by its verifier). The caller events give the call
sequence; the Driver phase trace proves which snapshot minted the ref each
mutation resolved (a new snapshot clears the tab's earlier refs, so the ref a
mutation resolves can only come from the most recent ``snap.stored``).

Usage: python3 classify_reads.py <trials-measured.tar.gz> <out.json>
Prints a one-line verdict. Pure standard library.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from collections import Counter

MUTATIONS = {"browser_type", "browser_click"}


def load(archive: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or "-fill-" not in member.name:
                continue
            data = tar.extractfile(member)
            assert data is not None
            rows = [json.loads(line) for line in io.TextIOWrapper(data, "utf-8") if line.strip()]
            out[member.name] = rows
    return out


def classify_trial(caller: list[dict], driver: list[dict]) -> list[dict]:
    """Return one row per get_browser_state call."""
    calls = [e for e in caller if e.get("event") == "call_send"]
    # Driver side: tool dispatches in order, with snapshot stores and ref resolutions.
    dispatches: list[dict] = []
    for mark in driver:
        phase = mark.get("phase")
        if phase == "dispatch.enter":
            dispatches.append({"tool": (mark.get("detail") or {}).get("tool"), "marks": []})
        elif dispatches:
            dispatches[-1]["marks"].append(phase)
    driver_tools = [d["tool"] for d in dispatches]
    caller_tools = [c["tool"] for c in calls if c["tool"] != "list_windows"]
    driver_tools_nolist = [t for t in driver_tools if t != "list_windows"]
    aligned = caller_tools == driver_tools_nolist
    rows = []
    disp = [d for d in dispatches if d["tool"] != "list_windows"]
    for index, call in enumerate(c for c in calls if c["tool"] != "list_windows"):
        if call["tool"] != "get_browser_state":
            continue
        row = {"label": call.get("label"), "aligned": aligned}
        if call.get("label") == "bind":
            row["category"] = "b"
            row["why"] = "pid+window_id binding: mints the target/tab capability every mutation re-proves"
            rows.append(row)
            continue
        d = disp[index] if aligned and index < len(disp) else None
        stored = d is not None and "snap.stored" in d["marks"]
        nxt = None
        for later_index in range(index + 1, len(disp) if aligned else 0):
            tool = disp[later_index]["tool"]
            if tool == "get_browser_state" or tool in MUTATIONS:
                nxt = disp[later_index]
                break
        resolved = (
            nxt is not None
            and nxt["tool"] in MUTATIONS
            and any(m.endswith(".ref_resolved") for m in nxt["marks"])
        )
        row.update(
            snapshot_stored=stored,
            next_tool=None if nxt is None else nxt["tool"],
            next_ref_resolved=resolved,
        )
        if stored and resolved:
            row["category"] = "a"
            row["why"] = "semantic_v2 snapshot whose minted ref the next mutation resolved (no snapshot between)"
        else:
            row["category"] = "outside"
            row["why"] = "not proven (a)-(d) from the traces"
        rows.append(row)
    return rows


def main() -> int:
    archive, out_path = sys.argv[1], sys.argv[2]
    digest = hashlib.sha256(open(archive, "rb").read()).hexdigest()
    files = load(archive)
    trials = sorted({name.rsplit(".driver-trace", 1)[0].removesuffix(".jsonl") for name in files})
    per_trial = []
    totals: Counter = Counter()
    by_arm: dict[str, Counter] = {}
    verification_driver_reads = 0
    for trial in trials:
        caller = files.get(f"{trial}.jsonl", [])
        driver = files.get(f"{trial}.driver-trace.jsonl", [])
        arm = trial.split("-")[2]
        rows = classify_trial(caller, driver)
        # (c): every post-effect verification in the caller is a fixture oracle read.
        oracle_reads = sum(1 for e in caller if e.get("event") == "oracle_send")
        sends = [e for e in caller if e.get("event") == "call_send"]
        last_mutation = max(
            (i for i, e in enumerate(sends) if e.get("tool") in MUTATIONS), default=len(sends)
        )
        verification_driver_reads += sum(
            1 for e in sends[last_mutation + 1 :] if e.get("tool") == "get_browser_state"
        )
        for row in rows:
            totals[row["category"]] += 1
            by_arm.setdefault(arm, Counter())[row["category"]] += 1
        per_trial.append({"trial": trial, "arm": arm, "reads": rows, "oracle_reads": oracle_reads})
    outside = totals.get("outside", 0)
    verdict = "NOT_ADMISSIBLE" if outside == 0 and totals else "AMENDMENT_REQUIRED"
    result = {
        "schema": "cua.i107.cshadow.admissibility.v1",
        "evidence": "SOURCE (run.py loop) + REAL traces reused from B-01 (PENDING; same libs/cua-driver tree)",
        "archive_sha256": digest,
        "trials": len(trials),
        "get_browser_state_calls": sum(totals.values()),
        "by_category": dict(sorted(totals.items())),
        "by_arm": {arm: dict(sorted(c.items())) for arm, c in sorted(by_arm.items())},
        "driver_reads_after_last_mutation": verification_driver_reads,
        "category_c_note": "post-effect verification is the fixture /state oracle (caller oracle_send), never a Driver read",
        "category_d_note": "no #105 reconciliation read exists in the main caller (OWN-105 runner fixes are not in main)",
        "verdict": verdict,
        "per_trial": per_trial,
    }
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print(
        f"admissibility: {verdict}; trials={len(trials)} calls={sum(totals.values())} "
        f"by_category={dict(sorted(totals.items()))} driver_reads_after_last_mutation={verification_driver_reads}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
