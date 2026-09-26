from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from observation import ObservationRecord
from speculate import (
    VisualSpeculator,
    discard_capture,
    start_speculative_capture,
    visual_from_capture,
)

ARGS = {"pid": 4242, "window_id": 7}


async def ok_call(name: str, args: object) -> dict:
    if name == "get_window_state":
        return {"capture_id": "cap-1"}
    if name == "parse_visual_regions":
        return {"parsed": True}
    raise AssertionError(name)


def parse_stub(wire: object, **kwargs: object) -> object:
    return {"capture_id": kwargs["expected_capture_id"]}


class VisualSpeculatorTest(unittest.TestCase):
    def test_cold_start_never_speculates(self) -> None:
        spec = VisualSpeculator(2)
        self.assertFalse(spec.should_speculate())

    def test_sticky_fires_after_one_needed_step(self) -> None:
        spec = VisualSpeculator(1)
        spec.observe(True)
        self.assertTrue(spec.should_speculate())

    def test_gate_two_requires_two_consecutive(self) -> None:
        spec = VisualSpeculator(2)
        spec.observe(True)
        self.assertFalse(spec.should_speculate())  # suppressed once
        spec.observe(True)
        self.assertTrue(spec.should_speculate())

    def test_gate_two_never_fires_on_sparse(self) -> None:
        spec = VisualSpeculator(2)
        for needed in (False, False, True, False, False, True, False):
            spec.should_speculate()
            spec.observe(needed)
        stats = spec.stats()
        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["false_positives"], 0)
        self.assertEqual(stats["misses"], 2)
        self.assertEqual(stats["suppressed"], 2)  # sticky-yes, gate said no

    def test_gate_two_never_fires_on_flicker(self) -> None:
        spec = VisualSpeculator(2)
        for step in range(10):
            spec.should_speculate()
            spec.observe(step % 2 == 0)
        self.assertEqual(spec.stats()["hits"], 0)
        self.assertEqual(spec.stats()["false_positives"], 0)

    def test_shortburst_pays_trailing_false_positive_per_run(self) -> None:
        # Runs of exactly 2 never trigger the gate in time: the decision is
        # made before the step is observed, so the fire lands one step late
        # (trailing false positive) — the documented cost of the gate.
        spec = VisualSpeculator(2)
        decisions = []
        for needed in (False, False, True, True, False, True, True, False):
            decisions.append((spec.should_speculate(), needed))
            spec.observe(needed)
        self.assertEqual(
            [d for d, _ in decisions],
            [False, False, False, False, True, False, False, True],
        )
        self.assertEqual(spec.stats()["hits"], 0)
        self.assertEqual(spec.stats()["false_positives"], 2)

    def test_stats_and_miss_rate(self) -> None:
        spec = VisualSpeculator(1)
        self.assertFalse(spec.should_speculate())  # cold start
        spec.observe(False)
        # miss
        self.assertFalse(spec.should_speculate())
        spec.observe(True)
        # hit
        self.assertTrue(spec.should_speculate())
        spec.observe(True)
        # false positive
        self.assertTrue(spec.should_speculate())
        spec.observe(False)
        self.assertEqual(
            spec.stats(),
            {"hits": 1, "false_positives": 1, "misses": 1, "suppressed": 0},
        )
        self.assertAlmostEqual(spec.miss_rate(), 0.5)

    def test_miss_rate_none_before_any_speculation(self) -> None:
        self.assertIsNone(VisualSpeculator(2).miss_rate())

    def test_confirmation_steps_clamped(self) -> None:
        self.assertEqual(VisualSpeculator(0).confirmation_steps, 1)


class CaptureHelpersTest(unittest.TestCase):
    def test_no_capture_when_not_speculating(self) -> None:
        self.assertIsNone(start_speculative_capture(ok_call, ARGS, False))

    def test_capture_returns_awaitable_when_speculating(self) -> None:
        capture = start_speculative_capture(ok_call, ARGS, True)
        self.assertIsNotNone(capture)
        assert capture is not None
        self.assertEqual(asyncio.run(capture)["capture_id"], "cap-1")

    def test_visual_from_capture_parses(self) -> None:
        async def main() -> object:
            capture = start_speculative_capture(ok_call, ARGS, True)
            assert capture is not None
            return await visual_from_capture(capture, ok_call, ARGS, parse_stub)

        self.assertEqual(
            asyncio.run(main()), {"capture_id": "cap-1"}
        )

    def test_visual_from_capture_raises_without_capture_id(self) -> None:
        async def bad_call(name: str, args: object) -> dict:
            return {}

        async def main() -> None:
            capture = start_speculative_capture(bad_call, ARGS, True)
            assert capture is not None
            await visual_from_capture(capture, bad_call, ARGS, parse_stub)

        with self.assertRaises(ValueError):
            asyncio.run(main())

    def test_discard_swallow_failure(self) -> None:
        async def failing_call(name: str, args: object) -> dict:
            raise RuntimeError("boom")

        async def main() -> None:
            capture = start_speculative_capture(failing_call, ARGS, True)
            await discard_capture(capture)

        asyncio.run(main())  # must not raise

    def test_discard_none_is_noop(self) -> None:
        asyncio.run(discard_capture(None))


class DiscardedRecordTest(unittest.TestCase):
    def test_discarded_defaults_false(self) -> None:
        record = ObservationRecord(step=1, kind="visual", latency_ms=0.0)
        self.assertFalse(record.discarded)

    def test_discarded_records_spend_not_evidence(self) -> None:
        record = ObservationRecord(
            step=2, kind="visual", latency_ms=0.0, discarded=True
        )
        self.assertTrue(record.discarded)
        self.assertIsNone(record.capture_id)


if __name__ == "__main__":
    unittest.main()
