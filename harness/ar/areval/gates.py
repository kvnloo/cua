"""Gates G1-G8 and GS: pure functions of raw rows (``ar.trial.v1`` / ``ar.build.v1``),
the pre-registration and, for G8, the changed paths. :func:`evaluate` runs G0..GS in order and
stops at the first failure. Nothing here reads files or clocks.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from statistics import fmean, median
from typing import Any, Iterable

from . import lord, stats
from .g0 import g0

POSITIVE_KINDS = ("task", "soak", "spot_gtk3_text", "spot_browser_fill_submit")
EXPECTED_DISPATCH = {"task": 1, "soak": 1, "spot_gtk3_text": 1, "spot_browser_fill_submit": 1}
GATE_ORDER = ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "GS")


def result(gate: str, ok: bool, reasons: list[str], **metrics: Any) -> dict[str, Any]:
    return {"gate": gate, "pass": bool(ok), "reasons": reasons, "metrics": metrics}


def trials(rows: Iterable[dict], kind: str | None = None, arm: str | None = None,
           warmup: bool | None = False) -> list[dict]:
    out = []
    for r in rows:
        if r.get("schema") != "ar.trial.v1":
            continue
        if kind is not None and r.get("kind") != kind:
            continue
        if arm is not None and r.get("arm") != arm:
            continue
        if warmup is not None and bool(r.get("warmup")) != warmup:
            continue
        out.append(r)
    return out


def pairs(rows: Iterable[dict], kind: str = "task", trace: bool | None = None) -> list[tuple[dict, dict]]:
    """(champion, candidate) rows of complete, verified pairs."""
    by: dict[Any, dict[str, dict]] = defaultdict(dict)
    for r in trials(rows, kind=kind):
        if trace is not None and bool(r.get("trace")) != trace:
            continue
        by[r["pair_id"]][r["arm"]] = r
    out = []
    for pid in sorted(by, key=str):
        p = by[pid]
        a, c = p.get("champion"), p.get("candidate")
        if a and c and a.get("verified") and c.get("verified") and a.get("T_ns") and c.get("T_ns"):
            out.append((a, c))
    return out


def ln_pairs(ps: list[tuple[dict, dict]]) -> list[float]:
    return stats.ln_ratios([(a["T_ns"], c["T_ns"]) for a, c in ps])


# --------------------------------------------------------------------------- G1
def g1(build_rows: list[dict], required_suites: list[str]) -> dict[str, Any]:
    reasons = []
    builds = [r for r in build_rows if r.get("kind") == "build"]
    tests = {r.get("suite"): r for r in build_rows if r.get("kind") == "test"}
    if not builds or not all(b.get("ok") for b in builds):
        reasons.append("build_failed_or_missing")
    for suite in required_suites:
        t = tests.get(suite)
        if t is None:
            reasons.append(f"suite_missing:{suite}")
        elif not t.get("ok") or t.get("failed", 1) != 0 or t.get("passed", 0) <= 0:
            reasons.append(f"suite_failed:{suite}")
    return result("G1", not reasons, reasons, builds=len(builds), suites=sorted(map(str, tests)))


# --------------------------------------------------------------------------- G2
_RANDOM_RUN = re.compile(r"[0-9a-fA-F]{6,}|\d+")


def _norm_file(path: str) -> str:
    return _RANDOM_RUN.sub("#", path)


def _do_action_marks(row: dict) -> int:
    return sum(1 for m in row.get("marks", [])
               if m.get("phase") == "atspi_action" and m.get("session") == "do_action_replied")


def g2(rows: list[dict], prereg: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    every = trials(rows, warmup=None)
    route = prereg["invariants"]["expected_route"]
    path = prereg["invariants"]["expected_path"]
    for r in every:
        tid = r.get("trial_id")
        kind = r.get("kind")
        positive = kind in POSITIVE_KINDS
        delta = r.get("seq_delta")
        if positive:
            if r.get("verified") and delta != 1:
                reasons.append(f"duplicate_or_missing_mutation:{tid}:seq_delta={delta}")
            if r.get("claimed_success") and not r.get("verified"):
                reasons.append(f"unverified_success:{tid}")
            if r.get("verified") and not r.get("journal_before_done"):
                reasons.append(f"journal_after_done:{tid}")
            if r.get("dispatch_calls", 0) > EXPECTED_DISPATCH.get(kind, 1):
                reasons.append(f"blind_replay_dispatch:{tid}")
            if r.get("trace") and _do_action_marks(r) > r.get("dispatch_calls", 0):
                reasons.append(f"blind_replay_marks:{tid}")
            if kind in ("task", "soak") and (r.get("route"), r.get("path")) != (route, path):
                reasons.append(f"provenance_route_mismatch:{tid}:{r.get('route')}/{r.get('path')}")
        else:
            if delta not in (0, None):
                reasons.append(f"stale_or_canary_dispatch_mutated:{tid}")
            if kind == "stale_negative" and r.get("claimed_success"):
                reasons.append(f"stale_dispatch_accepted:{tid}")
        if "footprint" not in r and not r.get("failure"):
            reasons.append(f"footprint_missing:{tid}")
    champ = [r["footprint"] for r in every if r.get("arm") == "champion" and "footprint" in r]
    cand = [r["footprint"] for r in every if r.get("arm") == "candidate" and "footprint" in r]
    env: dict[str, Any] = {}
    if champ and cand:
        env = {"procs": max(f["procs"] for f in champ), "sockets": max(f["sockets"] for f in champ),
               "files": sorted({_norm_file(x) for f in champ for x in f["home_files"]})}
        files = set(env["files"])
        for f in cand:
            if f["procs"] > env["procs"]:
                reasons.append(f"new_process:{f['procs']}>{env['procs']}")
            if f["sockets"] > env["sockets"]:
                reasons.append(f"new_socket:{f['sockets']}>{env['sockets']}")
            extra = sorted({_norm_file(x) for x in f["home_files"]} - files)
            if extra:
                reasons.append(f"new_file:{extra[0]}")
    elif every:
        reasons.append("footprint_absent_in_an_arm")
    reasons = sorted(set(reasons))
    return result("G2", not reasons, reasons, rows=len(every), champion_envelope=env)


# --------------------------------------------------------------------------- G3
def g3(rows: list[dict]) -> dict[str, Any]:
    reasons = []
    counts = {}
    for arm in ("champion", "candidate"):
        stale = trials(rows, kind="stale_negative", arm=arm, warmup=None)
        canary = trials(rows, kind="impossible_canary", arm=arm, warmup=None)
        counts[arm] = {"stale_negative": len(stale), "impossible_canary": len(canary)}
        if not stale:
            reasons.append(f"no_stale_negative:{arm}")
        if not canary:
            reasons.append(f"no_impossible_canary:{arm}")
        for r in stale:
            if r.get("claimed_success") or not r.get("refused") or r.get("seq_delta") != 0:
                reasons.append(f"negative_not_negative:{r.get('trial_id')}")
        for r in canary:
            if r.get("canary_outcome") not in ("refused", "unknown") or r.get("seq_delta") != 0:
                reasons.append(f"canary_not_refused:{r.get('trial_id')}:{r.get('canary_outcome')}")
    return result("G3", not reasons, reasons, counts=counts)


# --------------------------------------------------------------------------- G4
def g4(rows: list[dict]) -> dict[str, Any]:
    a = trials(rows, kind="task", arm="champion")
    c = trials(rows, kind="task", arm="candidate")
    va = sum(1 for r in a if r.get("verified"))
    vc = sum(1 for r in c if r.get("verified"))
    reasons = []
    if len(a) != len(c):
        reasons.append(f"attempted_differ:{len(a)}!={len(c)}")
    if va != vc:
        reasons.append(f"verified_differ:{va}!={vc}")
    if not a:
        reasons.append("no_task_rows")
    return result("G4", not reasons, reasons, attempted={"champion": len(a), "candidate": len(c)},
                  verified={"champion": va, "candidate": vc})


# --------------------------------------------------------------------------- G5
def g5(rows: list[dict], prereg: dict[str, Any], prior_p_values: list[float]) -> dict[str, Any]:
    tau = prereg["tau"]["value"]
    need = prereg["design"]["n_pairs"]
    seed = prereg["design"]["seed"]
    d = ln_pairs(pairs(rows, "task"))
    n = len(d)
    if n < need:
        return result("G5", False, [f"underpowered:{n}<{need}"], n_pairs=n, inconclusive=True)
    delta = fmean(d)
    ci = stats.bootstrap_ci(d, 0.95, seed=seed)
    p = stats.bootstrap_p_less(d, seed=seed + 1)
    decision = lord.decide(prior_p_values, p)
    threshold = -math.log1p(tau)
    reasons = []
    if not decision["rejected"]:
        reasons.append(f"not_significant:p={p:.4g}>alpha_i={decision['alpha_i']:.4g}")
    if delta > threshold:
        reasons.append(f"effect_below_tau:{delta:.4f}>{threshold:.4f}")
    sigma = stats.sd(d)
    return result("G5", not reasons, reasons, n_pairs=n, delta=delta, ci95=list(ci), p_value=p,
                  sigma_ln=sigma, power=stats.achieved_power(sigma, tau, n),
                  n_required_at_sigma=stats.n_pairs_required(sigma, tau) if sigma > 0 else 2,
                  threshold=threshold, lord=decision)


# --------------------------------------------------------------------------- G6
def g6(rows: list[dict], tau: float) -> dict[str, Any]:
    ta = [r["T_ns"] for r in trials(rows, kind="task", arm="champion") if r.get("verified")]
    tc = [r["T_ns"] for r in trials(rows, kind="task", arm="candidate") if r.get("verified")]
    if not ta or not tc:
        return result("G6", False, ["no_rows"])
    pa, pc = stats.quantile(ta, 0.9), stats.quantile(tc, 0.9)
    ratio = math.log(pc / pa)
    ok = ratio <= math.log1p(tau)
    return result("G6", ok, [] if ok else [f"p90_regression:{ratio:.4f}>{math.log1p(tau):.4f}"],
                  p90_champion_ms=pa / 1e6, p90_candidate_ms=pc / 1e6, ln_ratio=ratio)


# --------------------------------------------------------------------------- G7
def span_ns(row: dict, start: str, end: str) -> int | None:
    t0 = None
    for m in row.get("marks", []):
        key = f"{m.get('phase')}/{m.get('session')}"
        if t0 is None and key == start:
            t0 = m["t_mono_ns"]
        elif t0 is not None and key == end:
            return m["t_mono_ns"] - t0
    return None


def g7(rows: list[dict], prereg: dict[str, Any]) -> dict[str, Any]:
    tau = prereg["tau"]["value"]
    mech = prereg["mechanism"]
    on = pairs(rows, "task", trace=True)
    off = pairs(rows, "task", trace=False)
    reasons = []
    spans = [(span_ns(a, mech["start_mark"], mech["end_mark"]), span_ns(c, mech["start_mark"], mech["end_mark"]))
             for a, c in on]
    complete = [(a, c) for (a, c) in spans if a is not None and c is not None]
    if not on or len(complete) != len(on):
        reasons.append(f"phase_marks_missing:{len(complete)}/{len(on)}")
    total = fmean(a["T_ns"] - c["T_ns"] for a, c in on) if on else 0.0
    phase = fmean(a - c for a, c in complete) if complete else 0.0
    share = phase / total if total > 0 else None
    if total <= 0:
        reasons.append("no_saving_on_trace_on_pairs")
    elif phase < mech.get("min_share", 0.7) * total:
        reasons.append(f"mechanism_share:{share:.3f}<{mech.get('min_share', 0.7)}")
    d_on, d_off = ln_pairs(on), ln_pairs(off)
    agree = None
    if len(d_off) < 2 or len(d_on) < 2:
        reasons.append(f"trace_off_pairs:{len(d_off)}")
    else:
        agree = abs(fmean(d_off) - fmean(d_on))
        if agree > math.log1p(tau):
            reasons.append(f"trace_off_disagrees:{agree:.4f}>{math.log1p(tau):.4f}")
    return result("G7", not reasons, reasons, saving_ms=total / 1e6, phase_saving_ms=phase / 1e6,
                  share=share, delta_on=fmean(d_on) if d_on else None,
                  delta_off=fmean(d_off) if d_off else None, abs_on_off=agree,
                  pairs_on=len(on), pairs_off=len(off))


# --------------------------------------------------------------------------- G8
def g8(rows: list[dict], changed: list[str], allowlist: dict[str, Any], prereg: dict[str, Any]) -> dict[str, Any]:
    need = 1000 if any(p in allowlist.get("soak_1000_files", []) for p in changed) else 300
    soak = trials(rows, kind="soak", arm="candidate")
    route = (prereg["invariants"]["expected_route"], prereg["invariants"]["expected_path"])
    bad = [r.get("trial_id") for r in soak
           if not r.get("verified") or r.get("failure") or r.get("seq_delta") != 1
           or not r.get("journal_before_done") or (r.get("route"), r.get("path")) != route]
    reasons = []
    if len(soak) < need:
        reasons.append(f"soak_short:{len(soak)}<{need}")
    if bad:
        reasons.append(f"soak_failures:{len(bad)}:first={bad[0]}")
    return result("G8", not reasons, reasons, soak_trials=len(soak), required=need, failures=len(bad))


# --------------------------------------------------------------------------- GS
def gs(rows: list[dict], prereg: dict[str, Any]) -> dict[str, Any]:
    tau = prereg["tau"]["value"]
    min_pairs = prereg.get("spot_min_pairs", 10)
    seed = prereg["design"]["seed"]
    reasons = []
    per: dict[str, Any] = {}
    for kind in prereg["spot_checks"]:
        a = trials(rows, kind=kind, arm="champion")
        c = trials(rows, kind=kind, arm="candidate")
        va = sum(1 for r in a if r.get("verified"))
        vc = sum(1 for r in c if r.get("verified"))
        ps = pairs(rows, kind)
        info: dict[str, Any] = {"attempted": [len(a), len(c)], "verified": [va, vc], "pairs": len(ps)}
        if not a or not c:
            reasons.append(f"spot_not_run:{kind}")
        elif va < vc or va != len(a) or vc != len(c):
            reasons.append(f"spot_verified_inferior:{kind}:{va}/{len(a)} vs {vc}/{len(c)}")
        elif len(ps) < min_pairs:
            reasons.append(f"spot_pairs:{kind}:{len(ps)}<{min_pairs}")
        else:
            d = ln_pairs(ps)
            lo, hi = stats.bootstrap_ci(d, 0.95, seed=seed + 7)
            info.update(delta=fmean(d), ci95=[lo, hi])
            if hi > math.log1p(tau):
                reasons.append(f"spot_latency_inferior:{kind}:{hi:.4f}>{math.log1p(tau):.4f}")
        per[kind] = info
    return result("GS", not reasons, reasons, spot=per)


# --------------------------------------------------------------------------- pipeline
def evaluate(prereg: dict[str, Any], rows: list[dict], build_rows: list[dict], g0_inputs: dict[str, Any],
             allowlist: dict[str, Any], manifest: dict[str, Any], rules: dict[str, Any],
             prior_p_values: list[float]) -> dict[str, Any]:
    """All gates in order; stop at the first failure. Pure."""
    tau = prereg["tau"]["value"]
    steps = [
        ("G0", lambda: g0(g0_inputs, allowlist, manifest, rules)),
        ("G1", lambda: g1(build_rows, prereg["g1_required_suites"])),
        ("G2", lambda: g2(rows, prereg)),
        ("G3", lambda: g3(rows)),
        ("G4", lambda: g4(rows)),
        ("G5", lambda: g5(rows, prereg, prior_p_values)),
        ("G6", lambda: g6(rows, tau)),
        ("G7", lambda: g7(rows, prereg)),
        ("G8", lambda: g8(rows, g0_inputs_changed(g0_inputs), allowlist, prereg)),
        ("GS", lambda: gs(rows, prereg)),
    ]
    out: list[dict[str, Any]] = []
    failed = None
    for name, fn in steps:
        res = fn()
        out.append(res)
        if not res["pass"]:
            failed = name
            break
    g5r = next((g for g in out if g["gate"] == "G5"), None)
    inconclusive = bool(g5r and g5r["metrics"].get("inconclusive"))
    verdict = "KEEP" if failed is None else ("INCONCLUSIVE" if failed == "G5" and inconclusive else "REJECT")
    m = g5r["metrics"] if g5r else {}
    return {
        "verdict": verdict,
        "failed_gate": failed,
        "gates": out,
        "not_evaluated": [g for g in GATE_ORDER if g not in {x["gate"] for x in out}],
        "delta": m.get("delta"),
        "ci95": m.get("ci95"),
        "p_value": m.get("p_value"),
        "power": m.get("power"),
        "n_pairs": m.get("n_pairs"),
        "tau": tau,
        "lord": m.get("lord"),
        "median_T_ms": {arm: _median_ms(trials(rows, "task", arm)) for arm in ("champion", "candidate")},
    }


def _median_ms(rows: list[dict]) -> float | None:
    ts = [r["T_ns"] for r in rows if r.get("verified") and r.get("T_ns")]
    return median(ts) / 1e6 if ts else None


def g0_inputs_changed(g0_inputs: dict[str, Any]) -> list[str]:
    from .g0 import changed_paths
    return changed_paths(g0_inputs.get("diff", ""))
