#!/usr/bin/env python3
"""FIX-02 analysis: recompute every row from raw/ and write fix02-summary.json (stdlib only).

Definitions follow PREREG.json. Native:
  mutation = a fixture's post-call state differs from its pre-call state
  refused  = isError (or JSON-RPC error) and no mutation of either fixture
  verified = target's `agreed` flipped, its seq advanced by exactly 1, other fixture unchanged
Browser: the target journal (received/applied, state == token) and page beacons are the oracle.
"""

import collections
import glob
import json
import os
import random
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
B64_RUN = re.compile(r"[A-Za-z0-9+/=]{256,}")
PNG_SIG = "iVBORw0KGgo"
OTHER = {"A": "B", "B": "A"}
CROSS_STEPS = {"B-uses-A-capture", "B-uses-A-token-on-B-pid", "B-uses-A-token-on-A-pid",
               "B-stale-probe-on-A-pid", "B-uses-derived-token-on-A-pid", "B-uses-ended-A-token"}


# ── native ────────────────────────────────────────────────────────────────────
def load_native():
    blocks, attempts, setups = [], [], []
    for path in sorted(glob.glob(os.path.join(RAW, "native", "*", "T*", "*", "b*.jsonl"))):
        rel = os.path.relpath(path, HERE)
        arm = rel.split(os.sep)[2]
        with open(path, encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream if line.strip()]
        header = [r for r in records if r["kind"] == "block"]
        end = [r for r in records if r["kind"] == "block_end"]
        n_att = sum(1 for r in records if r["kind"] == "attempt")
        blocks.append({"file": rel, "arm": arm, "header": header[0] if header else None,
                       "complete": bool(end), "attempts": n_att})
        for record in records:
            record["_file"], record["_arm"] = rel, arm
            if record["kind"] == "attempt":
                attempts.append(record)
            elif record["kind"] == "setup":
                setups.append(record)
    return blocks, attempts, setups


def mutated(call, tag=None):
    if "pre" not in call:
        return False
    tags = [tag] if tag else ["A", "B"]
    return any(call["pre"].get(t) != call["post"].get(t) for t in tags if t in call["pre"])


def refused(call):
    return bool(call["is_error"]) and not mutated(call)


def verified(call, target):
    pre, post = call["pre"].get(target), call["post"].get(target)
    if not pre or not post:
        return False
    others_same = all(call["pre"].get(t) == call["post"].get(t) for t in call["pre"] if t != target)
    return (not call["is_error"] and post.get("agreed") == (not pre.get("agreed"))
            and post.get("seq") == pre.get("seq", 0) + 1 and others_same)


def step(attempt, name):
    found = [c for c in attempt["calls"] if c["step"] == name]
    return found[0] if found else None


