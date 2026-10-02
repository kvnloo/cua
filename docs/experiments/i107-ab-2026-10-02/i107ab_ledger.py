"""kvnloo/cua#107 lane AB: producer-RPC ledger parsing, semantic equivalence, /proc readers,
preflight and statistics helpers. Pure standard library so verify_artifacts.py can rerun it.
"""

from __future__ import annotations

import os
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import b01_analysis as A

LEDGER_MARKS = frozenset({"cdp.send", "cdp.reply", "cdp.event", "snap.acquired_dom", "snap.acquired_ax"})
SPANS10 = (
    "observation acquisition", "projection/encoding/transport", "provider inference",
    "resolution/validation", "dispatch", "wait", "fresh verification", "residual/unattributed",
)
OUTCOMES = ("verified", "refuted", "abstained", "unknown", "timeout", "budget_exhausted", "error")
# platform-linux browser_platform.rs isolated_browser_candidates() at the tested source.
DRIVER_ISOLATED_CANDIDATES = (
    "/opt/google/chrome/google-chrome", "/usr/lib/chromium/chromium",
    "/usr/lib/chromium-browser/chromium-browser", "/opt/microsoft/msedge/msedge",
)
CONTROL_KEYS = (("textbox", "verification value"), ("button", "Submit"))


# ── producer-RPC ledger ─────────────────────────────────────────────────────────

