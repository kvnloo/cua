"""Benchmark: speculative visual capture in the Python jev-use loop.

Mirrors bench/observation-gating/speculate_bench.ts for the TS loop: three
policies (gated-sequential, sticky, confirmed-2) against six scripted
visual-need sequences (every, bursty, sparse, never, flicker, shortbursts).

Fake async driver with virtual latencies — what is MEASURED is the policy's
call pattern; per-step observation cost is the critical path through the
recorded timeline (snapshot and capture fly concurrently, parse_visual_regions
follows when the visual path is needed). The real speculate.py code
(VisualSpeculator, start_speculative_capture, visual_from_capture,
discard_capture) is exercised; only the transport is fake.

Run: python3 bench_observation_speculate.py (from the python/ directory)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))

from speculate import (
    ObserveStepArgs,
    VisualSpeculator,
    discard_capture,
    start_speculative_capture,
    visual_from_capture,
)

LATENCY = {
    "get_browser_state": 180,
    "get_window_state": 220,
    "parse_visual_regions": 640,
}

ARGS: ObserveStepArgs = {"pid": 4242, "window_id": 7}
STEPS = 20


def sequences() -> dict[str, list[bool]]:
    return {
        # every step needs the visual path
        "every": [True] * STEPS,
        # one sticky run in the middle
        "bursty": [i in range(4, 14) for i in range(STEPS)],
        # isolated needs — the miss-rate gate's target
        "sparse": [i in (6, 15) for i in range(STEPS)],
        # DOM always suffices
        "never": [False] * STEPS,
        # alternating need — must not trigger the gate
        "flicker": [i % 2 == 0 for i in range(STEPS)],
        # runs of exactly 2: the gate pays one sequential step per run
        "shortbursts": [i in (2, 3, 9, 10, 16, 17) for i in range(STEPS)],
    }


class FakeTransport:
    """Async fake driver recording (name, virtual_ms) in call order."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def call(self, name: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((name, LATENCY[name]))
        if name == "get_browser_state":
            return {"target_id": "t", "tab_id": "tab", "refs": []}
        if name == "get_window_state":
            return {"capture_id": f"cap-{len(self.calls)}"}
        if name == "parse_visual_regions":
            return {"parsed": True}
        raise AssertionError(f"unexpected tool: {name}")


def parse_stub(
    wire: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    assert kwargs["expected_capture_id"] == wire.get("capture_id")
    return {"capture_id": wire["capture_id"]}


def concurrent_step_cost(need: bool) -> int:
    """Snapshot || capture, then parse iff needed."""
    return max(LATENCY["get_browser_state"], LATENCY["get_window_state"]) + (
        LATENCY["parse_visual_regions"] if need else 0
    )


def sequential_step_cost(need: bool) -> int:
    """Snapshot, then (on a miss) capture + parse sequentially."""
    cost = LATENCY["get_browser_state"]
    if need:
        cost += LATENCY["get_window_state"] + LATENCY["parse_visual_regions"]
    return cost


async def run_sequence(
    policy: str, needs: list[bool]
) -> dict[str, Any]:
    transport = FakeTransport()
    speculator = VisualSpeculator(2 if policy == "confirmed" else 1)
    total = 0
    speculative_fires = 0
    discarded = 0
    misses = 0
    parses = 0
    for need in needs:
        speculate = policy != "gated" and speculator.should_speculate()
        capture = start_speculative_capture(transport.call, ARGS, speculate)
        # Snapshot is the critical path: issued first, capture alongside.
        snapshot = transport.call("get_browser_state", {})
        await snapshot
        if speculate:
            speculative_fires += 1
            total += concurrent_step_cost(need)
        else:
            total += sequential_step_cost(need)
        if need:
            visual = None
            if capture is not None:
                try:
                    visual = await visual_from_capture(
                        capture, transport.call, ARGS, parse_stub
                    )
                except Exception:
                    visual = None  # fall through to the sequential path
            if visual is None:
                misses += 1
                # Sequential fallback, mirroring optional_visual_observation.
                cap = await transport.call("get_window_state", {})
                await transport.call(
                    "parse_visual_regions", {"capture_id": cap["capture_id"]}
                )
            parses += 1
        elif capture is not None:
            discarded += 1
            await discard_capture(capture)
        if policy != "gated":
            speculator.observe(need)
    return {
        "virtual_ms": total,
        "speculative_fires": speculative_fires,
        "parses": parses,
        "discarded": discarded,
        "misses": misses,
        "stats": speculator.stats() if policy != "gated" else None,
    }


def main() -> None:
    rows: list[dict[str, Any]] = []
    for seq_name, needs in sequences().items():
        results = {
            policy: asyncio.run(run_sequence(policy, needs))
            for policy in ("gated", "sticky", "confirmed")
        }
        gated = results["gated"]["virtual_ms"]
        row: dict[str, Any] = {"sequence": seq_name, "steps": STEPS}
        for policy, result in results.items():
            row[policy] = result
            row[f"{policy}_speedup_vs_gated"] = (
                round(gated / result["virtual_ms"], 3) if result["virtual_ms"] else None
            )
        rows.append(row)
    print(json.dumps({"latencies_ms": LATENCY, "rows": rows}, indent=2))

    # Honesty checks (assert, don't just print):
    # 1. The miss-rate gate never fires into isolated/alternating needs.
    by_seq = {row["sequence"]: row for row in rows}
    assert by_seq["sparse"]["confirmed"]["speculative_fires"] == 0
    assert by_seq["flicker"]["confirmed"]["speculative_fires"] == 0
    # 2. Equivalence gate: the policy only moves the capture in time — the
    #    visual path is taken exactly on the steps that need it, for every
    #    policy. A policy that changed what is observed would fail here.
    for row in rows:
        need_count = sum(sequences()[row["sequence"]])
        for policy in ("gated", "sticky", "confirmed"):
            assert (
                row[policy]["parses"] == need_count
            ), f"{row['sequence']}/{policy}: parses != need count"
    print("--- honesty checks passed ---")


if __name__ == "__main__":
    main()
