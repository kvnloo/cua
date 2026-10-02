"""ar-eval command line (evaluator only; run under hostless).

  manifest   build harness/ar/manifest.json for a champion commit
  selfcheck  verify the harness files against the manifest
  g0         collect G0 inputs for a candidate branch and print the G0 verdict
  tau        AA calibration -> tau (from AA raw rows)
  prereg     write a pre-registration for one request (validated against the schema)
  evaluate   run G0..GS on raw rows and append one line to results.jsonl
  verify     check the results.jsonl hash chain and replay LORD++
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from . import collect, gates, lord, results, stats
from .g0 import g0
from .scanner import RULES_PATH, load_rules
from .schema import load, validate

AR = Path(__file__).resolve().parent.parent
ALLOWLIST = AR / "allowlist.json"
MANIFEST = AR / "manifest.json"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def rows_sha(paths: list[str]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(Path(p).read_bytes())
    return h.hexdigest()


def cmd_manifest(a: argparse.Namespace) -> int:
    m = collect.build_manifest(Path(a.wt), a.champion, Path(a.itemcheck), json.loads(ALLOWLIST.read_text()))
    Path(a.out).write_text(json.dumps(m, indent=1, sort_keys=True) + "\n")
    print(sha_file(Path(a.out)))
    return 0


def cmd_selfcheck(a: argparse.Namespace) -> int:
    errors = collect.harness_selfcheck(Path(a.wt), json.loads(Path(a.manifest).read_text()))
    print(json.dumps({"ok": not errors, "errors": errors}))
    return 0 if not errors else 1


def cmd_g0(a: argparse.Namespace) -> int:
    allow = json.loads(ALLOWLIST.read_text())
    manifest = json.loads(Path(a.manifest).read_text())
    inputs = collect.collect_g0_inputs(Path(a.repo), a.champion, a.candidate, Path(a.itemcheck), allow, manifest)
    Path(a.out).write_text(json.dumps(inputs, sort_keys=True))
    res = g0(inputs, allow, manifest, load_rules())
    print(json.dumps(res, indent=1))
    return 0 if res["pass"] else 1


def cmd_tau(a: argparse.Namespace) -> int:
    rows = read_jsonl(a.aa_rows)
    # AA rows: both arms run the champion binary; the "candidate" arm is the second copy.
    d = gates.ln_pairs(gates.pairs(rows, "task"))
    out = stats.tau_from_aa(d, a.batch)
    out["sigma_ln"] = stats.sd(d)
    out["n_pairs_required"] = stats.n_pairs_required(out["sigma_ln"], out["tau"]) if out["sigma_ln"] > 0 else 2
    out["aa_rows_sha256"] = rows_sha(a.aa_rows)
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out))
    return 0


def cmd_prereg(a: argparse.Namespace) -> int:
    req_path = Path(a.request)
    req = json.loads(req_path.read_text())
    problems = validate(req, load("request.schema.json"))
    if problems:
        raise SystemExit(f"request invalid: {problems}")
    tau = json.loads(Path(a.tau).read_text())
    allow_sha, rules_sha = sha_file(ALLOWLIST), sha_file(RULES_PATH)
    n = max(stats.n_pairs_required(tau["sigma_ln"], tau["tau"]), a.min_pairs)
    pre = {
        "schema": "ar.prereg.v1",
        "eval_id": a.eval_id,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request": {"branch": req["branch"], "hypothesis": req["hypothesis"],
                    "submitted_utc": req["submitted_utc"], "request_sha256": sha_file(req_path)},
        "champion": {"commit": a.champion_commit, "binary_sha256": sha_file(Path(a.champion_bin)),
                     "binary_label": Path(a.champion_bin).name},
        "candidate": {"commit": a.candidate_commit, "binary_sha256": sha_file(Path(a.candidate_bin)),
                      "binary_label": Path(a.candidate_bin).name},
        "task": "gtk3_checkbox_toggle",
        "segment": "segment-1",
        "frozen": {"manifest_sha256": sha_file(Path(a.manifest)), "allowlist_sha256": allow_sha,
                   "scanner_rules_sha256": rules_sha, "harness_commit": a.harness_commit},
        "mechanism": {"start_mark": req.get("mechanism_start_mark", a.start_mark),
                      "end_mark": req.get("mechanism_end_mark", a.end_mark), "min_share": 0.7},
        "tau": {"value": tau["tau"], "floor": 0.02, "q975_abs_delta_aa_ln": tau["q975_abs_delta_aa_ln"],
                "aa_pairs": tau["aa_pairs"], "batch": tau["batch"], "aa_rows_sha256": tau["aa_rows_sha256"]},
        "design": {"n_pairs": n, "sigma_ln": tau["sigma_ln"], "alpha_one_sided": 0.01, "power": 0.8,
                   "order": "AB/BA alternating", "trace_off_fraction": 0.2, "session_trials": 48,
                   "block_max_minutes": 10, "seed": a.seed, "fresh_driver_per_trial": True,
                   "sandbox": "harness/ar/sandbox/sandbox-driver.sh", "psi_hz": 10},
        "fdr": {"procedure": "LORD++", "alpha": lord.ALPHA, "w0": lord.W0, "gamma_constant": lord.GAMMA_C},
        "invariants": {"expected_route": a.expected_route, "expected_path": a.expected_path},
        "soak": {"min_trials": a.soak},
        "spot_checks": ["spot_gtk3_text", "spot_browser_fill_submit"],
        "spot_min_pairs": a.spot_min_pairs,
        "g1_required_suites": ["cua-driver-core --lib", "platform-linux --lib"],
        "gates": list(gates.GATE_ORDER),
        "n01_reference": a.n01,
    }
    problems = validate(pre, load("prereg.schema.json"))
    if problems:
        raise SystemExit(f"prereg invalid: {problems}")
    Path(a.out).write_text(json.dumps(pre, indent=1, sort_keys=True) + "\n")
    print(sha_file(Path(a.out)))
    return 0


def cmd_evaluate(a: argparse.Namespace) -> int:
    prereg_path = Path(a.prereg)
    prereg = json.loads(prereg_path.read_text())
    problems = validate(prereg, load("prereg.schema.json"))
    if problems:
        raise SystemExit(f"prereg invalid: {problems}")
    manifest = json.loads(Path(a.manifest).read_text())
    if sha_file(Path(a.manifest)) != prereg["frozen"]["manifest_sha256"]:
        raise SystemExit("manifest differs from the pre-registered one")
    if sha_file(ALLOWLIST) != prereg["frozen"]["allowlist_sha256"] or sha_file(RULES_PATH) != prereg["frozen"]["scanner_rules_sha256"]:
        raise SystemExit("allowlist or scanner rules differ from the pre-registered ones")
    rows = read_jsonl(a.rows)
    build_rows = read_jsonl(a.build_rows) if a.build_rows else []
    g0_inputs = json.loads(Path(a.g0_inputs).read_text())
    res_path = Path(a.results)
    out = gates.evaluate(prereg, rows, build_rows, g0_inputs, json.loads(ALLOWLIST.read_text()), manifest,
                         load_rules(), results.prior_p_values(res_path))
    record = {"schema": "ar.result.v1", "eval_id": prereg["eval_id"], "prereg_sha256": sha_file(prereg_path),
              "rows_sha256": rows_sha(a.rows), "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              **out}
    rec = results.append(res_path, record)
    print(json.dumps({k: rec[k] for k in ("eval_id", "verdict", "failed_gate", "delta", "ci95", "p_value",
                                           "power", "lord")}, indent=1))
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    path = Path(a.results)
    errors = results.verify_chain(path)
    recs = [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
    logged = [r["lord"] for r in recs if r.get("lord")]
    replayed = lord.replay([x["p_value"] for x in logged])
    for got, want in zip(logged, replayed):
        if abs(got["alpha_i"] - want["alpha_i"]) > 1e-12 or got["rejected"] != want["rejected"]:
            errors.append(f"lord_mismatch:index={want['index']}")
    print(json.dumps({"ok": not errors, "errors": errors, "evaluations": len(recs), "lord_tests": len(logged)}))
    return 0 if not errors else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ar-eval", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("manifest"); s.add_argument("--wt", required=True); s.add_argument("--champion", required=True)
    s.add_argument("--itemcheck", required=True); s.add_argument("--out", default=str(MANIFEST)); s.set_defaults(fn=cmd_manifest)
    s = sub.add_parser("selfcheck"); s.add_argument("--wt", required=True); s.add_argument("--manifest", default=str(MANIFEST))
    s.set_defaults(fn=cmd_selfcheck)
    s = sub.add_parser("g0"); s.add_argument("--repo", required=True); s.add_argument("--champion", required=True)
    s.add_argument("--candidate", required=True); s.add_argument("--itemcheck", required=True)
    s.add_argument("--manifest", default=str(MANIFEST)); s.add_argument("--out", required=True); s.set_defaults(fn=cmd_g0)
    s = sub.add_parser("tau"); s.add_argument("--aa-rows", nargs="+", required=True); s.add_argument("--batch", type=int, required=True)
    s.add_argument("--out", required=True); s.set_defaults(fn=cmd_tau)
    s = sub.add_parser("prereg")
    for name in ("request", "eval-id", "champion-commit", "candidate-commit", "champion-bin", "candidate-bin",
                 "tau", "harness-commit", "out"):
        s.add_argument(f"--{name}", required=True)
    s.add_argument("--manifest", default=str(MANIFEST)); s.add_argument("--seed", type=int, required=True)
    s.add_argument("--start-mark", default="focus_guard/body_done"); s.add_argument("--end-mark", default="focus_guard/restored")
    s.add_argument("--expected-route", default="accessibility"); s.add_argument("--expected-path", default=None)
    s.add_argument("--soak", type=int, choices=(300, 1000), required=True); s.add_argument("--spot-min-pairs", type=int, default=10)
    s.add_argument("--min-pairs", type=int, default=10); s.add_argument("--n01", default=None); s.set_defaults(fn=cmd_prereg)
    s = sub.add_parser("evaluate"); s.add_argument("--prereg", required=True); s.add_argument("--rows", nargs="+", required=True)
    s.add_argument("--build-rows", nargs="*"); s.add_argument("--g0-inputs", required=True)
    s.add_argument("--manifest", default=str(MANIFEST)); s.add_argument("--results", required=True); s.set_defaults(fn=cmd_evaluate)
    s = sub.add_parser("verify"); s.add_argument("--results", required=True); s.set_defaults(fn=cmd_verify)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
