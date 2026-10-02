"""Gates G1-G8 and GS: pure functions of raw rows (``ar.trial.v1`` / ``ar.build.v1`` /
``ar.session.v1``), the pre-registration and, for G8, the changed paths. :func:`evaluate` runs
G0..GS in order and stops at the first failure. Nothing here reads files or clocks.

Latency gates read the pre-registered decision metric (``design.metric``): ``T_act`` (first
dispatch -> verified done) or ``T`` (Driver spawn -> verified done). Whole-task T stays a
guardrail in G6 (``guardrail.tau``).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import PurePosixPath
from statistics import fmean, median
from typing import Any, Iterable

from . import lord, stats
from .g0 import g0

POSITIVE_KINDS = ("task", "soak", "spot_gtk3_text", "spot_browser_fill_submit")
EXPECTED_DISPATCH = {"task": 1, "soak": 1, "spot_gtk3_text": 1, "spot_browser_fill_submit": 1}
GATE_ORDER = ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "GS")
DISPATCH_TOOLS = ("click", "set_value", "browser_type", "browser_click")


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


def t_act_ns(row: dict) -> int | None:
    """First dispatch (m0 of the first mutating call) to the verified done."""
    first = next((c["m0"] for c in row.get("calls", []) if c.get("tool") in DISPATCH_TOOLS), None)
    if first is None or not row.get("t_done_ns"):
        return None
    return row["t_done_ns"] - first


def value_ns(row: dict, metric: str = "T") -> int | None:
    """The row's latency under ``metric``: ``T`` (whole task) or ``T_act``."""
    if metric == "T":
        return row.get("T_ns")
    if metric == "T_act":
        return t_act_ns(row) if row.get("T_ns") else None
    raise ValueError(f"unknown metric {metric!r}")


def pairs(rows: Iterable[dict], kind: str = "task", trace: bool | None = None,
          metric: str = "T") -> list[tuple[dict, dict]]:
    """(champion, candidate) rows of complete, verified pairs with a value under ``metric``."""
    by: dict[Any, dict[str, dict]] = defaultdict(dict)
    for r in trials(rows, kind=kind):
        if trace is not None and bool(r.get("trace")) != trace:
            continue
        by[r["pair_id"]][r["arm"]] = r
    out = []
    for pid in sorted(by, key=str):
        p = by[pid]
        a, c = p.get("champion"), p.get("candidate")
        if a and c and a.get("verified") and c.get("verified") and value_ns(a, metric) and value_ns(c, metric):
            out.append((a, c))
    return out


def ln_pairs(ps: list[tuple[dict, dict]], metric: str = "T") -> list[float]:
    return stats.ln_ratios([(value_ns(a, metric), value_ns(c, metric)) for a, c in ps])


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


_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


_SANDBOX_ROOTS = ("/tmp", "/run/user/trial", "/home/trial")  # the dirs footprint() lists


def session_names(rows: Iterable[dict]) -> dict[tuple[Any, Any], dict[str, str]]:
    """Per (eval_id, session): the sandbox paths the HARNESS itself puts there, from the runner's
    session manifest (``ar.session.v1`` start record, ``session_binds``: the X socket, the session
    D-Bus socket, the AT-SPI socket, the Xauthority file, each bound at its own path by
    sandbox-driver.sh), plus the parent dirs bwrap creates for those binds below a listed root.
    Each maps to a stable ``<session:...>`` name, so a per-session random name (/tmp/dbus-<random>)
    compares equal across sessions while any other path, including a look-alike or another
    session's name, is still compared as itself."""
    out: dict[tuple[Any, Any], dict[str, str]] = {}
    for r in rows:
        if r.get("schema") != "ar.session.v1" or r.get("event") != "start":
            continue
        names: dict[str, str] = {}
        for key, path in sorted((r.get("session_binds") or {}).items()):
            if not path:
                continue
            bound = PurePosixPath(path)
            names[str(bound)] = f"<session:{key}>"
            for depth, parent in enumerate(bound.parents, 1):
                if not any(parent.is_relative_to(root) and str(parent) != root for root in _SANDBOX_ROOTS):
                    break
                names.setdefault(str(parent), f"<session:{key}:up{depth}>")
        out[(r.get("eval_id"), r.get("session"))] = names
    return out


def _norm_file(path: str, names: dict[str, str] | None = None) -> str:
    if names and path in names:
        return names[path]
    # UUIDs first (the Driver names its isolated browser profile isolated-<uuid>), whose 4-digit
    # hex groups the generic run rule would leave partly letters. The contents of that profile are
    # written by Chromium, not the Driver, and vary run to run (e.g. VariationsSeedV#), so the
    # profile counts as one entry, as does Mesa's hash-named shader cache; every other path is
    # still compared one by one.
    path = _PROFILE_CONTENT.sub(r"\1/...", _UUID.sub("<uuid>", path))
    return _RANDOM_RUN.sub("#", path)


_PROFILE_CONTENT = re.compile(r"(browser-profiles/isolated-<uuid>|\.cache/mesa_shader_cache)/.*")


