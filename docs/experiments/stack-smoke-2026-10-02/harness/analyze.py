"""Aggregate stack-smoke runs into summary.json against the PREREG gates (stdlib only).

usage: analyze.py <raw dir with runs/<run_id>/{run_summary.json,join/join_summary.json,shadow/decisions.full.jsonl}>
                  <plan.json> <drive-ledger.jsonl> <out summary.json>
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def wilson(k: int, n: int, z: float = 1.959964) -> list | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def sign_test(b: int, c: int) -> float:
    """Exact two-sided binomial p for discordant pairs b vs c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def main() -> None:
    raw, plan_p, ledger_p, out_p = map(Path, sys.argv[1:5])
    plan = json.loads(plan_p.read_text())["runs"]
    ledger = {r["run_id"]: r for r in jl(ledger_p)}
    S, J, D = {}, {}, {}
    for r in plan:
        rd = raw / "runs" / r["run_id"]
        if (rd / "run_summary.json").exists():
            S[r["run_id"]] = json.loads((rd / "run_summary.json").read_text())
        if (rd / "join" / "join_summary.json").exists():
            J[r["run_id"]] = json.loads((rd / "join" / "join_summary.json").read_text())
        D[r["run_id"]] = jl(rd / "shadow" / "decisions.full.jsonl")
    out: dict = {"schema": "stack_smoke.summary.v1", "planned": len(plan), "executed": len(S),
                 "harness_errors": [k for k, v in ledger.items() if "harness_error" in v],
                 "missing": [r["run_id"] for r in plan if r["run_id"] not in S]}

    # ---- outcomes by set/task/arm ----
    cells = defaultdict(lambda: {"n": 0, "pass": 0, "fail": 0, "unknown": 0, "hermes_rc_nonzero": 0})
    for r in plan:
        s = S.get(r["run_id"])
        key = f"{r['set']}|{r['task']}|{r['arm']}|{r['driver_key']}"
        c = cells[key]
        c["n"] += 1
        v = (s or {}).get("oracle", {}).get("verdict", "unknown")
        c[v if v in ("pass", "fail") else "unknown"] += 1
        c["hermes_rc_nonzero"] += int((s or {}).get("hermes_rc") not in (0,))
    for c in cells.values():
        c["pass_rate"] = round(c["pass"] / c["n"], 4) if c["n"] else None
        c["pass_wilson95"] = wilson(c["pass"], c["n"])
    out["outcomes"] = dict(sorted(cells.items()))

    shadow_runs = [r for r in plan if r["arm"] in ("on", "outage") and r["run_id"] in S]
    # ---- H1 join ----
    h1 = []
    for r in shadow_runs:
        s, j = S[r["run_id"]], J.get(r["run_id"], {})
        obs_t, rec_t = set(s["observer"]["trace_ids"]), set(s["shadow"]["receipt_trace_ids"])
        obs_u, rec_u = set(s["observer"]["turn_ids"]), set(s["shadow"]["receipt_turn_ids"])
        gold = {"pass": True, "fail": False}.get(s["oracle"].get("verdict"))
        tr = j.get("traces", [])
        ok = (bool(obs_t) and obs_t <= rec_t and obs_u <= rec_u and len(tr) == len(obs_t)
              and all(t["gold_verified"] == gold and t["observation_verified_success"] == gold
                      and (t.get("receipt_join") or {}).get("joined_receipt_trace_matches") for t in tr))
        h1.append({"run_id": r["run_id"], "ok": ok, "observer_traces": len(obs_t), "receipt_traces": len(rec_t),
                   "trace_sets_equal": obs_t == rec_t, "turn_sets_equal": obs_u == rec_u, "oracle": s["oracle"].get("verdict")})
    out["H1_join"] = {"runs": len(h1), "ok": sum(x["ok"] for x in h1), "gate": "100%",
                      "pass": bool(h1) and all(x["ok"] for x in h1), "failures": [x for x in h1 if not x["ok"]],
                      "per_run": h1}

    # ---- H2 persistence ----
    n_ok = n_bad = 0
    status_counts: dict = defaultdict(int)
    bad = []
    for r in shadow_runs:
        for d in D[r["run_id"]]:
            status_counts[f"{d['question_id']}|{d['status']}"] += 1
            if d["status"] != "ok":
                continue
            dec = d.get("decision") or {}
            ans = next((a for a in dec.get("answers", []) if a.get("question_id") == d["question_id"]), {})
            probs = ans.get("probabilities") or {}
            cands = d.get("candidates") or []
            good = (cands == sorted(d["request"]["questions"][0]["criteria"].keys()) and set(probs) == set(cands)
                    and all(isinstance(v, (int, float)) and math.isfinite(v) for v in probs.values())
                    and abs(sum(probs.values()) - 1.0) <= 1e-5 and ans.get("confidence") is not None
                    and isinstance(dec.get("latency_ms"), (int, float))
                    and all(dec.get(k) for k in ("backend", "model", "revision")))
            n_ok += good
            n_bad += not good
            if not good:
                bad.append({"run_id": r["run_id"], "opportunity_id": d["opportunity_id"]})
    out["H2_persistence"] = {"ok_receipts_checked": n_ok + n_bad, "complete": n_ok, "incomplete": n_bad,
                             "pass": n_bad == 0 and n_ok > 0, "status_counts": dict(status_counts), "incomplete_rows": bad[:20]}

    # ---- H3b paired ----
    pairs = []
    by = defaultdict(dict)
    for r in plan:
        if r["set"] == "measured" and r["arm"] in ("on", "off") and r["run_id"] in S:
            by[(r["task"], r["pair"])][r["arm"]] = S[r["run_id"]]
    for (task, pair), arms in sorted(by.items()):
        if set(arms) != {"on", "off"}:
            pairs.append({"task": task, "pair": pair, "complete": False})
            continue
        a, b = arms["on"]["state_db"], arms["off"]["state_db"]
        sa, sb = a.get("tool_sequence", []), b.get("tool_sequence", [])
        first = next((i for i in range(max(len(sa), len(sb))) if i >= len(sa) or i >= len(sb) or sa[i] != sb[i]), None)
        ra, rb = a.get("tool_result_sha256", []), b.get("tool_result_sha256", [])
        na, nb = a.get("tool_result_norm_sha256", []), b.get("tool_result_norm_sha256", [])
        cause = None
        if first is not None:  # inputs the model saw before its first differing call
            if ra[:first] == rb[:first]:
                cause = "identical_inputs(sampling_or_numeric_nondeterminism)"
            elif na[:first] == nb[:first]:
                cause = "inputs_differ_only_in_run_ids(pid/window/uuid)"
            else:
                cause = "inputs_differ_in_content(environment)"
        pairs.append({
            "task": task, "pair": pair, "complete": True,
            "tool_sequence_identical": sa == sb, "len_on": len(sa), "len_off": len(sb), "first_divergence_step": first,
            "divergence_cause": cause,
            "system_prompt_hash_equal": [x.get("system_prompt_hash") for x in a.get("sessions", [])] ==
                                        [x.get("system_prompt_hash") for x in b.get("sessions", [])],
            "final_text_equal": a.get("final_text_sha256") == b.get("final_text_sha256"),
            "oracle_on": arms["on"]["oracle"].get("verdict"), "oracle_off": arms["off"]["oracle"].get("verdict"),
            "rc_on": arms["on"]["hermes_rc"], "rc_off": arms["off"]["hermes_rc"]})
    comp = [p for p in pairs if p.get("complete")]
    ident = sum(p["tool_sequence_identical"] for p in comp)
    b_on = sum(p["oracle_on"] == "pass" and p["oracle_off"] != "pass" for p in comp)
    c_off = sum(p["oracle_off"] == "pass" and p["oracle_on"] != "pass" for p in comp)
    out["H3b_paired"] = {
        "pairs_planned": 24, "pairs_complete": len(comp), "tool_sequence_identical": ident,
        "identical_fraction": round(ident / len(comp), 4) if comp else None, "identical_wilson95": wilson(ident, len(comp)),
        "by_task": {t: {"pairs": sum(p["task"] == t for p in comp),
                        "identical": sum(p["task"] == t and p["tool_sequence_identical"] for p in comp)} for t in ("gtk3", "browser")},
        "system_prompt_hash_equal_pairs": sum(p["system_prompt_hash_equal"] for p in comp),
        "final_text_equal_pairs": sum(p["final_text_equal"] for p in comp),
        "oracle_concordant": sum(p["oracle_on"] == p["oracle_off"] for p in comp),
        "oracle_discordant_on_only_pass": b_on, "oracle_discordant_off_only_pass": c_off,
        "sign_test_p": sign_test(b_on, c_off),
        "divergence_causes": {k: sum(p.get("divergence_cause") == k for p in comp)
                              for k in sorted({p.get("divergence_cause") for p in comp if p.get("divergence_cause")})},
        "pairs": pairs}

    # ---- H4 outage ----
    outage = []
    for r in plan:
        if r["arm"] != "outage" or r["run_id"] not in S:
            continue
        s = S[r["run_id"]]
        st = s["shadow"]["receipt_statuses"]
        outage.append({"run_id": r["run_id"], "hermes_rc": s["hermes_rc"], "oracle": s["oracle"].get("verdict"),
                       "receipts": s["shadow"]["receipts"], "statuses": st,
                       "all_backend_unavailable": s["shadow"]["receipts"] > 0 and set(st) == {"backend_unavailable"},
                       "backend_error": (s["shadow"].get("backend_load") or {}).get("error", "")[:160]})
    out["H4_fail_open"] = {"runs": len(outage), "planned": sum(r["arm"] == "outage" for r in plan),
                           "completed_rc0": sum(o["hermes_rc"] == 0 for o in outage),
                           "all_receipts_backend_unavailable": sum(o["all_backend_unavailable"] for o in outage),
                           "pass": len(outage) == sum(r["arm"] == "outage" for r in plan) and
                                   all(o["hermes_rc"] == 0 and o["all_backend_unavailable"] for o in outage),
                           "per_run": outage}

    # ---- secondary ----
    api = defaultdict(int)
    vn = {"n": 0, "label_true": 0, "unknown": 0}
    for r in shadow_runs:
        j = J.get(r["run_id"], {})
        for k, v in (j.get("api_lane") or {}).items():
            api[k] += v
        for t in j.get("traces", []):
            vn["n"] += 1
            if t["gold_verified"] is None:
                vn["unknown"] += 1
            elif t["gold_verified"] is False:
                vn["label_true"] += 1  # verification_needed proxy label: unverified outcome failed the oracle
    api = dict(api)
    api["degenerate"] = api.get("n_positive", 0) < 5
    out["api_attempt_will_fail"] = api
    out["verification_needed_labels"] = vn
    pk = [s["observer"]["peak_prompt_tokens"] for s in S.values() if s["observer"]["peak_prompt_tokens"]]
    out["prompt_tokens"] = {"peak_max": max(pk) if pk else None, "served_context": 32768,
                            "any_over_served_context": any(x >= 32768 for x in pk)}
    iso = [s["isolation"] for s in S.values()]
    out["isolation"] = {"runs": len(iso), "all_masked_empty": sum(x["all_masked_empty"] for x in iso),
                        "env_live_refs_total": sum(x["env_inside_live_refs"] for x in iso),
                        "env_host_display_vars_total": sum(x["env_inside_host_display_vars"] for x in iso),
                        "live_home_files_changed": sorted({f for x in iso for f in x["live_home_entries_changed_during_run"]})}
    out["observer_dropped_rows_total"] = sum(s["observer"]["dropped_rows"] for s in S.values())
    out_p.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: out[k] for k in ("planned", "executed", "missing")}, sort_keys=True))
    for k in ("H1_join", "H2_persistence", "H4_fail_open"):
        print(k, out[k]["pass"])
    print("H3b", {k: out["H3b_paired"][k] for k in ("pairs_complete", "tool_sequence_identical", "oracle_discordant_on_only_pass",
                                                    "oracle_discordant_off_only_pass", "sign_test_p", "divergence_causes")})


if __name__ == "__main__":
    main()
