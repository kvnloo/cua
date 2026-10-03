"""B-06 per-trial extraction (standard library only). Shared by analyze_b06.py and verify_artifacts.py.

One row per trial = B-04's ``b04_rows.row`` (harness/b04/b04_rows.py, blob-identical: T_oracle, T_land, call
windows, Driver snapshot spans and sub-spans, route/forced-path receipts, E4 flags, validity) plus the
B-06 receipts:

- arm (C / Wa / Wb / P / Wn / SMOKE), plan, block, round, attempt, Williams row and position;
- process identity: Driver pid and Chrome browser pid with their /proc start times, read after the
  warm-up (warm arms) and immediately before the task navigate; ``pids_ok`` = both present and alive,
  and for warm arms identical (pid and start time) at warm-up and at task start;
- warm-up duration (``warmup_start`` -> ``warmup_end``, outside T);
- positive control: the measured CLOCK_MONOTONIC sleep inside T (``pc_sleep_ms``; arm P before snapshot1,
  arm P2 of PREREG-AMENDMENT-1 right after snapshot1 returns);
- refusal returned as success (an action call that returned ok with effect/status ``refused``).

valid = b04 validity AND pids_ok AND (arms P, P2: the sleep was measured) AND the arm's configuration
receipts (COMP: admission-cache env and >= 1 mcp.inner_validation_skipped mark, fill route 'compiled',
focus settle 0 on fill; SMOKE: no CUA_DRIVER_EXP_* and 0 skip marks: both from b04_rows).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "harness" / "b04"))
import b04_rows as B  # noqa: E402

load_dir, load_tar, windows, snap_measures, ev_first = B.load_dir, B.load_tar, B.windows, B.snap_measures, B.ev_first
WARM = {"Wa", "Wb", "P", "Wn", "P2"}  # P2: PREREG-AMENDMENT-1 block x


def _same(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    return bool(a and b and a.get("pid") == b.get("pid") and a.get("starttime") == b.get("starttime"))


def _alive(x: dict[str, Any] | None) -> bool:
    return bool(x and x.get("alive") and x.get("pid"))


def row(t: dict[str, Any]) -> dict[str, Any]:
    s = t["summary"]
    r = B.row(t)
    arm = s.get("b06_arm")
    r.update({"b06_arm": arm, "plan": s.get("probe"), "attempt": s.get("attempt"), "williams_row": s.get("williams_row"),
              "pos_in_round": s.get("pos_in_round"), "config": s.get("arm")})
    pre = s.get("pids_pretask") or {}
    wu = s.get("pids_warmup") or {}
    r["driver_pid"] = (pre.get("driver") or {}).get("pid")
    r["driver_starttime"] = (pre.get("driver") or {}).get("starttime")
    r["chrome_pid"] = (pre.get("chrome") or {}).get("pid")
    r["chrome_starttime"] = (pre.get("chrome") or {}).get("starttime")
    r["chrome_exe"] = (pre.get("chrome") or {}).get("exe")
    r["driver_exe"] = (pre.get("driver") or {}).get("exe")
    ok = _alive(pre.get("driver")) and _alive(pre.get("chrome"))
    if arm in WARM:
        ok = ok and _same(wu.get("driver"), pre.get("driver")) and _same(wu.get("chrome"), pre.get("chrome"))
        r["pids_same_warmup_task"] = _same(wu.get("driver"), pre.get("driver")) and _same(wu.get("chrome"), pre.get("chrome"))
    else:
        r["pids_same_warmup_task"] = None
    r["pids_ok"] = ok
    ws, we = ev_first(t, "warmup_start"), ev_first(t, "warmup_end")
    r["warmup_span_ms"] = (we["t_mono_ns"] - ws["t_mono_ns"]) / 1e6 if (ws and we) else (0.0 if arm not in WARM else None)
    r["pc_sleep_ms"] = s["pc_sleep_ns"] / 1e6 if s.get("pc_sleep_ns") is not None else None
    w = windows(t)
    r["refusal_as_success"] = any(x.get("ok") and (x.get("effect") == "refused" or x.get("status") == "refused")
                                  for k, x in w.items() if k.startswith("action"))
    r["valid_b04"] = r["valid"]
    r["valid"] = bool(r["valid_b04"] and ok and (arm not in ("P", "P2") or r["pc_sleep_ms"] is not None)
                      and not r["refusal_as_success"])
    r["arm_receipts_ok"] = r["arm_ok"]
    return r
