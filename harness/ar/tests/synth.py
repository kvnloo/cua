"""Synthetic raw rows for gate unit tests (no Driver, no session, no clock)."""

from __future__ import annotations

import math
import random
from typing import Any

MS = 1_000_000
ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
ROUTE = "accessibility"
FOOT = {"procs": 2, "sockets": 7, "fds": 17, "home_files": ["/home/trial/.cua-driver",
                                                              "/home/trial/.cua-driver/.telemetry_id"]}


def prereg(**over: Any) -> dict[str, Any]:
    p = {
        "tau": {"value": 0.02},
        "design": {"n_pairs": 30, "seed": 11, "metric": "T_act"},
        "guardrail": {"metric": "T", "tau": 0.03},
        "mechanism": {"start_mark": "focus_guard/body_done", "end_mark": "focus_guard/restored", "min_share": 0.7},
        "invariants": {"expected_route": ROUTE, "expected_path": None},
        "spot_checks": ["spot_gtk3_text", "spot_browser_fill_submit"],
        "spot_min_pairs": 10,
        "g1_required_suites": ["cua-driver-core --lib", "platform-linux --lib"],
    }
    for k, v in over.items():
        p[k] = v
    return p


def trial(tid: int, arm: str, kind: str, T_ms: float | None, phase_ms: float | None = None, trace: bool = True,
          pair: Any = None, order: str | None = None, position: int | None = None, **over: Any) -> dict[str, Any]:
    r: dict[str, Any] = {
        "schema": "ar.trial.v1", "trial_id": tid, "session": 0, "pair_id": pair, "order": order,
        "position": position, "arm": arm, "kind": kind, "trace": trace, "warmup": False,
        "binary_sha256": "0" * 64, "t_spawn_ns": 0, "failure": None, "journal": [], "calls": [],
        "loadavg_start": [0.5], "loadavg_end": [0.5], "footprint": {**FOOT, "home_files": list(FOOT["home_files"])},
    }
    positive = kind in ("task", "soak", "spot_gtk3_text", "spot_browser_fill_submit")
    if positive:
        r.update(verified=True, claimed_success=True, seq_delta=1, journal_before_done=True, dispatch_calls=1,
                 route=ROUTE if kind in ("task", "soak") else None, path=None)
        set_times(r, int(T_ms * MS))
        if trace and phase_ms is not None:
            t0 = 100 * MS
            r["marks"] = [
                {"phase": "atspi_action", "session": "do_action_replied", "t_mono_ns": t0 - MS},
                {"phase": "focus_guard", "session": "body_done", "t_mono_ns": t0},
                {"phase": "focus_guard", "session": "restored", "t_mono_ns": t0 + int(phase_ms * MS)},
            ]
    elif kind == "stale_negative":
        r.update(verified=False, claimed_success=False, refused=True, refused_stale=True, seq_delta=0,
                 dispatch_calls=1, route=None, path=None)
    elif kind == "impossible_canary":
        r.update(verified=False, claimed_success=False, refused=True, canary_outcome="refused", seq_delta=0,
                 dispatch_calls=1, route=None, path=None)
    r.update(over)
    return r


def set_times(row: dict[str, Any], T_ns: int, act_ns: int | None = None) -> dict[str, Any]:
    """Whole-task T (spawn -> verified done) and T_act (first dispatch m0 -> done; default 0.6 T,
    so both metrics share every paired ln ratio unless a test sets them apart)."""
    act_ns = T_ns * 3 // 5 if act_ns is None else act_ns
    row.update(T_ns=T_ns, t_done_ns=row["t_spawn_ns"] + T_ns)
    row["calls"] = [{"tool": "get_window_state", "m0": row["t_spawn_ns"]},
                    {"tool": "click", "m0": row["t_done_ns"] - act_ns}]
    return row


