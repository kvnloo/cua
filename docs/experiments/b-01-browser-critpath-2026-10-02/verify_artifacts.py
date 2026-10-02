"""Verify the B-01 packet: recompute every headline from raw/ and check receipts.

    python3 verify_artifacts.py            # exit 0 = all checks pass

Checks:
  1. b01-summary.json equals a fresh recomputation from raw/ (analyze.build).
  2. README quotes the headline numbers that the summary holds.
  3. 0 provider HTTP: every trial and manifest records 0 non-loopback connects, the
     manifests say provider=mock, and the dry live-request validation made 0 connects.
  4. Locks: every measured trial (blocks m, v, t) lies inside one EXCLUSIVE quiet-lane
     window; every control trial inside a SHARED window of <= 10 trials.
     4b. raw/lock-ledger.json lists every run manifest (shakedown included) with the lock mode
     its receipt shows; every run that broke or cannot show the lock rule is named in the
     README deviations; no shakedown trial is in the analysed set.
  5. PREREG.json was committed before the first measured trial (receipt + git, if present).
  6. The #24 fixtures are verbatim copies of kvnloo/cua 5474aa31f (when that git object exists).
  7. UNIT receipts: the touched suites passed with 0 failures.
  8. Default-off smoke: 5/5 verified with no trace or knob variable and no trace file found.
  9. Privacy: no absolute local path, temp path, user name or host name in any packet file.
 10. Stale-ref controls: refused before dispatch (0 dispatch marks in the call window), code
     browser_ref_stale.
 11. E2: every material row carries one of DELETED / IRREDUCIBLE / OWNER_DECISION / UNTESTED
     (or the mock-decision label).
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import analyze  # noqa: E402
import b01_analysis as A  # noqa: E402

FAIL: list[str] = []


def check(cond: bool, what: str) -> None:
    print(("PASS " if cond else "FAIL ") + what)
    if not cond:
        FAIL.append(what)


def main() -> None:
    raw = HERE / "raw"
    summary = json.loads((HERE / "b01-summary.json").read_text())
    fresh = analyze.build(raw)
    check(fresh == summary, "1 b01-summary.json equals a fresh recomputation from raw/")

    readme = (HERE / "README.md").read_text()
    heads = json.loads((HERE / "headline-numbers.json").read_text())
    for key, path in heads.items():
        node = summary
        for part in path["path"]:
            node = node[part] if not isinstance(node, list) else node[int(part)]
        text = path["fmt"].format(node)
        check(text in readme, f"2 README quotes {key} = {text}")

    trials = A.load_trials(raw)
    net = sum(t["summary"].get("network", {}).get("non_loopback_connect_attempts", 0) for t in trials)
    check(net == 0, f"3 non-loopback connects across {len(trials)} trials = {net}")
    manifests = sorted(raw.glob("run-manifest-*.json"))
    for m in manifests:
        d = json.loads(m.read_text())
        check(d.get("provider") == "mock" and d.get("network", {}).get("non_loopback_connect_attempts") == 0,
              f"3 {m.name}: provider=mock, 0 non-loopback connects")
    live = json.loads((raw / "live-request-validation.json").read_text())
    check(live["socket_connect_attempts"] == 0 and live["all_schema_valid"],
          "3 dry live-request validation: all schema-valid, 0 socket connects")

    by_name = {t["name"]: t for t in trials}
    for m in manifests:
        d = json.loads(m.read_text())
        locks = d.get("locks", [])
        acq = [x for x in locks if x["event"] == "lock_acquired"]
        rel = [x for x in locks if x["event"] == "lock_released"]
        for block, a, r in zip(d["blocks"], acq, rel):
            mode = a["mode"]
            starts = [by_name[n]["events"][0]["t_mono_ns"] for n in block if n in by_name]
            ends = [by_name[n]["events"][-1]["t_mono_ns"] for n in block if n in by_name]
            inside = all(a["t_mono_ns"] <= s for s in starts) and all(e <= r["t_mono_ns"] for e in ends)
            kinds = {by_name[n]["summary"]["block"][0] for n in block if n in by_name}
            if kinds & {"m", "v", "t"}:
                check(mode == "exclusive" and inside, f"4 {m.name}: {len(block)} measured trials inside an EXCLUSIVE window")
            else:
                check(mode == "shared" and inside and len(block) <= 10,
                      f"4 {m.name}: control block of {len(block)} inside a SHARED window")
        if d["plan_kind"] in ("measured", "controls"):
            check(len(acq) == len(d["blocks"]) == len(rel), f"4 {m.name}: one acquire/release per block")

    ledger = json.loads((raw / "lock-ledger.json").read_text())
    runs = {r["run"]: r for r in ledger["runs"]}
    for m in manifests + sorted((raw / "shakedown").glob("run-manifest-*.json")):
        d = json.loads(m.read_text())
        acq = [x for x in d.get("locks", []) if x["event"] == "lock_acquired"]
        mode = acq[0]["mode"] if acq else "none"
        n = sum(len(b) for b in d["blocks"])
        hits = [r for r in runs.values() if r.get("lock_mode") == mode and r.get("trials") == n
                and (r["run"] == d["plan_kind"] or r["run"].startswith(d["plan_kind"]))]
        check(bool(hits), f"4b {m.relative_to(raw)}: in lock-ledger.json with lock mode {mode} ({n} trials)")
    bad = [r["run"] for r in ledger["runs"] if r["compliant"] is not True]
    dev = readme[readme.index("## Deviations"):readme.index("## Limits")]
    check(all(r.removeprefix("build ") in dev for r in bad),
          f"4b README deviations name every run without a compliant lock receipt: {bad}")
    check(not any(t["name"].startswith("shake") for t in trials), "4b no shakedown trial in the analysed set")

    rec = json.loads((raw / "timeline-receipts.json").read_text())
    check(rec["prereg_commit_utc"] < rec["measured_start_utc"], "5 PREREG commit precedes the measured run (receipt)")
    mw = runs["measured"]["windows"][0]
    check(rec["prereg_commit_utc"] < rec["measured_lock_acquired_utc"] == mw["acquired_utc"],
          f"5 PREREG commit precedes the EXCLUSIVE lock acquisition {mw['acquired_utc']}")
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", rec["prereg_commit"]], cwd=HERE,
                             capture_output=True, text=True, check=True).stdout.strip()
        check(bool(out), f"5 PREREG commit {rec['prereg_commit'][:9]} exists in git ({out})")
        src = subprocess.run(["git", "show", f"{rec['prereg_commit']}:docs/experiments/{HERE.name}/PREREG.json"],
                             cwd=HERE, capture_output=True, text=True, check=True).stdout
        check(json.loads(src) == json.loads((HERE / "PREREG.json").read_text()), "5 PREREG.json unchanged since its commit")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("SKIP 5 git not available for the PREREG commit check")

    try:
        orig = subprocess.run(["git", "show", "5474aa31f090529e2a53466993bd19ce03406225:scripts/repro/issue24_battery_live.py"],
                              cwd=HERE, capture_output=True, text=True, check=True).stdout
        ours = (HERE / "b01_fixtures.py").read_text()
        for marker_a, marker_b in (('    "toggle-confirm": """', '    "two-fields": """'),
                                   ('    "modal": """', '    "ambiguous": """'),
                                   ("class State:", "def _named("), ("def oracle_ok(", "def expected_route(")):
            i = orig.index(marker_a)
            chunk = orig[i:orig.index(marker_b, i)]
            check(chunk in ours, f"6 verbatim fixture copy: {marker_a.strip()[:24]}")
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        print("SKIP 6 git object 5474aa31f not available")

    expect = {"cargo-test-b01-core.log": 7, "cargo-test-b01-linux.log": 3, "cargo-test-core-lib.log": 818,
              "cargo-test-platform-linux-lib.log": 602, "cargo-test-sdk-lib.log": 95, "cargo-test-cua-driver-bins.log": 290}
    for name, n in expect.items():
        text = (raw / "unit" / name).read_text()
        check(f"test result: ok. {n} passed; 0 failed" in text and "test result: FAILED" not in text,
              f"7 {name}: {n} passed, 0 failed")

    sm = summary["smoke"]
    check(sm["n"] == 5 and sm["verified"] == 5 and sm["trace_set"] == 0 and sm["knob_set"] == 0,
          "8 default-off smoke: 5/5 verified, trace and knob unset")
    tc = (raw / "default-off-trace-check.txt").read_text()
    check("trace_named_files=0" in tc and "trace_field_files=0" in tc, "8 no trace file in the smoke session or output")

    st = summary["controls"]["stale_ref"]["rows"]
    inv = summary["invariants"]
    check(all(r["dispatch_marks"] == 0 for r in st) and inv["stale_ref_trials_with_dispatch_marks"] == 0
          and inv["stale_ref_refusal_codes"] == ["browser_ref_stale"],
          f"10 stale-ref: {len(st)} refused before dispatch with code browser_ref_stale")

    allowed = ("DELETED", "IRREDUCIBLE", "OWNER_DECISION", "UNTESTED", "live decision")
    off = [(c, lab, r["component"]) for c, e in summary["E2"].items() for lab in ("best", "baseline")
           for r in e[lab]["rows"] if r["material"] and not r["verdict"].startswith(allowed)]
    check(not off, f"11 E2 material rows all carry an allowed verdict (offenders: {off})")

    host = socket.gethostname()
    user = os.environ.get("USER") or ""
    roots = ["home", "mnt", "tmp", "var" + "/tmp"]  # built from parts so this file does not match itself
    pat = re.compile("|".join("/" + r + "/" for r in roots) + "|cua-lane" + "-tmp|x11-session\\.[A-Za-z0-9]{6}")
    offenders = []
    for path in HERE.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        data = path.read_bytes()
        if path.suffix == ".gz":
            import gzip
            data = gzip.decompress(data)
        text = data.decode("utf-8", "replace")
        if pat.search(text) or (host and host in text) or (user and len(user) > 3 and f"/{user}/" in text):
            offenders.append(str(path.relative_to(HERE)))
    check(not offenders, f"9 privacy scan over every packet file (offenders: {offenders})")

    print(f"\n{len(FAIL)} failure(s)")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