def evaluate(a):
    """Per-attempt checks (name -> bool), refusal codes, cross-session/old-generation mutations."""
    row = a["row"]
    checks, codes, mutations = {}, {}, 0

    def need(name, ok):
        checks[name] = bool(ok)

    def code(name, call):
        if call is not None:
            codes[name] = call.get("refusal_code")

    if row == "I1":
        b = step(a, "B-uses-A-capture")
        code("B_uses_A_capture", b)
        need("B_capture_refused", b and refused(b))
        mutations += int(bool(b and mutated(b)))
        t = step(a, "A-uses-own-capture")
        need("A_own_capture_tail_verified", t and verified(t, "A"))
    elif row == "I2":
        for name in ("B-uses-A-token-on-B-pid", "B-uses-A-token-on-A-pid"):
            c = step(a, name)
            code(name, c)
            need(f"{name}_refused", c and refused(c))
            mutations += int(bool(c and mutated(c)))
        land = step(a, "B-uses-A-token-on-A-pid")
        checks["B_A_token_landed_on_A"] = bool(land and verified(land, "A"))
        t = step(a, "A-uses-own-token")
        need("A_own_token_tail_verified", t and verified(t, "A"))
    elif row == "I2d":
        p = step(a, "B-stale-probe-on-A-pid")
        code("probe", p)
        need("probe_refused", p and refused(p))
        checks["probe_disclosed_A_handle"] = bool(a.get("disclosed_A_handle"))
        checks["derived_from_disclosure"] = a.get("derived_source") == "disclosure"
        checks["derived_equals_A_token"] = bool(a.get("derived_equals_A_token"))
        d = step(a, "B-uses-derived-token-on-A-pid")
        code("derived", d)
        need("derived_token_refused", d and refused(d))
        checks["derived_token_landed_on_A"] = bool(d and verified(d, "A"))
        mutations += int(bool(d and mutated(d)))
        t = step(a, "A-uses-own-token")
        need("A_own_token_tail_verified", t and verified(t, "A"))
    elif row == "I3":
        b = step(a, "B-uses-own-pre-replacement-token")
        code("B_own", b)
        need("B_pre_replacement_token_verified", b and verified(b, "B"))
        s = step(a, "A-uses-own-superseded-token")
        code("A_superseded", s)
        need("A_superseded_refused", s and refused(s))
    elif row == "I4":
        b = step(a, "B-own-token-after-A-ended")
        need("B_own_token_verified_after_A_end", b and verified(b, "B"))
        x = step(a, "B-uses-ended-A-token")
        code("B_uses_ended_A_token", x)
        need("B_ended_A_token_refused", x and refused(x))
        mutations += int(bool(x and mutated(x)))
        y = step(a, "A-uses-own-token-after-end")
        code("A_own_after_end", y)
        need("A_own_ended_token_refused", y and refused(y))
    elif row == "I5":
        o = step(a, "A-uses-old-generation-token")
        code("old_token", o)
        need("old_token_refused", o and refused(o))
        c = step(a, "A-uses-old-generation-capture")
        code("old_capture", c)
        need("old_capture_refused", c and refused(c))
        n = step(a, "A-uses-new-generation-token")
        need("new_token_verified", n and verified(n, "A"))
        bname = "B-own-token-before-A-restart" if a["order"] == "AB" else "B-own-token-after-A-restart"
        b = step(a, bname)
        need("B_verified", b and verified(b, "B"))
    elif row == "I5p":
        t = step(a, "gen2-uses-gen1-token")
        code("gen1_token", t)
        need("gen1_token_refused", t and refused(t))
        mutations += int(bool(t and mutated(t)))
        c = step(a, "gen2-uses-gen1-capture")
        code("gen1_capture", c)
        need("gen1_capture_refused", c and refused(c))
        checks["gen1_token_string_equals_gen2"] = a.get("gen1_token") == a.get("gen2_token")
    elif row == "I5pt":
        t = step(a, "gen2-uses-gen1-token")
        code("gen1_token", t)
        need("gen1_token_refused", t and refused(t))
        mutations += int(bool(t and mutated(t)))
        checks["gen1_token_string_equals_gen2_handle"] = (
            (a.get("gen1_token") or "").split(":")[0] == (a.get("gen2_token") or "").split(":")[0])
    return checks, codes, mutations


NON_GATING = {"B_A_token_landed_on_A", "probe_disclosed_A_handle", "derived_from_disclosure",
              "derived_equals_A_token", "derived_token_landed_on_A", "gen1_token_string_equals_gen2",
              "gen1_token_string_equals_gen2_handle"}


def scan_i6(attempts, setups, arm="F"):
    """Content-free envelopes on one arm: every envelope returned to a session is scanned for the
    other session's note marker; refusals and cross-session responses also for image content; and
    every refusal's current_snapshots for a handle the OTHER session observed in the same block."""
    markers, positive = {}, []
    for s in setups:
        if s["_arm"] != arm:
            continue
        markers[(s["_file"], s["marker_tag"])] = s["marker"]
        obs = [c for c in s["calls"] if c["step"] == "observe-with-marker"]
        found = bool(obs) and s["marker"] in json.dumps(obs[0]["response"])
        positive.append({"file": s["_file"], "tag": s["marker_tag"], "found": found,
                         "saved_on_oracle": s.get("marker_saved")})
    handles = collections.defaultdict(set)  # (file, actor) -> snapshot handles that actor observed
    for record in [*attempts, *setups]:
        if record["_arm"] != arm:
            continue
        for c in record.get("calls", []):
            if c.get("tool") == "get_window_state":
                sid = (c["response"].get("structuredContent") or {}).get("snapshot_id")
                if sid:
                    handles[(record["_file"], c.get("actor"))].add(sid)
    scanned_all = scanned_strict = 0
    hits, disclosures = [], []
    for a in attempts:
        if a["_arm"] != arm or a["topology"] == "T3":
            continue
        for c in a["calls"]:
            actor = c.get("actor")
            body = json.dumps(c["response"])
            other_marker = markers.get((a["_file"], OTHER.get(actor)))
            scanned_all += 1
            problems = []
            if other_marker and other_marker in body:
                problems.append("other_session_marker")
            if c["is_error"] or c["step"] in CROSS_STEPS:
                scanned_strict += 1
                if PNG_SIG in body:
                    problems.append("png_base64_signature")
                if any(i.get("type") == "image" for i in c["response"].get("content", [])):
                    problems.append("image_item")
                if B64_RUN.search(body):
                    problems.append("base64_run_256")
                current = (c["response"].get("structuredContent") or {}).get("current_snapshots") or []
                foreign = {x.get("snapshot_id") for x in current} & handles[(a["_file"], OTHER.get(actor))]
                if foreign:
                    disclosures.append({"file": a["_file"], "attempt": a["attempt"], "step": c["step"],
                                        "foreign_handles": sorted(foreign)})
            if problems:
                hits.append({"file": a["_file"], "attempt": a["attempt"], "step": c["step"],
                             "problems": problems})
    return {
        "arm": arm, "envelopes_scanned_for_other_marker": scanned_all,
        "refusal_or_cross_envelopes_scanned_for_content": scanned_strict,
        "content_hits": len(hits), "hits": hits,
        "positive_control": {"block_sessions": len(positive),
                             "own_marker_found": sum(p["found"] for p in positive),
                             "marker_saved_on_oracle": sum(bool(p["saved_on_oracle"]) for p in positive)},
        "refusals_listing_other_session_handles": len(disclosures), "disclosures": disclosures,
    }


