"""Unit tests for the R2-07c toggle/modal compiled routine (UNIT evidence; no Driver, no browser).

run (under hostless): <jev-use>/.venv/bin/python -m unittest discover -s <packet>/harness \
    -p 'test_compiled_routine_tm.py' -v
"""

from __future__ import annotations

import asyncio
import copy
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "src" / "r2-10-composition-2026-10-02" / "harness" / "src" / "r2-07-2026-10-02"
                                / "harness")]

import compiled_routine as cr  # noqa: E402
import compiled_routine_tm as crt  # noqa: E402

TOGGLE_URL = "http://127.0.0.1:4321/toggle-confirm"
MODAL_URL = "http://127.0.0.1:4321/modal"


def toggle_artifact() -> dict:
    return {
        "schema": crt.SCHEMA, "routine_id": "r2-07c-toggle-unit", "task_class": "toggle_confirm",
        "steps": [
            {"logical_target": {"role": "checkbox", "name": "feature"}, "action": "browser_click",
             "input_route": "dom_event",
             "precondition": {"unique": True, "page_origin": cr.LOOPBACK_ORIGIN_PATTERN, "page_path": "/toggle-confirm",
                              "checked_state": "false", "requires_present": [{"role": "button", "name": "Confirm"}]},
             "postcondition": {"checked_state": "true"}},
            {"logical_target": {"role": "button", "name": "Confirm"}, "action": "browser_click",
             "input_route": "dom_event", "precondition": {"unique": True}, "depends_on": 0},
        ],
        "expected_outcome": {"oracle": "/state.checked == true", "journal_updates": 1, "completion_field": "checked"},
        "fallback_points": ["before each mutation: guarded continuation from the current state"],
    }


def modal_artifact() -> dict:
    return {
        "schema": crt.SCHEMA, "routine_id": "r2-07c-modal-unit", "task_class": "modal_act",
        "steps": [
            {"logical_target": {"role": "button", "name": "Open dialog"}, "action": "browser_click",
             "input_route": "dom_event",
             "precondition": {"unique": True, "page_origin": cr.LOOPBACK_ORIGIN_PATTERN, "page_path": "/modal",
                              "requires_absent": [{"role": "button", "name": "Confirm choice"}]},
             "postcondition": {"requires_present": [{"role": "button", "name": "Confirm choice"}]}},
            {"logical_target": {"role": "button", "name": "Confirm choice"}, "action": "browser_click",
             "input_route": "dom_event", "precondition": {"unique": True}, "depends_on": 0},
        ],
        "expected_outcome": {"oracle": "/state.opened == true and /state.modal == true", "journal_updates": 1,
                             "completion_field": "modal"},
        "fallback_points": ["before each mutation: guarded continuation from the current state"],
    }


class FakePage:
    """Scripted #24 page behind a fake Driver: every observation mints new refs p<n>:<i>."""

    def __init__(self, cls: str, *, checked=False, opened=False, confirms=1, url=None, click_script=None,
                 dialog_after_first=False):
        self.cls, self.checked, self.opened, self.confirms = cls, checked, opened, confirms
        self.url = url or (TOGGLE_URL if cls == "toggle" else MODAL_URL)
        self.n = 0
        self.calls: list[tuple[str, dict]] = []
        self.click_script = list(click_script or [])
        self.state = {"checked": None, "opened": opened, "modal": False}
        self.refs: dict[str, str] = {}
        self.dialog = False
        self.dialog_after_first = dialog_after_first
        self.clicked: list[str] = []

    def snapshot(self) -> dict:
        self.n += 1
        refs, self.refs = [], {}

        def add(role, name, key, states=None):
            ref = f"p{self.n}:{len(refs)}"
            self.refs[ref] = key
            refs.append({"ref": ref, "role": role, "name": name, "actions": ["click"], "states": states or {}})

        if self.dialog:
            add("button", "Stay signed in", "stay")
        elif self.url.endswith("/toggle-confirm"):
            add("checkbox", "feature", "box", {"checked": "true" if self.checked else "false"})
            for _ in range(self.confirms):
                add("button", "Confirm", "confirm")
        elif self.url.endswith("/modal"):
            add("button", "Open dialog", "open")
            if self.opened:
                for _ in range(self.confirms):
                    add("button", "Confirm choice", "ok")
        else:
            refs.append({"ref": f"p{self.n}:9", "role": "textbox", "name": "verification value", "actions": ["type"]})
            refs.append({"ref": f"p{self.n}:8", "role": "button", "name": "Submit", "actions": ["click"]})
        return {"snapshot": {"id": f"p{self.n}"}, "page": {"url": self.url}, "refs": refs,
                "target_id": "bt-x", "tab_id": "tab-x"}

    async def call(self, name, args):
        self.calls.append((name, dict(args)))
        if name == "get_browser_state":
            return self.snapshot()
        assert name == "browser_click", name
        assert args["ref"].startswith(f"p{self.n}:"), "dispatched a ref not from the latest observation"
        step = self.click_script.pop(0) if self.click_script else "ok"
        key = self.refs[args["ref"]]
        self.clicked.append(key)
        if step == "stale":
            return {"status": "ok", "effect": "refused", "summary": "refused (browser_ref_stale): node detached"}
        if step in ("transport_landed", "ok"):
            self.apply(key)
        if step.startswith("transport"):
            raise ConnectionResetError("connection closed")
        return {"status": "ok", "effect": "unverifiable", "route": "dom"}

    def apply(self, key):
        if key == "box":
            self.checked = not self.checked
            if self.dialog_after_first:
                self.dialog = True
        elif key == "confirm":
            self.state["checked"] = self.checked
        elif key == "open":
            self.opened = True
            self.state["opened"] = True
            if self.dialog_after_first:
                self.dialog = True
        elif key == "ok":
            self.state["modal"] = True


