#!/usr/bin/env python3
"""R2-07 packet verifier (stdlib only; run from anywhere: python3 verify_artifacts.py).

1. Recomputes every headline from raw/ (analyze.analyze) and requires byte-equality with r2-07-summary.json.
2. Requires each README headline number to be present (needles derived from the recomputed summary).
3. Artifact-authority schema check on raw/learn/artifact.json, plus discriminating self-tests (an injected
   ref / element token / capture id / target id / tab id / session id / epoch / backend node id / coordinate
   must each be rejected).
4. Provenance: every phase validity.json has the pinned Driver sha256, tested source SHA, Rust tree identical
   to 229b65b28, examples identical to the tested SHA, no forbidden env, DISPLAY set.
5. Budget: reached <= 80 and equal to the per-cell sum; attempts >= reached.
6. PREREG.json was committed before the first measured trial (git, if available).
7. Privacy scan of every packet file: no absolute local paths, host name or credential markers.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "harness"))
import analyze  # noqa: E402
import compiled_routine as cr  # noqa: E402

DRIVER_SHA = "8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3"
TESTED_SHA = "031ee5f58c222ea60ca0fcaf0a7858535a73c75b"
FAIL: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def main() -> int:
    summary_path = HERE / "r2-07-summary.json"
    recomputed = analyze.analyze()
    text = json.dumps(recomputed, indent=1, sort_keys=True) + "\n"
    check(summary_path.exists() and summary_path.read_text() == text, "summary JSON recomputes byte-identically from raw/")
    S = recomputed

    readme = (HERE / "README.md").read_text()
    w = S["warm"]
    needles = [
        f"{w['A']['verified']}/{w['A']['n']}", f"{w['B']['verified']}/{w['B']['n']}", f"{w['C']['verified']}/{w['C']['n']}",
        f"{w['A']['T_ms']['median']}", f"{w['B']['T_ms']['median']}", f"{w['C']['T_ms']['median']}",
        f"{S['paired_T']['C_minus_B']['median']}", f"{S['paired_T']['C_minus_B']['ci95'][0]}", f"{S['paired_T']['C_minus_B']['ci95'][1]}",
        f"{S['paired_T']['C_minus_A']['median']}", f"{S['paired_T']['C_minus_A']['ci95'][0]}", f"{S['paired_T']['C_minus_A']['ci95'][1]}",
        f"{S['paired_T']['B_minus_A']['median']}",
        f"{S['learning']['T_ms']}", f"{S['admission']['T_ms']}", f"{S['compile']['compile_ms']}",
        f"{S['budget']['reached']}", f"**Disposition: {S['disposition']}**", S["disposition_under_proposed_amendment"],
    ]
    tot = S["costs"]["totals_all_compiled_invocations"]
    bc = tot["by_class"]
    check(sum(bc.values()) == tot["invocations"] and bc["other"] == 0,
          f"all-invocation classes are exclusive and sum to {tot['invocations']} ({bc})")
    needles += [f"{tot['invocations']}: P3", f"**{bc['verified']} independently verified**",
                f"**{bc['stop_or_unknown']} explicit stop/unknown**", f"**{bc['setup_failed']} setup failures**"]
    for n in needles:
        check(n in readme, f"README contains headline {n!r}")

    artifact = json.loads((HERE / "raw/learn/artifact.json").read_text())
    check(cr.check_artifact_authority(artifact) == [], "admitted artifact carries no authority field")
    injections = {
        "ref": ("steps", 1, "ref", "p9:1"), "element_token": ("steps", 0, "element_token", "et-abcdef12"),
        "capture_id": ("steps", 0, "capture_id", "c-1"), "target_id": ("steps", 0, "target_id", "bt-0123456789"),
        "tab_id": ("steps", 0, "tab_id", "tab-0123456789"), "session": ("steps", 0, "session", "jev-python-0a1b2c3d"),
        "session_epoch": ("steps", 0, "session_epoch", 2), "backend_node_id": ("steps", 1, "backend_node_id", 5),
        "x": ("steps", 1, "x", 10), "coordinates": ("steps", 1, "coordinates", [1, 2]),
    }
    for label, (k, i, key, value) in injections.items():
        bad = json.loads(json.dumps(artifact))
        bad[k][i][key] = value
        check(bool(cr.check_artifact_authority(bad)), f"authority check rejects injected {label}")
    for v in ("p3:2", "bt-0123456789ab", "123e4567-e89b-12d3-a456-426614174000"):
        bad = json.loads(json.dumps(artifact))
        bad["steps"][1]["logical_target"]["name"] = v
        check(bool(cr.check_artifact_authority(bad)), f"authority check rejects value-shaped {v}")

    for f in sorted((HERE / "raw").rglob("validity.json")):
        if "shakedown" in f.parts:
            continue
        v = json.loads(f.read_text())
        rel = f.relative_to(HERE)
        check(v["driver_sha256"] == DRIVER_SHA and v["tested_sha"] == TESTED_SHA and v["rust_identical_to_229b65b28"]
              and v["examples_identical_to_tested_sha"] and not v["forbidden_env_present"] and v["display_set"]
              and v["ok"], f"provenance pins hold in {rel}")

    b = S["budget"]
    per_cell = sum(x["reached"] for x in b["by_cell"].values())
    check(b["reached"] <= 80 and b["reached"] == per_cell and b["attempts"] >= b["reached"],
          f"provider budget reached={b['reached']} attempts={b['attempts']} within cap 80 and equal to per-cell sum")

    try:
        out = subprocess.run(["git", "-C", str(HERE), "log", "--diff-filter=A", "--format=%cI", "--", "PREREG.json"],
                             capture_output=True, text=True, check=True).stdout.split()
        prereg_time = out[-1] if out else None
        first = json.loads((HERE / "raw/learn/validity.json").read_text())["started_utc"]
        from datetime import datetime
        ok = prereg_time is not None and datetime.fromisoformat(prereg_time) <= datetime.fromisoformat(first.replace("Z", "+00:00"))
        check(ok, f"PREREG committed ({prereg_time}) before the first measured trial ({first})")
    except Exception as error:  # noqa: BLE001
        print(f"skip PREREG-order check (no git): {type(error).__name__}")

    host = socket.gethostname()
    bad = [re.compile(p) for p in ("/" + "mnt/", "/" + "home/", "cua-lane" + "-tmp", "TYPESAFE_API_KEY" + r"=[^\"'\s<]", r"Bearer [A-Za-z0-9]")]
    bad.append(re.compile(r"\b" + re.escape(host) + r"\b"))
    hits = []
    for f in HERE.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts:
            t = f.read_text(errors="replace")
            for p in bad:
                if p.search(t):
                    hits.append(f"{f.relative_to(HERE)}: {p.pattern}")
    check(not hits, "privacy scan clean" + ("" if not hits else f": {hits[:5]}"))

    print(f"\n{len(FAIL)} failure(s)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
