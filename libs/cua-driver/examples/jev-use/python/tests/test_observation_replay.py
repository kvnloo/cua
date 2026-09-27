from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from observation_replay import Observation, policy_killed, replay

RECORDED_TEXT_CHANGE = Observation(
    revision="gtk-entry",
    invalidators=frozenset({"object:text-changed:insert", "object:text-changed:delete"}),
    changed=True,
    source="recorded",
)


class ObservationReplayTest(unittest.TestCase):
    def test_recorded_text_change_is_not_reused(self) -> None:
        result = replay([RECORDED_TEXT_CHANGE], "no_trusted_invalidator")
        self.assertEqual(result.skips, 0)
        self.assertEqual(result.false_reuses, 0)
        self.assertFalse(policy_killed(result))

    def test_synthetic_noop_may_skip_and_is_labeled_synthetic(self) -> None:
        first = Observation("rev-1", frozenset(), False, "synthetic")
        second = Observation("rev-1", frozenset(), False, "synthetic")
        result = replay([first, second], "no_trusted_invalidator")
        self.assertEqual(result.skips, 1)
        self.assertEqual(second.source, "synthetic")

    def test_false_reuse_kills_the_policy(self) -> None:
        quiet = Observation("rev-1", frozenset(), False, "synthetic")
        lie = Observation("rev-1", frozenset(), True, "synthetic")
        result = replay([quiet, lie], "no_trusted_invalidator")
        self.assertTrue(policy_killed(result))

    def test_always_observe_never_skips(self) -> None:
        steps = [
            Observation("rev-1", frozenset(), False, "synthetic"),
            Observation("rev-1", frozenset(), False, "synthetic"),
        ]
        self.assertEqual(replay(steps, "always").skips, 0)


if __name__ == "__main__":
    unittest.main()
