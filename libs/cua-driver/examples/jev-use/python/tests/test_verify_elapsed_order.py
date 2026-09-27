from __future__ import annotations

import unittest
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[4]
    / "rust/crates/cua-driver-core/src/expectation.rs"
)


class VerifyElapsedOrderTest(unittest.TestCase):
    def test_elapsed_ms_is_closed_before_optional_screenshot_evidence(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        elapsed = text.index("let elapsed_ms = started.elapsed()")
        screenshot = text.index("if input.include_screenshot == Some(true)")
        self.assertLess(elapsed, screenshot)

    def test_recommendation_is_verification_loop_time(self) -> None:
        # kvnloo/cua#22 option 1. Do not fold screenshot work into elapsed_ms.
        self.assertIn("verify_state: {}", SOURCE.read_text(encoding="utf-8"))

    def test_screenshot_evidence_observe_requests_no_elements(self) -> None:
        # kvnloo/cua#3 call site. This does not prove the native walker obeyed it.
        text = SOURCE.read_text(encoding="utf-8")
        start = text.index("if input.include_screenshot == Some(true)")
        window = text[start : start + 500]
        self.assertIn("observe(input.pid, input.window_id, false, true)", window)


if __name__ == "__main__":
    unittest.main()
