"""Benchmark: modality-gated observation in the jev-use Python recipe loop.

Mirrors bench/observation-gating/bench.ts: baseline (visual observation on
every step) vs gated (visual only when the snapshot yields no actionable
candidate). Fake driver with virtual latencies — what is MEASURED is the
policy's call pattern; wall-clock savings are eliminated-calls x per-call
cost. Gate-predicate CPU overhead is measured separately with real timers.

Run: python3 bench_observation_gating.py (from the python/ directory)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import build_candidates, choose_mock
from observation import ObservationLedger, ObservationRecord, needs_visual_observation

DEFAULT_LATENCY = {
    "get_browser_state": 180,
    "get_window_state": 220,
    "parse_visual_regions": 640,
    "browser_type": 300,
    "browser_click": 150,
}

TOKEN = "bench-token"
PID = 4242
WINDOW_ID = 7
OBSERVATION_TOOLS = {"get_browser_state", "get_window_state", "parse_visual_regions"}


class FakeDriver:
    def __init__(self, latency: dict[str, int], scenario: str) -> None:
        self.latency = latency
        self.scenario = scenario
        self.calls: list[tuple[str, int]] = []
        self.field_value = "other"
        self.submitted: str | None = None

    def call(self, name: str, args: dict) -> dict:
        latency_ms = self.latency.get(name, 0)
        self.calls.append((name, latency_ms))
        if name == "get_browser_state":
            refs: list[dict] = [
                {
                    "role": "textbox",
                    "name": "verification value",
                    "ref": "r1",
                    "value": self.field_value,
                }
            ]
            if self.scenario == "dom-complete":
                refs.append({"role": "button", "name": "Submit", "ref": "r2"})
            return {"target_id": "t", "tab_id": "tab", "refs": refs}
        if name == "get_window_state":
            return {"capture_id": f"cap-{len(self.calls)}"}
        if name == "parse_visual_regions":
            return {
                "schema": "cua.visual_regions_v1",
                "capture": {
                    "capture_id": str(args["capture_id"]),
                    "source": {"kind": "window", "pid": PID, "window_id": WINDOW_ID},
                    "screenshot": {
                        "mime_type": "image/png",
                        "reference": "shot-1",
                        "width": 1280,
                        "height": 800,
                    },
                    "action_coordinate_space": {"kind": "screenshot_pixels"},
                },
                "regions": [
                    {
                        "id": "v1",
                        "kind": "text",
                        "text": "Submit",
                        "confidence": 0.9,
                        "interactive": True,
                        "bounds": {"x": 100, "y": 100, "width": 80, "height": 30},
                    }
                ],
            }
        if name == "browser_type":
            self.field_value = str(args["text"])
            return {"ok": True}
        if name in {"browser_click", "click"}:
            self.submitted = self.field_value
            return {"ok": True}
        raise AssertionError(f"unexpected tool: {name}")

    def observation_latency(self) -> int:
        return sum(ms for name, ms in self.calls if name in OBSERVATION_TOOLS)

    def observation_calls(self) -> int:
        return sum(1 for name, _ in self.calls if name in OBSERVATION_TOOLS)


def run_task(
    policy: str, scenario: str, latency: dict[str, int], max_steps: int = 4
) -> tuple[bool, FakeDriver, ObservationLedger]:
    driver = FakeDriver(latency, scenario)
    ledger = ObservationLedger()
    for step in range(1, max_steps + 1):
        if driver.submitted == TOKEN:
            return True, driver, ledger
        snapshot = driver.call(
            "get_browser_state",
            {"target_id": "t", "tab_id": "tab", "snapshot_format": "semantic_v2"},
        )
        ledger.record(
            ObservationRecord(
                step=step, kind="snapshot", latency_ms=latency["get_browser_state"]
            )
        )
        candidates = build_candidates(snapshot, TOKEN, None, capture_bound_click=True)
        if policy == "baseline" or needs_visual_observation(candidates):
            capture = driver.call(
                "get_window_state", {"pid": PID, "window_id": WINDOW_ID}
            )
            driver.call(
                "parse_visual_regions",
                {
                    "capture_id": capture["capture_id"],
                    "options": {
                        "kinds": ["text", "icon"],
                        "min_confidence": 0.8,
                        "max_regions": 100,
                    },
                },
            )
            ledger.record(
                ObservationRecord(
                    step=step,
                    kind="visual",
                    latency_ms=latency["get_window_state"]
                    + latency["parse_visual_regions"],
                    capture_id=capture["capture_id"],
                )
            )
            # Rebuild with visual for the fallback (visual payload shape is
            # fixed here; build_candidates only needs the fallback branch).
            from core import parse_visual_regions as parse_wire

            visual = parse_wire(
                {
                    "schema": "cua.visual_regions_v1",
                    "capture": {
                        "capture_id": capture["capture_id"],
                        "source": {"kind": "window", "pid": PID, "window_id": WINDOW_ID},
                        "screenshot": {
                            "mime_type": "image/png",
                            "reference": "shot-1",
                            "width": 1280,
                            "height": 800,
                        },
                        "action_coordinate_space": {"kind": "screenshot_pixels"},
                    },
                    "regions": [
                        {
                            "id": "v1",
                            "kind": "text",
                            "text": "Submit",
                            "confidence": 0.9,
                            "interactive": True,
                            "bounds": {"x": 100, "y": 100, "width": 80, "height": 30},
                        }
                    ],
                },
                expected_capture_id=capture["capture_id"],
                expected_pid=PID,
                expected_window_id=WINDOW_ID,
            )
            candidates = build_candidates(
                snapshot, TOKEN, visual, capture_bound_click=True
            )
        choice, _, _ = choose_mock(candidates)
        if choice in (None, "abstain", "reobserve"):
            return False, driver, ledger
        candidate = next(item for item in candidates if item.id == choice)
        if candidate.tool is None:
            return False, driver, ledger
        driver.call(candidate.tool, dict(candidate.arguments))
    return driver.submitted == TOKEN, driver, ledger


def measure_gate_overhead() -> float:
    snapshot = {
        "target_id": "t",
        "tab_id": "tab",
        "refs": [
            {
                "role": "textbox",
                "name": "verification value",
                "ref": "r1",
                "value": "other",
            }
        ],
    }
    candidates = build_candidates(snapshot, TOKEN, None, capture_bound_click=True)
    iterations = 200_000
    started = time.perf_counter()
    for _ in range(iterations):
        needs_visual_observation(candidates)
    return (time.perf_counter() - started) / iterations * 1e9


def main() -> None:
    rows = []
    for scenario in ("dom-complete", "visual-fallback"):
        for policy in ("baseline", "gated"):
            verified, driver, ledger = run_task(policy, scenario, DEFAULT_LATENCY)
            if not verified:
                raise AssertionError(f"{policy}/{scenario} did not verify")
            rows.append(
                {
                    "scenario": scenario,
                    "policy": policy,
                    "observation_calls": driver.observation_calls(),
                    "visual_observations": ledger.count("visual"),
                    "observation_ms_virtual": driver.observation_latency(),
                }
            )
    print(
        json.dumps(
            {
                "latencies_ms": DEFAULT_LATENCY,
                "rows": rows,
                "gate_overhead_ns": round(measure_gate_overhead()),
            },
            indent=2,
        )
    )
    print("--- sensitivity (saved observation ms per task vs visual-path cost) ---")
    for visual_ms in (200, 860, 2000):
        latency = {
            **DEFAULT_LATENCY,
            "get_window_state": round(visual_ms * 0.26),
            "parse_visual_regions": round(visual_ms * 0.74),
        }
        parts = []
        for scenario in ("dom-complete", "visual-fallback"):
            _, base, _ = run_task("baseline", scenario, latency)
            _, gated, _ = run_task("gated", scenario, latency)
            parts.append(
                f"{scenario}: {base.observation_latency() - gated.observation_latency()}ms"
            )
        print(f"visual_path={visual_ms}ms -> {', '.join(parts)}")


if __name__ == "__main__":
    main()
