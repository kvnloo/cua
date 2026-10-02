#!/usr/bin/env python3
"""R2-09 quick per-trial view of a raw trials.jsonl (pilot inspection; stdlib only)."""

from __future__ import annotations

import json
import sys


def mark_ms(marks, scope, name_prefix, base_wall):
    for m in marks:
        if m.get("scope") == scope and str(m.get("mark", "")).startswith(name_prefix):
            return round((m["wall_ns"] - base_wall) / 1e6, 2), m["mark"]
    return None, None


def main() -> None:
    for line in open(sys.argv[1], encoding="utf-8"):
        r = json.loads(line)
        if r["event"] != "trial":
            print({k: v for k, v in r.items() if k in ("event", "failures", "chrome_version", "session_a11y",
                                                       "registry_pid_at_start", "registry_pid_at_end", "net")})
            continue
        print(f"== {r['id']} arm={r['arm']} fail={r.get('failure')} verified={r.get('oracle_verified')}"
              f" load={r.get('loadavg', [None])[0]}")
        for a in r.get("actions", []):
            st = a.get("structured", {})
            print(f"   {a['tool']:9s} {a['wrapper_ms']:8.1f} ms err={a['error']} route={st.get('route')}"
                  f" path={st.get('path')} effect={st.get('effect')} deliv={st.get('delivery')}"
                  f" code={st.get('code')}")
        marks = r.get("marks", [])
        dar = [m for m in marks if m.get("mark") == "do_action_replied"]
        if dar:
            base = dar[-1]["wall_ns"]
            for scope, pre in (("atspi_action", "post_wake"), ("atspi_action", "post_sleep_done"),
                               ("focus_guard", "body_done"), ("click", "ax_joined")):
                print(f"   mark {pre}: {mark_ms(marks, scope, pre, base)}")
        else:
            print("   no do_action_replied mark;", sorted({(m.get('scope'), m.get('mark')) for m in marks
                                                         if m.get('scope') in ('click', 'atspi_action')})[:12])
        ss = r.get("state_samples")
        if ss and r.get("actions"):
            ret_us = (r["actions"][-1]["m1"] - ss["anchor_ns"]) / 1000
            first_after = next((i for i, t in enumerate(ss["t0_us"]) if t >= ret_us), None)
            st = ss["states"][ss["idx"][first_after]] if first_after is not None else None
            exp = r.get("expected", {})
            vis = isinstance(st, dict) and all(st.get(k) == v for k, v in exp.items())
            land = next((ss["t1_us"][i] for i, ix in enumerate(ss["idx"])
                         if isinstance(ss["states"][ix], dict)
                         and all(ss["states"][ix].get(k) == v for k, v in exp.items())), None)
            print(f"   return={ret_us/1000:.1f} ms land={None if land is None else round(land/1000, 1)} visible_at_return={vis}")
            fs = r.get("final_state") or {}
            print("   journal", [(j["kind"], round((j["m_ns"] - ss["anchor_ns"]) / 1e6, 1))
                              for j in fs.get("journal", []) if j["kind"] != "loaded"])
        if r.get("listener"):
            sig = [e for e in r["listener"] if e.get("event") == "signal"
                   and str(e.get("interface", "")).endswith("Event.Object")]
            anchor = (r.get("state_samples") or {}).get("anchor_ns", 0)
            print(f"   listener object signals={len(sig)}",
                  [(e["member"], e.get("detail"), e.get("detail1"), e["sender"], e["path"][-12:],
                    round((e["m_ns"] - anchor) / 1e6, 1)) for e in sig
                   if e["member"] in ("StateChanged", "TextChanged", "PropertyChange")][:25])
        if r.get("perturb"):
            print("   perturb", r["perturb"], "registry_after", r.get("registry_pid_after"))
        if r.get("failure"):
            print("   logs", {k: v[-400:] for k, v in r.get("app_logs", {}).items()})


if __name__ == "__main__":
    main()