def ctx_for(page: FakePage) -> cr.ReplayContext:
    return cr.ReplayContext(driver=page, target_id="bt-x", tab_id="tab-x", pid=1, window_id=2, fixture_url=page.url,
                            token="t", read_oracle=lambda: dict(page.state))


def replay(art, page, fallback=None):
    routine = crt.RoutineTM(art, fallback=fallback)
    routine.RECONCILE_DEADLINE_S = 0.2
    routine.VERIFY_DEADLINE_S = 0.2
    rec = cr.ReplayRecord()
    asyncio.run(routine.replay(ctx_for(page), rec))
    return rec


def clicks(page):
    return list(page.clicked)


class AuthorityTests(unittest.TestCase):
    def test_clean_artifacts_pass(self):
        self.assertEqual(crt.check_artifact_authority_tm(toggle_artifact()), [])
        self.assertEqual(crt.check_artifact_authority_tm(modal_artifact()), [])

    def test_rejects_every_authority_field_anywhere(self):
        keys = {"ref": "p3:1", "element_token": "et-abcdef123", "capture_id": "c1", "target_id": "bt-1234567890",
                "tab_id": "tab-1234567890", "session": "jev-python-abcd1234", "session_epoch": 3, "generation": 2,
                "backend_node_id": 17, "x": 100, "y": 200, "coordinates": [1, 2], "bounds": {"w": 1}, "pid": 42,
                "window_id": 42, "snapshot_id": "p3", "frame_id": "f", "continuation": "bc-1"}
        for where in ("step", "precondition", "postcondition", "requires_present", "top"):
            for key, value in keys.items():
                with self.subTest(where=where, key=key):
                    art = toggle_artifact()
                    if where == "step":
                        art["steps"][1][key] = value
                    elif where == "precondition":
                        art["steps"][0]["precondition"][key] = value
                    elif where == "postcondition":
                        art["steps"][0]["postcondition"][key] = value
                    elif where == "requires_present":
                        art["steps"][0]["precondition"]["requires_present"][0][key] = value
                    else:
                        art[key] = value
                    self.assertTrue(crt.check_artifact_authority_tm(art))
                    with self.assertRaises(cr.ArtifactAuthorityError):
                        crt.RoutineTM(art)

    def test_rejects_authority_smuggled_as_values_and_floats(self):
        for value in ("p12:3", "bt-0123456789ab", "tab-0123456789ab", "jev-python-0a1b2c3d",
                      "123e4567-e89b-12d3-a456-426614174000"):
            with self.subTest(value):
                art = modal_artifact()
                art["steps"][0]["precondition"]["requires_absent"][0]["name"] = value
                self.assertTrue(crt.check_artifact_authority_tm(art))
        art = toggle_artifact()
        art["steps"][0]["precondition"]["unique"] = 1.0
        self.assertTrue(crt.check_artifact_authority_tm(art))
        art = toggle_artifact()
        art["steps"][0]["precondition"]["page_path"] = "http://127.0.0.1:4321/toggle-confirm"
        self.assertTrue(crt.check_artifact_authority_tm(art))
        art = toggle_artifact()
        art["steps"][0]["precondition"]["checked_state"] = "maybe"
        self.assertTrue(crt.check_artifact_authority_tm(art))

    def test_fill_artifact_is_not_a_toggle_modal_artifact(self):
        art = toggle_artifact()
        art["task_class"] = "fill_submit"
        self.assertTrue(crt.check_artifact_authority_tm(art))


