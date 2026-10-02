#!/usr/bin/env python3
"""OWN-36 analysis: recompute every row from raw/ and write own-36-summary.json.

Counts only (no timing). Definitions follow PREREG.json:
  mutation   = a fixture's post-call state differs from its pre-call state
  refused    = isError (or JSON-RPC error) and no mutation of either fixture
  verified   = target's `agreed` flipped, its seq advanced by exactly 1, other fixture unchanged
"""

import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
B64_RUN = re.compile(r"[A-Za-z0-9+/=]{256,}")
PNG_SIG = "iVBORw0KGgo"
OTHER = {"A": "B", "B": "A"}

# step -> (expectation, scanned-for-I6-as-cross-session)
CROSS_STEPS = {"B-uses-A-capture", "B-uses-A-token-on-B-pid", "B-uses-A-token-on-A-pid",
               "B-stale-probe-on-A-pid", "B-uses-derived-token-on-A-pid", "B-uses-ended-A-token"}


def load():
    blocks, attempts, setups = [], [], []
    for path in sorted(glob.glob(os.path.join(RAW, "T*", "*", "b*.jsonl"))):
        rel = os.path.relpath(path, HERE)
        with open(path, encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream if line.strip()]
        header = [r for r in records if r["kind"] == "block"]
        end = [r for r in records if r["kind"] == "block_end"]
        blocks.append({"file": rel, "header": header[0] if header else None,
                       "complete": bool(end), "records": len(records)})
        for record in records:
            record["_file"] = rel
            if record["kind"] == "attempt":
                attempts.append(record)
            elif record["kind"] == "setup":
                setups.append(record)
    return blocks, attempts, setups


def mutated(call, tag=None):
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
    """Per-attempt checks: dict name -> bool, plus cross-session mutation count and codes."""
    row, forged = a["row"], a.get("forged", False)
    checks, codes, cross_mutations = {}, {}, 0

    def need(name, ok):
        checks[name] = bool(ok)

    def code(name, call):
        if call is not None:
            codes[name] = call.get("refusal_code")

    if row == "P":
        for tag in "AB":
            need(f"own_token_{tag}_verified", step(a, f"own-token-{tag}") and
                 verified(step(a, f"own-token-{tag}"), tag))
    elif row == "I1":
        b = step(a, "B-uses-A-capture")
        code("B_uses_A_capture", b)
        need("B_capture_refused", b and refused(b))
        cross_mutations += int(bool(b and mutated(b)))
        t = step(a, "A-uses-own-capture")
        need("A_own_capture_tail_verified", t and verified(t, "A"))
    elif row == "I2":
        for name in ("B-uses-A-token-on-B-pid", "B-uses-A-token-on-A-pid"):
            c = step(a, name)
            code(name, c)
            need(f"{name}_refused", c and refused(c))
            cross_mutations += int(bool(c and mutated(c)))
        t = step(a, "A-uses-own-token")
        need("A_own_token_tail_verified", t and verified(t, "A"))
    elif row == "I2d":
        p = step(a, "B-stale-probe-on-A-pid")
        code("probe", p)
        need("probe_refused", p and refused(p))
        need("probe_disclosed_A_snapshot", bool(a.get("derived_token")))
        d = step(a, "B-uses-derived-token-on-A-pid")
        code("derived", d)
        checks["derived_token_landed_on_A"] = bool(d and verified(d, "A"))
        cross_mutations += int(bool(d and mutated(d)))
        t = step(a, "A-uses-own-token")
        need("A_own_token_tail_verified", t and verified(t, "A"))
    elif row == "I3":
        b = step(a, "B-uses-own-pre-replacement-token")
        code("B_own", b)
        if forged:
            need("B_forged_refused", b and refused(b))
        else:
            need("B_pre_replacement_token_verified", b and verified(b, "B"))
        s = step(a, "A-uses-own-superseded-token")
        code("A_superseded", s)
        need("A_superseded_refused", s and refused(s))
    elif row == "I3s":
        first, second = a["order"][0], a["order"][1]
        f = step(a, f"{first}-uses-token-after-{second}-observed")
        code("earlier_observer", f)
        checks["earlier_observer_token_refused"] = bool(f and refused(f))
        s = step(a, f"{second}-uses-own-latest-token")
        need("later_observer_verified", s and verified(s, "A"))
    elif row == "I4":
        b = step(a, "B-own-token-after-A-ended")
        need("B_own_token_verified_after_A_end", b and verified(b, "B"))
        x = step(a, "B-uses-ended-A-token")
        code("B_uses_ended_A_token", x)
        need("B_ended_A_token_refused", x and refused(x))
        cross_mutations += int(bool(x and mutated(x)))
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
    elif row == "N":
        r = step(a, "A-uses-stale-token-on-recreated-pid")
        code("recreated_pid", r)
        need("stale_token_on_recreated_window_refused", r and refused(r))
        d = step(a, "A-uses-stale-token-on-dead-pid")
        code("dead_pid", d)
        checks["dead_pid_no_mutation"] = bool(d and not mutated(d))
        checks["dead_pid_error"] = bool(d and d["is_error"])
    elif row == "I5p":
        t = step(a, "gen2-uses-gen1-token")
        code("gen1_token", t)
        need("gen1_token_refused", t and refused(t))
        cross_mutations += int(bool(t and mutated(t)))
        c = step(a, "gen2-uses-gen1-capture")
        code("gen1_capture", c)
        need("gen1_capture_refused", c and refused(c))
        checks["gen1_token_string_equals_gen2"] = a.get("gen1_token") == a.get("gen2_token")
    elif row == "X1":
        toks = a.get("tokens", {})
        checks["concurrent_process_tokens_equal"] = toks.get("A") == toks.get("B")
    return checks, codes, cross_mutations


