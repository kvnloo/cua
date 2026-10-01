"""Session-authority + exact single-candidate receipts for bound completion.

Invariant (kvnloo/cua#36 row not covered by trycua/cua#4317):
  No GuardedCompletionPlan / bound_completion_id minted in session A may
  authorize a provider-skip (or mutation) in session B. Admission requires
  exact one executable completion candidate in the same named session.

#4317 proves browser target/tab/ref isolation. This leaf proves the
guarded-caller-state / bound-completion row with content-free route receipts.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from bound_completion_authority import explain_bound_completion
from guarded_completion import plan_guarded_completion
from sources import Candidate
from tasks import FixtureFormTask, fixture_sources


def snapshot(value: str, submit_refs: list[str], *, field_ref: str = "p1:0") -> dict:
    refs = [
        {
            "role": "textbox",
            "name": "verification value",
            "ref": field_ref,
            "value": value,
        }
    ]
    refs.extend(
        {"role": "button", "name": "Submit", "ref": ref} for ref in submit_refs
    )
    return {"target_id": "target", "tab_id": "tab", "refs": refs}


class BoundCompletionSessionAuthorityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.task_a = FixtureFormTask("token-a")
        self.task_b = FixtureFormTask("token-b")
        # Independent target-owned journals. A foreign admit must not flip them.
        self.journal_a = {"submitted": None, "owner": "A"}
        self.journal_b = {"submitted": None, "owner": "B"}

    def _plan(self, task: FixtureFormTask, session: str, prior_ref: str = "p1:1"):
        sources = fixture_sources(snapshot("", [prior_ref]))
        selected = task.candidates(sources)[0]
        self.assertEqual(selected.id, "type-verification-value")
        plan = plan_guarded_completion(task, sources, selected, session=session)
        self.assertIsNotNone(plan)
        assert plan is not None
        return plan

    def _fresh(self, task: FixtureFormTask, token: str, submit_ref: str = "p2:1"):
        sources = fixture_sources(snapshot(token, [submit_ref]))
        return sources, task.candidates(sources)

    def test_exact_single_candidate_admits_guarded_route(self) -> None:
        plan = self._plan(self.task_a, "session-a")
        sources, candidates = self._fresh(self.task_a, "token-a")
        evidence = explain_bound_completion(
            plan, self.task_a, sources, candidates, session="session-a"
        )
        self.assertEqual(evidence.route, "guarded-completion")
        self.assertEqual(evidence.reason, "allowed")
        self.assertEqual(evidence.executable_count, 1)
        self.assertFalse(evidence.provider_called)
        self.assertTrue(evidence.dispatch_attempted)
        self.assertEqual(evidence.selected_id, "submit-form")
        self.journal_a["submitted"] = "token-a"
        self.assertEqual(self.journal_b, {"submitted": None, "owner": "B"})

    def test_non_unique_completion_falls_to_chooser(self) -> None:
        plan = self._plan(self.task_a, "session-a")
        sources, _ = self._fresh(self.task_a, "token-a")
        dup = Candidate(
            "submit-form",
            "dup",
            "browser_click",
            {"target_id": "target", "tab_id": "tab", "ref": "p2:1"},
            source="page",
        )
        for candidates, count in (
            ([], 0),
            (
                [
                    Candidate(
                        "submit-form",
                        "a",
                        "browser_click",
                        {"target_id": "target", "tab_id": "tab", "ref": "p2:1"},
                        source="page",
                    ),
                    dup,
                ],
                2,
            ),
        ):
            with self.subTest(executable_count=count):
                evidence = explain_bound_completion(
                    plan, self.task_a, sources, candidates, session="session-a"
                )
                self.assertEqual(evidence.route, "chooser")
                self.assertEqual(evidence.reason, "non_unique_completion")
                self.assertEqual(evidence.executable_count, count)
                self.assertTrue(evidence.provider_called)
                self.assertFalse(evidence.dispatch_attempted)
                self.assertIsNone(evidence.selected_id)

    def test_bidirectional_session_mismatch_never_dispatches(self) -> None:
        plan_a = self._plan(self.task_a, "session-a", prior_ref="p1:a")
        plan_b = self._plan(self.task_b, "session-b", prior_ref="p1:b")
        fresh_a, cands_a = self._fresh(self.task_a, "token-a", "p2:a")
        fresh_b, cands_b = self._fresh(self.task_b, "token-b", "p2:b")

        a_to_b = explain_bound_completion(
            plan_a, self.task_a, fresh_a, cands_a, session="session-b"
        )
        b_to_a = explain_bound_completion(
            plan_b, self.task_b, fresh_b, cands_b, session="session-a"
        )

        for evidence, label in ((a_to_b, "A→B"), (b_to_a, "B→A")):
            with self.subTest(direction=label):
                self.assertEqual(evidence.route, "chooser")
                self.assertEqual(evidence.reason, "session_mismatch")
                self.assertTrue(evidence.provider_called)
                self.assertFalse(evidence.dispatch_attempted)
                self.assertIsNone(evidence.selected_id)

        # Independent journals unchanged after deliberate cross-use.
        self.assertEqual(self.journal_a, {"submitted": None, "owner": "A"})
        self.assertEqual(self.journal_b, {"submitted": None, "owner": "B"})

    def test_foreign_attempt_does_not_poison_owning_plan(self) -> None:
        plan_a = self._plan(self.task_a, "session-a")
        sources, candidates = self._fresh(self.task_a, "token-a")

        foreign = explain_bound_completion(
            plan_a, self.task_a, sources, candidates, session="session-b"
        )
        self.assertEqual(foreign.reason, "session_mismatch")
        self.assertFalse(foreign.dispatch_attempted)

        own = explain_bound_completion(
            plan_a, self.task_a, sources, candidates, session="session-a"
        )
        self.assertEqual(own.route, "guarded-completion")
        self.assertEqual(own.reason, "allowed")
        self.assertTrue(own.dispatch_attempted)
        self.assertFalse(own.provider_called)
        self.journal_a["submitted"] = "token-a"
        self.assertEqual(self.journal_b, {"submitted": None, "owner": "B"})

    def test_receipt_dict_is_content_free(self) -> None:
        plan = self._plan(self.task_a, "session-a")
        sources, candidates = self._fresh(self.task_a, "token-a")
        payload = explain_bound_completion(
            plan, self.task_a, sources, candidates, session="session-a"
        ).as_dict()
        forbidden = ("token-a", "proof", "password", "authorization", "image_base64")
        text = str(payload).lower()
        for value in forbidden:
            self.assertNotIn(value, text)
        self.assertEqual(
            set(payload),
            {
                "route",
                "reason",
                "executable_count",
                "provider_called",
                "plan_session",
                "resolve_session",
                "selected_id",
                "dispatch_attempted",
            },
        )


if __name__ == "__main__":
    unittest.main()
