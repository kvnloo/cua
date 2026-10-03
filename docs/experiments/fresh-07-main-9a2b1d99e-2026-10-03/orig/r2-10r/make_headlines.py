#!/usr/bin/env python3
"""Write headline-numbers.json from r2-10r-summary.json, d1-summary.json and recert-summary.json.

Each headline is "<doc>:<path>" plus a format (doc S = r2-10r-summary, D = d1-summary, G = recert-summary,
N = nm2-sensitivity, PREREG-AMENDMENT-2);
verify_artifacts.py recomputes each value from raw/ and requires the formatted text to appear verbatim
in README.md. (R2-10R edit of the R2-10 make_headlines.py: three source documents, no live layer,
T_land S and D1 rows added.)
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = {"S": "r2-10r-summary.json", "D": "d1-summary.json", "G": "recert-summary.json", "N": "nm2-sensitivity.json"}
F1 = "{:.2f}"
F4 = "{:.4f}"
CI4 = "[{:.4f}, {:.4f}]"
CI = "[{:.2f}, {:.2f}]"
MS = "{:.1f} ms"
CLASSES = ("fill", "toggle", "modal")
TASKS = ("checkbox", "text")


def items() -> list[tuple[str, str, str]]:
    out = [("recert", "G:disposition", "{}"), ("provider_attempts", "S:provider.attempts", "{} attempts"),
           ("provider_reached", "S:provider.reached", "{} reached")]
    for arm in ("COMP", "COMP_E", "COMP_K"):
        for cls in CLASSES:
            base = f"S:browser.scripted.S.{arm}.{cls}.all"
            land = f"S:browser.scripted.S_land.{arm}.{cls}.all"
            out += [(f"S_{arm}_{cls}", f"{base}.S", F1), (f"S_{arm}_{cls}_ci", f"{base}.ci95", CI),
                    (f"S_{arm}_{cls}_n", f"{base}.n", "n={}"),
                    (f"T_{arm}_{cls}_BASE", f"{base}.median_base_ms", MS), (f"T_{arm}_{cls}", f"{base}.median_arm_ms", MS),
                    (f"Sland_{arm}_{cls}", f"{land}.S", F1), (f"Sland_{arm}_{cls}_ci", f"{land}.ci95", CI)]
    out += [("S_fill_amort", "S:browser.scripted.S.COMP.fill.amortized_mean_ratio.S", F1),
            ("S_fill_amort_ci", "S:browser.scripted.S.COMP.fill.amortized_mean_ratio.ci95", CI),
            ("S_fill_warm", "S:browser.scripted.S.COMP.fill.warm_only.S", F1),
            ("S_fill_warm_ci", "S:browser.scripted.S.COMP.fill.warm_only.ci95", CI),
            ("S_COMPK_fill_amort", "S:browser.scripted.S.COMP_K.fill.amortized_mean_ratio.S", F1),
            ("S_COMPK_fill_amort_ci", "S:browser.scripted.S.COMP_K.fill.amortized_mean_ratio.ci95", CI)]
    # PREREG-AMENDMENT-2: the three R2-10 fill rows the first gate list omitted (4 decimals, as gated)
    for arm, k in (("COMP_E", "amortized_mean_ratio"), ("COMP_E", "warm_only"), ("COMP_K", "warm_only")):
        out += [(f"S_{arm}_fill_{k}_4", f"S:browser.scripted.S.{arm}.fill.{k}.S", F4),
                (f"S_{arm}_fill_{k}_ci4", f"S:browser.scripted.S.{arm}.fill.{k}.ci95", CI4)]
    out += [("S_gated_n", "G:S_direction.gated_n", "{} gated S rows")]
    for arm in ("S0", "X"):
        for t in TASKS:
            base = f"S:native.S.{arm}.{t}.all"
            land = f"S:native.S_land.{arm}.{t}.all"
            out += [(f"S_{arm}_{t}", f"{base}.S", F1), (f"S_{arm}_{t}_ci", f"{base}.ci95", CI),
                    (f"S_{arm}_{t}_n", f"{base}.n", "n={}"),
                    (f"T_native_{t}_BASE_{arm}", f"{base}.median_base_ms", MS), (f"T_native_{t}_{arm}", f"{base}.median_arm_ms", MS),
                    (f"Sland_{arm}_{t}", f"{land}.S", F1), (f"Sland_{arm}_{t}_ci", f"{land}.ci95", CI)]
    for cls in CLASSES:
        base = f"S:browser.scripted.decomposition.{cls}/COMP"
        out += [(f"E2_{cls}_untested", f"{base}.untested_share", "{:.1%}"),
                (f"E2_{cls}_floor", f"{base}.floor_ratio_mean", "{:.2f}x"),
                (f"E2_{cls}_Tirr", f"{base}.T_irreducible_ms", MS),
                (f"E2_{cls}_meanT", f"{base}.mean_T_ms", MS),
                (f"WC_{cls}", f"S:browser.scripted.work_deleted_vs_wall_clock.{cls}.wall_clock_saved_median_paired_ms", MS)]
    for t in TASKS:
        base = f"S:native.decomposition.{t}/X"
        out += [(f"E2_native_{t}_untested", f"{base}.untested_share", "{:.1%}"),
                (f"E2_native_{t}_floor", f"{base}.floor_ratio_mean", "{:.2f}x"),
                (f"E2_native_{t}_Tirr", f"{base}.T_irreducible_ms", MS),
                (f"E2_native_{t}_meanT", f"{base}.mean_T_ms", MS),
                (f"WC_native_{t}_X", f"S:native.work_deleted_vs_wall_clock.{t}/X.wall_clock_saved_median_paired_ms", MS),
                (f"WC_native_{t}_S0", f"S:native.work_deleted_vs_wall_clock.{t}/S0.wall_clock_saved_median_paired_ms", MS)]
    out += [("D1_valid", "D:gate.valid", "{}/40 valid"), ("D1_digest_distinct", "D:gate.elements_digest_distinct", "{} distinct elements digest"),
            ("D1_trunc_false", "D:gate.truncated_false", "truncated=false {}/40"),
            ("D1_G2000", "D:gate.forced_path_G_2000", "G reported timeout_ms 2000 in {}/20"),
            ("D1_E1000", "D:gate.forced_path_E_1000", "E reported timeout_ms 1000 in {}/20"),
            ("D1_second1000", "D:gate.second_call_default_1000", "second call reported 1000 in {}/40"),
            ("D1_dT", "D:paired.T_ms_G_minus_E.median", "{:+.2f} ms"), ("D1_dT_ci", "D:paired.T_ms_G_minus_E.ci95", "[{:+.2f}, {:+.2f}] ms"),
            ("D1_dspan", "D:paired.driver_span_ms_G_minus_E.median", "{:+.2f} ms"),
            ("D1_dspan_ci", "D:paired.driver_span_ms_G_minus_E.ci95", "[{:+.2f}, {:+.2f}] ms"),
            ("D1_TG", "D:by_arm.G.T_ms.median", MS), ("D1_TE", "D:by_arm.E.T_ms.median", MS),
            ("D1_walkG", "D:by_arm.G.walk_elapsed_ms.median", "{} ms walk"), ("D1_walkE", "D:by_arm.E.walk_elapsed_ms.median", "{} ms walk"),
            ("D1_browser_gws", "D:browser_marks.get_window_state_dispatches", "{} get_window_state dispatches"),
            ("D1_browser_traces", "D:browser_marks.trace_files", "{} browser trace files")]
    for v in ("nm1_only", "drop_window"):  # PREREG-AMENDMENT-2: nm2 interference sensitivity
        for arm in ("S0", "X"):
            for t in TASKS:
                out += [(f"N2_{v}_{arm}_{t}", f"N:rows.{v}.{arm}.{t}.S", F4), (f"N2_{v}_{arm}_{t}_ci", f"N:rows.{v}.{arm}.{t}.ci95", CI4),
                        (f"N2_{v}_{arm}_{t}_n", f"N:rows.{v}.{arm}.{t}.n", "n={}")]
    out += [("N2_overlap", "N:interference.nm2_trials_overlapping_window_pad", "{} nm2 trials"),
            ("N2_maxdiff", "N:max_abs_median_diff_nm1_nm2_ms", "{:.2f} ms")]
    return out


def walk(obj, path):  # noqa: ANN001, ANN201
    doc, _, rest = path.partition(":")
    obj = obj[doc]
    for key in rest.split("."):
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def main() -> None:
    docs = {k: json.loads((HERE / v).read_text()) for k, v in DOCS.items()}
    nums = []
    for hid, path, fmt in items():
        try:
            v = walk(docs, path)
        except (KeyError, IndexError, TypeError):
            continue
        if v is None:
            continue
        text = fmt.format(*v) if isinstance(v, list) else fmt.format(v)
        nums.append({"id": hid, "path": path, "format": fmt, "text": text})
    (HERE / "headline-numbers.json").write_text(json.dumps({"numbers": nums}, indent=1) + "\n")
    for n in nums:
        print(f"{n['id']}: {n['text']}")


if __name__ == "__main__":
    main()