def summarize_native():
    blocks, attempts, setups = load_native()
    rows = {}
    for a in attempts:
        key = f"{a['_arm']}/{a['topology']}/{a['row']}"
        checks, codes, muts = evaluate(a)
        r = rows.setdefault(key, {"attempts": 0, "pass": 0, "checks": collections.Counter(),
                                  "check_n": collections.Counter(), "mutations": 0,
                                  "codes": collections.defaultdict(collections.Counter),
                                  "orders": collections.Counter(), "extra": collections.Counter()})
        r["attempts"] += 1
        r["orders"][a["order"]] += 1
        r["mutations"] += muts
        gating = [ok for name, ok in checks.items() if name not in NON_GATING]
        r["pass"] += int(all(gating) and muts == 0)
        for name, ok in checks.items():
            r["check_n"][name] += 1
            r["checks"][name] += int(ok)
        for name, value in codes.items():
            r["codes"][name][str(value)] += 1
        if a["row"] == "I2d":
            r["extra"][f"derived_source={a.get('derived_source')}"] += 1
        if a["row"] == "I5pt":
            el = a.get("gen2_element_at_gen1_index") or {}
            r["extra"][f"gen2_element_at_gen1_index={el.get('label')}"] += 1
    out_rows = {}
    for key, r in sorted(rows.items()):
        out_rows[key] = {"attempts": r["attempts"], "pass_all_gating_checks_and_0_mutations": r["pass"],
                         "mutations": r["mutations"],
                         "checks": {k: f"{r['checks'][k]}/{r['check_n'][k]}" for k in sorted(r["check_n"])},
                         "codes": {k: dict(v) for k, v in r["codes"].items()},
                         "orders": dict(r["orders"]), "extra": dict(r["extra"])}
    headers = [b["header"] for b in blocks if b["header"]]
    return {
        "blocks": len(blocks), "complete_blocks": sum(b["complete"] for b in blocks),
        "blocks_with_0_attempts": [b["file"] for b in blocks if b["attempts"] == 0],
        "attempts": len(attempts),
        "driver_by_arm": {arm: sorted({f"{b['header']['driver_sha256']} {b['header']['driver_version']}"
                                       for b in blocks if b["arm"] == arm and b["header"]})
                          for arm in ("U", "F")},
        "displays": dict(collections.Counter(h.get("display") for h in headers)),
        "rows": out_rows,
        "i6_F": scan_i6(attempts, setups, "F"),
        "i6_U_disclosures_for_reference": scan_i6(attempts, setups, "U")["refusals_listing_other_session_handles"],
    }


# ── browser ───────────────────────────────────────────────────────────────────
def load_cells():
    cells = []
    for path in sorted(glob.glob(os.path.join(RAW, "browser", "*", "cells", "*.jsonl"))):
        with open(path, encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream if line.strip()]
        cell = records[0]
        cell["_file"] = os.path.relpath(path, HERE)
        cell["_journal"] = next((r["events"] for r in records if r.get("type") == "target_journal"), [])
        cells.append(cell)
    return cells


