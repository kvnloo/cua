"""Pin the production agent-seat global lifetime to lane claims.

This is structural policy coverage. Native Wayland evidence still belongs to the
live Hyprland qualification lane.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/input_experiment.cpp"


def method(source: str, name: str) -> str:
    match = re.search(r"^    [^\n]*\b" + re.escape(name) + r"\([^\n]*\).*?^    }", source, re.M | re.S)
    if not match:
        raise AssertionError(f"production method not found: {name}")
    return match.group()


class AgentSeatLifetimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text()

    def test_global_is_created_only_for_a_lane_claim(self):
        start = method(self.source, "start")
        publish = method(self.source, "publish_seat_global")
        request = method(self.source, "request")

        self.assertNotIn("wl_global_create", start)
        self.assertEqual(self.source.count("wl_global_create("), 1)
        self.assertIn("wl_global_create(", publish)
        claim = request.index('command == "CLAIM"')
        publish_call = request.index("publish_seat_global()", claim)
        reserve = request.index("reservation = &c", claim)
        self.assertLess(publish_call, reserve)

    def test_design_never_replaces_hyprland_global_filter(self):
        self.assertNotIn("wl_display_set_global_filter", self.source)
        self.assertNotIn("/proc/", self.source)

    def test_withdrawal_is_generation_scoped_and_inert(self):
        withdraw = method(self.source, "withdraw_seat_global")
        bind = method(self.source, "bind_seat")
        self.assertIn("seat->generation == generation", withdraw)
        self.assertIn("sendCapabilities", withdraw)
        self.assertIn("wl_global_remove", withdraw)
        self.assertIn("retired_globals.push_back", withdraw)
        self.assertIn("epoch.generation", bind)
        self.assertIn("seat_generation_is_active", bind)
        self.assertIn("WL_SEAT_CAPABILITY_POINTER", bind)

    def test_safe_wayland_126_withdrawal_ack_is_used_when_available(self):
        self.assertIn("wl_global_set_withdrawn_listener", self.source)
        callback = method(self.source, "global_withdrawn")
        self.assertIn("wl_global_destroy", callback)
        self.assertIn("wl_global_get_user_data", callback)

    def test_target_binding_is_checked_before_grant_consumption(self):
        request = method(self.source, "request")
        key = request.index('if (command == "KEY")')
        key_bound = request.index("keyboard_bound(c)", key)
        key_consume = request.index("consume_grant(c, cap)", key)
        self.assertLess(key_bound, key_consume)

        click = request.index('if (command == "CLICK")', key_consume)
        click_bound = request.index("pointer_bound(c)", click)
        click_consume = request.index("consume_grant(c, cap)", click)
        self.assertLess(click_bound, click_consume)

        scroll = request.index('command == "SCROLL"', click_consume)
        scroll_bound = request.index("pointer_bound(c)", scroll)
        scroll_consume = request.index("consume_grant(c, cap)", scroll)
        self.assertLess(scroll_bound, scroll_consume)

        drag_bound = request.index("pointer_bound(c)", scroll_consume + 1)
        drag_consume = request.index("consume_grant(c, cap)", scroll_consume + 1)
        self.assertLess(drag_bound, drag_consume)

    def test_old_generations_cannot_receive_input(self):
        for name in ("pointer_enter", "button", "keyboard_enter", "key"):
            self.assertIn("seat_generation_is_active", method(self.source, name), name)

    def test_status_preserves_old_proof_identity_and_names_new_visibility_lifetime(self):
        status = self.source[self.source.index("std::string InputExperiment::status_json() const"):]
        self.assertIn('"seat_lifetime":"compositor"', status)
        self.assertIn('"seat_global_lifetime":"lane_claim"', status)
        self.assertIn("active_seat_resources()", status)
        self.assertIn("active_pointer_resources()", status)
        self.assertIn("active_keyboard_resources()", status)


if __name__ == "__main__":
    unittest.main()
