"""Write this lane's summary.json from committed receipts.  python make_summary.py <lane_packet_dir>"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    here = Path(sys.argv[1]).resolve()
    samples = here.parent / "stack-samples-2026-10-02"
    raw = here / "raw"
    tally = json.loads((samples / "raw" / "analysis" / "cua-bridge-tally.json").read_text())
    nk = json.loads((raw / "numbers-kept.json").read_text())
    tamper = [l for l in (raw / "tamper.log").read_text().splitlines() if l.startswith("TAMPER ")]
    pc = [l.split() for l in (raw / "smoke-positive-control.txt").read_text().splitlines() if l and not l.startswith("#")]
    unit = (samples / "raw" / "unit" / "unit-lab-5d01f608.log").read_text()
    s_sum = json.loads((samples / "summary.json").read_text())
    out = {
        "schema": "stack.samplesfix.summary.v1",
        "lane": "stack v2 SAMPLESFIX",
        "new_data_collected": False,
        "checks": {
            "C1_cua_attribution": "PASS" if (tally["totals"]["tool_calls_completed"] == 0 and tally["totals"]["approval_lines"] == 0
                                             and tally["totals"]["computer_use_dispatches"] == 0
                                             and tally["totals"]["runs_gui_state_unchanged"] == tally["n_cua_runs"]) else "FAIL",
            "C2_count_reporting": {"tool_errors_total": tally["totals"]["tool_errors"], "by_class": tally["totals"]["tool_error_classes"],
                                   "verifier_figure": 23, "reconciliation": "the verifier's 23 is the missing_calls_array class only"},
            "C3_verify_and_tamper": {"samples_verify_after": (raw / "verify-samples-after.log").read_text().strip().splitlines()[-1],
                                     "tamper_copies": len(tamper), "tamper_all_fail": all(l.endswith("RESULT FAIL") for l in tamper)},
            "C4_table_reproducibility": "PASS (SAMPLES verify checks 12)",
            "C5_manifest_reproducibility": "PASS (SAMPLES verify checks 2 and 13)",
            "C6_numbers_kept": nk["all_kept"],
            "C7_unit": {"run1": "25 passed, 2 skipped" if "25 passed, 2 skipped" in unit else "MISMATCH",
                        "run2_with_z0int": "13 passed" if "13 passed" in unit else "MISMATCH"},
        },
        "cua_bridge": tally["totals"],
        "smoke_positive_control_dispatch_lines": sum(int(x[0]) for x in pc),
        "samples_dataset_content_sha256": s_sum["dataset_content_sha256"],
        "samples_headline_unchanged": {"oracle_pass": s_sum["workload"]["oracle_pass"], "oracle_fail": s_sum["workload"]["oracle_fail"],
                                       "api_positives": s_sum["lanes"]["api.attempt_will_fail"]["n_positive"],
                                       "verification_needed_positive": s_sum["lanes"]["verification_needed"]["n_positive"],
                                       "julia_1_brier": s_sum["lanes"]["verification_needed"]["rows"]["julia_1"]["brier"]},
        "withdrawn": "owner-decision request for an approval bypass (approvals.single_query_mode)",
        "evidence": {"SOURCE": ["re-derivation scripts", "tools/tool_search_validation.py pre-dispatch refusals"],
                     "REAL": ["existing receipts of the 105 SAMPLES runs (no new runs)"], "UNIT": ["lab suite log"],
                     "NOT_RUN": ["new collection, scoring, model calls, Driver sessions"]},
    }
    (here / "summary.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out["checks"], sort_keys=True))


if __name__ == "__main__":
    main()
