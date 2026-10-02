#!/usr/bin/env python3
"""Render the README's generated tables from own-20-summary.json (deterministic).

usage: render_tables.py <own-20-summary.json>   -> markdown on stdout
verify_artifacts.py checks that the README block between the GENERATED markers equals this output
for the recomputed summary.
"""

from __future__ import annotations

import json
import sys

CLASS_ORDER = ["text", "focus", "selection", "checkbox", "child_add", "child_remove", "node_recreate", "window",
               "process_lifecycle", "restart_pipeline", "registry_restart", "listener_subscription"]
ROW_ORDER = ["text_v1", "text_v2", "focus_v1", "focus_v2", "selection_v1", "selection_v2", "checkbox_v1",
             "checkbox_v2", "child_add_pts", "child_add_stp", "child_remove_pts", "child_remove_stp", "recreate",
             "window_create", "window_destroy", "exit_v1", "exit_v2", "process_start", "post_restart_probe",
             "registry_restart", "post_registry_probe", "noop", "decoy", "listener_cycle"]


def ms(s: dict) -> str:
    if not s or not s.get("n"):
        return "n/a"
    return f'{s["median"]:.3f} / {s["p95"]:.3f} (n={s["n"]})'


def render(summary: dict) -> str:
    out = []
    out.append("### Classification (pre-registered rule)\n")
    out.append("| scope | verdict | own delta reps | own FN_L2 | own FN_L1 | inherited FN_L2 (rows) | event absence authorizes reuse | recommendation |")
    out.append("|---|---|---|---|---|---|---|---|")
    for scope in CLASS_ORDER:
        c = summary["classification"][scope]
        inh = sum(c["inherited_fn_l2"].values())
        inh_rows = ", ".join(f"{k} {v}/{c['inherited_delta_reps'][k]}" for k, v in c["inherited_fn_l2"].items()) or "none"
        out.append(f"| `{scope}` | {c['verdict']} | {c['own_delta_reps']} | {c['own_fn_l2']} | {c['own_fn_l1']} | "
                   f"{inh} ({inh_rows}) | {'yes' if c['event_absence_authorizes_reuse'] else 'no'} | {c['recommendation']} |")
    out.append("\n### Per-row census (all blocks; N of M = reps with the property of reps attempted)\n")
    out.append("| row | scope | variant | attempted | failures | relevant delta | L2 present | L1 present | FN_L2 | FN_L1 | FP (target) | FP (any AT-SPI) | obs/oracle disagree | L2 types seen | evidence |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for mid in ROW_ORDER:
        r = summary["per_row"].get(mid)
        if r is None:
            continue
        att = r["attempted"]
        out.append(f"| `{mid}` | {r['scope']} | {r['variant']} | {att} | {r['failures']} | {r['relevant_delta']}/{att} | "
                   f"{r['l2_present_in_delta']}/{r['relevant_delta']} | {r['l1_present_in_delta']}/{r['relevant_delta']} | "
                   f"{r['false_negative_l2']} | {r['false_negative_l1']} | {r['false_positive_target']}/{r['no_delta']} | "
                   f"{r['false_positive_any_atspi']}/{r['no_delta']} | {r['obs_oracle_disagree']} | "
                   f"{', '.join(r['l2_types_seen']) or 'none'} | REAL |")
    out.append("\n### Timings (timing blocks only, AMENDMENT-1; ms, median / nearest-rank p95)\n")
    out.append("| row | first L2 event after mutation start | first L1 event | last target event in window | first L2 after Driver tool return | fixture op | Driver call | evidence |")
    out.append("|---|---|---|---|---|---|---|---|")
    for mid in ROW_ORDER:
        r = summary["per_row"].get(mid)
        if r is None:
            continue
        out.append(f"| `{mid}` | {ms(r['first_l2_ms'])} | {ms(r['first_l1_ms'])} | {ms(r['last_target_event_ms'])} | "
                   f"{ms(r['first_l2_after_return_ms'])} | {ms(r['fixture_op_ms'])} | {ms(r['driver_call_ms'])} | REAL+BENCHMARK |")
    lt = summary["listener_timing_retained"]
    lc = summary["per_row"].get("listener_cycle", {})
    out.append("\n### Listener subscription and cleanup cost (timing blocks only; ms, median / p95)\n")
    out.append("| listener | subscription (address + connect + subscribe + RegisterEvent x4) | spawn to ready (process start included) | cleanup (DeregisterEvent x4 + unsubscribe + close) | SIGTERM to exit | evidence |")
    out.append("|---|---|---|---|---|---|")
    out.append(f"| retained, one per block | {ms(lt['subscription_ms'])} | {ms(lt['spawn_to_ready_ms'])} | {ms(lt['cleanup_ms'])} | {ms(lt['stop_to_exit_ms'])} | REAL+BENCHMARK |")
    out.append(f"| fresh, one per listener_cycle rep | {ms(lc.get('fresh_subscription_ms'))} | {ms(lc.get('fresh_spawn_to_ready_ms'))} | {ms(lc.get('fresh_cleanup_ms'))} | {ms(lc.get('fresh_stop_to_exit_ms'))} | REAL+BENCHMARK |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.stdout.write(render(json.load(open(sys.argv[1]))))