def _do_action_marks(row: dict) -> int:
    return sum(1 for m in row.get("marks", [])
               if m.get("phase") == "atspi_action" and m.get("session") == "do_action_replied")


def g2(rows: list[dict], prereg: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    every = trials(rows, warmup=None)
    names = session_names(rows)

    def norm(row: dict) -> set[str]:
        own = names.get((row.get("eval_id"), row.get("session")))
        return {_norm_file(x, own) for x in row["footprint"]["home_files"]}

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
        if r.get("leftover_procs"):
            reasons.append(f"process_outlived_driver:{tid}:{r.get('leftover_procs')}")
    # The envelope is per footprint class: the sandboxed GTK Driver and the unsandboxed browser
    # Driver (which launches Chromium) are compared only with their own champion rows, so a
    # browser process tree can never mask a new process in a GTK trial.
    envelopes: dict[str, Any] = {}
    for cls in sorted({_footprint_class(r) for r in every}):
        champ = [r for r in every if r.get("arm") == "champion" and "footprint" in r and _footprint_class(r) == cls]
        cand = [r for r in every if r.get("arm") == "candidate" and "footprint" in r and _footprint_class(r) == cls]
        if champ and cand:
            env = {"procs": max(r["footprint"]["procs"] for r in champ),
                   "sockets": max(r["footprint"]["sockets"] for r in champ),
                   "files": sorted(set().union(*(norm(r) for r in champ)))}
            envelopes[cls] = env
            files = set(env["files"])
            for r in cand:
                f = r["footprint"]
                if f["procs"] > env["procs"]:
                    reasons.append(f"new_process:{cls}:{f['procs']}>{env['procs']}")
                if f["sockets"] > env["sockets"]:
                    reasons.append(f"new_socket:{cls}:{f['sockets']}>{env['sockets']}")
                extra = sorted(norm(r) - files)
                if extra:
                    reasons.append(f"new_file:{cls}:{extra[0]}")
        else:
            reasons.append(f"footprint_absent_in_an_arm:{cls}")
    reasons = sorted(set(reasons))
    return result("G2", not reasons, reasons, rows=len(every), champion_envelope=envelopes)


def _footprint_class(row: dict) -> str:
    return "browser" if row.get("kind") == "spot_browser_fill_submit" else "gtk"


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
    metric = prereg["design"]["metric"]
    d = ln_pairs(pairs(rows, "task", metric=metric), metric)
    n = len(d)
    if n < need:
        return result("G5", False, [f"underpowered:{n}<{need}"], n_pairs=n, inconclusive=True, metric=metric)
    delta = fmean(d)
    ci = stats.bootstrap_ci(d, 0.95, seed=seed)
    # The level depends only on earlier rejections, so the resample count is fixed before the
    # data are looked at; its p floor 1/(b+1) is below the level (F2).
    b = stats.sign_flip_resamples(lord.next_alpha(prior_p_values))
    p = stats.sign_flip_p_less(d, b, seed=seed + 1)
    decision = lord.decide(prior_p_values, p)
    threshold = -math.log1p(tau)
    reasons = []
    if not decision["rejected"]:
        reasons.append(f"not_significant:p={p:.4g}>alpha_i={decision['alpha_i']:.4g}")
    if delta > threshold:
        reasons.append(f"effect_below_tau:{delta:.4f}>{threshold:.4f}")
    sigma = stats.sd(d)
    return result("G5", not reasons, reasons, metric=metric, n_pairs=n, delta=delta, ci95=list(ci), p_value=p,
                  p_test="paired_sign_flip", p_resamples=b, sigma_ln=sigma, power=stats.achieved_power(sigma, tau, n),
                  n_required_at_sigma=stats.n_pairs_required(sigma, tau) if sigma > 0 else 2,
                  threshold=threshold, lord=decision)


# --------------------------------------------------------------------------- G6
def g6(rows: list[dict], prereg: dict[str, Any]) -> dict[str, Any]:
    """Guardrails: the decision metric's p90 tail, and whole-task T's mean paired ln ratio
    (startup is outside T_act) within ln(1 + guardrail tau)."""
    tau = prereg["tau"]["value"]
    metric = prereg["design"]["metric"]
    ta = [value_ns(r, metric) for r in trials(rows, kind="task", arm="champion") if r.get("verified")]
    tc = [value_ns(r, metric) for r in trials(rows, kind="task", arm="candidate") if r.get("verified")]
    ta, tc = [x for x in ta if x], [x for x in tc if x]
    if not ta or not tc:
        return result("G6", False, ["no_rows"])
    reasons = []
    pa, pc = stats.quantile(ta, 0.9), stats.quantile(tc, 0.9)
    ratio = math.log(pc / pa)
    if ratio > math.log1p(tau):
        reasons.append(f"p90_regression:{ratio:.4f}>{math.log1p(tau):.4f}")
    guard = prereg["guardrail"]
    d_whole = ln_pairs(pairs(rows, "task", metric=guard["metric"]), guard["metric"])
    whole = fmean(d_whole) if d_whole else None
    if whole is None:
        reasons.append("whole_task_no_pairs")
    elif whole > math.log1p(guard["tau"]):
        reasons.append(f"whole_task_regression:{whole:.4f}>{math.log1p(guard['tau']):.4f}")
    return result("G6", not reasons, reasons, metric=metric, p90_champion_ms=pa / 1e6, p90_candidate_ms=pc / 1e6,
                  ln_ratio=ratio, whole_task_delta=whole, whole_task_limit=math.log1p(guard["tau"]))


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
    """Mechanism: the pre-registered phase carries >= min_share of the traced saving, and the
    trace-unset pairs agree: their Delta (all of them) lies inside the traced pairs' bootstrap
    CI95 widened by ln(1+tau) on each side (F3; a point-vs-point check false-rejected ~8 off
    pairs on a loaded host)."""
    tau = prereg["tau"]["value"]
    mech = prereg["mechanism"]
    metric = prereg["design"]["metric"]
    on = pairs(rows, "task", trace=True, metric=metric)
    off = pairs(rows, "task", trace=False, metric=metric)
    reasons = []
    spans = [(span_ns(a, mech["start_mark"], mech["end_mark"]), span_ns(c, mech["start_mark"], mech["end_mark"]))
             for a, c in on]
    complete = [(a, c) for (a, c) in spans if a is not None and c is not None]
    if not on or len(complete) != len(on):
        reasons.append(f"phase_marks_missing:{len(complete)}/{len(on)}")
    total = fmean(value_ns(a, metric) - value_ns(c, metric) for a, c in on) if on else 0.0
    phase = fmean(a - c for a, c in complete) if complete else 0.0
    share = phase / total if total > 0 else None
    if total <= 0:
        reasons.append("no_saving_on_trace_on_pairs")
    elif phase < mech.get("min_share", 0.7) * total:
        reasons.append(f"mechanism_share:{share:.3f}<{mech.get('min_share', 0.7)}")
    d_on, d_off = ln_pairs(on, metric), ln_pairs(off, metric)
    band = None
    if len(d_off) < 2 or len(d_on) < 2:
        reasons.append(f"trace_off_pairs:{len(d_off)}")
    else:
        lim = math.log1p(tau)
        lo, hi = stats.bootstrap_ci(d_on, 0.95, seed=prereg["design"]["seed"] + 11)
        band = [lo - lim, hi + lim]
        if not band[0] <= fmean(d_off) <= band[1]:
            reasons.append(f"trace_off_disagrees:{fmean(d_off):.4f}_outside_[{band[0]:.4f},{band[1]:.4f}]")
    return result("G7", not reasons, reasons, metric=metric, saving_ms=total / 1e6, phase_saving_ms=phase / 1e6,
                  share=share, delta_on=fmean(d_on) if d_on else None,
                  delta_off=fmean(d_off) if d_off else None, trace_off_band=band,
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
    metric = prereg["design"]["metric"]
    reasons = []
    per: dict[str, Any] = {}
    for kind in prereg["spot_checks"]:
        a = trials(rows, kind=kind, arm="champion")
        c = trials(rows, kind=kind, arm="candidate")
        va = sum(1 for r in a if r.get("verified"))
        vc = sum(1 for r in c if r.get("verified"))
        ps = pairs(rows, kind, metric=metric)
        info: dict[str, Any] = {"attempted": [len(a), len(c)], "verified": [va, vc], "pairs": len(ps)}
        if not a or not c:
            reasons.append(f"spot_not_run:{kind}")
        elif va < vc or va != len(a) or vc != len(c):
            reasons.append(f"spot_verified_inferior:{kind}:{va}/{len(a)} vs {vc}/{len(c)}")
        elif len(ps) < min_pairs:
            reasons.append(f"spot_pairs:{kind}:{len(ps)}<{min_pairs}")
        else:
            d = ln_pairs(ps, metric)
            lo, hi = stats.bootstrap_ci(d, 0.95, seed=seed + 7)
            info.update(delta=fmean(d), ci95=[lo, hi])
            if hi > math.log1p(tau):
                reasons.append(f"spot_latency_inferior:{kind}:{hi:.4f}>{math.log1p(tau):.4f}")
        per[kind] = info
    return result("GS", not reasons, reasons, metric=metric, spot=per)


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
        ("G6", lambda: g6(rows, prereg)),
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
        "metric": prereg["design"]["metric"],
        "median_T_ms": {arm: _median_ms(trials(rows, "task", arm), "T") for arm in ("champion", "candidate")},
        "median_T_act_ms": {arm: _median_ms(trials(rows, "task", arm), "T_act") for arm in ("champion", "candidate")},
    }


def _median_ms(rows: list[dict], metric: str) -> float | None:
    ts = [v for v in (value_ns(r, metric) for r in rows if r.get("verified")) if v]
    return median(ts) / 1e6 if ts else None


def g0_inputs_changed(g0_inputs: dict[str, Any]) -> list[str]:
    from .g0 import changed_paths
    return changed_paths(g0_inputs.get("diff", ""))
