from __future__ import annotations

import unittest


def window_ready(windows: list[dict], *, visual_changed: bool) -> bool:
    """Readiness for jev-use's browser window. A frame change is not proof."""
    del visual_changed
    return any(window.get("is_on_screen") for window in windows)


class WindowReadyTest(unittest.TestCase):
    def test_visible_window_is_ready(self) -> None:
        self.assertTrue(window_ready([{"is_on_screen": True, "bounds": {"width": 10, "height": 10}}], visual_changed=False))

    def test_unrelated_visual_change_is_not_readiness(self) -> None:
        self.assertFalse(window_ready([{"is_on_screen": False}], visual_changed=True))


if __name__ == "__main__":
    unittest.main()
