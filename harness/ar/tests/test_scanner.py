"""Every scanner rule fires on its own planted example; clean examples fire nothing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from areval.scanner import load_rules, parse_diff, scan  # noqa: E402

RULES = load_rules()
PATH = "libs/cua-driver/rust/crates/platform-linux/src/atspi/native.rs"


def diff(added=(), removed=()):
    body = "".join(f"-{x}\n" for x in removed) + "".join(f"+{x}\n" for x in added)
    return f"diff --git a/{PATH} b/{PATH}\n--- a/{PATH}\n+++ b/{PATH}\n@@ -1,1 +1,1 @@\n{body}"


class PlantedExamples(unittest.TestCase):
    def test_each_rule_fires_on_its_planted_example(self):
        self.assertGreaterEqual(len(RULES["rules"]), 11)
        for rule in RULES["rules"]:
            with self.subTest(rule=rule["id"]):
                d = diff(added=[rule["planted"]]) if rule["side"] == "added" else diff(removed=[rule["planted"]])
                fired = {h["rule"] for h in scan(d, RULES)}
                self.assertIn(rule["id"], fired)

    def test_clean_examples_fire_nothing(self):
        for line in RULES["clean_examples"]:
            with self.subTest(line=line):
                self.assertEqual(scan(diff(added=[line], removed=["// old"]), RULES), [])

    def test_modified_line_with_reread_is_not_a_removal(self):
        old = "let (acc, role) = live_accessible(conn, object_ref).await?;"
        new = "let (acc, role) = live_accessible(conn, object_ref).await?; // same call"
        self.assertEqual([h["rule"] for h in scan(diff(added=[new], removed=[old]), RULES)], [])

    def test_net_removal_fires(self):
        old = "let (acc, role) = live_accessible(conn, object_ref).await?;"
        self.assertIn("removed_reread_reconcile", {h["rule"] for h in scan(diff(removed=[old]), RULES)})

    def test_parse_diff_paths(self):
        files = parse_diff(diff(added=["a"], removed=["b"]))
        self.assertEqual(files, {PATH: {"added": ["a"], "removed": ["b"]}})


if __name__ == "__main__":
    unittest.main()
