from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from stale_batch import Child, Target, run_batch


def children() -> list[Child]:
    return [
        Child("field", Target("id-field", "field")),
        Child("submit", Target("id-submit", "submit")),
    ]


class StaleBatchTest(unittest.TestCase):
    def test_same_identity_may_dispatch_the_second_child(self) -> None:
        world = {"field": Target("id-field", "field"), "submit": Target("id-submit", "submit")}
        trace = run_batch(children(), lambda label: world.get(label), lambda: "ok")
        self.assertEqual(trace.dispatched, ["field", "submit"])
        self.assertEqual(trace.refused, [])

    def test_disappeared_target_is_refused(self) -> None:
        world = {"field": Target("id-field", "field"), "submit": Target("id-submit", "submit")}

        def apply() -> str:
            world.pop("submit")
            return "ok"

        trace = run_batch(children(), lambda label: world.get(label), apply)
        self.assertEqual(trace.dispatched, ["field"])
        self.assertEqual(trace.refused, ["submit"])

    def test_similar_label_with_a_new_identity_is_refused(self) -> None:
        world = {"field": Target("id-field", "field"), "submit": Target("id-submit", "submit")}

        def apply() -> str:
            world["submit"] = Target("id-submit-2", "submit")
            return "ok"

        trace = run_batch(children(), lambda label: world.get(label), apply)
        self.assertEqual(trace.refused, ["submit"])
        self.assertNotIn("submit", trace.dispatched)

    def test_failed_or_unknown_first_child_never_starts_the_second(self) -> None:
        world = {"field": Target("id-field", "field"), "submit": Target("id-submit", "submit")}
        for status in ("failed", "unknown"):
            with self.subTest(status=status):
                trace = run_batch(children(), lambda label: world.get(label), lambda: status)
                self.assertEqual(trace.dispatched, ["field"])
                self.assertEqual(trace.refused, [])


if __name__ == "__main__":
    unittest.main()
