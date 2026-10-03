"""RECERT-BUG01 part B: harness/probe_sessions.py (copied unchanged from BUG-01) plus an
independent CDP observer (cdp_observer.py). Measurement only.

The BUG-01 probe is imported unchanged; only its module-level `Probe` name is
replaced by a subclass that (1) opens the observer's own browser-level CDP
connection right after browser_prepare returns the browser pid, and (2) takes an
observer sample immediately BEFORE every navigation probe, i.e. before measured
call 1, 101, 201 and 301 of a 300-call long session (k = 0, 100, 200, 300).
Samples go to <out>/observer.jsonl, one JSON line each, keyed by the Driver
session label (calls.jsonl block rows map label -> series).

usage: probe_sessions_observed.py --out <dir> [--series L] [--long-calls 300] [--label measured]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "harness"))
sys.path.insert(0, str(HERE))

import probe_sessions  # noqa: E402  (harness, blob-identical to BUG-01)
from bug01_common import Probe, sanitize  # noqa: E402
from cdp_observer import Observer  # noqa: E402

OUT: dict[str, Path] = {}
LONG_CALLS: dict[str, int] = {"n": 300}


class ObservedProbe(Probe):
    def __init__(self, session: Any, label: str) -> None:
        super().__init__(session, label)
        self.observer: Observer | None = None
        self.measured_calls = 0
        self.setup_nav_done = False
        self.samples = 0

    def _emit(self, row: dict[str, Any]) -> None:
        with (OUT["dir"] / "observer.jsonl").open("a") as fh:
            fh.write(json.dumps(sanitize(row), sort_keys=True) + "\n")

    def _sample(self, tag: str) -> None:
        row: dict[str, Any] = {"event": "observer_sample", "label": self.label, "tag": tag, "measured_calls_done": self.measured_calls, "sample_no": self.samples}
        try:
            row.update(self.observer.sample() if self.observer else {"error": "no observer"})
        except Exception as exc:  # keep failures in the record
            row["error"] = f"{type(exc).__name__}: {exc}"
        self.samples += 1
        self._emit(row)

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "browser_navigate" and self.setup_nav_done:
            self._sample("before_nav_probe")
        r = await super().call(name, args)
        if name == "browser_prepare":
            try:
                pid = int((r.get("structured") or {})["prepared_pid"])
                self.observer = Observer(pid)
                self._emit({"event": "observer_connected", "label": self.label, "t_ms": time.time() * 1000})
                self._sample("after_prepare")
            except Exception as exc:  # noqa: BLE001
                self._emit({"event": "observer_connect_error", "label": self.label, "error": f"{type(exc).__name__}: {exc}"})
        elif name == "browser_navigate" and not self.setup_nav_done:
            self.setup_nav_done = True
        elif name == "browser_navigate" and self.measured_calls == LONG_CALLS["n"]:
            # The BUG-01 probe ends a long session with its last navigation probe, so no call
            # observes the post-navigation burst at call 301. Add exactly one trailing
            # semantic snapshot (not counted as a measured call) for B2 at 301.
            await asyncio.sleep(0.5)
            tail = await super().call("get_browser_state", {"target_id": args["target_id"], "tab_id": args["tab_id"], "snapshot_format": "semantic_v2"})
            self._emit({"event": "post_final_nav_call", "label": self.label, "tool": "get_browser_state", "t_start_ms": tail.get("t_start_ms"), "t_end_ms": tail.get("t_end_ms"), "accepted": tail.get("accepted"), "is_error": tail.get("is_error"), "refusal": tail.get("refusal")})
        elif name in ("get_browser_state", "browser_click") and "tab_id" in args and self.setup_nav_done:
            self.measured_calls += 1
        return r


def main() -> None:
    out_idx = sys.argv.index("--out") + 1
    OUT["dir"] = Path(sys.argv[out_idx])
    if "--long-calls" in sys.argv:
        LONG_CALLS["n"] = int(sys.argv[sys.argv.index("--long-calls") + 1])
    probe_sessions.Probe = ObservedProbe  # the only change to the BUG-01 probe's behaviour
    probe_sessions.main()


if __name__ == "__main__":
    main()
