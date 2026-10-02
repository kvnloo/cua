"""Unit tests for the pure AR fixture modules (no GTK, no Driver, no display)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ar_external as ext  # noqa: E402
import ar_oracle as orc  # noqa: E402
import ar_sandbox as sbx  # noqa: E402
from ar_layout import CHECK_LABELS, layout_for  # noqa: E402

NONCE = "n" * 32
PID = 4242


def rec(**kw):
    base = {"schema": orc.GTK_SCHEMA, "nonce": NONCE, "pid": PID, "event": "toggle", "checked": True,
            "handler_calls": 1, "t_handler_ns": 1_000, "t_applied_ns": 1_100, "seq": 1}
    base.update(kw)
    return base


class LayoutTests(unittest.TestCase):
    def test_deterministic_per_seed_and_varies_across_seeds(self):
        self.assertEqual(layout_for("checkbox", 7, "normal"), layout_for("checkbox", 7, "normal"))
        layouts = [layout_for("checkbox", s, "normal") for s in range(40)]
        self.assertGreater(len({l["target_label"] for l in layouts}), 5)
        self.assertGreater(len({tuple(map(tuple, l["items"])).__hash__() for l in layouts}), 20)
        self.assertGreater(len({tuple(l["window_pos"]) for l in layouts}), 30)

    def test_target_present_once_and_task_semantics_constant(self):
        for s in range(50):
            lay = layout_for("checkbox", s, "normal")
            targets = [lab for kind, lab in lay["items"] if kind == "target"]
            self.assertEqual(targets, [lay["target_label"]])
            labels = [lab for _, lab in lay["items"]]
            self.assertEqual(len(labels), len(set(labels)))
            self.assertEqual(len(lay["items"]), 6)

    def test_absent_variant_removes_target_label_keeps_size(self):
        for s in range(50):
            lay = layout_for("checkbox", s, "absent")
            labels = [lab for _, lab in lay["items"]]
            self.assertNotIn(lay["target_label"], labels)
            self.assertEqual(len(labels), 6)
            self.assertTrue(all(lab in CHECK_LABELS or kind == "button" for kind, lab in lay["items"]))
            self.assertEqual(set(lay["widget_ids"]), set(labels))

    def test_variant_delays_in_range(self):
        for s in range(50):
            lay = layout_for("checkbox", s, "delayed")
            self.assertTrue(200 <= lay["delay_ms"] <= 500)
            self.assertTrue(30 <= lay["steal_map_ms"] <= 200)

    def test_text_layout_has_field_and_save(self):
        lay = layout_for("text", 3, "normal")
        self.assertIn(("note", lay["note_label"]), [tuple(i) for i in lay["items"]])
        self.assertTrue(lay["save_label"])


class GtkOracleTests(unittest.TestCase):
    initial = {"checked": False}

    def ev(self, records, done=2_000, spawn=500):
        return orc.evaluate_gtk(records, task="checkbox", nonce=NONCE, app_pid=PID, initial=self.initial,
                                t_spawn_ns=spawn, t_done_ns=done)

    def test_one_own_effect_verifies(self):
        v = self.ev([rec()])
        self.assertTrue(v["verified"])
        self.assertEqual(v["mutation_count"], 1)

    def test_duplicate_mutation_fails(self):
        v = self.ev([rec(), rec(seq=2, handler_calls=2, checked=False)])
        self.assertTrue(v["duplicate_mutation"])
        self.assertFalse(v["verified"])

    def test_foreign_nonce_or_pid_fails(self):
        self.assertFalse(self.ev([rec(nonce="x" * 32)])["verified"])
        self.assertFalse(self.ev([rec(pid=1)])["verified"])
        self.assertFalse(self.ev([rec(), rec(nonce="x")])["verified"])

    def test_wrong_direction_fails(self):
        self.assertFalse(self.ev([rec(checked=False)])["verified"])

    def test_effect_after_done_or_before_spawn_fails(self):
        self.assertFalse(self.ev([rec()], done=1_050)["verified"])
        self.assertFalse(self.ev([rec()], spawn=1_050)["verified"])

    def test_confirms_matches_caller_done_condition(self):
        self.assertIsNone(orc.gtk_confirms([], task="checkbox", nonce=NONCE, app_pid=PID, initial=self.initial))
        hit = orc.gtk_confirms([rec(nonce="x"), rec()], task="checkbox", nonce=NONCE, app_pid=PID,
                               initial=self.initial)
        self.assertEqual(hit["nonce"], NONCE)

    def test_text_effect(self):
        r = rec(event="save", note_saved="v1")
        r.pop("checked")
        v = orc.evaluate_gtk([r], task="text", nonce=NONCE, app_pid=PID, initial={}, t_spawn_ns=0,
                             t_done_ns=5_000, expected_note="v1")
        self.assertTrue(v["verified"])
        v = orc.evaluate_gtk([r], task="text", nonce=NONCE, app_pid=PID, initial={}, t_spawn_ns=0,
                             t_done_ns=5_000, expected_note="v2")
        self.assertFalse(v["verified"])

    def test_read_journal_ignores_torn_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "j.jsonl"
            p.write_text(json.dumps(rec()) + "\n" + '{"schema": "cua.ar')
            self.assertEqual(len(orc.read_journal(p)), 1)
            self.assertEqual(orc.read_journal(Path(d) / "missing"), [])


class ControlVerdictTests(unittest.TestCase):
    def oracle(self, records, done=2_000):
        return orc.evaluate_gtk(records, task="checkbox", nonce=NONCE, app_pid=PID, initial={"checked": False},
                                t_spawn_ns=0, t_done_ns=done)

    def test_reference_pass_and_early_done_fail(self):
        caller = {"outcome": "verified", "dispatch_count": 1, "t_done_ns": 2_000}
        self.assertTrue(orc.gtk_control_verdict("reference", caller, self.oracle([rec()]))["passed"])
        early = {"outcome": "verified", "dispatch_count": 1, "t_done_ns": 1_050}
        self.assertFalse(orc.gtk_control_verdict("reference", early, self.oracle([rec()], done=1_050))["passed"])

    def test_redispatch_fails(self):
        caller = {"outcome": "verified", "dispatch_count": 2, "t_done_ns": 2_000}
        self.assertFalse(orc.gtk_control_verdict("reference", caller, self.oracle([rec()]))["passed"])
        caller = {"outcome": "verified", "dispatch_count": 1, "t_done_ns": 2_000}
        v = orc.gtk_control_verdict("reference", caller, self.oracle([rec()]), {"do_action_on_bus": 2})
        self.assertFalse(v["passed"])

    def test_stale_token(self):
        ok = {"outcome": "refused", "error_code": "stale_element_token", "dispatch_count": 1}
        self.assertTrue(orc.gtk_control_verdict("negative_stale_token", ok, self.oracle([]),
                                                {"do_action_on_bus": 0})["passed"])
        self.assertFalse(orc.gtk_control_verdict("negative_stale_token", ok, self.oracle([rec()]))["passed"])
        accepted = {"outcome": "unknown", "dispatch_count": 1}
        self.assertFalse(orc.gtk_control_verdict("negative_stale_token", accepted, self.oracle([]))["passed"])

    def test_canaries_never_success(self):
        for kind in ("canary_absent", "canary_disabled"):
            claimed = {"outcome": "verified", "dispatch_count": 1}
            self.assertFalse(orc.gtk_control_verdict(kind, claimed, self.oracle([]))["passed"])
        self.assertTrue(orc.gtk_control_verdict("canary_absent", {"outcome": "unknown"}, self.oracle([]))["passed"])
        self.assertTrue(orc.gtk_control_verdict("canary_disabled", {"outcome": "refused", "dispatch_count": 1,
                                                                    "canary_disable_ack": "disabled 12"},
                                                self.oracle([]))["passed"])
        self.assertFalse(orc.gtk_control_verdict("canary_disabled", {"outcome": "refused", "dispatch_count": 1},
                                                 self.oracle([]))["passed"])
        self.assertFalse(orc.gtk_control_verdict("canary_disabled", {"outcome": "unknown", "dispatch_count": 0},
                                                 self.oracle([]))["passed"])

    def test_delayed_requires_real_delay(self):
        caller = {"outcome": "verified", "dispatch_count": 1, "t_done_ns": 900_000_000}
        late = rec(t_handler_ns=1_000, t_applied_ns=1_000 + 300_000_000)
        self.assertTrue(orc.gtk_control_verdict("delayed_effect", caller, self.oracle([late], done=900_000_000))["passed"])
        self.assertFalse(orc.gtk_control_verdict("delayed_effect", caller, self.oracle([rec()], done=900_000_000))["passed"])

    def test_focus_steal_needs_steal_and_restore(self):
        caller = {"outcome": "verified", "dispatch_count": 1, "t_done_ns": 2_000}
        o = self.oracle([rec()])
        self.assertTrue(orc.gtk_control_verdict("focus_steal", caller, o,
                                                {"steal_observed": True, "focus_back_with_user": True})["passed"])
        self.assertFalse(orc.gtk_control_verdict("focus_steal", caller, o,
                                                 {"steal_observed": True, "focus_back_with_user": False})["passed"])
        self.assertFalse(orc.gtk_control_verdict("focus_steal", caller, o,
                                                 {"steal_observed": False, "focus_back_with_user": True})["passed"])

    def test_driver_claim_before_effect_fails(self):
        late = rec(t_handler_ns=1_000, t_applied_ns=300_000_000)
        o = self.oracle([late], done=900_000_000)
        early_claim = {"outcome": "verified", "dispatch_count": 1, "t_done_ns": 900_000_000,
                       "calls": [{"tool": "click", "ok": True, "t1_ns": 100_000_000,
                                  "structured": {"effect": "verified"}}]}
        self.assertFalse(orc.gtk_control_verdict("delayed_effect", early_claim, o)["passed"])
        honest = dict(early_claim, calls=[{"tool": "click", "ok": True, "t1_ns": 100_000_000,
                                           "structured": {"effect": "unverifiable"}}])
        self.assertTrue(orc.gtk_control_verdict("delayed_effect", honest, o)["passed"])
        never = {"outcome": "unknown", "dispatch_count": 1, "canary_disable_ack": "disabled 1",
                 "calls": [{"tool": "click", "ok": True, "t1_ns": 5, "structured": {"verified": True}}]}
        self.assertFalse(orc.gtk_control_verdict("canary_disabled", never, self.oracle([]))["passed"])

    def test_set_value_confirmation_is_not_the_journaled_effect(self):
        r = rec(event="save", note_saved="v1", t_applied_ns=500_000_000)
        r.pop("checked")
        o = orc.evaluate_gtk([r], task="text", nonce=NONCE, app_pid=PID, initial={}, t_spawn_ns=0,
                             t_done_ns=900_000_000, expected_note="v1")
        caller = {"outcome": "verified", "dispatch_count": 2, "t_done_ns": 900_000_000,
                  "calls": [{"tool": "set_value", "ok": True, "t1_ns": 100_000_000, "structured": {"effect": "confirmed"}},
                            {"tool": "click", "ok": True, "t1_ns": 800_000_000, "structured": {"effect": "unverifiable"}}]}
        self.assertTrue(orc.gtk_control_verdict("text_save", caller, o)["passed"])
        caller["calls"][1]["structured"] = {"effect": "verified"}
        caller["calls"][1]["t1_ns"] = 400_000_000
        self.assertFalse(orc.gtk_control_verdict("text_save", caller, o)["passed"])

    def test_no_action(self):
        self.assertTrue(orc.gtk_control_verdict("negative_no_action", {"outcome": "observed_only"},
                                                self.oracle([]))["passed"])
        self.assertFalse(orc.gtk_control_verdict("negative_no_action", {"outcome": "observed_only"},
                                                 self.oracle([rec()]))["passed"])


class BrowserOracleTests(unittest.TestCase):
    def journal(self, trusted=True, posts=1, order=orc.TRUSTED_SEQUENCE):
        page = [{"source": "page", "seq": i, "kind": k, "is_trusted": trusted, "target": "button[type=submit]"}
                for i, k in enumerate(order)]
        page.append({"source": "page", "seq": 99, "kind": "submit", "is_trusted": trusted, "target": "form"})
        tgt = [{"source": "target", "kind": "submit_post", "value": "tok", "recv_mono_ns": 1_000 + i}
               for i in range(posts)]
        return page + tgt

    def test_trusted_single_post_verifies(self):
        v = orc.evaluate_browser(self.journal(), {"submitted": "tok"}, token="tok", t_spawn_ns=0, t_done_ns=2_000)
        self.assertTrue(v["verified"])

    def test_untrusted_or_duplicate_or_missing_fails(self):
        self.assertFalse(orc.evaluate_browser(self.journal(trusted=False), {"submitted": "tok"}, token="tok",
                                              t_spawn_ns=0, t_done_ns=2_000)["verified"])
        self.assertFalse(orc.evaluate_browser(self.journal(posts=2), {"submitted": "tok"}, token="tok",
                                              t_spawn_ns=0, t_done_ns=2_000)["verified"])
        self.assertFalse(orc.evaluate_browser(self.journal(order=("click",)), {"submitted": "tok"}, token="tok",
                                              t_spawn_ns=0, t_done_ns=2_000)["verified"])
        self.assertFalse(orc.evaluate_browser(self.journal(), {"submitted": "tok"}, token="tok",
                                              t_spawn_ns=0, t_done_ns=500)["verified"])


class ExternalTests(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(ext.norm("chrome_crashpad 1234 deadbeef99"), "chrome_crashpad # #")
        self.assertEqual(ext.norm_path("runtime/at-spi2-UDO3V1/socket"), "runtime/at-spi#-XXXXXX/socket")
        self.assertEqual(ext.norm_path("runtime/at-spi2-MCSIWq"), "runtime/at-spi#-XXXXXX")
        self.assertEqual(ext.norm("cua-driver-r2-m"), "cua-driver-r#-m")
        self.assertEqual(ext.norm_path("runtime/at-spi2-abcdef/socket"), "runtime/at-spi#-XXXXXX/socket")
        self.assertEqual(ext.norm_path("driver_home/.cua-driver/x.json"), "driver_home/.cua-driver/x.json")
        self.assertEqual(ext.norm_path("tmp/.org.chromium.Chromium.aB3dEf"), "tmp/.org.chromium.Chromium.XXXXXX")

    def test_diff_ignores_descendants_of_harness_pids(self):
        before = {"procs": {10: {"comm": "openbox", "ppid": 1}}, "sockets": {}, "files": {}}
        after = {"procs": {10: {"comm": "openbox", "ppid": 1}, 12: {"comm": "python3", "ppid": 1},
                           13: {"comm": "bwrap", "ppid": 12}, 14: {"comm": "glycin-svg", "ppid": 13}},
                 "sockets": {}, "files": {}}
        self.assertEqual(ext.diff(before, after, ignore_pids=[12])["new_processes"], [])

    def test_descendants(self):
        table = {2: {"ppid": 1}, 3: {"ppid": 2}, 4: {"ppid": 3}, 5: {"ppid": 1}}
        self.assertEqual(ext.descendants(table, 2), {3, 4})

    def test_diff_and_signature(self):
        before = {"procs": {10: {"comm": "openbox", "ppid": 1}}, "sockets": {}, "files": {"driver_home/a": "f"}}
        after = {"procs": {10: {"comm": "openbox", "ppid": 1}, 11: {"comm": "cua-driver", "ppid": 1},
                           12: {"comm": "fixture", "ppid": 1}},
                 "sockets": {77: {"desc": "unix:/x/sock-123", "pid": 11, "comm": "cua-driver"}},
                 "files": {"driver_home/a": "f", "driver_home/b-42": "f"}}
        d = ext.diff(before, after, ignore_pids=[12])
        self.assertEqual(d["new_processes"], ["cua-driver"])
        self.assertEqual(d["new_listening_sockets"], ["cua-driver|unix:/x/sock-#"])
        self.assertEqual(d["new_files"], ["f:driver_home/b-#"])
        sig = ext.signature({"during": d, "leftover": {}})
        self.assertIn("during:new_processes:cua-driver", sig)
        self.assertEqual(ext.extra_vs_reference(sig, sig), [])
        self.assertEqual(ext.extra_vs_reference(sig + ["x"], sig), ["x"])

    def test_file_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "sub").mkdir()
            (Path(d) / "sub" / "f1").write_text("x")
            inv = ext.file_inventory({"root": d})
            self.assertEqual(inv, {"root/sub": "d", "root/sub/f1": "f"})

    def test_process_table_has_self(self):
        self.assertIn(os.getpid(), ext.process_table())


class SandboxTests(unittest.TestCase):
    def test_argv_masks_private_and_binds_home(self):
        argv = sbx.driver_argv("/drv", trial_home="/h/t1", runtime_dir="/r", private_roots=["/p"])
        self.assertEqual(argv[:5], [sbx.BWRAP, "--ro-bind", "/", "/", "--dev-bind"])
        self.assertIn("--bind", argv)
        i = argv.index("--tmpfs")
        self.assertEqual(argv[i:i + 4], ["--tmpfs", "/p", "--remount-ro", "/p"])
        self.assertEqual(argv[-3:], ["--", "/drv", "mcp"])
        self.assertIn("--die-with-parent", argv)

    def test_env_moves_home(self):
        env = sbx.driver_env({"HOME": "/old", "XDG_STATE_HOME": "/old/s", "DISPLAY": ":9"}, "/h/t1")
        self.assertEqual(env["HOME"], "/h/t1")
        self.assertEqual(env["TMPDIR"], "/h/t1/tmp")
        self.assertNotIn("XDG_STATE_HOME", env)
        self.assertEqual(env["DISPLAY"], ":9")


if __name__ == "__main__":
    unittest.main()