GATING_CHECKS = {
    "P": None, "I1": None, "I2": None, "I3": None, "I4": None, "I5": None, "N": None, "I5p": None,
}
DIAGNOSTIC_ROWS = {"I2d", "I3s", "X1"}
NON_GATING_CHECKS = {"derived_token_landed_on_A", "earlier_observer_token_refused",
                     "dead_pid_no_mutation", "dead_pid_error", "gen1_token_string_equals_gen2",
                     "concurrent_process_tokens_equal"}


def scan_i6(attempts, setups):
    markers = {}
    positive = []
    for s in setups:
        markers[(s["_file"], s["marker_tag"])] = s["marker"]
        obs = [c for c in s["calls"] if c["step"] == "observe-with-marker"]
        found = bool(obs) and s["marker"] in json.dumps(obs[0]["response"])
        positive.append({"file": s["_file"], "tag": s["marker_tag"], "found": found,
                         "saved_on_oracle": s.get("marker_saved")})
    scanned, hits, disclosures = 0, [], 0
    for a in attempts:
        if a["topology"] == "T3":
            continue
        for c in a["calls"]:
            if not (c["is_error"] or c["step"] in CROSS_STEPS):
                continue
            scanned += 1
            actor = c["actor"]
            other_marker = markers.get((a["_file"], OTHER[actor]))
            body = json.dumps(c["response"])
            problems = []
            if other_marker and other_marker in body:
                problems.append("other_session_marker")
            if PNG_SIG in body:
                problems.append("png_base64_signature")
            if any(i.get("type") == "image" for i in c["response"].get("content", [])):
                problems.append("image_item")
            if B64_RUN.search(body):
                problems.append("base64_run_256")
            if problems:
                hits.append({"file": a["_file"], "attempt": a["attempt"], "step": c["step"],
                             "problems": problems})
            current = (c["response"].get("structuredContent") or {}).get("current_snapshots") or []
            other_windows = {post.get("pid") for post in [c["pre"].get(OTHER[actor])] if post}
            target_pid = c["args"].get("pid")
            if current and target_pid in other_windows:
                disclosures += 1
    return {
        "envelopes_scanned": scanned,
        "content_hits": len(hits),
        "hits": hits,
        "positive_control": {"blocks_sessions": len(positive),
                             "own_marker_found": sum(p["found"] for p in positive),
                             "marker_saved_on_oracle": sum(bool(p["saved_on_oracle"]) for p in positive)},
        "refusals_disclosing_other_session_snapshot_handles": disclosures,
    }


