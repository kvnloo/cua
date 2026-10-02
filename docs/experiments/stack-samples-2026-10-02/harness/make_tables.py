"""Render every results table of README.md from committed raw files (SAMPLESFIX). Stdlib only.

  python make_tables.py <packet_dir> --write   -> rewrite the generated blocks in README.md
  python make_tables.py <packet_dir> --check   -> exit 1 if any block in README.md differs

Each block sits between "<!-- BEGIN GENERATED <name> -->" and "<!-- END GENERATED <name> -->" lines.
Sources: dataset/runs.jsonl, dataset/events.jsonl, raw/analysis/{api,turn}-analysis.json,
raw/analysis/cua-bridge-tally.json and raw/scored/<lane>/scored-*.jsonl (warm max latency only).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MODEL_ROWS = [("julia_1", "julia_1 (CPU)"), ("laya_421m", "laya_421m (CPU, current default candidate)"),
              ("nanojev", "nanojev (GPU, comparison only)"), ("decider_2b", "decider_2b (GPU)"),
              ("qwen_3b_baseline", "qwen_3b_baseline (Ollama logprobs, CPU)")]
G3_WORD = {"no_detectable_difference": "no difference", "worse": "worse", "better": "better"}


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def f(x, nd: int) -> str:
    return "" if x is None else f"{x:.{nd}f}"


def ms(x, nd: int = 1) -> str:
    return "" if x is None else f"{x:,.{nd}f}"


def table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def warm_walls(packet: Path, lane: str, name: str) -> list[float]:
    """Same series as analyze.py's warm_wall_ms_p50/p95: scorer_timing.wall_ms per call, first call excluded."""
    rows = jl(packet / "raw" / "scored" / lane / f"scored-{name}.jsonl")
    return [float(r["scorer_timing"]["wall_ms"]) for r in rows if "wall_ms" in (r.get("scorer_timing") or {})][1:]


