"""Write headline-numbers.json: every number the README headline/results tables quote, with its path in
b04-summary.json and its rendered text (verify_artifacts.py check 3 re-renders and searches README)."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

E = []


def add(id_: str, path: list, kind: str) -> None:
    E.append({"id": id_, "path": path, "kind": kind})


add("trials_valid", ["trials_valid"], "int")
add("trials_total", ["trials_total"], "int")
for est, k1, k2 in (("E_span", "num", "ci"), ("E_walk", "num2", "ci2")):
    for cls in ("fill", "toggle"):
        for D in ("D80", "D160"):
            add(f"P1_{est}_{cls}_{D}_mean", ["P1", f"{est}/{cls}/{D}", "mean"], k1)
            add(f"P1_{est}_{cls}_{D}_ci", ["P1", f"{est}/{cls}/{D}", "mean_ci"], k2)
        add(f"POS_{est}_{cls}_npos", ["POS", f"{est}/{cls}", "n_delta_positive"], "int")
        add(f"POS_{est}_{cls}_median", ["POS", f"{est}/{cls}", "median"], k1)
        add(f"POS_{est}_{cls}_ci", ["POS", f"{est}/{cls}", "median_ci"], k2)
        add(f"POS_{est}_{cls}_lit_mean", ["POS", f"{est}/{cls}", "literal_inject20_excess", "mean"], k1)
for cls in ("fill", "toggle", "modal"):
    add(f"P2_{cls}_median", ["P2", f"E_span/{cls}", "median"], "num")
    add(f"P2_{cls}_ci", ["P2", f"E_span/{cls}", "median_ci"], "ci")
    add(f"P2_{cls}_mean", ["P2", f"E_span/{cls}", "mean"], "num")
    add(f"P2_{cls}_cold", ["P2", f"E_span/{cls}", "cold_excess", "mean"], "num")
    add(f"P2_{cls}_warm", ["P2", f"E_span/{cls}", "warm_excess", "mean"], "num")
    add(f"P2w_{cls}_median", ["P2", f"E_walk/{cls}", "median"], "num2")
    add(f"P2w_{cls}_ci", ["P2", f"E_walk/{cls}", "median_ci"], "ci2")
for cls in ("fill", "toggle"):
    add(f"P3_{cls}_median", ["P3", f"E_span/{cls}", "median"], "num")
    add(f"P3_{cls}_ci", ["P3", f"E_span/{cls}", "median_ci"], "ci")
    add(f"P3_{cls}_mean", ["P3", f"E_span/{cls}", "mean"], "num")
    add(f"P3_{cls}_samedoc", ["P3", f"E_span/{cls}", "samedoc_excess", "mean"], "num")
    for arm in ("W0", "W80", "PREWARM"):
        add(f"P4_{cls}_{arm}_median", ["P4", f"{cls}/{arm}", "median"], "num")
    for arm in ("W80", "PREWARM"):
        add(f"P4_{cls}_{arm}_d", ["P4", f"{cls}/{arm}-W0", "median"], "num")
        add(f"P4_{cls}_{arm}_ci", ["P4", f"{cls}/{arm}-W0", "median_ci"], "ci")
    add(f"P4_{cls}_PREWARM_inT", ["P4", f"{cls}/PREWARM-W0", "T_oracle_excl_warmup", "median"], "num")
    add(f"P4_{cls}_PREWARM_inT_ci", ["P4", f"{cls}/PREWARM-W0", "T_oracle_excl_warmup", "median_ci"], "ci")
    add(f"P4_{cls}_PREWARM_warmup", ["P4", f"{cls}/PREWARM", "warmup", "median"], "num")
    for D in ("D80", "D160"):
        add(f"P1_{cls}_{D}_ax", ["component_split_snapshot1_minus_resnap1_mean_ms", f"P1/{cls}/{D}", "ax_tree"], "num")
    add(f"cold_{cls}_domdoc", ["component_split_snapshot1_minus_resnap1_mean_ms", f"{cls}/cold", "dom_get_document"], "num")
    add(f"cold_{cls}_attach", ["component_split_snapshot1_minus_resnap1_mean_ms", f"{cls}/cold", "attach"], "num")
    add(f"cold_{cls}_ax", ["component_split_snapshot1_minus_resnap1_mean_ms", f"{cls}/cold", "ax_tree"], "num")
    add(f"u_split_{cls}", ["accounting", cls, "u_split"], "pct")
for layer in ("scripted", "live"):
    for cls in ("fill", "toggle", "modal"):
        k = f"{layer}/{cls}"
        add(f"ER_{layer}_{cls}", ["r2_10_rows", k, "E_R_mean"], "num")
        add(f"ER_{layer}_{cls}_ci", ["r2_10_rows", k, "E_R_ci"], "ci")
        add(f"obs_{layer}_{cls}", ["r2_10_rows", k, "R2_10_observation_ms"], "num")
        add(f"obsbase_{layer}_{cls}", ["r2_10_rows", k, "observation_base_ms"], "num")
        add(f"T_{layer}_{cls}", ["r2_10_rows", k, "R2_10_mean_T_ms"], "num")
        add(f"share_old_{layer}_{cls}", ["r2_10_rows", k, "R2_10_untested_share"], "pct")
        add(f"share_new_{layer}_{cls}", ["r2_10_rows", k, "updated_untested_share"], "pct")
        if cls != "modal":
            add(f"share_split_{layer}_{cls}", ["r2_10_rows", k, "updated_untested_share_descriptive_split"], "pct")


def get(d, path):
    for p in path:
        d = d[p]
    return d


def render(v, kind: str) -> str:
    if kind == "num":
        return f"{v:.1f}"
    if kind == "num2":
        return f"{v:.2f}"
    if kind == "int":
        return str(int(v))
    if kind == "pct":
        return f"{100 * v:.1f}%"
    if kind == "ci":
        return f"[{v[0]:.1f}, {v[1]:.1f}]"
    if kind == "ci2":
        return f"[{v[0]:.2f}, {v[1]:.2f}]"
    raise ValueError(kind)


def main() -> None:
    s = json.loads((HERE / "b04-summary.json").read_text())
    for e in E:
        e["text"] = render(get(s, e["path"]), e["kind"])
    (HERE / "headline-numbers.json").write_text(json.dumps({"source": "b04-summary.json", "entries": E}, indent=1) + "\n")
    for e in E:
        print(e["id"], e["text"])


if __name__ == "__main__":
    main()