def with_sessions(rows: list[dict[str, Any]], eval_id: str = "ar-20261002-synth",
                  manifest: bool = True) -> list[dict[str, Any]]:
    """Spread rows over sessions the way plan.py does (paired GTK sessions, candidate-only soak
    sessions of 47, a browser session) and give every GTK row the sandbox /tmp listing of its own
    session: the bwrap-created X11 dir, the bound X socket and the session's randomly named D-Bus
    socket. With ``manifest`` each session also gets the runner's ``ar.session.v1`` start record
    naming those binds (``session_binds``), as session.py writes it."""
    out: list[dict[str, Any]] = []
    sessions: dict[int, str] = {}
    soak_seen = 0
    for r in rows:
        kind = r.get("kind")
        if kind == "soak":
            s = 10 + soak_seen // 47
            soak_seen += 1
        elif kind == "spot_browser_fill_submit":
            s = 9
        else:
            s = (r["trial_id"] // 2) % 2  # two paired GTK sessions
        r["session"], r["eval_id"] = s, eval_id
        if kind != "spot_browser_fill_submit":
            dbus = sessions.setdefault(s, "/tmp/dbus-" + "".join(random.Random(s).choices(ALNUM, k=10)))
            r["footprint"]["home_files"] = [*r["footprint"]["home_files"], "/tmp/.X11-unix", "/tmp/.X11-unix/X99",
                                            dbus]
        else:
            sessions.setdefault(s, f"/tmp/dbus-browser{s}")
    if manifest:
        for s, dbus in sorted(sessions.items()):
            out.append({"schema": "ar.session.v1", "event": "start", "session": s, "eval_id": eval_id,
                        "session_binds": {"x11": "/tmp/.X11-unix/X99", "dbus": dbus,
                                          "a11y": f"/run/user/1000/at-spi/bus_{s}", "xauthority": None}})
    return out + rows


def rows(n_pairs: int = 40, effect_ln: float = -0.10, sigma: float = 0.03, seed: int = 5,
         base_ms: float = 1500.0, phase_champion_ms: float = 241.0, phase_share: float = 1.0,
         off_effect_ln: float | None = None, soak: int = 300, spot_pairs: int = 12,
         spot_effect_ln: float = 0.0) -> list[dict[str, Any]]:
    """A complete evaluation: task pairs (20% trace off), controls, soak and spot pairs."""
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    tid = 0
    off = set(range(0, n_pairs, 5))  # 20%
    for k in range(n_pairs):
        a_ms = base_ms * math.exp(rng.gauss(0, 0.05))
        eff = off_effect_ln if (off_effect_ln is not None and k in off) else effect_ln
        c_ms = a_ms * math.exp(eff + rng.gauss(0, sigma))
        saving = a_ms - c_ms
        a_phase = phase_champion_ms
        c_phase = phase_champion_ms - phase_share * saving
        order = "AB" if k % 2 == 0 else "BA"
        arms = [("champion", a_ms, a_phase), ("candidate", c_ms, c_phase)]
        if order == "BA":
            arms.reverse()
        for pos, (arm, t, ph) in enumerate(arms):
            out.append(trial(tid, arm, "task", t, ph, trace=k not in off, pair=f"p{k}", order=order, position=pos))
            tid += 1
    for arm in ("champion", "candidate"):
        for kind in ("stale_negative", "impossible_canary"):
            out.append(trial(tid, arm, kind, None))
            tid += 1
    for _ in range(soak):
        out.append(trial(tid, "candidate", "soak", base_ms, trace=False))
        tid += 1
    for kind in ("spot_gtk3_text", "spot_browser_fill_submit"):
        for k in range(spot_pairs):
            a_ms = 3000 * math.exp(rng.gauss(0, 0.03))
            c_ms = a_ms * math.exp(spot_effect_ln + rng.gauss(0, 0.01))
            for pos, (arm, t) in enumerate([("champion", a_ms), ("candidate", c_ms)]):
                out.append(trial(tid, arm, kind, t, pair=f"{kind}-{k}", order="AB", position=pos))
                tid += 1
    return out


def build_rows(ok: bool = True) -> list[dict[str, Any]]:
    return [
        {"schema": "ar.build.v1", "kind": "build", "ok": True, "label": "x", "sha256": "0" * 64},
        {"schema": "ar.build.v1", "kind": "test", "suite": "cua-driver-core --lib", "ok": True, "passed": 817, "failed": 0},
        {"schema": "ar.build.v1", "kind": "test", "suite": "platform-linux --lib", "ok": ok, "passed": 599,
         "failed": 0 if ok else 1},
    ]


ALLOW = {"items": {"libs/cua-driver/rust/crates/platform-linux/src/input/focus_guard.rs": ["const SETTLE_WATCH"]},
         "soak_1000_files": ["libs/cua-driver/rust/crates/platform-linux/src/input/focus_guard.rs"]}
FG = "libs/cua-driver/rust/crates/platform-linux/src/input/focus_guard.rs"
MANIFEST = {"candidate_frozen": {"libs/cua-driver/rust/Cargo.lock": "a" * 64},
            "test_items": {FG: {"mod tests::fn t": "b" * 64}}}


def diff(path: str = FG, removed: str = "const SETTLE_WATCH: Duration = Duration::from_millis(220);",
         added: str = "const SETTLE_WATCH: Duration = Duration::from_millis(120);") -> str:
    return (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -40 +40 @@\n-{removed}\n+{added}\n")


def g0_inputs(**over: Any) -> dict[str, Any]:
    inp = {
        "diff": diff(),
        "itemcheck": {"schema": "ar.itemcheck.v1", "ok": True, "violations": [],
                      "files": {FG: {"changed_allowed": ["const SETTLE_WATCH"],
                                     "test_items_cand": {"mod tests::fn t": "b" * 64}}}},
        "frozen_sha256": {"libs/cua-driver/rust/Cargo.lock": "a" * 64},
        "lineage_ok": True,
    }
    inp.update(over)
    return inp
