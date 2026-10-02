"""Build bug01-summary.json from raw/ (parts A and B plus the UNIT receipts).

usage: make_summary.py [packet_dir] [--write]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import analyze_a  # noqa: E402
import analyze_b  # noqa: E402

TEST_LINE = re.compile(r"^test (\S+) \.\.\. (ok|FAILED|ignored)$")


def outcomes(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        m = TEST_LINE.match(line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def steps(path: Path) -> dict[str, int]:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            m = re.match(r"(\S+) rc=(\d+)", line)
            if m:
                out[m.group(1)] = int(m.group(2))
    return out


def unit(packet: Path) -> dict[str, Any]:
    u = packet / "raw" / "unit"
    red_name = "browser::v2_tests::foreground_trusted_browser_input_receipt_does_not_claim_background_delivery"
    guard_name = "browser::v2_tests::background_browser_receipts_keep_background_delivery"
    res: dict[str, Any] = {}
    for label in ("main-test", "fix", "fix2"):
        core = outcomes(u / label / "core-all.txt")
        res[label] = {
            "head": (u / label / "env.txt").read_text().split()[0].split("=")[1] if (u / label / "env.txt").exists() else None,
            "steps_rc": steps(u / label / "steps.txt"),
            "core_tests": len(core),
            "core_failed": sorted(k for k, v in core.items() if v == "FAILED"),
            "red_test": core.get(red_name),
            "guard_test": core.get(guard_name),
            "contract_failed": sorted(k for k, v in outcomes(u / label / "contract-all.txt").items() if v == "FAILED"),
            "driver_goldens_failed": sorted(k for k, v in outcomes(u / label / "driver-receipt-goldens.txt").items() if v == "FAILED"),
            "driver_goldens_tests": len(outcomes(u / label / "driver-receipt-goldens.txt")),
            "contract_tests": len(outcomes(u / label / "contract-all.txt")),
        }
    main_core = outcomes(u / "main-test" / "core-all.txt")
    fix_core = outcomes(u / "fix" / "core-all.txt")
    res["core_outcome_changes_main_test_to_fix"] = {k: [main_core.get(k), fix_core.get(k)] for k in sorted(set(main_core) | set(fix_core)) if main_core.get(k) != fix_core.get(k)}
    fix2_core = outcomes(u / "fix2" / "core-all.txt")
    res["core_outcome_changes_main_test_to_fix2"] = {k: [main_core.get(k), fix2_core.get(k)] for k in sorted(set(main_core) | set(fix2_core)) if main_core.get(k) != fix2_core.get(k)}
    for label, other in (("contract-all", "contract"), ("driver-receipt-goldens", "goldens")):
        res[f"{other}_outcomes_identical_fix_to_fix2"] = outcomes(u / "fix" / f"{label}.txt") == outcomes(u / "fix2" / f"{label}.txt")
    guard_names = [
        "browser::v2_tests::foreground_request_on_a_platform_that_keeps_background_posture_reports_background",
        "browser::v2_tests::foreground_request_on_an_embedded_route_reports_background",
    ]
    red2 = outcomes(u / "guard-red" / "core-focused.txt")
    env2 = u / "guard-red" / "env.txt"
    res["guard-red"] = {
        "head": env2.read_text().split()[0].split("=")[1] if env2.exists() else None,
        "steps_rc": steps(u / "guard-red" / "steps.txt"),
        "outcomes": red2,
    }
    res["activation_guards"] = {name: {"at_guard_test_commit": red2.get(name), "at_fix2": fix2_core.get(name)} for name in guard_names}
    hist2 = u / "fix2" / "history-rerun.txt"
    res["history_rerun_at_fix2"] = [line.strip() for line in hist2.read_text().splitlines() if line.startswith("test result")] if hist2.exists() else []
    instr = outcomes(u / "instr" / "core-lib.txt")
    res["instr"] = {
        "core_lib_tests": len(instr),
        "core_lib_failed": sorted(k for k, v in instr.items() if v == "FAILED"),
        "cdp_counters_tests_ok": sorted(k for k, v in instr.items() if k.startswith("browser::cdp_counters::") and v == "ok"),
    }
    hist = (u / "fix" / "history-rerun.txt")
    res["history_rerun_at_fix"] = [line.strip() for line in hist.read_text().splitlines() if line.startswith("test result")] if hist.exists() else []
    repro = outcomes(u / "repro-ignored.txt")
    res["part_b_repro_ignored_run"] = repro
    return res


def build(packet: Path) -> dict[str, Any]:
    a = analyze_a.main(packet)
    b = analyze_b.main(packet)
    u = unit(packet)
    # The fix candidate is 2533db6d5 + 49a3adf0f ("fix2"); 2533db6d5 alone
    # ("fix") is superseded and kept only as history.
    T_base = a["baseline"]["arms"]["T"]
    T_fix = a["fix2"]["arms"]["T"]
    fix_arms = a["fix2"]["arms"]
    act = a["activation_decoy_control"].get("fix2", {}).get("arms", {})
    gate_a = {
        "fix_label": "fix2",
        "baseline_mislabels_trusted_foreground": T_base["mislabel_trusted_fg_as_background"],
        "red_at_main_test": u["main-test"]["red_test"],
        "green_at_fix": u["fix2"]["red_test"],
        "guard_passes_both": u["main-test"]["guard_test"] == "ok" and u["fix2"]["guard_test"] == "ok",
        "activation_guards_red_then_green": all(v == {"at_guard_test_commit": "FAILED", "at_fix2": "ok"} for v in u["activation_guards"].values()),
        "fix_T_foreground": T_fix["click_delivery_mode"].get("foreground", 0) == T_fix["click_accepted"] == T_fix["n"],
        "fix_D_Y_Ndomfg_background": fix_arms["D"]["click_delivery_mode"] == {"background": fix_arms["D"]["n"]} and fix_arms["N_domfg"]["click_delivery_mode"] == {"background": fix_arms["N_domfg"]["n"]} and all(arm["type_delivery_mode"] == {"background": arm["n"]} for arm in fix_arms.values()),
        "fix_Nbg_no_delivery": fix_arms["N_bg"]["click_delivery_mode"] == {"None": fix_arms["N_bg"]["n"]} and fix_arms["N_bg"]["click_accepted"] == 0,
        "only_delivery_mode_changed": a["only_delivery_mode_changed_fix2"],
        "contract_and_goldens_unchanged": u["main-test"]["steps_rc"].get("contract-all") == 0 and u["fix2"]["steps_rc"].get("contract-all") == 0 and u["main-test"]["steps_rc"].get("driver-receipt-goldens") == 0 and u["fix2"]["steps_rc"].get("driver-receipt-goldens") == 0,
        "supporting_not_preregistered_decoy_control": {
            "T_activates_browser": act.get("T", {}).get("browser_active_post") == act.get("T", {}).get("n", -1) == act.get("T", {}).get("decoy_active_pre"),
            "D_leaves_decoy_active": act.get("D", {}).get("decoy_active_post") == act.get("D", {}).get("n", -1) == act.get("D", {}).get("decoy_active_pre"),
            "T_receipt_foreground": act.get("T", {}).get("receipt_delivery_mode") == {"foreground": act.get("T", {}).get("n")},
            "D_receipt_background": act.get("D", {}).get("receipt_delivery_mode") == {"background": act.get("D", {}).get("n")},
        },
    }
    gate_a["disposition"] = "CONFIRMED_BUG" if (gate_a["baseline_mislabels_trusted_foreground"] >= 1 and gate_a["red_at_main_test"] == "FAILED" and gate_a["green_at_fix"] == "ok" and all(gate_a[k] for k in ("guard_passes_both", "activation_guards_red_then_green", "fix_T_foreground", "fix_D_Y_Ndomfg_background", "fix_Nbg_no_delivery", "only_delivery_mode_changed", "contract_and_goldens_unchanged"))) else "NOT_A_BUG"
    for side in ("baseline", "fix"):
        a.pop("field_distributions", None)
    return {"schema": "cua.bug01.summary.v1", "part_a": a, "part_a_gates": gate_a, "part_b": b, "unit": u, "provider": {"attempts": 0, "reached": 0}}


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    packet = Path(args[0]) if args else HERE
    summary = build(packet)
    text = json.dumps(summary, indent=1, sort_keys=True) + "\n"
    if "--write" in sys.argv:
        (packet / "bug01-summary.json").write_text(text)
    else:
        sys.stdout.write(text)
