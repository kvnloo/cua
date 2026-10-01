"""Recompute every R2-06 headline number from raw/ and check the packet.

usage: python3 verify_artifacts.py   (stdlib only; exits non-zero on mismatch)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402

PREREG_SHA256 = "4f88adc786ae0ddc4f79bbdabda09850b34502d000f001e61d10e6a13c93f840"

# Headline numbers stated in README.md (main phase, main Driver 0.32.0).
HEADLINE = {
    "T": {"n": 30, "accepted": 30, "verified_immediate": 17, "verified_late": 13, "verified_within_bound": 30,
          "trusted_pointerdown_on_submit_trials": 30, "click_on_submit_trials": 30, "submit_event_trials": 30,
          "exactly_one_post_with_token_trials": 30, "posts_total": 30, "x11_button_events_total": 0, "x11_any_events_total": 0,
          "active_is_browser_pre": 30, "active_is_browser_post": 30, "page_has_focus_at_pointerdown": 30,
          "point_inside_rect_at_load": 30, "point_inside_rect_at_pointerdown": 30, "rect_moved_load_to_pointerdown": 0,
          "resize_events_total": 0, "stale_page_events_total": 0},
    "D": {"n": 30, "accepted": 30, "verified_immediate": 30, "verified_late": 0, "verified_within_bound": 30,
          "click_on_submit_trials": 30, "submit_event_trials": 30, "exactly_one_post_with_token_trials": 30,
          "posts_total": 30, "x11_any_events_total": 0},
    "T_plain": {"n": 5, "accepted": 5, "verified_immediate": 2, "verified_late": 3, "verified_within_bound": 5, "posts_total": 5},
    "D_plain": {"n": 5, "accepted": 5, "verified_immediate": 5, "verified_within_bound": 5, "posts_total": 5},
}
CONTROLS = {
    "N_bg": ("refused", "browser_input_trust_unavailable"),
    "N_stale": ("refused", "browser_ref_stale"),
    "N_blank": ("miss_wrong_target", None),
    "N_empty": ("miss_click_no_submit_invalid", None),
}


def main() -> None:
    fails: list[str] = []
    prereg = hashlib.sha256((HERE / "PREREG.json").read_bytes()).hexdigest()
    if prereg != PREREG_SHA256:
        fails.append(f"PREREG.json sha256 {prereg} != pre-registered {PREREG_SHA256}")

    fresh = json.loads(json.dumps(analyze.compute(), sort_keys=True, default=list))
    stored = json.loads((HERE / "r2-06-summary.json").read_text())
    if fresh != stored:
        fails.append("r2-06-summary.json differs from a fresh recomputation of raw/")
    main_phase = fresh["phases"]["main"]
    if main_phase["trials"] != 82 or main_phase["harness_errors"] != 0 or main_phase["blocks"] != 8:
        fails.append(f"main phase shape: {main_phase['trials']} trials, {main_phase['harness_errors']} harness errors, {main_phase['blocks']} blocks")
    if main_phase["driver_versions"] != ["0.32.0"]:
        fails.append(f"driver versions {main_phase['driver_versions']}")
    st = main_phase["x_recorder_selftest_events"] or {}
    if not st.get("RawMotion"):
        fails.append("X recorder positive control saw no RawMotion")
    for arm, expected in HEADLINE.items():
        got = main_phase["arms"][arm]
        for k, v in expected.items():
            if got.get(k) != v:
                fails.append(f"{arm}.{k}: recomputed {got.get(k)!r} != README {v!r}")
    for arm, (cls, code) in CONTROLS.items():
        rows = main_phase["controls"][arm]
        if len(rows) != 3:
            fails.append(f"{arm}: {len(rows)} trials")
        for r in rows:
            if r["class"] != cls or r["refusal_code"] != code or r["final_state"] != {"submitted": None} or r["posts_total"] != 0:
                fails.append(f"{arm}: unexpected control row {r}")
    conc = main_phase["post_timing_concordance"]
    if not (conc["separated"] and conc["late_all_post_after_return"]):
        fails.append(f"POST timing does not separate immediate/late: {conc}")
    # Verifier arm (fix proposal) on identical T receipts.
    t = main_phase["arms"]["T"]
    single_read, bounded = t["verified_immediate"], t["verified_within_bound"]
    if (single_read, bounded) != (17, 30):
        fails.append(f"verifier arm: single-read {single_read}/30, bounded {bounded}/30")

    readme = (HERE / "README.md").read_text()
    for needle in ("**17/30**", "**30/30**", "**13/30**", "KEEP H", "3.6–10.1 ms", "4f88adc786ae0ddc4f79bbdabda09850b34502d000f001e61d10e6a13c93f840"):
        if needle not in readme:
            fails.append(f"README missing headline {needle!r}")

    # Privacy scan: no absolute local paths, host markers or secret-looking values in the packet.
    bad = re.compile("/" + "home/|/" + "mnt/|/" + r"tmp/claude|x11-session\.[A-Za-z0-9]{6}|TYPESAFE_API_KEY" + r"=|sk-[A-Za-z0-9]{16,}|BEGIN [A-Z ]*PRIVATE KEY")
    for f in HERE.rglob("*"):
        if f.is_file() and f.suffix in {".json", ".jsonl", ".md", ".py", ".sh", ".txt", ".log"}:
            text = f.read_text(errors="replace")
            m = bad.search(text)
            if m:
                fails.append(f"privacy: {f.relative_to(HERE)} contains {m.group(0)!r}")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print(json.dumps({
        "T_trusted": f"accepted {t['accepted']}/30, single immediate read verified {single_read}/30, bounded (<=3000 ms) re-read verified {bounded}/30, late {t['verified_late']}/30",
        "D_dom_event": f"verified immediate {main_phase['arms']['D']['verified_immediate']}/30",
        "late_first_verified_ms_min_p50_max": t["late_first_verified_ms_min_p50_max"],
        "post_timing": conc,
        "controls": "N_bg 3/3 refused trust_unavailable; N_stale 3/3 refused ref_stale; N_blank 3/3 accepted, body hit, no submit; N_empty 3/3 invalid, no POST",
        "x11_events_during_clicks": t["x11_any_events_total"] + main_phase["arms"]["D"]["x11_any_events_total"],
        "prereg_sha256_ok": prereg == PREREG_SHA256,
    }, indent=1))
    print("R2-06 evidence checks passed")


if __name__ == "__main__":
    main()
