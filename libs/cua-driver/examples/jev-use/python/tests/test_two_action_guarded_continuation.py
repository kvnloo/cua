"""Two-action guarded continuation journals (kvnloo/cua#5 / #3963 gap).

Invariant ``two_action_guarded_continuation``:
  1. Happy path attributes provider→guarded-completion with
     provider_decisions=1, actions_dispatched=2, guarded_child_admitted.
  2. Pending plan is single-shot: after any resolve attempt the plan is
     consumed; a third step cannot auto-admit another guarded child.
  3. Failed child-2 proof (postcondition / stale ref) ⇒ second_dispatch=0,
     route=chooser, plan still consumed.
  4. Receipts are content-free.

Not covered by fork #79 (single-resolve session authority), #4317 (browser
ref isolation), or #4318 (element_token schema). Avoids #26 generic
one-candidate fast path.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from tasks import FixtureFormTask, fixture_sources
from two_action_continuation import journal_two_action_continuation


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


class TwoActionGuardedContinuationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.task = FixtureFormTask("proof-token")
        self.session = "session-a"
        self.initial = fixture_sources(snapshot("", ["p1:1"]))

    def test_happy_path_provider_then_guarded_completion(self) -> None:
        fresh = fixture_sources(snapshot("proof-token", ["p2:1"]))
        journal = journal_two_action_continuation(
            self.task, self.initial, fresh, session=self.session
        )
        self.assertEqual(
            list(journal.decision_routes), ["provider", "guarded-completion"]
        )
        self.assertEqual(journal.provider_decisions, 1)
        self.assertEqual(journal.actions_dispatched, 2)
        self.assertTrue(journal.guarded_child_admitted)
        self.assertTrue(journal.second_dispatch_attempted)
        self.assertTrue(journal.plan_consumed)
        self.assertEqual(journal.steps[0].candidate_id, "type-verification-value")
        self.assertEqual(journal.steps[1].candidate_id, "submit-form")
        self.assertTrue(journal.steps[0].plan_pending_after)
        self.assertFalse(journal.steps[1].plan_pending_after)
        self.assertFalse(journal.steps[1].provider_called)

    def test_failed_postcondition_clears_authority_no_second_dispatch(self) -> None:
        # Wrong token ⇒ postcondition unverified ⇒ resolve fails closed.
        fresh = fixture_sources(snapshot("wrong-token", ["p2:1"]))
        journal = journal_two_action_continuation(
            self.task, self.initial, fresh, session=self.session
        )
        self.assertEqual(list(journal.decision_routes), ["provider", "chooser"])
        self.assertEqual(journal.provider_decisions, 2)
        self.assertEqual(journal.actions_dispatched, 1)
        self.assertFalse(journal.guarded_child_admitted)
        self.assertFalse(journal.second_dispatch_attempted)
        self.assertTrue(journal.plan_consumed)
        self.assertFalse(journal.steps[1].dispatch_attempted)

    def test_stale_ref_clears_authority_no_second_dispatch(self) -> None:
        # Reuse prior submit ref ⇒ stale_or_reused_ref ⇒ no child-2 dispatch.
        fresh = fixture_sources(snapshot("proof-token", ["p1:1"]))
        journal = journal_two_action_continuation(
            self.task, self.initial, fresh, session=self.session
        )
        self.assertEqual(list(journal.decision_routes), ["provider", "chooser"])
        self.assertEqual(journal.actions_dispatched, 1)
        self.assertFalse(journal.guarded_child_admitted)
        self.assertFalse(journal.second_dispatch_attempted)
        self.assertTrue(journal.plan_consumed)

    def test_consumed_plan_does_not_authorize_third_step(self) -> None:
        fresh = fixture_sources(snapshot("proof-token", ["p2:1"]))
        third = fixture_sources(snapshot("proof-token", ["p3:1"]))
        journal = journal_two_action_continuation(
            self.task,
            self.initial,
            fresh,
            session=self.session,
            third_sources=third,
        )
        self.assertEqual(
            list(journal.decision_routes),
            ["provider", "guarded-completion", "chooser"],
        )
        self.assertEqual(journal.provider_decisions, 2)
        self.assertEqual(journal.actions_dispatched, 2)
        self.assertTrue(journal.guarded_child_admitted)
        self.assertTrue(journal.plan_consumed)
        self.assertEqual(journal.steps[2].route, "chooser")
        self.assertFalse(journal.steps[2].dispatch_attempted)
        self.assertTrue(journal.steps[2].provider_called)

    def test_journal_dict_is_content_free(self) -> None:
        fresh = fixture_sources(snapshot("proof-token", ["p2:1"]))
        payload = journal_two_action_continuation(
            self.task, self.initial, fresh, session=self.session
        ).as_dict()
        forbidden = ("proof-token", "password", "authorization", "image_base64")
        text = str(payload).lower()
        for value in forbidden:
            self.assertNotIn(value, text)
        self.assertEqual(
            set(payload),
            {
                "provider_decisions",
                "actions_dispatched",
                "guarded_child_admitted",
                "decision_routes",
                "plan_consumed",
                "second_dispatch_attempted",
                "steps",
            },
        )


if __name__ == "__main__":
    unittest.main()
