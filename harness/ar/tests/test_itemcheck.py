"""itemcheck on the real segment-1 files (skipped unless AR_ITEMCHECK names the built binary).

Uses the worktree's own focus_guard.rs as the base and planted edits as candidates.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

AR = Path(__file__).resolve().parent.parent
WT = AR.parent.parent
FG = "libs/cua-driver/rust/crates/platform-linux/src/input/focus_guard.rs"
BIN = os.environ.get("AR_ITEMCHECK")


@unittest.skipUnless(BIN, "AR_ITEMCHECK not set")
class RealFiles(unittest.TestCase):
    def check(self, old: str, new: str) -> dict:
        allow = json.loads((AR / "allowlist.json").read_text())["items"]
        base = (WT / FG).read_text()
        self.assertIn(old, base)
        cand = base.replace(old, new, 1)
        with tempfile.TemporaryDirectory() as tmp:
            b, c = Path(tmp) / "b.rs", Path(tmp) / "c.rs"
            b.write_text(base)
            c.write_text(cand)
            diff = subprocess.run(["git", "diff", "--no-index", "-U0", str(b), str(c)], capture_output=True, text=True).stdout
            hunks = []
            for line in diff.splitlines():
                if line.startswith("@@"):
                    old_part, new_part = line.split()[1:3]
                    bs, _, bl = old_part[1:].partition(",")
                    cs, _, cl = new_part[1:].partition(",")
                    hunks.append([int(bs), int(bl or 1), int(cs), int(cl or 1)])
            req = Path(tmp) / "req.json"
            req.write_text(json.dumps({"allowlist": allow, "files": [{"key": FG, "base": str(b), "cand": str(c),
                                                                      "hunks": hunks}]}))
            out = subprocess.run([BIN, "--request", str(req)], capture_output=True, text=True)
            return json.loads(out.stdout)

    def test_allowed_constant(self):
        r = self.check("Duration::from_millis(220)", "Duration::from_millis(120)")
        self.assertTrue(r["ok"], r["violations"])
        self.assertEqual(r["files"][FG]["changed_allowed"], ["const SETTLE_WATCH"])

    def test_allowed_polling_function(self):
        r = self.check("std::thread::sleep(SETTLE_POLL);", "std::thread::sleep(SETTLE_POLL / 2);")
        self.assertTrue(r["ok"], r["violations"])

    def test_frozen_restore_budget(self):
        r = self.check("Duration::from_millis(600)", "Duration::from_millis(100)")
        self.assertFalse(r["ok"])
        self.assertEqual(r["violations"][0]["item"], "const RESTORE_BUDGET")

    def test_phase_trace_line_removed(self):
        r = self.check('    cua_driver_core::phase_trace::mark("focus_guard", "restored");\n', "")
        self.assertFalse(r["ok"])

    def test_test_item_edited(self):
        r = self.check("assert!(SETTLE_WATCH_NEW_WINDOW + RESTORE_BUDGET <= Duration::from_millis(1500));",
                       "assert!(true);")
        self.assertFalse(r["ok"])
        self.assertTrue(any(v["kind"] == "test_item_changed" for v in r["violations"]))


if __name__ == "__main__":
    unittest.main()
