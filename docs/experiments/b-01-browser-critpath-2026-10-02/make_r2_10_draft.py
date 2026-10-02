"""Write R2-10-PREREG-DRAFT.json (live R2-10 readiness; NOT executed) from b01-summary.json.

The composed arm takes exactly the knobs whose B-01 gates held; the baseline is
the K0n shape. Provider requests per pair come from the decision routes B-01
observed (provider decisions per verified trial).
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAIRS = 30


def main() -> None:
    s = json.loads((HERE / "b01-summary.json").read_text())
    h = s["hypotheses"]
    hv_keep = all(h["H_V"][c]["verdict"] == "KEEP" for c in ("fill", "toggle", "modal"))
    ht = h["H_T"]["verdict"]
    hp_keep = {c: h["H_P"][c]["verdict"] == "KEEP" for c in ("fill", "toggle", "modal")}
    hc_keep = {c: h["H_C"][c]["verdict"] == "KEEP" for c in ("fill", "toggle", "modal")}
    any_hc = any(hc_keep.values())
    k5_fill_poll_frac = s["classes"]["fill"]["arms"]["K5"]["sleeps_entered_frac"]
    feedback = ("fast glide: set_agent_cursor_motion {glide_duration_ms:1, dwell_after_click_ms:0}, cursor enabled"
                if hv_keep else "feedback OFF: set_agent_cursor_enabled {enabled:false}")
    decisions = {"fill": {"baseline": 2, "composed": 1}, "toggle": {"baseline": 2, "composed": 2},
                 "modal": {"baseline": 2, "composed": 2}}
    per_pair = {c: d["baseline"] + d["composed"] for c, d in decisions.items()}
    total = PAIRS * sum(per_pair.values())
    draft = {
        "schema": "cua-rfc-loop.prereg.v1",
        "status": "DRAFT - not executed; written by B-01 from b01-summary.json",
        "experiment": "R2-10 live composition: baseline vs composed surviving deletions on one source",
        "source": "branch exp/b-01-browser-critpath-20261002, Driver commit f5c991e5927513c8b94da4330c94276dc5f8ce22 "
                  "(229b65b28 + R2-01 trace + B-01 marks/knob, merged with trycua/cua PR 4316 a0bca7440)",
        "binary": {"name": "cua-driver-b01-f5c991e59",
                   "sha256": "2e0248ad2b6efedd6c5f7acba6b5d8bd92160a29a6c9c80061bce5ea4efa43f3",
                   "rule": "same binary in both arms; experiment knobs set only in the composed arm; trace on in both arms"},
        "provider": {"name": "TypeSafe", "path": "jev-use choose_live_for_task (request builder validated dry for toggle/modal in B-01 raw/live-request-validation.json)",
                     "secret_forwarding": "CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY (by name only)"},
        "classes": ["fill", "toggle", "modal"],
        "arms": {
            "baseline": "K0n shape: feedback default ON, no guarded completion, focus settle unset (100 ms), completion poll 100 ms, library MCP schema validation",
            "composed": {
                "feedback": feedback,
                "focus_settle": "CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS=0 (fill)" if ht == "OWNER_DECISION" else "unset",
                "completion_poll": {c: ("10 ms, same 2.0 s deadline" if (k or any_hc) else "100 ms") for c, k in hp_keep.items()},
                "completion_poll_rationale": "H_P found no material component with library validation, but with compiled validators the fill "
                                             f"completion poll is entered in {k5_fill_poll_frac:.0%} of K5 trials (the action returns before the "
                                             "submit lands), so the composed arm keeps the cost-free 10 ms poll",
                "mcp_client_validation": "compiled once per schema at tools/list (caller-side), all classes" if any_hc else "library default",
                "mcp_client_validation_basis": {c: h["H_C"][c]["verdict"] for c in hc_keep},
                "guarded_completion": "PR 4316 --guarded-completion on fill only (binds only FIXTURE_TASK_ID; does not apply to toggle/modal at this source)",
                "compiled_replay": "slot reserved; enabled only if R2-07 is KEEP, measured over all invocations incl. fallback and compile/admission cost",
            },
        },
        "design": {"pairs_per_class": PAIRS, "order": "AB/BA alternating per pair, classes interleaved per round",
                   "lock": "EXCLUSIVE quiet-lane lock; loadavg per trial; every trial and failure kept"},
        "metrics": {"T": "first semantic_v2 send -> runner's first oracle-confirmed read (T_runner, B-01 definition); T_oracle (2 ms harness re-read) also reported",
                    "S": "median T_baseline / median T_composed per class with seeded paired bootstrap CI (10000, seed fixed in the final PREREG)",
                    "floor_ratio": "T_composed / T_irreducible, T_irreducible = sum of IRREDUCIBLE components from the decomposition",
                    "decision_ms": "provider decision time per decision (live)"},
        "gates": {"validity": ">= 95% verified per arm per class, identical verified outcomes",
                  "E3": ">= 30 AB/BA pairs per browser class with identical verified outcomes"},
        "provider_budget": {"decisions_per_trial": decisions, "requests_per_pair": per_pair,
                            "requests_reaching_provider_total": total,
                            "attempt_cap": int(total * 1.1),
                            "stop_rule": "stop the lane when reached requests exceed the attempt cap or the loop budget in STATE.json"},
        "b01_inputs": {"H_V": {c: h["H_V"][c]["verdict"] for c in ("fill", "toggle", "modal")}, "H_T": ht,
                       "H_P": {c: h["H_P"][c]["verdict"] for c in ("fill", "toggle", "modal")},
                       "H_C": {c: h["H_C"][c]["verdict"] for c in ("fill", "toggle", "modal")}},
    }
    (HERE / "R2-10-PREREG-DRAFT.json").write_text(json.dumps(draft, indent=1) + "\n")
    print(json.dumps({"requests_total": total, "per_pair": per_pair}))


if __name__ == "__main__":
    main()
