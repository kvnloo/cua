#!/usr/bin/env python3
"""RECERT-FIX a3 analysis (stdlib only): every counted record -> recert-summary.json.

Applies PREREG.json's refusal classification and gates to the raw records:
  raw/fix02/native/<arm>/<topology>/<row>/b*.jsonl   FIX-02 native rows (wave-3 harness)
  raw/fix02/w2/<arm>/<row>/b*.jsonl                  Part B two-window rows
  raw/fix02/browser/<block>-<phase>-<arm>[-code]/    F3 (py, ts) and F4 cells
  raw/own09r/{sdk/{main,stress},cabi}/<M|P>/*.jsonl  OWN-09R rows (harness verdicts)
  raw/own16w/<X11|SW>/<U|F>/<T1|T2>/raw/             OWN-16W sessions (wave-3 harness records)
  raw/unit/**                                        unit logs (red/green, suites)
Every attempt stays in the denominator. usage: analyze.py [--check] (compare with the committed summary)
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
ARMS = ("U", "F")


def jl(path):
    out = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ── call classification (PREREG refusal_classification) ─────────────────────
def sc(call):
    return ((call.get("response") or {}).get("structuredContent")) or {}


def not_success(call):
    s = sc(call)
    return bool(call.get("is_error")) or "rpc_error" in (call.get("response") or {}) \
        or isinstance(s.get("refusal"), dict) or s.get("effect") == "refused" or bool(call.get("refusal_code"))


def changed(call, key=None):
    pre, post = call.get("pre") or {}, call.get("post") or {}
    if key is None:
        return pre != post
    return pre.get(key) != post.get(key)


def refused(call):
    return not_success(call) and not changed(call)


def landed(call, key=None):
    return changed(call, key)


def verified(call, key=None):
    return not not_success(call) and changed(call, key)


def step(rec, name):
    for call in rec["calls"]:
        if call["step"] == name:
            return call
    return None


def wkey(call, window):
    """Per-window state change in the two-window fixture."""
    pre = ((call.get("pre") or {}).get("P") or {}).get("windows") or {}
    post = ((call.get("post") or {}).get("P") or {}).get("windows") or {}
    a, b = dict(pre.get(window) or {}), dict(post.get(window) or {})
    a.pop("open", None), b.pop("open", None)
    return a != b


# ── FIX-02 native ────────────────────────────────────────────────────────────
def native(arm):
    rows = defaultdict(list)
    headers = []
    for path in sorted(glob.glob(os.path.join(RAW, "fix02", "native", arm, "*", "*", "b*.jsonl"))):
        for rec in jl(path):
            if rec.get("kind") == "block":
                headers.append({"file": os.path.relpath(path, HERE), "sha256": rec["driver_sha256"],
                                "version": rec["driver_version"], "display": rec.get("display")})
            elif rec.get("kind") == "attempt":
                rec["_file"] = os.path.relpath(path, HERE)
                key = rec["row"] + ("_forged" if rec.get("forged") else "")
                rows[key].append(rec)
    out = {}
    e4 = Counter()
    for key, recs in sorted(rows.items()):
        res = Counter()
        res["n"] = len(recs)
        for rec in recs:
            r = rec["row"]
            if r in ("I2",):
                b_b, b_a, tail = (step(rec, "B-uses-A-token-on-B-pid"), step(rec, "B-uses-A-token-on-A-pid"),
                                  step(rec, "A-uses-own-token"))
                both_refused = refused(b_b) and refused(b_a)
                res["B_refused_both"] += both_refused
                res["B_landed_on_A"] += landed(b_a, "A")
                res["B_landed_any"] += landed(b_b) or landed(b_a)
                res["A_tail_verified"] += verified(tail, "A")
                res["unverified_success"] += (not not_success(b_a) and not changed(b_a)) + \
                    (not not_success(b_b) and not changed(b_b))
                e4["cross_session_mutations"] += landed(b_b) or landed(b_a)
                res["pass"] += both_refused and verified(tail, "A")
            elif r == "I2d":
                probe, derived, tail = (step(rec, "B-stale-probe-on-A-pid"), step(rec, "B-uses-derived-token-on-A-pid"),
                                        step(rec, "A-uses-own-token"))
                res["disclosed_A_handle"] += bool(rec.get("disclosed_A_handle"))
                res["derived_refused"] += refused(derived)
                res["derived_landed"] += landed(derived, "A")
                res["derived_from_disclosure"] += rec.get("derived_source") == "disclosure"
                res["A_tail_verified"] += verified(tail, "A")
                res["probe_landed"] += landed(probe)
                e4["cross_session_mutations"] += landed(derived) or landed(probe)
                res["pass"] += refused(derived) and not rec.get("disclosed_A_handle") and verified(tail, "A")
            elif r in ("I5p", "I5ps", "I5pt"):
                tok = step(rec, "gen2-uses-gen1-token")
                cap = step(rec, "gen2-uses-gen1-capture")
                res["token_refused"] += refused(tok)
                res["token_landed"] += landed(tok)
                res["strings_differ"] += rec.get("gen1_token") != rec.get("gen2_token")
                e4["stale_dispatches"] += landed(tok) + (landed(cap) if cap else 0)
                if cap is not None:
                    res["capture_refused"] += refused(cap)
                    res["capture_landed"] += landed(cap)
                    res["pass"] += refused(tok) and refused(cap) and rec.get("gen1_token") != rec.get("gen2_token")
                else:
                    el = rec.get("gen2_element_at_gen1_index") or {}
                    res[f"gen2_element_at_gen1_index:{el.get('label')}"] += 1
                    res["pass"] += refused(tok)
                res["unverified_success"] += not not_success(tok) and not changed(tok)
            elif r == "P":
                ok = all(verified(c, c["actor"]) for c in rec["calls"] if c["step"].startswith("own-token-"))
                res["both_verified"] += ok
                res["pass"] += ok
            elif r == "I3s":
                first, second = rec["order"][0], rec["order"][1]
                c1 = step(rec, f"{first}-uses-token-after-{second}-observed")
                c2 = step(rec, f"{second}-uses-own-latest-token")
                res["superseded_first_refused"] += refused(c1)
                res["superseded_first_landed"] += landed(c1)
                res["second_verified"] += verified(c2, "A")
            elif r == "I1":
                b, a = step(rec, "B-uses-A-capture"), step(rec, "A-uses-own-capture")
                res["B_refused"] += refused(b)
                res["B_landed"] += landed(b)
                res["A_tail_verified"] += verified(a, "A")
                e4["cross_session_mutations"] += landed(b)
                res["pass"] += refused(b) and verified(a, "A")
            codes = Counter(c.get("refusal_code") for c in rec["calls"] if c.get("refusal_code"))
            for code, n in codes.items():
                res[f"code:{code}"] += n
        out[key] = dict(res)
    return out, headers, dict(e4)


# ── Part B two-window rows ──────────────────────────────────────────────────
def w2(arm):
    rows = defaultdict(list)
    headers = []
    for path in sorted(glob.glob(os.path.join(RAW, "fix02", "w2", arm, "W2*", "b*.jsonl"))):
        for rec in jl(path):
            if rec.get("kind") == "block":
                headers.append({"file": os.path.relpath(path, HERE), "sha256": rec["driver_sha256"],
                                "version": rec["driver_version"], "fixture_sha256": rec.get("fixture_sha256")})
            elif rec.get("kind") == "attempt":
                rows[rec["row"]].append(rec)
    out, e4 = {}, Counter()
    for row, recs in sorted(rows.items()):
        res = Counter(n=len(recs))
        for rec in recs:
            if row == "W2a":
                x = step(rec, "B-uses-A-w1-token")
                pa, pb = step(rec, "A-uses-own-w1-token"), step(rec, "B-uses-own-w2-token")
                res["cross_refused"] += refused(x)
                res["cross_landed"] += landed(x)
                res["positives_verified"] += verified(pa, "P") and wkey(pa, "w1") and not wkey(pa, "w2") \
                    and verified(pb, "P") and wkey(pb, "w2") and not wkey(pb, "w1")
                e4["cross_session_mutations"] += landed(x)
                res["unverified_success"] += not not_success(x) and not changed(x)
                res["pass"] += refused(x) and res["positives_verified"] >= 0 and (
                    verified(pa, "P") and wkey(pa, "w1") and verified(pb, "P") and wkey(pb, "w2"))
            elif row == "W2b":
                p1, p2 = step(rec, "A-uses-w1-token-after-observing-w2"), step(rec, "A-uses-w2-token")
                ok = verified(p1, "P") and wkey(p1, "w1") and not wkey(p1, "w2") and \
                    verified(p2, "P") and wkey(p2, "w2") and not wkey(p2, "w1")
                res["w1_after_w2_verified"] += verified(p1, "P") and wkey(p1, "w1")
                res["positives_verified"] += ok
                res["pass"] += ok
            elif row == "W2c":
                x, p = step(rec, "A-clicks-in-w2-with-w1-capture"), step(rec, "A-clicks-in-w2-with-w2-capture")
                res["mismatch_refused"] += refused(x)
                res["mismatch_landed"] += landed(x)
                ok = verified(p, "P") and wkey(p, "w2") and not wkey(p, "w1")
                res["positives_verified"] += ok
                e4["stale_dispatches"] += landed(x)
                res["unverified_success"] += not not_success(x) and not changed(x)
                res["pass"] += refused(x) and ok
            elif row == "W2d":
                x, p = step(rec, "A-uses-closed-w1-token"), step(rec, "A-uses-w2-token-after-w1-closed")
                res["w1_closed_confirmed"] += bool(rec.get("w1_closed_confirmed"))
                res["closed_refused"] += refused(x)
                res["closed_landed"] += landed(x)
                ok = verified(p, "P") and wkey(p, "w2")
                res["positives_verified"] += ok
                e4["stale_dispatches"] += landed(x)
                res["unverified_success"] += not not_success(x) and not changed(x)
                res["pass"] += refused(x) and ok and bool(rec.get("w1_closed_confirmed"))
            for c in rec["calls"]:
                if c.get("refusal_code"):
                    res[f"code:{c['refusal_code']}"] += 1
                if c["tool"] == "click" and not not_success(c):
                    res[f"route:{sc(c).get('route')}"] += 1
        out[row] = dict(res)
    return out, headers, dict(e4)


# ── browser F3 / F4 ─────────────────────────────────────────────────────────
def browser(arm):
    out, e4, validity = {}, Counter(), []
    for d in sorted(glob.glob(os.path.join(RAW, "fix02", "browser", f"*-*-{arm}*"))):
        if not os.path.isdir(d):
            continue
        v = json.load(open(os.path.join(d, "validity.json")))
        validity.append({"dir": os.path.relpath(d, HERE), "ok": v.get("ok"), "head": v.get("head"),
                         "ts_head": v.get("ts_head"), "driver_sha256": v["driver"]["sha256"],
                         "driver_version": v["driver"]["version"]})
        for cell in jl(os.path.join(d, "cells.jsonl")):
            phase = cell["phase"]
            runtime = cell.get("runtime") or ("ts" if phase == "f3ts" else "py")
            key = f"F4" if phase == "f4" else f"F3-{runtime}-{cell['code']}"
            res = out.setdefault(key, Counter())
            res["n"] += 1
            if phase == "f4":
                ok = cell["old_ref_result"] == "refused" and cell["old_node_events"] == 0 and cell["rebind_verified"]
                res["old_ref_refused"] += cell["old_ref_result"] == "refused"
                res["old_ref_accepted"] += cell["old_ref_result"] == "accepted"
                res["old_node_events"] += cell["old_node_events"]
                res["rebind_verified"] += bool(cell["rebind_verified"])
                res["pass"] += ok
                e4["stale_dispatches"] += cell["old_ref_result"] == "accepted"
                continue
            red = cell["redispatches_after_refusal"]
            res["redispatches"] += red
            res["duplicate_submits"] += cell["duplicate_submits"]
            res["injected"] += bool(cell["injected"])
            res[f"outcome:{cell['outcome']}"] += 1
            res["unverified_success"] += bool(cell.get("unverified_success"))
            e4["duplicates"] += cell["duplicate_submits"]
            e4["unverified_successes"] += bool(cell.get("unverified_success"))
            if cell["code"] == "trust_unknown":
                blind = red > 0
                res["blind_redispatches"] += red if blind else 0
                e4["blind_redispatches"] += red
                res["pass"] += (red == 0 and cell["outcome"] == "unknown" and cell["journal_applied"] == 1
                                and cell["injected"])
            elif cell["code"] == "stale":
                res["pass"] += (red == 1 and cell["outcome"] == "verified" and cell["independently_verified"]
                                and cell["injected"])
    return {k: dict(v) for k, v in out.items()}, validity, dict(e4)


# ── OWN-09R ────────────────────────────────────────────────────────────────
def own09r():
    out = {}
    for path in sorted(glob.glob(os.path.join(RAW, "own09r", "*", "**", "*.jsonl"), recursive=True)):
        rel = os.path.relpath(path, os.path.join(RAW, "own09r"))
        parts = rel.split(os.sep)
        if parts[0] not in ("sdk", "cabi"):
            continue
        arm = parts[-2]
        variant = os.path.basename(path)[:-6]
        recs = jl(path)
        res = out.setdefault(arm, {}).setdefault(variant, Counter())
        for rec in recs:
            res["n"] += 1
            res[str(rec.get("verdict"))] += 1
            res["harness_error"] += bool(rec.get("error"))
    return {a: {k: dict(v) for k, v in vs.items()} for a, vs in out.items()}


def own09r_gates(m):
    P, M = m.get("P", {}), m.get("M", {})

    def cnt(arm, variant, verdict):
        return (arm.get(variant) or {}).get(verdict, 0)

    def n(arm, variant):
        return (arm.get(variant) or {}).get("n", 0)

    gates = {
        "P_R1D_pass_40": cnt(P, "R1D__flag_before_admission", "PASS") == 40 == n(P, "R1D__flag_before_admission"),
        "P_R6_pass_80": cnt(P, "R6__shutdown_after_cancel", "PASS") + cnt(P, "R6__end_session_after_cancel", "PASS") == 80
        == n(P, "R6__shutdown_after_cancel") + n(P, "R6__end_session_after_cancel"),
        "P_R2_pass_40": cnt(P, "R2__cancel_after_admission", "PASS") == 40 == n(P, "R2__cancel_after_admission"),
        "P_R4_pass": all(cnt(P, v, "PASS") == 40 == n(P, v) for v in (
            "R4__after_completion", "R4__after_inflight_cancel", "R4C__after_completion_retained_token",
            "R4C__after_inflight_cancel_retained_token")),
        "P_R7_pass_40": cnt(P, "R7__ack_lost_guarded_retry", "PASS") == 40 == n(P, "R7__ack_lost_guarded_retry"),
        "P_R5_pass_40": cnt(P, "R5__foreign_session_and_transport", "PASS") == 40 == n(P, "R5__foreign_session_and_transport"),
        "M_R1D_fail_40": cnt(M, "R1D__flag_before_admission", "FAIL") == 40 == n(M, "R1D__flag_before_admission"),
        "M_R2_fail_40": cnt(M, "R2__cancel_after_admission", "FAIL") == 40,
        "M_R6_fail_80": cnt(M, "R6__shutdown_after_cancel", "FAIL") + cnt(M, "R6__end_session_after_cancel", "FAIL") == 80,
        "M_R7_fail_40": cnt(M, "R7__ack_lost_guarded_retry", "FAIL") == 40,
    }
    controls = {}
    for arm_name, arm in (("M", M), ("P", P)):
        for variant, res in sorted(arm.items()):
            if "broken" in variant:
                # R8's broken control is detected when the honoring transport HONORS the notification.
                detected = "HONORED" if variant.startswith("R8__") else "FAIL"
                controls[f"{arm_name}:{variant}"] = res.get(detected, 0) == res.get("n")
            if "control" in variant or "no_cancel" in variant:
                controls[f"{arm_name}:{variant}"] = res.get("PASS", 0) == res.get("n")
    return gates, controls


# ── unit logs ───────────────────────────────────────────────────────────────
RESULT = re.compile(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed")
FAILED_TEST = re.compile(r"^test (\S+) \.\.\. FAILED", re.M)


def unit():
    out = {}
    for path in sorted(glob.glob(os.path.join(RAW, "unit", "**", "*.log"), recursive=True)):
        text = open(path, encoding="utf-8", errors="replace").read()
        passed = sum(int(m.group(2)) for m in RESULT.finditer(text))
        failed = sum(int(m.group(3)) for m in RESULT.finditer(text))
        rc = re.findall(r"\[unit\] rc=(\d+)", text)
        out[os.path.relpath(path, os.path.join(RAW, "unit"))] = {
            "passed": passed, "failed": failed, "failed_tests": sorted(set(FAILED_TEST.findall(text))),
            "rc": int(rc[-1]) if rc else None, "compile_error": "error[E" in text or "could not compile" in text}
    for steps in sorted(glob.glob(os.path.join(RAW, "unit", "**", "steps.txt"), recursive=True)):
        d = os.path.dirname(steps)
        py = open(os.path.join(d, "python-unittest-discover.log"), errors="replace").read()
        ts = open(os.path.join(d, "ts-npm-test.log"), errors="replace").read()
        py_fail = re.findall(r"^(?:FAIL|ERROR): (\S+) \((\S+)\)", py, re.M)
        out[os.path.relpath(d, os.path.join(RAW, "unit")) + "/"] = {
            "py_ran": int((re.findall(r"^Ran (\d+) tests", py, re.M) or [0])[-1]),
            "py_ok": bool(re.search(r"^OK", py, re.M)),
            "py_failed_tests": sorted(cls for _name, cls in py_fail),
            "ts_tests": int((re.findall(r"^# tests (\d+)", ts, re.M) or [0])[-1]),
            "ts_fail": int((re.findall(r"^# fail (\d+)", ts, re.M) or [-1])[-1]),
            "ts_failed_tests": re.findall(r"^not ok \d+ - (.+)$", ts, re.M),
            "steps": open(steps).read().split("\n")}
    return out


FIX02_RED_EXPECTED = {
    "another_sessions_token_is_refused_and_stays_live_for_its_owner",
    "a_token_minted_from_another_sessions_handle_is_refused",
    "stale_refusal_names_only_the_callers_own_snapshots",
    "anonymous_and_named_snapshots_do_not_resolve_for_each_other",
    "a_capture_only_publication_resolves_only_for_its_session",
    "two_windows_of_one_process_keep_tokens_per_window_and_per_session",
    "a_restarted_process_does_not_reissue_its_predecessors_tokens",
    "browser::v2_tests::set_input_files_refuses_a_detached_file_input",
}
SW_WANT = {"both": "positive_control_pass", "screenshot_only": "honored_complete",
           "accessibility_only": "honored_complete", "neither": "rejected_explicit",
           "unknown_field": "rejected_explicit", "legacy_omitted": "default_honored",
           "string_false": "refused_invalid_arguments", "string_true": "refused_invalid_arguments"}


def dispositions(s):
    """PREREG disposition_rule, applied mechanically."""
    F, U = s["fix02"].get("F", {}), s["fix02"].get("U", {})
    BF, WF = s["browser"].get("F", {}), s["w2"].get("F", {})
    unit = s["unit"]

    def full(row, n, arm=F):
        return arm.get(row, {}).get("n") == n and arm.get(row, {}).get("pass") == n

    def ufail(log):
        return unit.get(log, {})

    red = set(ufail("fix02/red-core.log").get("failed_tests", []))
    fix02_unit = (ufail("fix02/F-core.log").get("failed") == 0 and ufail("fix02/F-core.log").get("passed", 0) > 0
                  and ufail("fix02/F-platform-linux-lib.log").get("failed") == 0
                  and red == FIX02_RED_EXPECTED
                  and unit.get("fix02/F-jev/", {}).get("py_ok") is True
                  and unit.get("fix02/F-jev/", {}).get("ts_fail") == 0
                  and all(t.startswith("test_runner_refusal.") for t in unit.get("fix02/red-jev/", {}).get("py_failed_tests", ["x"]))
                  and len(unit.get("fix02/red-jev/", {}).get("py_failed_tests", [])) == 3
                  and unit.get("fix02/red-jev/", {}).get("ts_fail") == 3)
    rows = {
        "F1": {"I2 F' 40/40": full("I2", 40), "I2d F' 40/40": full("I2d", 40),
               "U' lands I2 (>=1)": U.get("I2", {}).get("B_landed_on_A", 0) >= 1,
               "U' lands I2d (>=1)": U.get("I2d", {}).get("derived_landed", 0) >= 1,
               "forged I2 refused 10/10": full("I2_forged", 10), "P 20/20": full("P", 20)},
        "F2": {"I5p F' 20/20": full("I5p", 20), "I5ps F' 20/20": full("I5ps", 20), "I5pt F' 10/10": full("I5pt", 10),
               "U' accepts I5p (>=1)": U.get("I5p", {}).get("token_landed", 0) >= 1,
               "forged I1 refused 10/10": full("I1_forged", 10)},
        "F3": {f"{k} 10/10": BF.get(k, {}).get("n") == 10 and BF.get(k, {}).get("pass") == 10
               for k in ("F3-py-stale", "F3-py-trust_unknown", "F3-ts-stale", "F3-ts-trust_unknown")},
        "F4": {"F4 F' 20/20 (narrower claim; TOCTOU not covered)": BF.get("F4", {}).get("n") == 20
               and BF.get("F4", {}).get("pass") == 20},
    }
    rows["F3"]["0 blind re-dispatches on F'"] = s["e4"].get("F", {}).get("blind_redispatches", 1) == 0
    for k in rows:
        rows[k]["unit red/green + suites"] = fix02_unit
    out = {}
    wave3 = {"F1": "KEEP", "F2": "KEEP", "F3": "KEEP", "F4": "REVISE"}
    for k, gates in rows.items():
        failing = [g for g, ok in gates.items() if not ok]
        out[f"FIX-02 {k}"] = {"wave3": wave3[k], "verdict": "RECERT_PASS" if not failing else "REVISE",
                              "disposition": wave3[k] if not failing else "REVISE", "gates": gates,
                              "failing_rows": failing}
    w2g = {f"{r} F' 20/20": WF.get(r, {}).get("n") == 20 and WF.get(r, {}).get("pass") == 20
           for r in ("W2a", "W2b", "W2c", "W2d")}
    w2g["0 cross-session mutations on F'"] = s["e4"].get("F", {}).get("cross_session_mutations", 1) == 0
    failing = [g for g, ok in w2g.items() if not ok]
    out["kvnloo/cua#36 same-process two-window row"] = {
        "verdict": "KEEP" if not failing else "KILL", "gates": w2g, "failing_rows": failing,
        "u_prime_default_path": {r: s["w2"].get("U", {}).get(r) for r in ("W2a", "W2b", "W2c", "W2d")}}
    o9 = s.get("own09r", {})
    g9 = dict(o9.get("gates", {}))
    g9["every control as wave 3"] = bool(o9.get("controls")) and all(o9["controls"].values())
    for log in ("own09r/c1-green-slice-a.log", "own09r/c2-green-unit.log", "own09r/c3-green-unit.log",
                "own09r/head-cua-driver-sdk.log", "own09r/head-cua-driver.log"):
        g9[f"unit {log} 0 failed"] = ufail(log).get("failed") == 0 and ufail(log).get("passed", 0) > 0
    # Head cua-driver-core (Deviation, rule fixed before the part-C results existed, as the wave-3 FIX-02
    # precedent for the same history test): met by the first run, or by a full re-run with 0 failures
    # plus 20/20 isolated passes of every first-run failure on P'. The first run stays reported.
    first = ufail("own09r/head-cua-driver-core.log")
    rerun = ufail("own09r/head-cua-driver-core-rerun.log")
    iso = s.get("own09r", {}).get("history_isolation", {})
    met = (first.get("failed") == 0 and first.get("passed", 0) > 0) or (
        rerun.get("failed") == 0 and rerun.get("passed", 0) > 0
        and all(iso.get("P", {}).get(t.split("::")[-1], {}) == {"runs": 20, "pass": 20}
                for t in first.get("failed_tests", [])) and first.get("failed_tests"))
    g9["unit head cua-driver-core 0 failed (first run, or re-run + 20/20 isolation)"] = bool(met)
    for log in ("own09r/c2-red-unit.log", "own09r/c3-red-unit.log"):
        g9[f"unit {log} red"] = ufail(log).get("failed", 0) >= 1
    g9["unit c1 red (compile error)"] = ufail("own09r/c1-red-sdk-lib-no-run.log").get("compile_error") is True
    failing = [g for g, ok in g9.items() if not ok]
    out["OWN-09R (kvnloo/cua#84 revision)"] = {"wave3": "KEEP", "verdict": "RECERT_PASS" if not failing else "REVISE",
                                               "gates": g9, "failing_rows": failing}
    if not failing and first.get("failed"):
        # The verdict uses the re-run rule of 34b55dfac; a strict reading of PREREG ("head suites 0 failed")
        # would make the head-core unit row REVISE. Reported next to the verdict, not instead of it.
        out["OWN-09R (kvnloo/cua#84 revision)"].update({
            "qualifier": "RECERT_PASS under Deviation 6 (strict PREREG reading: REVISE on the head-core unit row)",
            "strict_prereg_reading": {"verdict": "REVISE", "failing_rows": ["unit head cua-driver-core first run "
                                      f"{first.get('passed')}/{first.get('failed')} failed"]}})
    s16 = s.get("own16w") or {}
    x11, sw = (s16.get("modes") or {}).get("X11", {}), (s16.get("modes") or {}).get("SW", {})
    xr = lambda b, r: ((x11.get("rows") or {}).get(b, {}).get(r) or {})
    g16 = {
        "X11 F'' string_false refused 42/42": xr("F", "string_false").get("class") == "refused_invalid_arguments"
        and xr("F", "string_false").get("pooled", {}).get("n") == 42,
        "X11 F'' string_true refused 42/42": xr("F", "string_true").get("class") == "refused_invalid_arguments"
        and xr("F", "string_true").get("pooled", {}).get("n") == 42,
        "X11 U'' accepts 42/42 (both string rows)": all(xr("U", r).get("class") == "silently_accepted_default"
                                                        and xr("U", r).get("pooled", {}).get("n") == 42
                                                        for r in ("string_false", "string_true")),
        "X11 F'' positive control": xr("F", "both").get("class") == "positive_control_pass",
        "S-W F'' rows meet the wave-3 gates": {r: v.get("class") for r, v in (sw.get("rows") or {}).get("F", {}).items()} == SW_WANT
        and all(v["pooled"]["n"] == 42 for v in (sw.get("rows") or {}).get("F", {}).values()),
        "S-W token click verified per F'' session": bool(sw) and all(
            t["usability"].get("oracle_verified") is True for t in sw["truth"]["F"]),
        "unit selector red on U''": ufail("own16w/red-selector-U.log").get("failed", 0) >= 1,
        "unit selector green on F''": ufail("own16w/green-selector-F.log").get("failed") == 0
        and ufail("own16w/green-selector-F.log").get("passed", 0) >= 1,
        "unit F'' platform-linux lib 0 failed": ufail("own16w/F-platform-linux-lib.log").get("failed") == 0,
    }
    failing = [g for g, ok in g16.items() if not ok]
    out["OWN-16W"] = {"wave3": "KEEP (S-W; X11 string fix)", "verdict": "RECERT_PASS" if not failing else "REVISE",
                      "gates": g16, "failing_rows": failing,
                      "observation": {"X11 U'' positive control": xr("U", "both").get("class"),
                                      "X11 U'' walk oracle agrees": xr("U", "both").get("pooled", {}).get("oracle_walk_agrees")}}
    return out


def main():
    summary = {"schema": "recert-fix-a3-summary-v1", "fix02": {}, "w2": {}, "browser": {}, "e4": {}}
    for arm in ARMS:
        n, nh, ne4 = native(arm)
        w, wh, we4 = w2(arm)
        b, bv, be4 = browser(arm)
        summary["fix02"][arm] = n
        summary["w2"][arm] = w
        summary["browser"][arm] = b
        summary.setdefault("headers", {})[arm] = {
            "native_driver_sha256": sorted({h["sha256"] for h in nh}),
            "w2_driver_sha256": sorted({h["sha256"] for h in wh}),
            "browser_driver_sha256": sorted({v["driver_sha256"] for v in bv}),
            "versions": sorted({h["version"] for h in nh + wh} | {v["driver_version"] for v in bv}),
            "w2_fixture_sha256": sorted({h["fixture_sha256"] for h in wh if h.get("fixture_sha256")}),
            "browser_validity_ok": all(v["ok"] for v in bv), "blocks": len(nh) + len(wh) + len(bv)}
        e4 = Counter()
        for part in (ne4, we4, be4):
            e4.update(part)
        summary["e4"][arm] = {k: e4.get(k, 0) for k in ("cross_session_mutations", "stale_dispatches",
                                                         "duplicates", "unverified_successes", "blind_redispatches")}
    o9 = own09r()
    summary["own09r"] = {"matrix": o9}
    if o9:
        g, c = own09r_gates(o9)
        summary["own09r"]["gates"], summary["own09r"]["controls"] = g, c
    iso = {}
    for log in sorted(glob.glob(os.path.join(RAW, "unit", "own09r", "history-isolation", "[PM]-*-[0-9][0-9].log"))):
        arm, rest = os.path.basename(log)[:-4].split("-", 1)
        test = rest.rsplit("-", 1)[0]
        ent = iso.setdefault(arm, {}).setdefault(test, {"runs": 0, "pass": 0})
        ent["runs"] += 1
        # A pass needs exactly one test run and passed (an --exact filter that matched nothing is not a pass).
        ent["pass"] += bool(re.search(r"test result: ok\. 1 passed; 0 failed", open(log, errors="replace").read()))
    summary["own09r"]["history_isolation"] = iso
    summary["unit"] = unit()
    s16p = os.path.join(RAW, "own16w", "own-16w-summary.json")
    summary["own16w"] = json.load(open(s16p)) if os.path.exists(s16p) else None
    disp = dispositions(summary)
    summary["own16w"] = {"source": "raw/own16w/own-16w-summary.json (harness/own16w-w3/analyze.py --write)"}
    text = json.dumps(summary, indent=1, sort_keys=True) + "\n"
    dtext = json.dumps(disp, indent=1, sort_keys=True) + "\n"
    target = os.path.join(HERE, "recert-summary.json")
    dtarget = os.path.join(HERE, "dispositions.json")
    if "--check" in sys.argv:
        same = os.path.exists(target) and open(target).read() == text and \
            os.path.exists(dtarget) and open(dtarget).read() == dtext
        print("summary and dispositions match" if same else "summary or dispositions DIFFER")
        return 0 if same else 1
    open(target, "w").write(text)
    open(dtarget, "w").write(dtext)
    print(dtext)
    return 0


if __name__ == "__main__":
    sys.exit(main())