def strip_ledger(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Phase marks only: ledger marks are measurement points, never phase boundaries."""
    return [m for m in trace if m.get("phase") not in LEDGER_MARKS]


def decomposable(trial: dict[str, Any]) -> dict[str, Any]:
    return {**trial, "trace": strip_ledger(trial.get("trace") or [])}


def ledger_for_window(trace: list[dict[str, Any]], t0: int, t1: int) -> dict[str, Any]:
    sends: dict[int, str] = {}
    methods: Counter[str] = Counter()
    events: Counter[str] = Counter()
    reply_by_method: Counter[str] = Counter()
    out = {"send_bytes": 0, "reply_bytes": 0, "event_bytes": 0, "dom_nodes": 0, "layout_nodes": 0,
           "ax_nodes": 0, "unmatched_replies": 0, "reply_errors": 0}
    for m in trace:
        t = m.get("t_mono_ns", -1)
        if not (t0 <= t <= t1):
            continue
        phase, d = m.get("phase"), (m.get("detail") or {})
        if phase == "cdp.send":
            sends[d.get("id")] = d.get("method", "?")
            methods[d.get("method", "?")] += 1
            out["send_bytes"] += int(d.get("bytes") or 0)
        elif phase == "cdp.reply":
            out["reply_bytes"] += int(d.get("bytes") or 0)
            out["reply_errors"] += 1 if d.get("error") else 0
            method = sends.get(d.get("id"))
            if method is None:
                out["unmatched_replies"] += 1
            else:
                reply_by_method[method] += int(d.get("bytes") or 0)
        elif phase == "cdp.event":
            events[d.get("method", "?")] += 1
            out["event_bytes"] += int(d.get("bytes") or 0)
        elif phase == "snap.acquired_dom":
            out["dom_nodes"] += int(d.get("dom_nodes") or 0)
            out["layout_nodes"] += int(d.get("layout_nodes") or 0)
        elif phase == "snap.acquired_ax":
            out["ax_nodes"] += int(d.get("ax_nodes") or 0)
    return {"methods": dict(methods), "reply_bytes_by_method": dict(reply_by_method), "events": dict(events), **out}


def snapshot_ledgers(trial: dict[str, Any]) -> list[dict[str, Any]]:
    """One ledger per decision snapshot (caller labels snapshot1, snapshot2, ...), in order."""
    out = []
    for w in A._windows(trial["events"]):
        if w["tool"] == "get_browser_state" and w["label"].startswith("snapshot"):
            out.append({"label": w["label"], **ledger_for_window(trial["trace"], w["t0"], w["t1"])})
    return out


def compare_acquisition(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> dict[str, Any]:
    diffs = []
    steps_equal = len(a) == len(b)
    if not steps_equal:
        diffs.append(f"snapshot count {len(a)} != {len(b)}")
    methods_equal = steps_equal
    nodes_equal = steps_equal
    for i, (x, y) in enumerate(zip(a, b), 1):
        if Counter(x["methods"]) != Counter(y["methods"]):
            methods_equal = False
            diffs.append(f"step{i} methods {dict(Counter(x['methods']) - Counter(y['methods']))} vs "
                         f"{dict(Counter(y['methods']) - Counter(x['methods']))}")
        for k in ("dom_nodes", "layout_nodes", "ax_nodes"):
            if x[k] != y[k]:
                nodes_equal = False
                diffs.append(f"step{i} {k} {x[k]} != {y[k]}")
    return {"steps_equal": steps_equal, "methods_equal": methods_equal, "nodes_equal": nodes_equal, "diffs": diffs}


# ── #10 span mapping ────────────────────────────────────────────────────────────

def span10(comp: dict[str, float], sub: dict[str, float]) -> dict[str, float]:
    obs_cdp = sub.get("observation_cdp", 0.0)
    g = lambda *names: sum(comp.get(n, 0.0) for n in names)  # noqa: E731
    return {
        "observation acquisition": obs_cdp,
        "projection/encoding/transport": (comp.get("observation", 0.0) - obs_cdp)
        + g("driver_post_dispatch", "transport", "client_parse", "client_validation"),
        "provider inference": g("decision"),
        "resolution/validation": g("resolution", "revalidate", "driver_pre_dispatch", "input_prep", "candidate_build"),
        "dispatch": g("dispatch", "dispatch_post"),
        "wait": g("visualization", "settles", "sleeps_polls", "target_effect_lag"),
        "fresh verification": g("verification_reads", "oracle_detect_lag"),
        "residual/unattributed": g("runner_overhead", "unattributed"),
    }


# ── semantic equivalence ────────────────────────────────────────────────────────

def logical_controls(snapshot: dict[str, Any], token: str) -> dict[str, Any]:
    refs = snapshot.get("refs") or []
    out: dict[str, Any] = {}
    for role, name in CONTROL_KEYS:
        matches = [r for r in refs if r.get("role") == role and r.get("name") == name]
        first = matches[0] if matches else None
        out[f"{role}:{name}"] = {
            "count": len(matches),
            "frame": first.get("frame") if first else None,
            "visibility": first.get("visibility") if first else None,
            "actions": sorted(first.get("actions") or []) if first else None,
            "states": sorted((first.get("states") or {}).keys()) if first else None,
            "value_is_token": (first.get("value") == token) if first else None,
            "value_empty": (not first.get("value")) if first else None,
        }
    return out


def equivalent(a_steps: list[dict[str, Any]], b_steps: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = []
    if len(a_steps) != len(b_steps):
        reasons.append(f"step count {len(a_steps)} != {len(b_steps)}")
    for i, (x, y) in enumerate(zip(a_steps, b_steps), 1):
        if x["candidates"] != y["candidates"]:
            reasons.append(f"step{i} candidates {x['candidates']} != {y['candidates']}")
        for key in sorted(set(x["controls"]) | set(y["controls"])):
            if x["controls"].get(key) != y["controls"].get(key):
                reasons.append(f"step{i} {key} {x['controls'].get(key)} != {y['controls'].get(key)}")
    return {"equivalent": not reasons, "reasons": reasons}


# ── /proc readers (read-only) ───────────────────────────────────────────────────

def _stat_fields(pid: int, proc: Path) -> list[str] | None:
    try:
        text = (proc / str(pid) / "stat").read_text()
    except OSError:
        return None
    return text[text.rindex(")") + 2:].split()


def cpu_ticks(pid: int, proc: Path = Path("/proc")) -> int | None:
    f = _stat_fields(pid, proc)
    return None if f is None else int(f[11]) + int(f[12])


def status_kb(pid: int, keys: tuple[str, ...] = ("VmHWM", "VmRSS"), proc: Path = Path("/proc")) -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        for line in (proc / str(pid) / "status").read_text().splitlines():
            k, _, v = line.partition(":")
            if k in keys:
                out[k] = int(v.split()[0])
    except OSError:
        pass
    return out


def _ppids(proc: Path) -> dict[int, int]:
    out = {}
    for d in proc.iterdir():
        if d.name.isdigit():
            f = _stat_fields(int(d.name), proc)
            if f is not None:
                out[int(d.name)] = int(f[1])
    return out


def descendants(root: int, proc: Path = Path("/proc")) -> set[int]:
    ppids = _ppids(proc)
    found: set[int] = set()
    frontier = {root}
    while frontier:
        nxt = {p for p, pp in ppids.items() if pp in frontier and p not in found}
        found |= nxt
        frontier = nxt
    return found


def tree_usage(root: int, proc: Path = Path("/proc")) -> dict[str, int]:
    pids = {root} | descendants(root, proc)
    cpu = rss = alive = 0
    for p in pids:
        t = cpu_ticks(p, proc)
        if t is None:
            continue
        alive += 1
        cpu += t
        rss += status_kb(p, ("VmRSS",), proc).get("VmRSS", 0)
    return {"pids": alive, "cpu_ticks": cpu, "rss_kb": rss}


def children_with_argv0(parent: int, argv0: str, proc: Path = Path("/proc")) -> list[int]:
    out = []
    for p, pp in sorted(_ppids(proc).items()):
        if pp != parent:
            continue
        try:
            if (proc / str(p) / "cmdline").read_bytes().split(b"\x00")[0].decode() == argv0:
                out.append(p)
        except OSError:
            continue
    return out


def pressure(proc: Path = Path("/proc")) -> dict[str, str]:
    out = {}
    for k in ("cpu", "memory"):
        try:
            out[k] = (proc / "pressure" / k).read_text().strip()
        except OSError:
            out[k] = "unavailable"
    return out


def clk_tck() -> int:
    return os.sysconf("SC_CLK_TCK")


# ── preflight: can the Driver's isolated-launch precondition hold here? ─────────

def trust_precondition(candidates: list[str] | tuple[str, ...] = DRIVER_ISOLATED_CANDIDATES) -> dict[str, Any]:
    """Read-only mirror of trusted_root_owned_installation; the Driver still runs its own check."""
    checked = []
    for c in candidates:
        path = Path(c)
        reason = "ok"
        if not path.is_absolute():
            reason = "not_absolute"
        else:
            cur: Path | None = path
            while cur is not None:
                try:
                    st = os.lstat(cur)
                except OSError:
                    reason = "missing"
                    break
                if (st.st_mode & 0o170000) == 0o120000:
                    reason = "symlink"
                    break
                if st.st_uid != 0:
                    reason = "uid_not_0"
                    break
                if st.st_mode & 0o022:
                    reason = "group_or_world_writable"
                    break
                cur = None if cur.parent == cur else cur.parent
            if reason == "ok" and not (path.is_file() and os.stat(path).st_mode & 0o111):
                reason = "not_executable_file"
        checked.append({"candidate_index": len(checked), "reason": reason})
    return {"ok": any(c["reason"] == "ok" for c in checked), "checked": checked}


# ── statistics ──────────────────────────────────────────────────────────────────

def threshold_ms(a_median: float) -> float:
    return max(5.0, 0.05 * a_median)


def improvement_verdict(median: float, ci: list[float] | None, threshold: float) -> str:
    if ci is None:
        return "inconclusive"
    if median <= -threshold and ci[1] < 0:
        return "meaningful"
    if ci[0] > -threshold:
        return "no_meaningful_benefit"
    return "inconclusive"


def within_noise(deltas: list[float], a_median: float, rel: float = 0.02) -> dict[str, Any]:
    if not deltas:
        return {"equal": None, "n": 0}
    med = statistics.median(deltas)
    ci = A.boot_ci(len(deltas), lambda idx: statistics.median([deltas[i] for i in idx]))
    bound = abs(a_median) * rel
    equal = abs(med) <= bound and (ci is None or ci[0] <= 0 <= ci[1])
    return {"equal": equal, "n": len(deltas), "median": med, "ci95": ci, "bound": bound}


def denominators(outcomes: list[str]) -> dict[str, int]:
    out = {k: 0 for k in OUTCOMES}
    out["other"] = 0
    for o in outcomes:
        out[o if o in out else "other"] += 1
    out["n"] = len(outcomes)
    return out


def abba_pairs(a: str, b: str, n: int) -> list[tuple[str, str]]:
    return [(a, b) if i % 4 in (0, 3) else (b, a) for i in range(n)]


def paired_values(rows: list[dict[str, Any]], a: str, b: str, key: str) -> tuple[list[float], list[float]]:
    by: dict[str, dict[str, float]] = {}
    for r in rows:
        if r.get(key) is not None:
            by.setdefault(r["pair"], {})[r["arm"]] = r[key]
    pairs = [v for _, v in sorted(by.items()) if a in v and b in v]
    return [v[a] for v in pairs], [v[b] for v in pairs]


# ── wire capture ────────────────────────────────────────────────────────────────

def recording_parser(parse: Callable[[str], Any], record: Callable[..., None]) -> Callable[[str], Any]:
    def wrapped(line: str) -> Any:
        t0 = time.monotonic_ns()
        try:
            return parse(line)
        finally:
            record(t0=t0, t1=time.monotonic_ns(), bytes=len(line.encode()))
    return wrapped
