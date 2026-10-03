#!/usr/bin/env python3
"""FRESH-07: assemble fresh07-summary.json from the packet's own artifacts (stdlib only)."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(p: str) -> dict:
    return json.loads((HERE / p).read_text(encoding="utf-8"))


def main() -> None:
    probe = load("probe-summary.json")["binaries"]
    claims = load("claims.json")
    p = load("p2/own-20p/own20p-recert-summary.json")
    q = load("p2/own-20q/own20q-summary.json")
    timing = load("p2/timing-status.json")
    old = ("Rp", "B7", "Rn")
    S = {
        "schema": "cua.r2.fresh07.summary.v1",
        "lane": "FRESH-07",
        "sources": {"old": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218", "new": "9a2b1d99ec8044ff58b2a2b46802edd2609c057b"},
        "changes": {
            "overlay.rs (trycua/cua PR 4529)": "Linux-relevant; AFFECTS native guarded rows and cursor-on timing rows",
            "expectation.rs (trycua/cua PR 4531)": "UNAFFECTED for every claim (SOURCE + UNIT)",
            "version bump 0.33.0": "UNAFFECTED for every claim (SOURCE + REAL tools/list digest)",
            "non-Linux files": "33 of 39 paths; scenarios.json appkit-only",
        },
        "probe": {
            "old_idle_viewable_empty": sum(probe[n]["points"]["S1_idle"].get("VIEWABLE(b0,i0)", 0) for n in old),
            "old_runs": sum(probe[n]["runs"] for n in old),
            "new_idle_unmapped": probe["M"]["points"]["S1_idle"].get("UNMAPPED(b0,i0)", 0),
            "new_runs": probe["M"]["runs"],
            "grab_text_new_on_off": [probe["M"]["grab_held_by_on"], probe["M"]["grab_held_by_off"]],
            "grab_text_old_on_off": [sum(probe[n]["grab_held_by_on"] for n in old), sum(probe[n]["grab_held_by_off"] for n in old)],
            "old_overlay_viewable_before_initialize": sum(probe[n]["startup_viewable_before_init"] for n in old),
            "class": "FIXTURE",
        },
        "claims": [{k: c[k] for k in ("claim", "packet", "verdict", "phase2")} for c in claims["overlay_rs_per_claim"]],
        "phase2": {
            "OWN-20P": {"R1_gate": p["r1"]["gate"], "G0m_restored": f"{p['r1']['G0m_restored']}/{p['r1']['G0m_attempted']}",
                        "checkbox_G0m_receipts": p["r1"]["checkbox/G0m"]["receipt_outcomes"],
                        "U0m_silent_miss": f"{p['r1']['U0m_silent_miss']}/{p['r1']['U0m_attempted']}",
                        "normal_gate": p["normal"]["gate"], "class": "REAL (FIXTURE)", "verdict": "RECERT_FAIL (R1); NORMAL holds"},
            "OWN-20Q": {"R1m_gate": q["r1m"]["gate"], "G0_verified_restore": f"{q['r1m']['G0_verified_restore']}/40",
                        "U0_silent_miss": f"{q['r1m']['U0_silent_miss']}/40", "DLG_gate": q["dlg"]["gate"],
                        "GA_misclassified": q["dlg"]["GA_misclassified"], "GQ_verified_restore": q["dlg"]["GQ_verified_restore"],
                        "GQ_receipts": q["dlg"]["receipts"]["GQ"], "dialog_control": {k: v["dialog_left_focused"] for k, v in q["dlg"]["dialog_control"].items()},
                        "normal_gate": q["normal"]["gate"], "class": "REAL (FIXTURE)", "verdict": "RECERT_FAIL (R1m, DLG); dialog control and normal path hold"},
            "R2-10R_default_off_smoke": {"pass": True, "toolslist_sha256": "33772fab460a59e43b7a3bdb2c7a600477768fbc55715a419ad4ab1cfee9c9b1", "class": "REAL"},
            "timing_rows": timing,
        },
        "changed_claims": [
            "OWN-20P R1 (kvnloo/cua#20 G port): G0m restore 40/40 -> 20/40 on 9a2b1d99e (checkbox 0/20 focus_outcome=grab_held)",
            "OWN-20Q R1m (kvnloo/cua#20): G0 verified restore 40/40 -> 20/40",
            "OWN-20Q DLG (kvnloo/cua#20 DLG fix): GQ correct 20/20 -> 0/20 restored (grab_held 20/20)",
        ],
        "mechanism": "9a2b1d99e keeps the X11 agent overlay unmapped at idle; a native background click's cursor reveal maps it while focus_guard::guarded watches; focus_guard.rs mapped_popups() has no own-overlay filter, so the overlay counts as a new popup (grab_held_by) and the guard skips the restore after a focus steal",
        "e4": {"own20p": p["e4"], "own20q": q.get("e4")},
        "provider": {"attempts": 0, "reached": 0},
        "work_deleted_vs_wall_clock": "none claimed (freshness only)",
    }
    (HERE / "fresh07-summary.json").write_text(json.dumps(S, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"changed_claims": len(S["changed_claims"]), "timing": timing.get("status")}))


if __name__ == "__main__":
    main()
