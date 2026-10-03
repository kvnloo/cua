#!/usr/bin/env python3
"""OWN-78L packet verifier (standard library only; run from a clean clone of the branch, under the
lane's bin/hostless, with no provider key).

1. Recomputes own78l-summary.json from raw/ with analyze.py and requires equality.
2. Requires the headline numbers and the disposition to appear verbatim in README.md.
3. Reuse: the OWN-78A files this packet imports are blob-identical (at HEAD) to the OWN-78A packet
   head, and every cell's validity.json recorded the same blob ids before it ran.
4. Validity per cell: ok, Driver sha256 + version, F tree ids equal git's, harness/launcher sha256
   equal the PREREG commit's files, key present only in the R1 cells, telemetry off.
5. Budget: ledger attempts/reached <= 8/6 and equal budget.json; every sent attempt went to
   api.typesafe.ai with status 200 and a request id; no control cell sent anything; per-trial
   allowance never exceeded.
6. Locks: one shared acquisition per cell, held <= 300 s, the cell ran inside its window.
7. Ordering: the PREREG commit is an ancestor of HEAD and precedes every unit run and cell.
8. Gate: the disposition follows the pre-registered conditions.
9. Privacy: every commit base..HEAD (OWN-78A privacy_scan) and every packet file has no absolute path.
10. Every file README.md or the summary cites is tracked (OWN-78A verify_helper.check_cited).

usage: python3 verify_artifacts.py [--base <sha>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
A_DIR = HERE.parent / "own-78a-abstain-isolation-4394-2026-10-03"
sys.path.insert(0, str(HERE))
sys.path.append(str(A_DIR / "harness"))  # appended: OWN-78A's packet also has an analyze.py
sys.path.append(str(A_DIR))
import analyze  # noqa: E402

BASE = "6f6c67955505e5b48f130a69feac9ea11c6e9ed6"
PREREG_SHA = "fad2e963db48deba3134aa4e0d4074b840862c1d"
PACKET_REL = "docs/experiments/own-78l-r1-lite-f-2026-10-03"
A_REL = "docs/experiments/own-78a-abstain-isolation-4394-2026-10-03"
F_SHA = "61eec09092fd161f62651a890c882f276a642855"
PR_HEAD = "039257811e0bbb2348c616c52562409923d2856f"
EXAMPLES = "libs/cua-driver/examples/jev-use"
DRIVER_SHA256 = "19bad35248702fd42f6aa372f1f4bebe4ca3728d9be0f67287f1c186a0b47df9"
REUSED = {  # path under the OWN-78A packet -> blob id at 6f6c67955
    "harness/own78a_harness.py": "01c08b1d1d206b9c4203f7acafb570e4a99364a6",
    "harness/own78a_launcher.py": "e814b649116349718e4c1dde28bd423b4f6bb50c",
    "harness/in_session.sh": "e7b2bcdc3a77499f13594ad3cb305afddcf0b6aa",
    "harness/unit.sh": "05c87cd6ca825eb67952c084c234fc5357120ae7",
    "harness/privacy_scan.py": "512412c9e49e54c3f5651d6285c9d19eb1bf8ab4",
    "harness/package_raw.py": "72df76c1570c4f06bc80d529b9b93d00b57fdd14",
    "verify_helper.py": "23a3af67da58c1e9398ecb28f8587fe344e25669",
}
CELLS = ("STUBt1", "CAP0t1", "MOCKt1", "MOCKt2", "MOCKt3", "R1t1", "R1t2", "R1t3")
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args()

    summary = analyze.analyze()
    committed = json.loads((HERE / "own78l-summary.json").read_text())
    check("summary recomputes from raw/", summary == committed)

    readme = (HERE / "README.md").read_text()
    r1, prov = summary["r1_lite"], summary["provider"]
    for text in (summary["headline"], f"**Disposition: {summary['disposition']}.**",
                 f"verified **{r1['verified']}/3**", f"backend == responder **{r1['backend_equals_responder']}/3**",
                 f"{prov['attempts']} attempts / {prov['reached']} reached", r1["models"][0] if r1["models"] else "?"):
        check(f"README states '{text}'", text in readme)

    prereg = json.loads((HERE / "PREREG.json").read_text())
    for rel, blob in REUSED.items():
        head = git("rev-parse", f"HEAD:{A_REL}/{rel}").strip()
        base = git("rev-parse", f"{BASE}:{A_REL}/{rel}").strip()
        check(f"reused {rel} blob-identical to OWN-78A head", head == blob == base)
    check("PREREG reuse blobs match", all(REUSED[f"harness/{k}"] == v for k, v in prereg["reuse"]["blobs"].items()))

    prereg_time = utc(git("log", "-1", "--format=%cI", PREREG_SHA).strip())
    locks = analyze.jsonl(HERE / "raw" / "locks.jsonl")
    check("one lock receipt per cell", sorted(l["label"] for l in locks) == sorted(f"own78l-{c}" for c in CELLS))
    tree_id = git("rev-parse", f"{F_SHA}:{EXAMPLES}").strip()
    for cell in CELLS:
        v = json.loads((HERE / "raw" / cell / "validity.json").read_text())
        end = json.loads((HERE / "raw" / cell / "end.json").read_text())
        check(f"{cell}: validity ok, Driver sha256 + version", v["ok"] and v["driver_sha256"] == DRIVER_SHA256
              and v["driver_version_in_session"] == "cua-driver 0.31.0")
        check(f"{cell}: reuse blobs recorded before the cell", v["reuse"]["ok"]
              and all(v["reuse"]["found"][k] == REUSED[f"harness/{k}"] for k in v["reuse"]["found"]))
        check(f"{cell}: F tree matches git", v["trees"]["f"]["ok"] and v["trees"]["f"]["sha"] == F_SHA
              and v["trees"]["f"]["examples_tree_id"] == tree_id)
        for fname, key in (("own78l_harness.py", "harness_sha256"), ("own78l_launcher.py", "launcher_sha256")):
            blob = subprocess.run(["git", "-C", str(HERE), "show", f"{PREREG_SHA}:{PACKET_REL}/harness/{fname}"],
                                  capture_output=True, check=True).stdout
            check(f"{cell}: {fname} sha256 equals the PREREG commit's", hashlib.sha256(blob).hexdigest() == v[key])
        check(f"{cell}: key present only in R1 cells", v["typesafe_key_present"] == cell.startswith("R1"))
        check(f"{cell}: Driver telemetry off, no forbidden env", v["telemetry_disabled"] and not v["forbidden_env_present"])
        check(f"{cell}: started after the PREREG commit", utc(v["started_utc"]) > prereg_time)
        lock = next((l for l in locks if l["label"] == f"own78l-{cell}"), None)
        check(f"{cell}: inside one shared acquisition held <= 300 s", lock is not None and lock["mode"] == "shared"
              and lock["held_ms"] <= 300000 and lock["rc"] == 0
              and utc(lock["acquired"]) <= utc(v["started_utc"])
              and utc(end["ended_utc"]) <= utc(lock["released"]) + timedelta(seconds=1))
    runs = json.loads((HERE / "raw" / "unit" / "runs.json").read_text())["runs"]
    check("every unit run started after the PREREG commit", all(utc(r["started_utc"]) > prereg_time for r in runs))
    ancestor = subprocess.run(["git", "-C", str(HERE), "merge-base", "--is-ancestor", PREREG_SHA, "HEAD"]).returncode == 0
    check("PREREG commit is an ancestor of HEAD", ancestor)

    ledger = analyze.jsonl(HERE / "raw" / "provider-ledger.jsonl")
    sent = [r for r in ledger if not r.get("guard_refused")]
    budget = json.loads((HERE / "raw" / "budget.json").read_text())
    check("budget within lane cap 6 reached / 8 attempts", prov["reached"] <= 6 and prov["attempts"] <= 8)
    check("budget.json agrees with the ledger", budget["attempts"] == prov["attempts"] and budget["reached"] == prov["reached"])
    check("every sent attempt: api.typesafe.ai /v1/systemone, 200, request id present",
          all(r["host"] == "api.typesafe.ai" and r["path"] == "/v1/systemone" and r["status"] == 200
              and r["request_id_present"] for r in sent))
    check("no control cell sent a request", all(r["block"].startswith("R1") for r in sent))
    for t in r1["trials"]:
        if t["evidence_class"] != "NOT_RUN":
            check(f"{t['trial']}: within its allowance and <= 2 decisions", t["reached"] <= t["allowance"][0]
                  and t["attempts"] <= t["allowance"][1] and t["backend_vs_responder"]["n_decisions"] <= 2)
    for name in ("budget-mock.json", "budget-cap0.json"):
        b = json.loads((HERE / "raw" / name).read_text())
        check(f"{name}: cap 0 and 0 used", b["lane_cap_reached"] == b["lane_cap_attempts"] == 0
              and b["attempts"] == b["reached"] == 0)

    conditions = summary["gate_conditions"]
    expected = "KEEP" if all(conditions.values()) and all(summary["validity_ok"].values()) else "REVISE"
    check("disposition follows the pre-registered gate", summary["disposition"] == expected)
    check("E4: 0 duplicate mutations, replays, unverified successes in every arm",
          all(v == 0 for v in summary["e4_all_arms"].values()))

    p = json.loads((HERE / "provenance.json").read_text())
    check("provenance: PR head start == end == tested PR head",
          p["pr_4394_live_head"]["start"]["head"] == p["pr_4394_live_head"]["end"]["head"] == PR_HEAD)
    check("provenance: PREREG sha", p["prereg_commit"]["sha"] == PREREG_SHA)

    import privacy_scan
    ok, problems, note = privacy_scan.scan(args.base, str(HERE))
    check(f"privacy: every commit {args.base[:9]}..HEAD ({note})", ok, "; ".join(problems[:8]))
    import verify_helper
    findings = verify_helper.check_cited(HERE, "all")
    check("every file README or the summary cites is tracked", not findings,
          ", ".join(f"{f['path']} {f['kind']}" for f in findings[:8]))
    absolute = re.compile(r"/(?:home|mnt|Users|tmp)/[A-Za-z0-9_.-]")
    leaked = [str(q.relative_to(HERE)) for q in HERE.rglob("*")
              if q.is_file() and "__pycache__" not in q.parts and absolute.search(q.read_text(errors="replace"))]
    check("packet: no absolute local paths", not leaked, ", ".join(leaked[:5]))

    print(f"\n{len(FAILS)} failed" if FAILS else "\nALL CHECKS PASS")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
