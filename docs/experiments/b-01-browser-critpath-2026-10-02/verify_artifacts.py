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
 12. B-01R text fix: the README quotes the MCP admission cost per tools/call, per action step and
     per task, and the observation cost per snapshot, exactly as recomputed from raw/; neither
     '4.4 ... per call' nor 'under the cargo lock' appears outside Deviation 13's before-quotes;
     the Driver binary row and provenance.json say the build lock was not receipted.
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


def per_call_costs(trials: list[dict], cls: str, arm: str, block: str) -> dict[str, float]:
    """MCP admission and observation costs of one arm, recomputed from raw/ with b01_analysis.

    Per task = mean over valid trials of the decomposition's sub-spans. The divisors are counted
    from raw/ as well: tools/call windows inside T that carry an mcp.line_read mark, the action
    windows inside T, and the snapshot windows inside T.
    """
    import statistics

    adm, cdp, proc, calls, steps, snaps = [], [], [], [], [], []
    for t in trials:
        s = t["summary"]
        if s["cls"] != cls or s["arm"] != arm or s["block"] != block or not A.is_valid(t)[0]:
            continue
        d = A.decompose(t)
        t0 = d["T0_ns"]
        t1 = t0 + round(d["T_runner_ms"] * 1e6)
        wins = [w for w in A._windows(t["events"]) if w["t1"] >= t0 and w["t0"] <= t1]
        reads = [m["t_mono_ns"] for m in t["trace"] if m["phase"] == "mcp.line_read"]
        calls.append(sum(1 for w in wins if any(w["t0"] <= x <= w["t1"] for x in reads)))
        steps.append(sum(1 for w in wins if w["label"].startswith("action")))
        snaps.append(len(d["observations"]))
        adm.append(d["sub"].get("pre_admission_validate", 0.0) + d["sub"].get("pre_inner_validate", 0.0))
        cdp.append(d["sub"].get("observation_cdp", 0.0))
        proc.append(d["sub"].get("observation_processing", 0.0))
    assert len(set(calls)) == len(set(steps)) == len(set(snaps)) == 1, (cls, arm, calls, steps, snaps)
    per_task = statistics.mean(adm)
    return {"n": len(adm), "calls_per_task": calls[0], "steps_per_task": steps[0], "snapshots_per_task": snaps[0],
            "admission_per_task": per_task, "admission_per_call": per_task / calls[0],
            "admission_per_step": per_task / steps[0], "obs_cdp_per_task": statistics.mean(cdp),
            "obs_cdp_per_snapshot": statistics.mean(cdp) / snaps[0], "obs_proc_per_task": statistics.mean(proc),
            "obs_proc_per_snapshot": statistics.mean(proc) / snaps[0]}


def check_text_fix(readme: str, trials: list[dict], summary: dict) -> None:
    """12. B-01R text fix: per-call / per-step / per-task admission cost, per-snapshot observation cost,
    and the unreceipted build lock. Deviation 13 quotes the superseded wording verbatim as its "before"
    column, so the absence checks run on the README with that one section removed."""
    start = readme.find("13. **Text fix pass (B-01R).**")
    check(start >= 0, "12 README has Deviation 13 'Text fix pass (B-01R)'")
    end = readme.index("## Limits")
    body = readme[:start] + readme[end:] if start >= 0 else readme
    check(not re.search(r"4\.4[^|\n]{0,20}per call", body), "12 no '4.4 ... per call' outside the Deviation 13 before-quotes")
    check("under the cargo lock" not in body, "12 no 'under the cargo lock' outside the Deviation 13 before-quotes")
    prov_row = next(line for line in readme.splitlines() if line.startswith("| Driver binary |"))
    check("documented command; lock not receipted (Deviation 9)" in prov_row,
          "12 provenance Driver binary row: 'documented command; lock not receipted (Deviation 9)'")
    prov = json.loads((HERE / "provenance.json").read_text())
    check("not receipted" in prov["driver_binary"].get("lock", "")
          and "build b01-f5c991e59" in prov["lock_ledger"]["unreceipted_runs"],
          "12 provenance.json driver_binary.lock says the build lock was not receipted")

    fill = per_call_costs(trials, "fill", "K3", "m")
    tog = per_call_costs(trials, "toggle", "K5", "v")
    mod = per_call_costs(trials, "modal", "K5", "v")
    e2 = summary["E2"]
    for cls, c in (("fill", fill), ("toggle", tog), ("modal", mod)):
        want = e2[cls]["best"]["untested_plausibly_deletable_ms"]["mcp_admission_tool_list_validation"]
        check(abs(c["admission_per_task"] - want) < 1e-3 and c["calls_per_task"] == 4 and c["steps_per_task"] == 2
              and c["snapshots_per_task"] == 2,
              f"12 {cls} {e2[cls]['best_composed_arm']}: admission per task {c['admission_per_task']:.3f} ms equals the "
              f"summary; {c['calls_per_task']} tools/call, {c['steps_per_task']} action steps, "
              f"{c['snapshots_per_task']} snapshots per task (n = {c['n']})")
    f = fill
    quotes = [
        f"about {f['admission_per_call']:.1f} ms per tools/call, about {f['admission_per_step']:.1f} ms per action step "
        f"(2 calls) and {f['admission_per_task']:.1f} ms per task (4 calls)",
        f"{f['admission_per_task']:.1f} ms per task sits in",
        f"about {f['admission_per_call']:.1f} ms per tools/call and {f['admission_per_step']:.1f} ms per action step",
        f"admission span {tog['admission_per_task']:.1f} / {mod['admission_per_task']:.1f} ms per task, about "
        f"{tog['admission_per_call']:.1f} / {mod['admission_per_call']:.1f} ms per tools/call",
        f"Per-snapshot cost (mean of the 2): {f['obs_cdp_per_snapshot']:.1f} ms CDP vs {f['obs_proc_per_snapshot']:.1f} ms "
        f"processing ({f['obs_cdp_per_task']:.1f} and {f['obs_proc_per_task']:.1f} ms per task)",
    ]
    for q in quotes:
        check(q in body, f"12 README quotes the raw recomputation: '{q}'")


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

    check_text_fix(readme, trials, summary)

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
