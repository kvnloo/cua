#!/usr/bin/env python3
"""Write headline-numbers.json from r2-10-summary.json (standard library only).

Each headline is a path into the summary plus a format; verify_artifacts.py recomputes the value
from raw/ and requires the formatted text to appear verbatim in README.md.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
F1 = "{:.2f}"
CI = "[{:.2f}, {:.2f}]"
MS = "{:.1f} ms"


def items() -> list[tuple[str, str, str]]:
    out = [("disposition", "gates.disposition", "{}"),
           ("provider_attempts", "provider.attempts", "{} attempts"),
           ("provider_reached", "provider.reached", "{} reached")]
    for layer in ("live", "scripted"):
        for cls in ("fill", "toggle", "modal"):
            base = f"browser.{layer}.S.COMP.{cls}.all"
            out += [(f"S_{layer}_{cls}", f"{base}.S", F1), (f"S_{layer}_{cls}_ci", f"{base}.ci95", CI),
                    (f"S_{layer}_{cls}_n", f"{base}.n", "n={}"),
                    (f"T_{layer}_{cls}_BASE", f"{base}.median_base_ms", MS),
                    (f"T_{layer}_{cls}_COMP", f"{base}.median_arm_ms", MS)]
        out += [(f"S_{layer}_fill_amort", f"browser.{layer}.S.COMP.fill.amortized_mean_ratio.S", F1),
                (f"S_{layer}_fill_amort_ci", f"browser.{layer}.S.COMP.fill.amortized_mean_ratio.ci95", CI),
                (f"S_{layer}_fill_warm", f"browser.{layer}.S.COMP.fill.warm_only.S", F1),
                (f"S_{layer}_fill_warm_ci", f"browser.{layer}.S.COMP.fill.warm_only.ci95", CI)]
    for arm in ("COMP_K", "COMP_E"):
        for cls in ("fill", "toggle", "modal"):
            base = f"browser.scripted.S.{arm}.{cls}.all"
            out += [(f"S_{arm}_{cls}", f"{base}.S", F1), (f"S_{arm}_{cls}_ci", f"{base}.ci95", CI)]
    for arm in ("S0", "X"):
        for t in ("checkbox", "text"):
            base = f"native.S.{arm}.{t}.all"
            out += [(f"S_{arm}_{t}", f"{base}.S", F1), (f"S_{arm}_{t}_ci", f"{base}.ci95", CI),
                    (f"S_{arm}_{t}_n", f"{base}.n", "n={}"),
                    (f"T_native_{t}_BASE_{arm}", f"{base}.median_base_ms", MS),
                    (f"T_native_{t}_{arm}", f"{base}.median_arm_ms", MS)]
    for layer in ("live", "scripted"):
        for cls in ("fill", "toggle", "modal"):
            base = f"browser.{layer}.decomposition.{cls}/COMP"
            out += [(f"E2_{layer}_{cls}_untested", f"{base}.untested_share", "{:.1%}"),
                    (f"E2_{layer}_{cls}_floor", f"{base}.floor_ratio_mean", "{:.2f}x"),
                    (f"E2_{layer}_{cls}_Tirr", f"{base}.T_irreducible_ms", MS),
                    (f"E2_{layer}_{cls}_meanT", f"{base}.mean_T_ms", MS),
                    (f"WC_{layer}_{cls}", f"browser.{layer}.work_deleted_vs_wall_clock.{cls}.wall_clock_saved_median_paired_ms", MS)]
    for t in ("checkbox", "text"):
        base = f"native.decomposition.{t}/X"
        out += [(f"E2_native_{t}_untested", f"{base}.untested_share", "{:.1%}"),
                (f"E2_native_{t}_floor", f"{base}.floor_ratio_mean", "{:.2f}x"),
                (f"E2_native_{t}_Tirr", f"{base}.T_irreducible_ms", MS),
                (f"WC_native_{t}_X", f"native.work_deleted_vs_wall_clock.{t}/X.wall_clock_saved_median_paired_ms", MS)]
    return out


def walk(obj, path):  # noqa: ANN001, ANN201
    for key in path.split("."):
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def main() -> None:
    s = json.loads((HERE / "r2-10-summary.json").read_text())
    nums = []
    for hid, path, fmt in items():
        try:
            v = walk(s, path)
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