class CompileTests(unittest.TestCase):
    @staticmethod
    def obs(n, entries, url=TOGGLE_URL):
        return {"kind": "driver_call", "ok": True, "tool": "get_browser_state", "arg_snapshot_format": "semantic_v2",
                "page_url": url, "refs_logical": [{"ref": f"p{n}:{i}", "role": r, "name": nm, "value_state": "empty",
                                                   "checked_state": cs} for i, (r, nm, cs) in enumerate(entries)]}

    @staticmethod
    def click(ref):
        return {"kind": "driver_call", "ok": True, "tool": "browser_click", "arg_ref": ref, "arg_input_route": "dom_event"}

    def toggle_trace(self, dup=False):
        o1 = [("checkbox", "feature", "false"), ("button", "Confirm", "false")]
        o2 = [("checkbox", "feature", "true"), ("button", "Confirm", "false")]
        if dup:
            o1.append(("button", "Confirm", "false"))
        return [{"kind": "provider_response", "ok": True}, self.obs(1, o1), self.click("p1:0"),
                {"kind": "provider_response", "ok": True}, self.obs(2, o2), self.click("p2:1")]

    def modal_trace(self):
        o1 = [("button", "Open dialog", "false")]
        o2 = [("button", "Open dialog", "false"), ("button", "Confirm choice", "false")]
        return [{"kind": "provider_response", "ok": True}, self.obs(1, o1, MODAL_URL), self.click("p1:0"),
                {"kind": "provider_response", "ok": True}, self.obs(2, o2, MODAL_URL), self.click("p2:1")]

    def test_compiles_toggle_preconditions_from_the_trace(self):
        art = crt.compile_trace_tm(self.toggle_trace(), learning_verified=True, routine_id="r", task_class="toggle_confirm")
        self.assertEqual(crt.check_artifact_authority_tm(art), [])
        s0, s1 = art["steps"]
        self.assertEqual(s0["precondition"]["checked_state"], "false")
        self.assertEqual(s0["precondition"]["requires_present"], [{"role": "button", "name": "Confirm"}])
        self.assertEqual(s0["precondition"]["page_path"], "/toggle-confirm")
        self.assertEqual(s0["postcondition"], {"checked_state": "true"})
        self.assertEqual(s1["depends_on"], 0)
        self.assertNotIn("p1:0", crt.dumps(art))
        self.assertEqual(art["compiled_from"]["learning_provider_decisions"], 2)

    def test_compiles_modal_preconditions_from_the_trace(self):
        art = crt.compile_trace_tm(self.modal_trace(), learning_verified=True, routine_id="r", task_class="modal_act")
        s0 = art["steps"][0]
        self.assertEqual(s0["precondition"]["requires_absent"], [{"role": "button", "name": "Confirm choice"}])
        self.assertEqual(s0["postcondition"], {"requires_present": [{"role": "button", "name": "Confirm choice"}]})
        self.assertNotIn("checked_state", s0["precondition"])

    def test_refuses_unverified_ambiguous_and_wrong_shapes(self):
        with self.assertRaises(cr.CompileError):
            crt.compile_trace_tm(self.toggle_trace(), learning_verified=False, routine_id="r", task_class="toggle_confirm")
        with self.assertRaises(cr.CompileError):
            crt.compile_trace_tm(self.toggle_trace(dup=True), learning_verified=True, routine_id="r",
                                 task_class="toggle_confirm")
        three = self.toggle_trace() + [self.obs(3, [("button", "Confirm", "false")]), self.click("p3:0")]
        with self.assertRaises(cr.CompileError):
            crt.compile_trace_tm(three, learning_verified=True, routine_id="r", task_class="toggle_confirm")
        reused = self.toggle_trace()
        del reused[4]  # second click reuses the first observation: not fresh
        with self.assertRaises(cr.CompileError):
            crt.compile_trace_tm(reused, learning_verified=True, routine_id="r", task_class="toggle_confirm")
        typed = self.toggle_trace()
        typed[2] = {**typed[2], "tool": "browser_type"}
        with self.assertRaises(cr.CompileError):
            crt.compile_trace_tm(typed, learning_verified=True, routine_id="r", task_class="toggle_confirm")


