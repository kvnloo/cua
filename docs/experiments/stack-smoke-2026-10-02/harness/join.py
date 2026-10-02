"""Join each shadow-arm run's independent fixture verdict onto its Hermes trace with EXISTING z0int code.

Run with the z0int venv after the run finished (offline; Hermes is gone).
  * adapters.hermes_z0int.normalize_envelope / close_observation / join_outcome  (turn lane)
  * z0int.receipt.join_outcome(trace_id, Outcome(...))                            (receipt lane)
  * api.attempt_will_fail labels: objective lifecycle (#386 semantics), per attempt key
    (api_request_id, retry_count), with every unmatched attempt COUNTED (never dropped).
Writes <run>/join/{observations.jsonl,api_lane_labels.jsonl,join_summary.json}; z0int.receipt.join_outcome
appends to <run>/shadow/z0int-home/receipts/outcomes.jsonl (+ an updated receipt row).
usage: join.py --z0-wt <dir> <run dir> [...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--z0-wt", required=True)
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    sys.path[:0] = [a.z0_wt, str(Path(a.z0_wt) / "src")]
    from adapters.hermes_z0int import close_observation, join_outcome, normalize_envelope
    from z0int import receipt as zr

    for arg in a.runs:
        rd = Path(arg)
        run = json.loads((rd / "run.json").read_text())
        oracle = json.loads((rd / "oracle.json").read_text()) if (rd / "oracle.json").exists() else {"verdict": "unknown"}
        gold = {"pass": True, "fail": False}.get(oracle.get("verdict"))
        ev = jl(rd / "home" / ".hermes" / "plugin-data" / "z0-hermes-observer" / "events.jsonl")
        out = rd / "join"
        out.mkdir(exist_ok=True)
        zhome = rd / "shadow" / "z0int-home"
        summary = {"run_id": run["run_id"], "arm": run["arm"], "oracle_verdict": oracle.get("verdict"), "traces": []}
        # ---- turn lane: one observation per trace (turn) ----
        traces: dict[str, dict] = {}
        for r in ev:
            i, f = r.get("identity") or {}, r.get("fields") or {}
            if not (i.get("trace_id") and i.get("turn_id")):
                continue
            t = traces.setdefault(i["trace_id"], {"session_id": i.get("session_id"), "turn_id": i.get("turn_id"),
                                                  "model": None, "completed": None, "exit": None})
            t["model"] = f.get("model") or t["model"]
            if r.get("event") == "on_session_end":
                t["completed"], t["exit"] = f.get("completed"), f.get("turn_exit_reason")
        with (out / "observations.jsonl").open("w") as fh:
            for tid, t in traces.items():
                env = normalize_envelope({"session_id": t["session_id"], "turn_id": t["turn_id"], "trace_id": tid,
                                          "process_id": 0})
                execution_completed = bool(t["completed"]) if t["completed"] is not None else t["exit"] is not None
                obs = close_observation(env, execution_completed=execution_completed, verified_success=None,
                                        model=t["model"], provider="hermes")
                joined = join_outcome(obs, gold_verified=gold)
                fh.write(json.dumps(joined, sort_keys=True) + "\n")
                rec_join = None
                if zhome.exists():  # receipt lane: shadow arms only (off arm writes no z0int receipts)
                    oc = zr.Outcome(execution_completed=execution_completed, verified_success=gold,
                                    verification_source=oracle.get("source") or "fixture_oracle:unknown",
                                    source="hermes", note=f"stack-smoke {run['run_id']}")
                    rec_join = zr.join_outcome(tid, oc, root=zhome)
                summary["traces"].append({
                    "trace_id": tid, "turn_id": t["turn_id"], "session_id": t["session_id"],
                    "execution_completed": execution_completed, "gold_verified": gold,
                    "observation_verified_success": joined["verified_success"],
                    "receipt_join": None if rec_join is None else {
                        "outcome_tier": rec_join["outcome_tier"],
                        "joined_receipt_capability": (rec_join.get("receipt") or {}).get("capability_id"),
                        "joined_receipt_trace_matches": (rec_join.get("receipt") or {}).get("trace_id") == tid}})
        # ---- api lane: objective lifecycle label per physical attempt ----
        pending: dict[tuple, dict] = {}
        labels, n_terminal_without_pre, n_overwritten = [], 0, 0
        for r in ev:
            e, i, f = r.get("event"), r.get("identity") or {}, r.get("fields") or {}
            key = (i.get("api_request_id"), int(f.get("api_call_count") or 0))
            if not key[0]:
                continue
            if e == "pre_api_request":
                if key in pending:
                    n_overwritten += 1
                pending[key] = {"opportunity_id": f"{key[0]}#r{int(f.get('retry_count') or 0)}", "trace_id": i.get("trace_id")}
            elif e in ("post_api_request", "api_request_error"):
                p = pending.pop(key, None)
                if p is None:
                    n_terminal_without_pre += 1
                    continue
                labels.append({**p, "attempt_will_fail_label": e == "api_request_error", "outcome_source": e})
        with (out / "api_lane_labels.jsonl").open("w") as fh:
            for x in labels:
                fh.write(json.dumps(x, sort_keys=True) + "\n")
        summary["api_lane"] = {"n_pre": sum(r.get("event") == "pre_api_request" for r in ev), "n_joined": len(labels),
                               "n_orphan_pre": len(pending), "n_overwritten_pre": n_overwritten,
                               "n_terminal_without_pre": n_terminal_without_pre,
                               "n_positive": sum(x["attempt_will_fail_label"] for x in labels),
                               "n_negative": sum(not x["attempt_will_fail_label"] for x in labels)}
        (out / "join_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
        print(run["run_id"], oracle.get("verdict"), len(traces), summary["api_lane"])


if __name__ == "__main__":
    main()