def f3_gate(c):
    code = c.get("code")
    if c["phase"] == "f3ctl":
        return (c["refusals_seen"] == 0 and c["outcome"] == "verified" and c["independently_verified"]
                and c["click_dispatches_by_caller"] == 1)
    if not c["injected"]:
        return False
    if code == "stale":
        return (c["click_dispatches_by_caller"] == 2 and c["observations_between_first_and_second_click"] == 1
                and c["outcome"] == "verified" and c["independently_verified"])
    if code in ("trust_unknown", "trust_unknown_visible"):
        return (c["click_dispatches_by_caller"] == 1 and c["outcome"] == "unknown" and c["journal_applied"] == 1
                and c["journal_received"] == 1)
    if code == "not_retryable":
        return c["click_dispatches_by_caller"] == 1 and c["outcome"] == "unknown" and c["journal_applied"] == 0
    return False


def f4_gate(c):
    return (c.get("old_ref_result") == "refused" and c.get("old_ref_code") == "browser_ref_stale"
            and c["old_node_events"] == 0 and c["rebind_verified"])


def summarize_browser():
    cells = load_cells()
    groups = collections.defaultdict(list)
    for c in cells:
        key = f"{c['phase']}/{c.get('code') or '-'}/{c['arm']}" if c["phase"] != "f4" else f"f4/-/{c['arm']}"
        groups[key].append(c)
    out = {}
    for key, cs in sorted(groups.items()):
        phase = key.split("/")[0]
        g = {"n": len(cs), "outcomes": dict(collections.Counter(str(c.get("outcome")) for c in cs))}
        if phase in ("f3", "f3ctl"):
            g.update({
                "injected": sum(bool(c.get("injected")) for c in cs),
                "click_dispatches": dict(collections.Counter(c["click_dispatches_by_caller"] for c in cs)),
                "redispatch_after_refusal": sum(c["redispatches_after_refusal"] > 0 for c in cs),
                "clicks_forwarded_to_driver": dict(collections.Counter(c["clicks_forwarded_to_driver"] for c in cs)),
                "observations_between_clicks": dict(collections.Counter(
                    str(c["observations_between_first_and_second_click"]) for c in cs)),
                "journal_received": dict(collections.Counter(c["journal_received"] for c in cs)),
                "journal_applied": dict(collections.Counter(c["journal_applied"] for c in cs)),
                "duplicate_submits_total": sum(c["duplicate_submits"] for c in cs),
                "cells_with_duplicate_submit": sum(c["duplicate_submits"] > 0 for c in cs),
                "independently_verified": sum(bool(c["independently_verified"]) for c in cs),
                "unverified_success": sum(bool(c["unverified_success"]) for c in cs),
                "refusal_codes_seen": dict(collections.Counter(
                    str((c.get("first_click") or {}).get("code")) for c in cs if c["refusals_seen"])),
                "retryable_seen_by_runner": dict(collections.Counter(
                    str((c.get("first_click") or {}).get("retryable")) for c in cs if c["refusals_seen"])),
                "gate_pass": sum(f3_gate(c) for c in cs),
                "nonloopback_refused_max": max(c.get("nonloopback_refused_total", 0) for c in cs),
            })
        else:
            g.update({
                "old_ref_result": dict(collections.Counter(str(c.get("old_ref_result")) for c in cs)),
                "old_ref_code": dict(collections.Counter(str(c.get("old_ref_code")) for c in cs)),
                "cells_with_old_node_events": sum(c["old_node_events"] > 0 for c in cs),
                "old_node_events_total": sum(c["old_node_events"] for c in cs),
                "old_node_event_kinds": dict(collections.Counter(
                    k for c in cs for k in c["journal_summary"]["page_event_kinds"] if k.startswith("old:"))),
                "rebind_verified": sum(bool(c["rebind_verified"]) for c in cs),
                "gate_pass": sum(f4_gate(c) for c in cs),
                "nonloopback_refused_max": max(c.get("nonloopback_refused_total", 0) for c in cs),
            })
        out[key] = g
    validity = []
    for path in sorted(glob.glob(os.path.join(RAW, "browser", "*", "validity.json"))):
        with open(path, encoding="utf-8") as stream:
            v = json.load(stream)
        validity.append({"block": os.path.basename(os.path.dirname(path)), "ok": v["ok"], "arm": v["arm"],
                         "driver_sha256": v["driver"]["sha256"], "driver_version": v["driver"]["version"],
                         "head": v["head"], "rust_tree": v["rust_tree_at_head"], "display": v["display"]})
    return {"cells": len(cells), "groups": out, "blocks": validity,
            "driver_by_arm": {arm: sorted({f"{v['driver_sha256']} {v['driver_version']}" for v in validity
                                           if v["arm"] == arm}) for arm in ("U", "F")}}


# ── timing ────────────────────────────────────────────────────────────────────
def bootstrap_median_ci(values, seed=20261002, n=10000):
    rng = random.Random(seed)
    meds = sorted(statistics.median(rng.choices(values, k=len(values))) for _ in range(n))
    return [round(meds[int(0.025 * n)], 3), round(meds[int(0.975 * n) - 1], 3)]


