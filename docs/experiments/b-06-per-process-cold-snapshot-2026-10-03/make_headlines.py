"""Write headline-numbers.json from b06-summary.json (standard library only).

Every quoted number in README.md is listed with its JSON path in the summary, its exact value and the
exact text the README uses; verify_artifacts.py re-checks value and text.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def f1(v: float) -> str:
    s = f"{v:.1f}"
    return "0.0" if s == "-0.0" else s


def cb(v: float) -> str:
    s = f1(v)
    return f"{v:.2f}" if s == "0.0" and v != 0 else s


def ci(v: list[float]) -> str:
    return f"[{cb(v[0])}, {cb(v[1])}]"


def pct(v: float) -> str:
    return f"{100 * v:.2f}%"


def build(doc: dict) -> list[dict]:
    out = []

    def add(name: str, path: list, fmt) -> None:
        node = doc
        for k in path:
            node = node[k]
        out.append({"name": name, "path": path, "value": node, "readme_text": fmt(node)})

    for c in ("fill", "toggle", "modal"):
        base = ["classes", c]
        add(f"{c}_D_median", base + ["D_C_minus_Wa", "median"], lambda v: f"D {f1(v)}")
        add(f"{c}_D_ci", base + ["D_C_minus_Wa", "ci"], ci)
        add(f"{c}_Dprime_median", base + ["Dprime_C_minus_Wb", "median"], lambda v: f"D' {f1(v)}")
        add(f"{c}_NC_median", base + ["NC_Wa_minus_Wb", "median"], lambda v: f"Wa−Wb {f1(v)}")
        add(f"{c}_NC_ci", base + ["NC_Wa_minus_Wb", "ci"], ci)
        add(f"{c}_PC_median", base + ["PC_P_minus_Wa", "median"], lambda v: f"P−Wa {f1(v)}")
        add(f"{c}_PC_ci", base + ["PC_P_minus_Wa", "ci"], ci)
        for a in ("C", "Wa", "Wb", "P"):
            add(f"{c}_{a}_T_median", base + ["arms", a, "T_oracle_median"], lambda v, a=a: f"{a} {f1(v)}")
        add(f"{c}_warmup_Wa", base + ["arms", "Wa", "warmup_median"], lambda v: f"warm-up {f1(v)}")
        add(f"{c}_k1", base + ["amortized", "k1_T_Wa_plus_warmup"], lambda v: f"k=1 {f1(v)}")
        add(f"{c}_k5", base + ["amortized", "k5_T_Wa_plus_warmup_over_5"], lambda v: f"k=5 {f1(v)}")
        add(f"{c}_Wn_minus_Wa", ["wn_block", c, "Wn_minus_Wa", "median"], lambda v: f"Wn−Wa {f1(v)}")
        add(f"{c}_Wn_minus_Wa_ci", ["wn_block", c, "Wn_minus_Wa", "ci"], ci)
        add(f"{c}_E_R_prime", ["e2", "classes", c, "E_R_prime_mean_ms"], lambda v: f"E_R' {f1(v)}")
        add(f"{c}_share_r10r", ["e2", "classes", c, "untested_share_r10r"], pct)
        add(f"{c}_share_pre", ["e2", "classes", c, "share_pre_B06_B04_mapping"], pct)
    for c in ("fill", "toggle"):
        base = ["block_x_amendment_1", "classes", c]
        add(f"x_{c}_D_median", base + ["D_C_minus_Wa", "median"], lambda v: f"D {f1(v)}")
        add(f"x_{c}_D_ci", base + ["D_C_minus_Wa", "ci"], ci)
        add(f"x_{c}_Dprime_median", base + ["Dprime_C_minus_Wb", "median"], lambda v: f"D' {f1(v)}")
        add(f"x_{c}_NC_median", base + ["NC_Wa_minus_Wb", "median"], lambda v: f"Wa−Wb {f1(v)}")
        add(f"x_{c}_NC_ci", base + ["NC_Wa_minus_Wb", "ci"], ci)
        add(f"x_{c}_PC2_median", base + ["PC_P2_minus_Wa", "median"], lambda v: f"P2−Wa {f1(v)}")
        add(f"x_{c}_PC2_ci", base + ["PC_P2_minus_Wa", "ci"], ci)
        add(f"x_{c}_verdict", base + ["verdict"], lambda v: v)
        add(f"{c}_verdict", ["classes", c, "verdict"], lambda v: v)
        add(f"{c}_share_post_primary", ["e2", "classes", c, "share_post_B06"], pct)
        add(f"{c}_share_post_amended", ["e2_amended", "classes", c, "share_post_B06"], pct)
    return out


def main() -> None:
    doc = json.loads((HERE / "b06-summary.json").read_text())
    nums = build(doc)
    (HERE / "headline-numbers.json").write_text(json.dumps({"schema": "b-06.headlines.v1", "source": "b06-summary.json",
                                                            "numbers": nums}, indent=1, ensure_ascii=False) + "\n")
    for n in nums:
        print(n["name"], "|", n["readme_text"])


if __name__ == "__main__":
    main()
