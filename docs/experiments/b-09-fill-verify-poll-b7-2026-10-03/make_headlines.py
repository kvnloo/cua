"""Write headline-numbers.json from b09-summary.json (standard library only; run under bin/hostless).

Every quoted number in README.md is listed with its JSON path in the summary, its exact value and the exact
text the README uses; verify_artifacts.py re-checks value and text. (B-08's make_headlines.py, adapted.)
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("BASE", "P10a", "P10b", "P1", "P0", "PC")


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

    F = ["fill"]
    add("measured_valid", ["n_trials", "valid_measured"], lambda v: f"{v} of 216")
    add("e4_total", ["e4_total"], lambda v: f"E4 total {v}")
    add("disposition", ["disposition", "value"], lambda v: f"Disposition: {v}")
    add("poll_verdict", F + ["poll_verdict"], lambda v: f"poll verdict {v}")
    add("best_arm", F + ["best_arm"], lambda v: f"composed arm {v}")
    for key, lab in (("NC_P10a_minus_P10b", "P10a-P10b"), ("PC_PC_minus_P10a", "PC-P10a"),
                     ("POLL_P10a_minus_P1", "P10a-P1"), ("P10a_minus_P0", "P10a-P0"), ("P1_minus_P0", "P1-P0")):
        add(f"{key}_median", F + [key, "median"], lambda v, lab=lab: f"{lab} {f2(v)}")
        add(f"{key}_ci", F + [key, "ci"], ci)
        add(f"{key}_n", F + [key, "n_pairs"], lambda v, lab=lab: f"{lab} n={v}")
    for k, lab in (("T_j_ms", "T_j"), ("T_oracle_ms", "T_oracle")):
        add(f"sec_{lab}_POLL", F + ["secondary", k, "POLL", "median"], lambda v, lab=lab: f"{lab} P10a-P1 {f2(v)}")
        add(f"sec_{lab}_NC", F + ["secondary", k, "NC", "median"], lambda v, lab=lab: f"{lab} P10a-P10b {f2(v)}")
        add(f"sec_{lab}_PC", F + ["secondary", k, "PC", "median"], lambda v, lab=lab: f"{lab} PC-P10a {f2(v)}")
    add("S", F + ["S", "S"], lambda v: f"S = {f1(v)}")
    add("S_ci", F + ["S", "ci"], lambda v: f"S CI [{f1(v[0])}, {f1(v[1])}]")
    add("S_n", F + ["S", "n_pairs"], lambda v: f"S over {v} pairs")
    add("S_base_med", F + ["S", "median_a"], lambda v: f"median T BASE {f1(v)}")
    add("S_comp_med", F + ["S", "median_b"], lambda v: f"median T composed {f2(v)}")
    for k, lab in (("T_j_ms", "T_j"), ("T_oracle_ms", "T_oracle")):
        add(f"S_{lab}", F + ["S_secondary", k, "S"], lambda v, lab=lab: f"S on {lab} {f1(v)}")
    for a in ARMS:
        b = F + ["arms", a]
        add(f"{a}_valid", b + ["valid"], lambda v, a=a: f"{a} {v}/36")
        add(f"{a}_T", b + ["T_runner_median"], lambda v, a=a: f"{a} T {f2(v)}")
        add(f"{a}_reads", b + ["n_reads", "mean"], lambda v, a=a: f"{a} reads {f2(v)}")
        add(f"{a}_sleeps", b + ["n_sleeps", "mean"], lambda v, a=a: f"{a} sleeps {f2(v)}")
        add(f"{a}_pollms", b + ["poll_sleep_ms", "mean"], lambda v, a=a: f"{a} poll sleep {f2(v)}")
        add(f"{a}_efflat", b + ["effect_latency_ms", "median"], lambda v, a=a: f"{a} effect latency {f2(v)}")
        add(f"{a}_load", b + ["loadavg_1m", "max"], lambda v, a=a: f"{a} load max {f2(v)}")
    add("pc_sleep", F + ["arms", "PC", "pc_sleep_ms", "median"], lambda v: f"PC sleep {f2(v)} ms")
    add("smoke", F + ["smoke", "valid"], lambda v: f"SMOKE {v}/5")
    add("nw2", ["nw2", "pass"], lambda v: f"N-W2 {v}/3")
    add("reads_added_P0", F + ["P0_descriptive", "reads_added_P0_vs_P1"], lambda v: f"P0 adds {f2(v)} reads per task vs P1")
    add("reads_added_P1", F + ["P0_descriptive", "reads_added_P1_vs_P10a"], lambda v: f"P1 adds {f2(v)} reads per task vs P10a")
    pe = ["part_E_prime"]
    add("c_m", pe + ["c_m_us"], lambda v: f"c_m = {f2(v)} us")
    for arm in sorted(doc["part_E_prime"]["arms"]):
        a = pe + ["arms", arm]
        for view in ("corr", "raw"):
            for bg in ("irreducible", "untested"):
                k = f"{view}:below_gate_as_{bg}"
                add(f"{arm}_{view}_{bg}_share", a + [k, "untested_share"],
                    lambda v, arm=arm, view=view, bg=bg: f"{arm} {view} BG={bg[:3].upper()} {pct(v)}")
            rs = a + [f"runner_split:{view}"]
            for f in ("runner_b08_labels_ms", "poll_sleep_ms", "read_hop_ms", "runner_other_ms", "target_effect_lag_ms",
                      "effect_wait_inside_poll_sleep_ms"):
                add(f"{arm}_{view}_{f}", rs + [f], lambda v, arm=arm, view=view, f=f: f"{arm} {view} {f[:-3]} {f2(v)}")
        add(f"{arm}_meanT_corr", a + ["corr:below_gate_as_untested", "mean_T_ms"], lambda v, arm=arm: f"mean T {arm} {f2(v)}")
        for ex in ("excl_cold_excess", "incl_cold_excess"):
            add(f"{arm}_floor_{ex}", a + ["corr:below_gate_as_irreducible", "floor_ratio", ex],
                lambda v, arm=arm, ex=ex: f"{arm} floor ratio ({ex.replace('_', ' ')}) {f2(v)}")
    return out


def main() -> None:
    doc = json.loads((HERE / "b09-summary.json").read_text())
    nums = build(doc)
    (HERE / "headline-numbers.json").write_text(json.dumps({"schema": "b-09.headlines.v1", "source": "b09-summary.json",
                                                            "numbers": nums}, indent=1, ensure_ascii=False) + "\n")
    for n in nums:
        print(n["name"], "|", n["readme_text"])


if __name__ == "__main__":
    main()