def summarize_timing():
    path = os.path.join(RAW, "timing", "timing.jsonl")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    pairs = [r for r in records if r["kind"] == "pair"]
    header = next(r for r in records if r["kind"] == "header")
    order = header["order"]
    u_blocks = [i for i, a in enumerate(order) if a == "U"]
    f_blocks = [i for i, a in enumerate(order) if a == "F"]
    by_block = collections.defaultdict(list)
    for p in pairs:
        by_block[p["block"]].append(p)
    out = {"header": header, "pairs_per_arm": {}, "medians_ms": {}, "errors": {}, "not_landed": {}}
    for arm in ("U", "F"):
        ps = [p for p in pairs if p["arm"] == arm]
        out["pairs_per_arm"][arm] = len(ps)
        out["medians_ms"][arm] = {"get_window_state": round(statistics.median(p["gws_ms"] for p in ps), 3),
                                  "click": round(statistics.median(p["click_ms"] for p in ps), 3)}
        out["errors"][arm] = sum(p["gws_error"] or p["click_error"] for p in ps)
        out["not_landed"][arm] = sum(not p["click_landed"] for p in ps)
    diffs = {"click": [], "get_window_state": []}
    for ub, fb in zip(u_blocks, f_blocks):
        for pu, pf in zip(by_block[ub], by_block[fb]):
            diffs["click"].append(pf["click_ms"] - pu["click_ms"])
            diffs["get_window_state"].append(pf["gws_ms"] - pu["gws_ms"])
    out["paired_F_minus_U_ms"] = {k: {"n": len(v), "median": round(statistics.median(v), 3),
                                      "ci95": bootstrap_median_ci(v)} for k, v in diffs.items() if v}
    out["loadavg_per_block"] = {str(b): by_block[b][0]["loadavg_block"] for b in sorted(by_block) if by_block[b]}
    out["complete"] = any(r["kind"] == "end" for r in records)
    return out


# ── unit ──────────────────────────────────────────────────────────────────────
def summarize_unit():
    out = {}
    for path in sorted(glob.glob(os.path.join(RAW, "unit", "**", "*.log"), recursive=True)):
        rel = os.path.relpath(path, os.path.join(RAW, "unit"))
        with open(path, encoding="utf-8", errors="replace") as stream:
            text = stream.read()
        results = re.findall(r"^test result: (\w+)\. (\d+) passed; (\d+) failed", text, re.M)
        failed = sorted(set(re.findall(r"^test (\S+) \.\.\. FAILED$", text, re.M)))
        py = re.findall(r"^Ran (\d+) tests", text, re.M)
        py_status = re.findall(r"^(OK.*|FAILED \(.*\))$", text, re.M)
        ts = re.findall(r"^# (pass|fail) (\d+)$", text, re.M)
        entry = {}
        if results:
            entry["rust_passed"] = sum(int(p) for _, p, _ in results)
            entry["rust_failed"] = sum(int(f) for _, _, f in results)
        if failed:
            entry["failed_tests"] = failed
        if py:
            entry["python_ran"] = int(py[-1])
            entry["python_status"] = py_status[-1] if py_status else None
            entry["python_failed_tests"] = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.M)))
        if ts:
            entry.update({f"ts_{k}": int(v) for k, v in ts})
            entry["ts_failed_tests"] = re.findall(r"^not ok \d+ - (.*)$", text, re.M)
        if entry:
            out[rel] = entry
    return out


def main():
    summary = {
        "schema": "fix02.summary.v1",
        "native": summarize_native(),
        "browser": summarize_browser(),
        "timing": summarize_timing(),
        "unit": summarize_unit(),
    }
    target = os.path.join(HERE, "fix02-summary.json")
    with open(target, "w", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=1, sort_keys=True, default=str)
        stream.write("\n")
    if "--print" in sys.argv:
        print(json.dumps({"native_rows": {k: (v["attempts"], v["pass_all_gating_checks_and_0_mutations"],
                                              v["mutations"]) for k, v in summary["native"]["rows"].items()},
                          "browser": {k: (v["n"], v["gate_pass"]) for k, v in summary["browser"]["groups"].items()},
                          "i6_F": {k: summary["native"]["i6_F"][k] for k in
                                   ("content_hits", "refusals_listing_other_session_handles", "positive_control")},
                          "timing": summary["timing"] and summary["timing"]["paired_F_minus_U_ms"]}, indent=1))


if __name__ == "__main__":
    main()
