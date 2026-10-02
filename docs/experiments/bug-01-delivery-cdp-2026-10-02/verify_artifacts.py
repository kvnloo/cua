"""Verify the BUG-01 packet: recompute every number from raw/, check receipts and scan for privacy leaks.

usage: python3 verify_artifacts.py   (exit 0 = all checks pass)
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_summary  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, what: str) -> None:
    print(("PASS " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def utc_ms(stamp: str) -> float:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000


def lock_window(name: str) -> tuple[float, float, str]:
    text = (HERE / "raw" / name).read_text()
    acq = re.search(r"lock_acquired_(\w+) (\S+)", text)
    rel = re.search(r"lock_released (\S+)", text)
    return utc_ms(acq.group(2)), utc_ms(rel.group(1)) + 999, acq.group(1)


def main() -> int:
    summary = make_summary.build(HERE)
    committed = json.loads((HERE / "bug01-summary.json").read_text())
    check(summary == committed, "bug01-summary.json equals a fresh recomputation from raw/")

    a, ga, b, u = summary["part_a"], summary["part_a_gates"], summary["part_b"], summary["unit"]
    prov = json.loads((HERE / "provenance.json").read_text())
    # Part A numbers quoted in the README.
    check(a["baseline"]["trials"] == 70 and a["fix"]["trials"] == 70, "part A: 70 + 70 trials, every trial kept")
    check(a["baseline"]["harness_errors"] == 0 and a["fix"]["harness_errors"] == 0, "part A: 0 harness errors")
    check(a["baseline"]["arms"]["T"]["click_delivery_mode"] == {"background": 20}, "part A baseline: T receipts delivery=background 20/20")
    check(a["baseline"]["arms"]["T"]["page_trusted_foreground"] == 20 and a["baseline"]["arms"]["T"]["verified"] == 20, "part A baseline: T page trusted-foreground 20/20, verified 20/20")
    check(a["fix"]["arms"]["T"]["click_delivery_mode"] == {"foreground": 20}, "part A fix: T receipts delivery=foreground 20/20")
    check(a["fix"]["arms"]["T"]["page_trusted_foreground"] == 20 and a["fix"]["arms"]["T"]["verified"] == 20, "part A fix: T page trusted-foreground 20/20, verified 20/20")
    check(a["receipt_field_changes_baseline_to_fix"] == [{"arm": "T", "baseline": {"background": 20}, "field": "delivery_mode", "fix": {"foreground": 20}, "receipt": "click"}], "part A: the only receipt field change is T click delivery_mode")
    check(ga["disposition"] == "CONFIRMED_BUG", "part A gate: CONFIRMED_BUG")
    check(u["main-test"]["head"] == prov["sources"]["commits"]["failing_test_main_plus_test"], "UNIT red run head == failing-test commit")
    check(u["fix"]["head"] == prov["sources"]["commits"]["fix"], "UNIT green run head == fix commit")
    check(u["main-test"]["red_test"] == "FAILED" and u["fix"]["red_test"] == "ok", "UNIT: red at main+test, green at fix")
    flaky = {k for k in u["core_outcome_changes_main_test_to_fix"] if k.startswith("history::")}
    other = {k for k, v in u["core_outcome_changes_main_test_to_fix"].items() if k not in flaky and not (v[0] is None and k.startswith("browser::cdp_counters::"))}
    check(other == {"browser::v2_tests::foreground_trusted_browser_input_receipt_does_not_claim_background_delivery"}, "UNIT: besides new counter tests and history flakes, only the red test changed outcome")
    check(len(u["history_rerun_at_fix"]) == 5 and all("0 failed" in line for line in u["history_rerun_at_fix"]), "UNIT: history tests pass 5/5 in isolation at the fix")
    check(len(u["instr"]["cdp_counters_tests_ok"]) == 6, "UNIT: 6 cdp_counters tests pass")
    check(u["part_b_repro_ignored_run"] == {"browser::v2_tests::repeated_browser_calls_do_not_accumulate_cdp_tab_sessions": "FAILED"}, "UNIT: part B repro fails when run with --ignored")
    # Part B numbers quoted in the README.
    check(b["calls_measured"] == 1800 and b["calls_accepted"] == 1800 and b["unmatched_calls_without_counter_line"] == 0, "part B: 1800/1800 calls accepted, all joined to a counter line")
    check(all(v["attach_sent_during_calls"] == v["calls"] and v["detach_sent_during_calls"] == 0 for v in b["attach_detach_per_series"].values()), "part B: exactly 1 attach and 0 detach per measured call in every series")
    check(b["M1_live_sessions_end_of_L"] == [304.0, 304.0, 304.0] and b["M1_live_sessions_max_C"] == 11.0, "part B: 304 live sessions at the end of each L, max 11 in C")
    check(b["gates"]["disposition"] == "ACCUMULATION_ONLY", "part B gate: ACCUMULATION_ONLY")
    burst = b["exploratory_not_preregistered_post_navigation_burst"]
    check([p["events_next_call"] for p in burst["L"]] == [1, 101, 201] * 3, "part B exploratory: post-navigation bursts 1/101/201 events in each L")
    # Binary identity in raw session envs.
    for label, key in (("baseline", "baseline"), ("fix", "fix")):
        env = json.loads((HERE / "raw" / "part-a" / f"{label}-session-env.json").read_text())
        check(env["driver_sha256"] == prov["binaries"][key]["sha256"], f"part A {label}: Driver sha256 matches provenance")
        check(env["driver_version_in_session"] == "cua-driver 0.32.0", f"part A {label}: version recorded in session")
    envb = json.loads((HERE / "raw" / "part-b" / "session-env.json").read_text())
    check(envb["driver_sha256"] == prov["binaries"]["instrumented"]["sha256"], "part B: Driver sha256 matches provenance")
    # Lock receipts.
    for name, raw_glob, field in (("part-a-baseline.lockinfo", "part-a/baseline-*.jsonl", None), ("part-a-fix.lockinfo", "part-a/fix-*.jsonl", None)):
        t0, t1, mode = lock_window(name)
        times = []
        for p in sorted((HERE / "raw").glob(raw_glob)):
            rec = json.loads(p.read_text().splitlines()[0])
            if rec.get("event") == "trial":
                times += [rec["type"]["t_start_ms"], (rec.get("click") or {}).get("t_end_ms") or rec["type"]["t_end_ms"]]
        check(mode == "shared" and len(times) == 140 and all(t0 <= t <= t1 for t in times), f"{name}: all 70 trials inside the SHARED quiet-lane window")
    t0, t1, mode = lock_window("part-b-measured.lockinfo")
    calls = [json.loads(line) for line in (HERE / "raw" / "part-b" / "calls.jsonl").read_text().splitlines()]
    times = [c["t_start_ms"] for c in calls if c.get("event") == "call"] + [c["t_end_ms"] for c in calls if c.get("event") == "call"]
    check(mode == "exclusive" and all(t0 <= t <= t1 for t in times), "part-b-measured.lockinfo: every part B call inside the EXCLUSIVE quiet-lane window")
    off = (HERE / "raw" / "default-off-check.txt").read_text()
    check("set in session command: 0" in off and "*counter* in retained session dir + smoke outdir: 0" in off and "containing cua.bug01.cdp_counters: 0" in off and "rc_verify_setup=0" in off, "default-off smoke: rc 0 and no counter file")
    # SHAs exist in the repository (when run from a clone that has them).
    in_repo = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--git-dir"], capture_output=True).returncode == 0
    if not in_repo:
        print("SKIP commit-existence checks (not inside a git clone)")
    for name, sha in prov["sources"]["commits"].items():
        if in_repo and re.fullmatch(r"[0-9a-f]{40}", sha):
            ok = subprocess.run(["git", "-C", str(HERE), "cat-file", "-e", sha + "^{commit}"], capture_output=True).returncode == 0
            check(ok, f"commit {name} {sha[:9]} exists")
    # Privacy scan.
    host = socket.gethostname()
    abs_path = re.compile(r"(?<![A-Za-z0-9_>.\-])/(?:home|mnt|tmp|root|var/tmp)/")
    secretish = re.compile(r"(sk-[A-Za-z0-9]{16,}|TYPESAFE_API_KEY\s*=\s*\S+|ghp_[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY)")
    leaks = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        text = p.read_text(errors="replace")
        rel = p.relative_to(HERE)
        if abs_path.search(text):
            leaks.append(f"{rel}: absolute path")
        if host and len(host) > 2 and host in text:
            leaks.append(f"{rel}: host name")
        if secretish.search(text):
            leaks.append(f"{rel}: secret-like token")
    check(not leaks, "privacy scan: no absolute local paths, host name or secret-like tokens" + ("" if not leaks else f" ({leaks[:5]})"))
    print(f"\n{len(FAILS)} failing check(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