def blocks(packet: Path) -> dict[str, str]:
    runs = jl(packet / "dataset" / "runs.jsonl")
    ran = [r for r in runs if r["status"] == "RUN"]
    events = jl(packet / "dataset" / "events.jsonl")
    out: dict[str, str] = {}

    # workload by kind
    kinds: dict[str, list[int]] = {}
    for r in ran:
        k = kinds.setdefault(r["kind"], [0, 0, 0])
        k[0] += 1
        k[1] += r["verified_success"] is True
        k[2] += r["verified_success"] is False
    label = {"file": "file tools (10 families)", "cua": "CUA, GTK3 TaskWindow in a private Xvfb session"}
    out["workload"] = table(["kind", "run", "oracle pass", "oracle fail"],
                            [[label.get(k, k), str(v[0]), str(v[1]), str(v[2])] for k, v in sorted(kinds.items(), key=lambda kv: kv[0] != "file")]
                            + [["total", str(len(ran)), str(sum(v[1] for v in kinds.values())), str(sum(v[2] for v in kinds.values()))]])

    # exit codes x turn exit reason (observer on_session_end)
    reason = {(e.get("identity") or {}).get("session_id"): (e.get("fields") or {}).get("turn_exit_reason")
              for e in events if e.get("event") == "on_session_end"}
    combos: dict[tuple, list[str]] = {}
    for r in ran:
        combos.setdefault((r["exit_code"], reason.get(r["session_id"])), []).append(r["task_id"])
    out["exits"] = table(["exit code", "turn_exit_reason (observer on_session_end)", "runs", "tasks"],
                         [[str(c), f"`{why}`", str(len(ids)), ", ".join(ids) if len(ids) <= 8 else "(file and CUA tasks)"]
                          for (c, why), ids in sorted(combos.items(), key=lambda kv: (kv[0][0], -len(kv[1])))])

    # CUA runs, from the bridge tally
    t = json.loads((packet / "raw" / "analysis" / "cua-bridge-tally.json").read_text())
    crow = []
    for x in t["runs"]:
        o = x["oracle"]
        want = o.get("value") or o.get("reply") or json.dumps(o.get("state"), sort_keys=True)
        cls = ", ".join(f"{n} {c}" for c, n in x["tool_error_classes"].items())
        crow.append([x["task_id"], f"`{want}`", "pass" if x["verified_success"] else "fail",
                     f"{x['exit_code']} `{x['turn_exit_reason']}`", str(x["api_calls_agent_log"]),
                     str(x["tool_calls_completed"]), f"{x['tool_errors']} ({cls})", str(x["approval_lines"]),
                     "no" if x["gui_state_unchanged"] else "yes", f"`{x['reply'][:40]}`"])
    tt = t["totals"]
    crow.append(["total (12 runs)", "", f"{tt['oracle_pass']} pass", "", str(tt["api_calls_agent_log"]),
                 str(tt["tool_calls_completed"]),
                 f"{tt['tool_errors']} ({', '.join(f'{n} {c}' for c, n in tt['tool_error_classes'].items())})",
                 str(tt["approval_lines"]), f"{t['n_cua_runs'] - tt['runs_gui_state_unchanged']} changed", ""])
    out["cua"] = table(["task", "oracle expects", "verdict", "exit / turn_exit_reason", "API calls", "tool calls completed",
                        "tool errors (class)", "approval lines", "GUI state changed", "reply (first 40 chars)"], crow)

    # api lane
    a = json.loads((packet / "raw" / "analysis" / "api-analysis.json").read_text())
    arow = []
    for name, lab in [("deterministic_loo_group_prior", "deterministic LOO-run prior"), ("decider_2b", "decider_2b"),
                      ("nanojev", "nanojev"), ("deterministic_constant_0_5", "deterministic 0.5"), ("laya_421m", "laya_421m"),
                      ("julia_1", "julia_1"), ("qwen_3b_baseline", "qwen_3b_baseline")]:
        v = a["rows"][name]
        ps = [(b["mean_probability"], b["n"]) for b in v["calibration_bins"]]
        mean_p = sum(p * n for p, n in ps) / sum(n for _, n in ps)
        arow.append([lab, f(v["brier"], 4), f(v["log_loss"], 3), f(mean_p, 3), str(v["denominators"]["n_scored"]),
                     str(v["n_probability_exactly_0_or_1"])])
    out["api"] = table(["row", "Brier", "log-loss", "mean p(fail)", "scored", "p exactly 0 or 1"], arow)

    # verification_needed lane
    d = json.loads((packet / "raw" / "analysis" / "turn-analysis.json").read_text())
    rows = d["rows"]
    trow = [["base rate in-sample (oracle-optimistic ref)", f(rows["julia_1"]["base_rate_brier"], 4)] + [""] * 6]
    for name, lab in [("deterministic_constant_0_5", "deterministic constant 0.5"), ("deterministic_loo_group_prior", "deterministic LOO-family prior")] + MODEL_ROWS:
        v = rows[name]
        g = v.get("vs_deterministic_loo_group_prior")
        g3 = "(reference)" if g is None else f"{G3_WORD.get(g['G3'], g['G3'])} {g['brier_diff']:+.3f} [{g['ci95'][0]:+.3f}, {g['ci95'][1]:+.3f}]"
        lat = v.get("latency") or {}
        warm = warm_walls(packet, "turn", name) if lat else []
        trow.append([lab, f(v["brier"], 4), f(v["log_loss"], 3), f(v["ece"], 3), f(v["accuracy_at_0_5"], 3), g3,
                     ms(lat.get("first_call_wall_ms"), 0),
                     " / ".join(ms(x) for x in (lat.get("warm_wall_ms_p50"), lat.get("warm_wall_ms_p95"),
                                                max(warm) if warm else None)) if lat else ""])
    trow.append(["JEV reference", "NOT_RUN (TypeSafe, paid)"] + [""] * 6)
    fo = rows["failopen_ollama_deadport"]["denominators"]
    trow.append(["fail-open control (dead-port adapter)",
                 f"coverage {fo['coverage']:.1f}, {fo['n_backend_error']}/{fo['n_rows']} rows `backend_error`"] + [""] * 6)
    out["turn"] = table(["row", "Brier", "log-loss", "ECE", "acc@0.5", "G3 vs LOO prior: Brier diff [95% CI]",
                         "first call wall ms", "warm wall p50 / p95 / max ms"], trow)

    # Brier by kind
    krow = []
    for name, lab in MODEL_ROWS:
        sl = rows[name]["brier_slices"]
        krow.append([lab.split(" ")[0], f(sl["kind=cua"]["brier"], 3), str(sl["kind=cua"]["n"]),
                     f(sl["kind=file"]["brier"], 3), str(sl["kind=file"]["n"])])
    out["by_kind"] = table(["row", "Brier cua", "n cua", "Brier file", "n file"], krow)

    # pairwise disagreement at 0.5 on the same 105 examples
    dis = d["disagreement"]
    drow = [[k.replace("|", " vs "), f"{v['disagree_rate_at_0_5']:.3f}", f"{round(v['disagree_rate_at_0_5'] * v['n'])}/{v['n']}"]
            for k, v in sorted(dis["pairwise"].items())]
    drow.append(["all model rows right / all model rows wrong", "",
                 f"{dis['all_model_rows_right']} / {dis['all_model_rows_wrong']} of {dis['n_labelled_scored_by_all_model_rows']}"])
    out["disagreement"] = table(["pair", "disagreement at 0.5", "examples"], drow)
    return out


BLOCK = re.compile(r"(<!-- BEGIN GENERATED (?P<name>[a-z_]+) -->\n)(?P<body>.*?)(\n<!-- END GENERATED (?P=name) -->)", re.S)


def render(readme: str, gen: dict[str, str]) -> str:
    return ANY_BLOCK.sub(lambda m: f"<!-- BEGIN GENERATED {m['name']} -->\n{gen[m['name']]}\n<!-- END GENERATED {m['name']} -->", readme)


ANY_BLOCK = re.compile(r"<!-- BEGIN GENERATED (?P<name>[a-z_]+) -->\n.*?<!-- END GENERATED (?P=name) -->", re.S)


def check(packet: Path) -> list[str]:
    """Names of generated blocks that are missing, differ, or are unknown in README.md."""
    readme = (packet / "README.md").read_text(encoding="utf-8")
    gen = blocks(packet)
    found = {m["name"]: m["body"] for m in BLOCK.finditer(readme)}
    names = [m["name"] for m in ANY_BLOCK.finditer(readme)]
    return ([n for n in gen if found.get(n) != gen[n]] + [n for n in names if n not in gen]
            + [n for n in set(names) if names.count(n) > 1])


def main() -> None:
    packet = Path(sys.argv[1])
    if sys.argv[2] == "--write":
        p = packet / "README.md"
        p.write_text(render(p.read_text(encoding="utf-8"), blocks(packet)), encoding="utf-8")
    bad = check(packet)
    print(json.dumps({"generated_blocks": sorted(blocks(packet)), "mismatched": bad}))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