def summarize():
    blocks, attempts, setups = load()
    rows = collections.defaultdict(lambda: {"attempts": 0, "checks": collections.Counter(),
                                            "check_n": collections.Counter(),
                                            "codes": collections.defaultdict(collections.Counter),
                                            "cross_session_mutations": 0, "orders": collections.Counter(),
                                            "arms": collections.defaultdict(collections.Counter)})
    for a in attempts:
        key = f"{a['topology']}/{a['row']}{'/forged' if a.get('forged') else ''}"
        checks, codes, cross = evaluate(a)
        r = rows[key]
        r["attempts"] += 1
        r["orders"][a["order"]] += 1
        r["cross_session_mutations"] += cross
        for name, ok in checks.items():
            r["check_n"][name] += 1
            r["checks"][name] += int(ok)
        for name, value in codes.items():
            r["codes"][name][str(value)] += 1
        if a["row"] == "I5p":
            arm = a.get("arm")
            r["arms"][arm]["attempts"] += 1
            r["arms"][arm]["gen1_token_accepted"] += int(not checks["gen1_token_refused"])
            r["arms"][arm]["gen1_capture_refused"] += int(checks["gen1_capture_refused"])
    out = {}
    for key, r in sorted(rows.items()):
        row = key.split("/")[1]
        gating = {n: (r["checks"][n], r["check_n"][n]) for n in r["check_n"] if n not in NON_GATING_CHECKS}
        all_pass = all(ok == n for ok, n in gating.values())
        if row in DIAGNOSTIC_ROWS:
            verdict = "DIAGNOSTIC"
        elif row in ("P", "N") or key.endswith("/forged"):
            verdict = "CONTROL_PASS" if all_pass else "CONTROL_FAIL"
        else:
            verdict = "KILL" if r["cross_session_mutations"] or not all_pass else "KEEP"
            if not all_pass and not r["cross_session_mutations"]:
                verdict = "KILL"
        out[key] = {
            "attempts": r["attempts"], "orders": dict(r["orders"]),
            "cross_session_mutations": r["cross_session_mutations"],
            "checks": {n: f"{r['checks'][n]}/{r['check_n'][n]}" for n in sorted(r["check_n"])},
            "refusal_codes": {n: dict(c) for n, c in r["codes"].items()},
            "verdict": verdict,
        }
        if r["arms"]:
            out[key]["arms"] = {arm: dict(c) for arm, c in r["arms"].items()}
    i6 = scan_i6(attempts, setups)
    i6["verdict"] = ("KEEP" if i6["content_hits"] == 0
                     and i6["positive_control"]["own_marker_found"] == i6["positive_control"]["blocks_sessions"]
                     else "KILL")
    displays = collections.Counter(b["header"]["display"] for b in blocks if b["header"])
    shas = {b["header"]["driver_sha256"] for b in blocks if b["header"]}
    versions = {b["header"]["driver_version"] for b in blocks if b["header"]}
    return {
        "schema": "cua.own36.summary.v1",
        "blocks": len(blocks), "blocks_complete": sum(b["complete"] for b in blocks),
        "attempts_total": len(attempts), "setup_records": len(setups),
        "driver_sha256_seen": sorted(shas), "driver_version_seen": sorted(versions),
        "displays": dict(displays),
        "rows": out, "I6": i6,
    }


def main():
    summary = summarize()
    path = os.path.join(HERE, "own-36-summary.json")
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write("\n")
    for key, row in summary["rows"].items():
        print(f"{key:22s} n={row['attempts']:3d} xmut={row['cross_session_mutations']:3d} "
              f"{row['verdict']:12s} {row['checks']}")
    print("I6", json.dumps({k: v for k, v in summary["I6"].items() if k != "hits"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