class ReplayTests(unittest.TestCase):
    def test_toggle_happy_path_binds_fresh_before_every_click(self):
        page = FakePage("toggle")
        rec = replay(toggle_artifact(), page)
        self.assertEqual(rec.outcome, "verified")
        self.assertEqual([c[0] for c in page.calls], ["get_browser_state", "browser_click", "get_browser_state",
                                                      "browser_click"])
        self.assertTrue(all(m["fresh"] for m in rec.mutations))
        self.assertEqual(rec.provider_decisions, 0)

    def test_modal_happy_path(self):
        page = FakePage("modal")
        rec = replay(modal_artifact(), page)
        self.assertEqual(rec.outcome, "verified")
        self.assertEqual(clicks(page), ["open", "ok"])

    def test_already_checked_falls_back_without_touching_the_checkbox(self):
        page = FakePage("toggle", checked=True)
        seen = {}

        async def fb(ctx, rec, index, reason):
            seen.update(index=index, reason=reason, clicks=list(clicks(page)))
            return "stopped"

        rec = replay(toggle_artifact(), page, fallback=fb)
        self.assertEqual(seen, {"index": 0, "reason": "checked_state", "clicks": []})
        self.assertEqual(rec.route, "compiled+fallback")

    def test_modal_already_open_falls_back_before_any_click(self):
        page = FakePage("modal", opened=True)
        rec = replay(modal_artifact(), page)
        self.assertIn("requires_absent", rec.stop_reason)
        self.assertEqual(clicks(page), [])

    def test_missing_or_renamed_confirm_never_dispatches(self):
        page = FakePage("toggle", confirms=0)
        rec = replay(toggle_artifact(), page)
        self.assertIn("requires_present", rec.stop_reason)
        self.assertEqual(clicks(page), [])
        page = FakePage("modal", confirms=0)
        rec = replay(modal_artifact(), page)
        self.assertEqual(clicks(page), ["open"])
        self.assertIn("target_not_found", rec.stop_reason)

    def test_duplicate_targets_never_dispatch_ambiguously(self):
        page = FakePage("toggle", confirms=2)
        rec = replay(toggle_artifact(), page)
        self.assertIn("requires_present_ambiguous", rec.stop_reason)
        self.assertEqual(clicks(page), [])
        page = FakePage("modal", confirms=2)
        rec = replay(modal_artifact(), page)
        self.assertIn("target_ambiguous", rec.stop_reason)
        self.assertEqual(clicks(page), ["open"])

    def test_unexpected_dialog_after_action_1_stops_before_action_2(self):
        for cls, art in (("toggle", toggle_artifact()), ("modal", modal_artifact())):
            with self.subTest(cls):
                page = FakePage(cls, dialog_after_first=True)
                rec = replay(art, page)
                self.assertEqual(len(clicks(page)), 1)
                self.assertEqual(rec.outcome, "stopped")

    def test_out_of_domain_pages_dispatch_nothing(self):
        for art, url in ((toggle_artifact(), MODAL_URL), (toggle_artifact(), "http://127.0.0.1:4321/"),
                         (modal_artifact(), TOGGLE_URL)):
            with self.subTest(url=url, cls=art["task_class"]):
                page = FakePage("toggle", url=url)
                rec = replay(art, page)
                self.assertEqual(clicks(page), [])
                self.assertEqual(rec.outcome, "stopped")

    def test_stale_refusal_gets_exactly_one_rebind(self):
        page = FakePage("toggle", click_script=["ok", "stale", "ok"])
        rec = replay(toggle_artifact(), page)
        self.assertEqual(rec.outcome, "verified")
        self.assertEqual([m["result"] for m in rec.mutations], ["accepted", "refused", "accepted"])
        page = FakePage("toggle", click_script=["ok", "stale", "stale"])
        rec = replay(toggle_artifact(), page)
        self.assertEqual((rec.outcome, rec.stop_reason), ("stopped", "refused:browser_ref_stale"))
        self.assertEqual(sum(1 for c in page.calls if c[0] == "browser_click"), 3)

    def test_ack_loss_on_action_2_reconciles_and_never_redispatches(self):
        page = FakePage("modal", click_script=["ok", "transport_landed"])
        rec = replay(modal_artifact(), page)
        self.assertEqual(rec.outcome, "verified_by_reconcile")
        self.assertEqual(clicks(page), ["open", "ok"])
        page = FakePage("toggle", click_script=["ok", "transport_lost"])
        rec = replay(toggle_artifact(), page)
        self.assertEqual(rec.outcome, "unknown")
        self.assertEqual(sum(1 for c in page.calls if c[0] == "browser_click"), 2)

    def test_dependency_postcondition_blocks_confirm_when_the_box_did_not_change(self):
        page = FakePage("toggle", click_script=["noop"])
        rec = replay(toggle_artifact(), page)
        self.assertIn("dependency_postcondition", rec.stop_reason)
        self.assertEqual(sum(1 for c in page.calls if c[0] == "browser_click"), 1)

    def test_refuted_toggle_is_not_verified(self):
        art = toggle_artifact()
        page = FakePage("toggle")
        page.state["checked"] = False
        rec = replay(copy.deepcopy(art), page)
        self.assertEqual(rec.outcome, "verified")  # the confirm click overwrote with checked=True
        self.assertEqual(crt.verdict("toggle_confirm", {"checked": False}), "refuted")
        self.assertEqual(crt.verdict("modal_act", {"opened": True, "modal": False}), "pending")


if __name__ == "__main__":
    unittest.main()
