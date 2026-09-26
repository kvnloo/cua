"""Open-packet tables are the results of the shipped functions."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from chooser_projection import history_report, projection_report
from compatibility_matrix import LINUX_STUB, matrix_tsv
from core import Candidate
from cost_ledger import ledger_tsv
from goal_gates import done_label, task_rows
from guarded_run import Decision, admit_guarded_run
from migration_matrix import documented_versions, migration_tsv
from old_driver_fallback import decision_rows
from provider_parity import parity_report
from regression_budget import (
    WorkCounts,
    ci_may_gate_on_milliseconds,
    decisions_deleted_when_admitted,
    metric_layer,
    semantic_path_ok,
    structural_ax_walks,
)
from task_accounting import event_schema, project_event
from task_battery import battery_table, evaluate, promote_globally, run_interleaved, standard_battery
from transfer_probe import comparison_rows

ROOT = Path(__file__).resolve().parents[6]
HANDOFF = ROOT / "scripts" / "repro" / "handoff"


class OpenPacketTest(unittest.TestCase):
    def test_goal_rows_match_the_file_and_leave_latency_unset(self) -> None:
        rows = task_rows()
        recorded = json.loads((HANDOFF / "issue-23-goals.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded, rows)
        self.assertTrue(any(row["model_done_gate"] is False for row in rows))
        self.assertTrue(all(row["latency_ms"] is None for row in rows))
        self.assertTrue(all(row["confidence_threshold"] is None for row in rows))
        self.assertTrue(all(row["calibration_trials"] == 0 for row in rows))
        self.assertEqual(done_label(None), "unknown")
        self.assertNotEqual(done_label(None), done_label(False))
        by_task = {row["task"]: row for row in rows}
        unknown = by_task["cannot_answer is not false"]
        self.assertEqual(unknown["done_label"], "unknown")
        self.assertTrue(unknown["needs_reobserve"])
        self.assertEqual(unknown["reobserve_action"], "reobserve")
        self.assertFalse(unknown["completed"])
        premature = by_task["model done, ground truth false, no oracle"]
        self.assertTrue(premature["premature_stop"])
        self.assertTrue(premature["arm_factorized_completed"])
        self.assertFalse(premature["arm_ordinary_completed"])
        missed = by_task["model not done, ground truth true, no oracle"]
        self.assertTrue(missed["missed_completion"])
        oracle = by_task["model done, oracle failed"]
        self.assertFalse(oracle["completed"])
        self.assertEqual(oracle["arm_local"], "false")

    def test_battery_table_is_the_interleaved_runner(self) -> None:
        recorded = json.loads((HANDOFF / "issue-24-battery.json").read_text(encoding="utf-8"))
        table = battery_table()
        self.assertEqual(recorded, table)
        self.assertEqual(len(standard_battery()), 5)
        self.assertEqual(len(table), 20)
        self.assertFalse(promote_globally(run_interleaved(standard_battery())))
        self.assertEqual(
            [item.name for item in run_interleaved(standard_battery())],
            [name for name, _candidates in standard_battery()],
        )
        self.assertTrue(all(row["live_success"] is None and row["wall_time_ms"] is None for row in table))
        by_key = {(row["task"], row["arm"]): row for row in table}
        self.assertTrue(by_key[("fill-submit", "lazy-vision")]["fast_path"])
        self.assertEqual(by_key[("fill-submit", "lazy-vision")]["visual_parses"], 0)
        self.assertEqual(by_key[("visual-needed", "lazy-vision")]["visual_parses"], 1)
        self.assertEqual(by_key[("two-fields", "guarded-run")]["admission"], "admitted")
        self.assertEqual(by_key[("two-fields", "guarded-run")]["actions"], 2)
        self.assertEqual(by_key[("two-fields", "guarded-run")]["decisions"], 1)
        self.assertEqual(by_key[("fill-submit", "guarded-run")]["admission"], "not admitted")
        form = evaluate("form-fill", [Candidate("only-action", "only-action", "browser_click", {})])
        self.assertTrue(form.fast_path)
        self.assertFalse(hasattr(form, "retained_ground_truth"))

    def test_semantic_budget_does_not_use_milliseconds(self) -> None:
        self.assertFalse(ci_may_gate_on_milliseconds())
        self.assertTrue(semantic_path_ok(WorkCounts(0, 1, 0, 1)))
        self.assertFalse(semantic_path_ok(WorkCounts(1, 1, 0, 1)))
        self.assertFalse(semantic_path_ok(WorkCounts(0, 1, 1, 1)))
        self.assertEqual(metric_layer("visual_parses"), "hard CI counter")
        self.assertEqual(metric_layer("wall_clock_ms"), "evidence artifact")
        self.assertEqual(structural_ax_walks(include_elements=False), 0)
        self.assertEqual(structural_ax_walks(include_elements=True), 1)
        plan = admit_guarded_run(
            [
                Candidate("type-verification-value", "type", "browser_type", {}),
                Candidate("submit-form", "submit", "browser_click", {}),
            ],
            Decision("run", ("type-verification-value", "submit-form")),
            token="proof",
            submit_ref="ref-submit",
        )
        self.assertEqual(decisions_deleted_when_admitted(2, plan is not None), 1)
        self.assertIsNone(decisions_deleted_when_admitted(1, False))
        text = (HANDOFF / "issue-35-budget.md").read_text(encoding="utf-8")
        self.assertIn("do not add a CI wall-clock gate", text)
        self.assertIn("semantic_path_ok", text)
        self.assertIn("This Linux host is present.", text)

    def test_second_harness_spike_stays_deleted(self) -> None:
        rows = comparison_rows()
        recorded = json.loads((HANDOFF / "issue-49-comparison.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded, rows)
        by_concept = {row["concept"]: row for row in rows}
        self.assertEqual(by_concept["one executable candidate"]["shipped_result"], "only-action")
        self.assertEqual(by_concept["freshness"]["shipped_result"], "stale refused")
        self.assertTrue(all(row["second_harness"] == "deleted" for row in rows))
        self.assertEqual(len(rows), 5)
        spike = (HANDOFF / "issue-49-spike.md").read_text(encoding="utf-8")
        self.assertIn("No TypeSafe or Jev import was added.", spike)

    def test_compatibility_probe_matches_the_matrix(self) -> None:
        recorded = (HANDOFF / "issue-27-matrix.tsv").read_text(encoding="utf-8")
        self.assertEqual(recorded, matrix_tsv(ROOT))
        probe = HANDOFF / "issue-27-probe.py"
        completed = subprocess.run(
            [sys.executable, str(probe)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.stdout, recorded)
        stub = (ROOT / LINUX_STUB).read_text(encoding="utf-8")
        self.assertNotIn("include_accessibility_tree", stub)
        self.assertIn("schema/property preflight", recorded)
        self.assertIn("not captured", recorded)
        self.assertIn("get_window_state.include_accessibility_tree", recorded)

    def test_event_schema_drops_marker_text(self) -> None:
        schema = event_schema()
        self.assertEqual(
            set(schema["fields"]),
            {"cold_setup_ms", "verified_outcome_ms", "runner_lifetime_ms", "named_span_ms"},
        )
        marker = "SECRET-MARKER"
        projected = project_event(
            {
                "verified_outcome_ms": 5,
                "token": marker,
                "screenshot": marker,
                "window_title": marker,
                "ocr_text": marker,
                "prompt": marker,
                "credential": marker,
            }
        )
        self.assertEqual(projected, {"verified_outcome_ms": 5})
        self.assertNotIn(marker, json.dumps(projected))
        runner = (ROOT / "libs/cua-driver/examples/jev-use/python/run.py").read_text(encoding="utf-8")
        self.assertIn('"token": token', runner)
        note = (HANDOFF / "issue-34-privacy.md").read_text(encoding="utf-8")
        self.assertIn("project_event", note)
        self.assertIn(marker, note)

    def test_cost_ledger_points_at_real_files(self) -> None:
        recorded = (HANDOFF / "issue-45-ledger.tsv").read_text(encoding="utf-8")
        self.assertEqual(recorded, ledger_tsv(ROOT))
        mechanisms = set()
        for line in recorded.splitlines()[1:]:
            cells = line.split("\t")
            mechanisms.add(cells[0])
            evidence = cells[1]
            self.assertTrue((ROOT / evidence).is_file(), evidence)
            self.assertIn("not measured", line)
            self.assertEqual(cells[3], "0")
        self.assertIn("lazy vision", mechanisms)
        self.assertIn("conditional observation", mechanisms)
        self.assertIn("not added", recorded)

    def test_migration_matrix_reads_the_contract_readme(self) -> None:
        recorded = (HANDOFF / "issue-38-matrix.tsv").read_text(encoding="utf-8")
        self.assertEqual(recorded, migration_tsv(ROOT))
        readme = (ROOT / "libs/cua-driver/contract/README.md").read_text(encoding="utf-8")
        versions = documented_versions(readme)
        self.assertEqual(versions["contract_version"], "0.8.0")
        self.assertEqual(versions["capability_version"], "1")
        self.assertIn("deny_unknown_fields", recorded)
        self.assertIn("no field added", recorded)
        self.assertIn("not run", recorded)

    def test_old_driver_fallback_calls_the_shipped_helper(self) -> None:
        rows = asyncio.run(decision_rows())
        recorded = json.loads((HANDOFF / "issue-28-decisions.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded, rows)
        by_case = {row["case"]: row for row in rows}
        self.assertEqual(by_case["semantic executable candidate"]["calls"], 0)
        self.assertEqual(by_case["semantic executable candidate"]["outcome"], "not called")
        self.assertEqual(by_case["both selectors advertised"]["calls"], 2)
        self.assertEqual(by_case["both selectors advertised"]["outcome"], "capture-submit")
        self.assertIs(by_case["both selectors advertised"]["include_accessibility_tree"], False)
        self.assertEqual(by_case["older schema missing parse_visual_regions"]["calls"], 0)
        self.assertEqual(by_case["older schema missing parse_visual_regions"]["outcome"], "none")
        self.assertFalse(by_case["platform subset without capture_id"]["capture_bound_click"])
        self.assertEqual(by_case["platform subset without capture_id"]["calls"], 0)
        self.assertEqual(by_case["permission refusal"]["calls"], 1)
        self.assertEqual(by_case["permission refusal"]["retries"], 0)
        self.assertEqual(by_case["permission refusal"]["outcome"], "none")
        self.assertEqual(by_case["malformed capture id"]["calls"], 1)
        self.assertEqual(by_case["malformed capture id"]["outcome"], "none")
        self.assertTrue(all(row["live_driver"] == "not used" for row in rows))
        self.assertTrue(all(row["gains_authority"] is False for row in rows))

    def test_projection_history_and_mock_parity_call_the_shipped_checks(self) -> None:
        candidates = [
            Candidate(
                "type-verification-value",
                "Type the token.",
                "browser_type",
                {"text": "secret"},
            )
        ]
        report = projection_report(candidates)
        self.assertEqual(report["chooser_fields"], ["description", "id"])
        self.assertTrue(report["arguments_stay_local"])
        self.assertEqual(report["receipts"], "not produced")
        recorded = json.loads((HANDOFF / "issue-46-projection.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded, report)
        history = history_report()
        self.assertEqual(history["kept_fields"], ["outcome", "selected_id"])
        self.assertTrue(history["extra_field_rejected"])
        self.assertIsNone(history["measured_success"])
        self.assertEqual(history["proposal"], "not justified")
        self.assertEqual(
            json.loads((HANDOFF / "issue-47-history.json").read_text(encoding="utf-8")),
            history,
        )
        parity = parity_report()
        mock = parity["rows"][0]
        self.assertEqual(mock["provider"], "mock")
        self.assertEqual(mock["selected_id"], "type-verification-value")
        self.assertTrue(mock["malformed_rejected"])
        self.assertTrue(mock["arguments_on_candidate"])
        self.assertFalse(mock["arguments_in_selected_id"])
        self.assertEqual(parity["rows"][1]["ran"], "not run")
        self.assertEqual(parity["rows"][2]["ran"], "not run")
        self.assertEqual(
            json.loads((HANDOFF / "issue-48-parity.json").read_text(encoding="utf-8")),
            parity,
        )


if __name__ == "__main__":
    unittest.main()
