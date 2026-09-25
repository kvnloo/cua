"""The pruning and assimilation records have to match the functions they cite."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from action_consumer import typed_choice
from browser_revision import BrowserNode, StaleRefError, bind
from cancellation_lifetime import Lifetime
from core import Candidate
from guarded_run import (
    Decision,
    FreshObservation,
    admit_guarded_run,
    second_child_allowed,
)
from passive_observation import AuthorityError, Row, action_target, verification_text
from run_length import execute_capped, recommend_cap, wasted_after_stop
from shadow_probe import ShadowSample
from stale_batch import Child, Target, run_batch
from task_accounting import TrialClocks, outcome_time, phase0_spans_cover_outcome

ROOT = Path(__file__).resolve().parents[6]
HANDOFF = ROOT / "scripts" / "repro" / "handoff"
FORK_SHA = "92b5035ea08b2126f947db0dfd8ecf829013d7b4"


def _plan():
    admitted = admit_guarded_run(
        [
            Candidate("type-verification-value", "type", "browser_type", {}),
            Candidate("submit-form", "submit", "browser_click", {}),
        ],
        Decision("run", ("type-verification-value", "submit-form")),
        token="proof",
        submit_ref="ref-submit",
    )
    assert admitted is not None
    return admitted


class HandoffPruningTest(unittest.TestCase):
    def test_doc_matrix_quotes_the_cited_lines(self) -> None:
        with (HANDOFF / "issue-50-matrix.tsv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertGreaterEqual(len(rows), 20)
        seen = {row["invariant"] for row in rows}
        for name in (
            "reobserve after mutation",
            "stale tokens/captures",
            "unknown is not success",
            "unverifiable actions",
            "no blind replay",
            "screenshot/tree modality",
            "visual capture one-action lifetime",
            "chooser authority",
            "guarded runs/batching",
            "future conditional observation",
        ):
            self.assertIn(name, seen)
        for row in rows:
            line = (ROOT / row["source"]).read_text(encoding="utf-8").splitlines()[
                int(row["line"]) - 1
            ]
            self.assertIn(row["quote"], line)
            self.assertEqual(row["must_not_weaken"], "yes")
        docs = (HANDOFF / "issue-50-docs.md").read_text(encoding="utf-8")
        self.assertIn("do not edit", docs)
        self.assertIn("BLOCKED", docs)

    def test_ownership_uses_the_six_outcomes_and_deletes_the_extra_services(self) -> None:
        allowed = {
            "already exists",
            "extend existing owner minimally",
            "caller/recipe-local",
            "shared helper earned by two call sites",
            "new public/runtime owner",
            "delete from plan",
        }
        with (HANDOFF / "ownership.tsv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        requirements = {row["requirement"] for row in rows}
        for name in (
            "telemetry and timing",
            "observation projection",
            "deterministic fast path",
            "compiled postconditions",
            "guarded runs",
            "mechanical batching",
            "settlement provenance",
            "passive evidence",
            "freshness and revision tracking",
            "cancellation",
            "conditional observation",
            "provider adapters",
        ):
            self.assertIn(name, requirements)
        for row in rows:
            self.assertIn(row["disposition"], allowed)
            self.assertTrue((ROOT / row["evidence"]).is_file(), row["evidence"])
        dispositions = {row["disposition"] for row in rows}
        self.assertNotIn("new public/runtime owner", dispositions)
        self.assertNotIn("shared helper earned by two call sites", dispositions)
        deleted = {
            row["requirement"]
            for row in rows
            if row["disposition"] == "delete from plan"
        }
        for name in (
            "hard-coded run length of 4",
            "universal shadow store",
            "second verifier",
            "shared postcondition compiler",
            "shared guarded-run type",
            "generic lifecycle service",
        ):
            self.assertIn(name, deleted)

    def test_decision_table_kills_only_the_behaviors_the_functions_refuse(self) -> None:
        with (HANDOFF / "decision-table.tsv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(
            sorted(row["decision"] for row in rows),
            ["BLOCKED"] * len(rows),
        )
        blocked_names = {row["mechanism"] for row in rows}
        for name in (
            "capture skip from a shadow probe",
            "guarded-run length 4 as a shared constant",
            "passive row as an action target",
        ):
            self.assertIn(name, blocked_names)
        for row in rows:
            self.assertEqual(row["decision"], "BLOCKED")
            self.assertTrue((ROOT / row["evidence"]).is_file())
            if row["decision"] == "BLOCKED":
                self.assertTrue(row["missing_evidence"])
                self.assertIn("leave", row["next_action"])
        advice = recommend_cap(stop_at_first_child=7, runs=10)
        self.assertIn("cap at 2", advice)
        ran = execute_capped(_plan(), ["refuted"], [None], 4)
        self.assertEqual(ran, 1)
        self.assertEqual(wasted_after_stop(4, ran), 3)
        with self.assertRaises(AuthorityError):
            action_target(Row("calc-result", "6", passive=True))
        with self.assertRaises(RuntimeError):
            ShadowSample("gtk3-entry", "probe", (), skip_capture=True)
        table = (HANDOFF / "decision-table.tsv").read_text(encoding="utf-8")
        self.assertIn("macOS machine", table)
        self.assertIn("Windows machine", table)
        self.assertIn("do not embed 4", table)
        self.assertIn("do not skip", table)

    def test_run_length_recommendation_quotes_the_function(self) -> None:
        text = (HANDOFF / "issue-54-recommendation.md").read_text(encoding="utf-8")
        self.assertIn(recommend_cap(7, 10), text)
        self.assertIn("Deleted:", text)
        self.assertIn("Local:", text)
        self.assertIn("Shared: nothing", text)
        fresh = FreshObservation("proof", "ref-submit", "c2")
        self.assertEqual(execute_capped(_plan(), ["verified"], [fresh], 2), 2)

    def test_observation_architecture_names_the_existing_owners(self) -> None:
        text = (HANDOFF / "issue-56-architecture.md").read_text(encoding="utf-8")
        source = (
            ROOT / "libs/cua-driver/rust/crates/cua-driver-core/src/expectation.rs"
        ).read_text(encoding="utf-8").splitlines()
        self.assertIn("elapsed_ms", source[309])
        self.assertIn("observe(input.pid, input.window_id, false, true)", source[328])
        for name in (
            "ObservationService",
            "ObservationBudgetService",
            "RevisionService",
            "PassiveEvidenceService",
        ):
            self.assertIn(name, text)
        self.assertIn("line 310", text)
        self.assertIn("line 329", text)
        run_py = (BASE / "python" / "run.py").read_text(encoding="utf-8")
        self.assertNotIn("lazy_vision", run_py)

    def test_batch_and_guard_keep_separate_owners(self) -> None:
        world = {
            "field": Target("id-field", "field"),
            "submit": Target("id-submit", "submit"),
        }
        children = [
            Child("field", Target("id-field", "field")),
            Child("submit", Target("id-submit", "submit")),
        ]
        trace = run_batch(children, lambda label: world.get(label), lambda: "ok")
        self.assertEqual(trace.dispatched, ["field", "submit"])
        plan = _plan()
        fresh = FreshObservation(plan.token, plan.submit_ref, "cap-2")
        self.assertTrue(second_child_allowed("verified", fresh, plan))
        moved = FreshObservation(plan.token, "other-ref", "cap-2")
        self.assertFalse(second_child_allowed("verified", moved, plan))
        text = (HANDOFF / "issue-59-contract.md").read_text(encoding="utf-8")
        self.assertIn("trycua/cua#2794 and #3494", text)
        self.assertIn("No competing batch API", text)
        self.assertIn("never reads the field token", text)

    def test_sequences_follow_lifetime_and_revision(self) -> None:
        queued = Lifetime("req-1")
        queued.admit()
        queued.observe_cancel()
        with self.assertRaises(RuntimeError):
            queued.release()
        finished = Lifetime("req-1")
        finished.admit()
        finished.observe_cancel()
        finished.native_exit()
        finished.release()
        finished.finish()
        foreign = Lifetime("req-1")
        foreign.admit()
        foreign.native_exit()
        foreign.release()
        with self.assertRaises(RuntimeError):
            foreign.finish("req-2")
        node = BrowserNode("ref-submit", 2, "Submit")
        with self.assertRaises(StaleRefError):
            bind(node, "ref-submit", 1)
        text = (HANDOFF / "sequences.md").read_text(encoding="utf-8")
        self.assertIn("No ExecutionContext", text)
        self.assertIn("No LifecycleService", text)
        for event in finished.events:
            self.assertIn(event, text)
        for event in queued.events:
            self.assertIn(event, text)

    def test_keep_draft_packet_matches_the_unlocked_walker(self) -> None:
        packet = (HANDOFF / "issue-63-packet.md").read_text(encoding="utf-8")
        self.assertIn("Verdict withheld", packet)
        self.assertIn("Trace: none", packet)
        self.assertIn("Missing machines: macOS", packet)
        self.assertIn(FORK_SHA, packet)
        source = (
            ROOT / "libs/cua-driver/rust/crates/cua-driver-core/src/expectation.rs"
        ).read_text(encoding="utf-8").splitlines()
        self.assertIn("let elapsed_ms", source[309])
        self.assertIn("observe(input.pid, input.window_id, false, true)", source[328])
        subprocess.check_call(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{FORK_SHA}:libs/cua-driver/rust/crates/cua-driver-core/src/expectation.rs"]
        )
        subprocess.check_call(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", FORK_SHA, "HEAD"]
        )

    def test_passive_vectors_match_the_3904_comment(self) -> None:
        result = Row("calc-result", "6", passive=True)
        button = Row("calc-equals", "=", passive=False)
        self.assertEqual(verification_text([result, button], "calc-result"), "6")
        with self.assertRaises(AuthorityError):
            action_target(result)
        self.assertEqual(action_target(button), "calc-equals")
        text = (HANDOFF / "issue-65-3904.md").read_text(encoding="utf-8")
        self.assertIn("Missing machine: macOS", text)
        self.assertIn("Not posted", text)

    def test_cancellation_plan_separates_covered_order_from_missing_fixtures(self) -> None:
        text = (HANDOFF / "issue-67-plan.md").read_text(encoding="utf-8")
        self.assertIn("NEEDS DESIGN DECISION", text)
        self.assertIn("READY WHEN RFC APPROVES", text)
        for name in (
            "Cancel while queued",
            "Cancel after native admission",
            "Held key or modifier cleanup",
            "Pointer or drag cleanup",
            "Late cancel after completion",
            "Request-id reuse rejected before dispatch",
        ):
            self.assertIn(name, text)
        self.assertIn("not in `Lifetime`", text)

    def test_measurement_decision_uses_outcome_time_only(self) -> None:
        trial = TrialClocks(
            cold_setup_ms=10,
            verified_outcome_ms=100,
            runner_lifetime_ms=250,
            named_span_ms=95,
        )
        self.assertEqual(outcome_time(trial), 100)
        self.assertNotEqual(outcome_time(trial), trial.runner_lifetime_ms)
        self.assertTrue(phase0_spans_cover_outcome(trial))
        text = (HANDOFF / "issue-69-measurement.md").read_text(encoding="utf-8")
        self.assertIn("downstream benchmark-only tooling", text)
        self.assertIn("Do not add this report to trycua/cua#4052", text)

    def test_provider_adapter_does_not_import_policy(self) -> None:
        adapter = (BASE / "python" / "jev_adapter.py").read_text(encoding="utf-8")
        runner = (BASE / "python" / "run.py").read_text(encoding="utf-8")
        for name in (
            "deterministic_fast_path",
            "guarded_run",
            "lazy_vision",
            "goal_gates",
        ):
            self.assertNotIn(name, adapter)
            self.assertNotIn(name, runner)
        text = (HANDOFF / "issue-70-scope.md").read_text(encoding="utf-8")
        self.assertIn("NO CHANGE NEEDED", text)

    def test_consumer_decisions_do_not_need_a_public_poll_field(self) -> None:
        self.assertEqual(
            typed_choice("confirmed", "completed", passive_success=False), "continue"
        )
        self.assertEqual(
            typed_choice("confirmed", "skipped", passive_success=False), "observe"
        )
        self.assertEqual(
            typed_choice("refused", "skipped", passive_success=False), "stop"
        )
        self.assertEqual(
            typed_choice("unverifiable", "unavailable", passive_success=False), "observe"
        )
        text = (HANDOFF / "issue-71-decision.md").read_text(encoding="utf-8")
        self.assertIn("NO PUBLIC FIELD", text)
        workflow = (
            ROOT / "libs/cua-driver/rust/Skills/cua-driver/WORKFLOW.md"
        ).read_text(encoding="utf-8").splitlines()
        self.assertIn("never authorization or an automatic retry", workflow[120])

    def test_rfc_delta_has_the_required_sections_and_does_not_edit_upstream(self) -> None:
        text = (HANDOFF / "rfc-3963-delta.md").read_text(encoding="utf-8")
        for heading in (
            "## 1. North-star",
            "## 2. Invariants that remain",
            "## 3. Current repo-native owners",
            "## 4. Disposition table",
            "## 5. Remaining deltas",
            "## 6. Deleted architecture",
            "## 7. Phase gates",
            "## 8. Dependency graph",
            "## 9. Migration plan",
        ):
            self.assertIn(heading, text)
        self.assertIn("does not edit trycua/cua#3963", text)
        for gone in (
            "universal shadow-state service",
            "second verifier",
            "competing batch API",
            "generic lifecycle service",
            "fixed GuardedRun length",
        ):
            self.assertIn(gone, text)
        self.assertIn("gives every mechanism the state BLOCKED", text)

    def test_promotion_dag_is_the_posting_queue(self) -> None:
        dag = json.loads((HANDOFF / "promotion-dag.json").read_text(encoding="utf-8"))
        allowed = {
            "READY NOW",
            "WAITING ON DOWNSTREAM EXPERIMENT",
            "WAITING ON RFC DECISION",
            "ASSIMILATED",
        }
        ids = [item["id"] for item in dag["items"]]
        self.assertLess(ids.index("elapsed-ms-boundary"), ids.index("4052"))
        self.assertEqual(ids[-1], "3796")
        ready = [item["id"] for item in dag["items"] if item["posting_status"] == "READY NOW"]
        self.assertEqual(ready, ["elapsed-ms-boundary"])
        for item in dag["items"]:
            self.assertIn(item["posting_status"], allowed)
            self.assertIn(item["action"], {"comment", "update existing PR", "new PR", "no action"})
            self.assertNotEqual(item["action"], "new PR")
            self.assertTrue((ROOT / item["evidence"]).is_file())
            for key in (
                "surviving_delta",
                "owner",
                "sha",
                "evidence_complete",
                "evidence_missing",
                "dependency",
                "stop_condition",
                "comment",
            ):
                self.assertTrue(item[key], key)
        queue = (HANDOFF / "issue-74-queue.md").read_text(encoding="utf-8")
        self.assertIn("Nothing in this queue was posted upstream", queue)
        self.assertLess(queue.index("elapsed-ms-boundary"), queue.index("`4052`"))
        self.assertLess(queue.index("`4052`"), queue.index("`3796`"))

    def test_issue_55_graph_matches_typed_choice(self) -> None:
        text = (HANDOFF / "issue-55-consumers.md").read_text(encoding="utf-8")
        self.assertIn("No new public field", text)
        self.assertIn("stays open", text)
        self.assertIn("no wire marker is added", text)
        self.assertIn("Dropped per #3971", text)
        source = (
            ROOT / "libs/cua-driver/rust/crates/platform-macos/src/window_change_detector.rs"
        ).read_text(encoding="utf-8")
        self.assertIn("\n    poll: PollProvenance,\n", source)
        self.assertNotIn("pub poll: PollProvenance", source)
        with (HANDOFF / "issue-55-edges.tsv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertGreaterEqual(len(rows), 4)
        for row in rows:
            choice = typed_choice(
                row["effect"],
                row["observation"],
                passive_success=row["passive_success"] == "true",
            )
            self.assertEqual(choice, row["decision"], row["consumer"])

    def test_blocked_notes_name_the_linux_host(self) -> None:
        names = (
            "issue-2-block.md",
            "issue-4-block.md",
            "issue-10-block.md",
            "issue-46-block.md",
            "issue-47-block.md",
            "issue-48-block.md",
            "issue-64-block.md",
            "issue-72-block.md",
        )
        for name in names:
            text = (HANDOFF / name).read_text(encoding="utf-8")
            self.assertIn("Missing machine: this Linux host.", text, name)
        windows = (HANDOFF / "issue-19-block.md").read_text(encoding="utf-8")
        self.assertIn("Missing machine: Windows", windows)
        macos = (HANDOFF / "issue-18-block.md").read_text(encoding="utf-8")
        self.assertIn("Missing machine: macOS", macos)
        cited = (HANDOFF / "issue-3-macos-trace.md").read_text(encoding="utf-8")
        self.assertIn(
            "https://github.com/trycua/cua/pull/4164#issuecomment-5840994846",
            cited,
        )
        self.assertIn("not a walk this Linux host ran", cited)

    def test_closed_issue_citations_and_machine_blocks(self) -> None:
        closed = (HANDOFF / "closed-issues.md").read_text(encoding="utf-8")
        for number in (3, 53, 55, 57, 58, 60, 63, 66, 68, 69, 70, 71):
            self.assertIn(f"| {number} |", closed)
            self.assertIn(f"issues/{number}#issuecomment-", closed)
        blocks = {
            "issue-2-block.md": "Missing machine: this Linux host.",
            "issue-4-block.md": "Missing machine: this Linux host.",
            "issue-8-block.md": "Missing machine: macOS",
            "issue-46-block.md": "Missing machine: this Linux host.",
            "issue-64-block.md": "Missing machine: this Linux host.",
        }
        for name, phrase in blocks.items():
            self.assertIn(phrase, (HANDOFF / name).read_text(encoding="utf-8"), name)

    def test_repro_notes_do_not_apply_a_promotion_verdict(self) -> None:
        banned = re.compile(r"\b(KEEP|REVISE|KILL|KILLED)\b")
        hits = []
        for path in (ROOT / "scripts" / "repro").rglob("*"):
            if path.suffix.lower() not in {".md", ".tsv", ".json", ".txt", ".jsonl"}:
                continue
            if banned.search(path.read_text(encoding="utf-8", errors="replace")):
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
