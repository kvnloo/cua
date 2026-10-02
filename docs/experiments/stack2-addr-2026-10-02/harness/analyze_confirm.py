"""Grade the confirmation set (CONFIRM_PREREG.json) with the main analyzer's statistics (stdlib only).

usage: analyze_confirm.py <raw dir> <plan_confirm.json> <drive-ledger.jsonl> <summary.json of the main set> <out json>
"""
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("analyze", Path(__file__).with_name("analyze.py"))
an = importlib.util.module_from_spec(spec)
spec.loader.exec_module(an)

raw, plan_p, ledger_p, main_p, out_p = map(Path, sys.argv[1:6])
plan = json.loads(plan_p.read_text())["runs"]
ledger = {r["run_id"]: r for r in an.jl(ledger_p)}
recs = []
for r in plan:
    sp = raw / "runs" / r["run_id"] / "run_summary.json"
    s = json.loads(sp.read_text()) if sp.exists() else {}
    recs.append({**r, "executed": r["run_id"] in ledger, "verdict": s.get("oracle", {}).get("verdict", "unknown"),
                 "hermes_rc": s.get("hermes_rc"), "tools": s.get("tools"),
                 "peak_prompt_tokens": (s.get("observer") or {}).get("peak_prompt_tokens")})
allc = an.cell_stats(recs)
main = json.loads(main_p.read_text())["cells"]
out = {
    "schema": "stack2_addr.confirm_summary.v1", "planned": len(plan), "executed": sum(r["executed"] for r in recs),
    "by_task": {t: an.cell_stats([r for r in recs if r["task"] == t]) for t in ("gtk3", "browser")},
    "C1_contract": {"addressing_refused": allc["result_classes"].get("addressing_refused", 0),
                    "pass": allc["result_classes"].get("addressing_refused", 0) == 0 and allc["runs_missing_summary"] == 0},
    "C4_authority": {"stale_token": allc["result_classes"].get("stale_token", 0),
                     "invalid_token": allc["result_classes"].get("invalid_token", 0),
                     "token_unavailable": allc["result_classes"].get("token_unavailable", 0),
                     "pass": allc["result_classes"].get("stale_token", 0) == 0 and allc["result_classes"].get("invalid_token", 0) == 0},
    "C3_reference_70cfc7a5_after": {t: {k: main[f"measured|{t}|after|main_0_32_0"][k] for k in ("pass", "n", "pass_wilson95")}
                                    for t in ("gtk3", "browser")},
    "all": allc,
}
Path(out_p).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(json.dumps({k: out[k] for k in ("planned", "executed", "C1_contract", "C4_authority")}))
print({t: (v["pass"], v["n"]) for t, v in out["by_task"].items()})
