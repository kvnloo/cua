"""Write headline-numbers.json from b08-summary.json (standard library only; run under bin/hostless).

Every quoted number in README.md is listed with its JSON path in the summary, its exact value and the exact
text the README uses; verify_artifacts.py re-checks value and text. (B-06's make_headlines.py, adapted.)
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLASSES = ("fill", "toggle", "modal")


def f1(v: float) -> str:
    s = f"{v:.1f}"
    return "0.0" if s == "-0.0" else s


def f2(v: float) -> str:
    s = f"{v:.2f}"
    return "0.00" if s == "-0.00" else s


def ci(v: list[float]) -> str:
    return f"[{f2(v[0])}, {f2(v[1])}]"


def pct(v: float) -> str:
    return f"{100 * v:.1f}%"


def build(doc: dict) -> list[dict]:
    out = []

    def add(name: str, path: list, fmt) -> None:
        node = doc
        for k in path:
            node = node[k]
        out.append({"name": name, "path": path, "value": node, "readme_text": fmt(node)})

    add("agreement_share", ["agreement_T_j_vs_T_oracle", "share"], lambda v: f"agreement {pct(v)}")
    add("measured_valid", ["n_trials", "valid_measured"], lambda v: f"{v} of 384")
    add("e4_total", ["e4_total"], lambda v: f"E4 total {v}")
    add("c_m", ["part_E", "c_m_us"], lambda v: f"c_m = {f2(v)} us")
    add("disposition", ["disposition", "value"], lambda v: f"Disposition: {v}")
    for c in CLASSES:
        b = ["classes", c]
        add(f"{c}_verdict", b + ["verdict"], lambda v, c=c: f"{c}: {v}")
        add(f"{c}_D_median", b + ["D_C_minus_Wa", "median"], lambda v: f"D {f2(v)}")
        add(f"{c}_D_ci", b + ["D_C_minus_Wa", "ci"], ci)
        add(f"{c}_Dprime", b + ["Dprime_C_minus_Wb", "median"], lambda v: f"D' {f2(v)}")
        add(f"{c}_NC_median", b + ["NC_Wa_minus_Wb", "median"], lambda v: f"Wa-Wb {f2(v)}")
        add(f"{c}_NC_ci", b + ["NC_Wa_minus_Wb", "ci"], ci)
        add(f"{c}_PC2_median", b + ["PC2_P2_minus_Wa", "median"], lambda v: f"P2-Wa {f2(v)}")
        add(f"{c}_PC2_ci", b + ["PC2_P2_minus_Wa", "ci"], ci)
        add(f"{c}_TC", b + ["T_C_median"], lambda v: f"T_C {f2(v)}")
        for a in ("C", "Wa", "Wb", "P2"):
            add(f"{c}_{a}_valid", b + ["arms", a, "valid"], lambda v, a=a: f"{a} {v}/32")
            add(f"{c}_{a}_Tj", b + ["arms", a, "T_j_median"], lambda v, a=a: f"{a} {f2(v)}")
        add(f"{c}_warmup", b + ["arms", "Wa", "warmup_median"], lambda v: f"warm-up {f1(v)}")
        add(f"{c}_E_C", b + ["arms", "C", "E_snapshot1_minus_snapshot2_median"], lambda v: f"E(C) {f2(v)}")
        add(f"{c}_E_Wa", b + ["arms", "Wa", "E_snapshot1_minus_snapshot2_median"], lambda v: f"E(Wa) {f2(v)}")
        add(f"{c}_smoke", b + ["smoke", "valid"], lambda v: f"smoke {v}/5")
        pe = ["part_E", "classes", c]
        add(f"{c}_pp_ms", pe + ["cold_per_process_ms_C"], lambda v: f"per-process {f2(v)} ms")
        for arm in ("C", "Wa"):
            for view in ("corr", "raw"):
                for bg in ("irreducible", "untested"):
                    k = f"{view}:below_gate_as_{bg}"
                    add(f"{c}_{arm}_{view}_{bg}_share", pe + [arm, k, "untested_share"],
                        lambda v, arm=arm, view=view, bg=bg: f"{arm} {view} BG={bg[:3].upper()} {pct(v)}")
            add(f"{c}_{arm}_meanT_corr", pe + [arm, "corr:below_gate_as_untested", "mean_T_ms"],
                lambda v, arm=arm: f"mean T {arm} {f2(v)}")
    ph = ["part_E", "classes", "fill", "C", "post_hoc_unmarked_verify_poll"]
    add("fill_C_unmarked_poll_ms", ph + ["mean_ms"], lambda v: f"unmarked poll {f2(v)} ms")
    add("fill_C_posthoc_irr", ph + ["untested_share_if_counted_as_sleeps_polls", "corr:below_gate_as_irreducible"],
        lambda v: f"post-hoc fill C BG=IRR {pct(v)}")
    add("fill_C_posthoc_unt", ph + ["untested_share_if_counted_as_sleeps_polls", "corr:below_gate_as_untested"],
        lambda v: f"post-hoc fill C BG=UNT {pct(v)}")
    return out


def main() -> None:
    doc = json.loads((HERE / "b08-summary.json").read_text())
    nums = build(doc)
    (HERE / "headline-numbers.json").write_text(json.dumps({"schema": "b-08.headlines.v1", "source": "b08-summary.json",
                                                            "numbers": nums}, indent=1, ensure_ascii=False) + "\n")
    for n in nums:
        print(n["name"], "|", n["readme_text"])


if __name__ == "__main__":
    main()
