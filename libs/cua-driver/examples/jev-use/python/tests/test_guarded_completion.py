from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from guarded_completion import plan_guarded_completion, resolve_guarded_completion
from sources import Candidate
from tasks import FixtureFormTask, fixture_sources


def snapshot(value: str, submit_refs: list[str]) -> dict:
    refs = [
        {
            "role": "textbox",
            "name": "verification value",
            "ref": "p1:0",
            "value": value,
        }
    ]
    refs.extend(
        {"role": "button", "name": "Submit", "ref": ref}
        for ref in submit_refs
    )
    return {"target_id": "target", "tab_id": "tab", "refs": refs}


class GuardedCompletionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.task = FixtureFormTask("proof")

    def initial(self):
        sources = fixture_sources(snapshot("", ["p1:1"]))
        selected = self.task.candidates(sources)[0]
        self.assertEqual(selected.id, "type-verification-value")
        return sources, selected

    def test_fresh_unique_completion_uses_only_the_fresh_ref(self) -> None:
        sources, selected = self.initial()
        plan = plan_guarded_completion(self.task, sources, selected, session="session-a")
        self.assertIsNotNone(plan)
        assert plan is not None

        fresh_sources = fixture_sources(snapshot("proof", ["p2:1"]))
        candidates = self.task.candidates(fresh_sources)
        completion = resolve_guarded_completion(
            plan, self.task, fresh_sources, candidates, session="session-a"
        )
        self.assertIsNotNone(completion)
        assert completion is not None
        self.assertEqual(completion.id, "submit-form")
        self.assertEqual(completion.arguments["ref"], "p2:1")
        self.assertNotEqual(completion.arguments["ref"], plan.prior_ref)

    def test_wrong_session_fails_closed(self) -> None:
        sources, selected = self.initial()
        plan = plan_guarded_completion(self.task, sources, selected, session="session-a")
        assert plan is not None
        fresh_sources = fixture_sources(snapshot("proof", ["p2:1"]))
        self.assertIsNone(
            resolve_guarded_completion(
                plan,
                self.task,
                fresh_sources,
                self.task.candidates(fresh_sources),
                session="session-b",
            )
        )

    def test_ambiguous_or_missing_target_fails_closed(self) -> None:
        sources, selected = self.initial()
        plan = plan_guarded_completion(self.task, sources, selected, session="session-a")
        assert plan is not None
        for refs in ([], ["p2:1", "p2:2"]):
            with self.subTest(refs=refs):
                fresh_sources = fixture_sources(snapshot("proof", refs))
                self.assertIsNone(
                    resolve_guarded_completion(
                        plan,
                        self.task,
                        fresh_sources,
                        self.task.candidates(fresh_sources),
                        session="session-a",
                    )
                )

    def test_unverified_first_postcondition_fails_closed(self) -> None:
        sources, selected = self.initial()
        plan = plan_guarded_completion(self.task, sources, selected, session="session-a")
        assert plan is not None
        fresh_sources = fixture_sources(snapshot("other", ["p2:1"]))
        self.assertIsNone(
            resolve_guarded_completion(
                plan,
                self.task,
                fresh_sources,
                self.task.candidates(fresh_sources),
                session="session-a",
            )
        )

    def test_old_or_tampered_ref_never_gains_authority(self) -> None:
        sources, selected = self.initial()
        plan = plan_guarded_completion(self.task, sources, selected, session="session-a")
        assert plan is not None
        fresh_sources = fixture_sources(snapshot("proof", ["p2:1"]))
        bad = Candidate(
            "submit-form",
            "tampered",
            "browser_click",
            {"target_id": "target", "tab_id": "tab", "ref": plan.prior_ref},
            source="page",
        )
        self.assertIsNone(
            resolve_guarded_completion(
                plan, self.task, fresh_sources, [bad], session="session-a"
            )
        )

    def test_plan_requires_unique_initial_logical_target(self) -> None:
        for refs in ([], ["p1:1", "p1:2"]):
            with self.subTest(refs=refs):
                sources = fixture_sources(snapshot("", refs))
                selected = self.task.candidates(sources)[0]
                self.assertIsNone(
                    plan_guarded_completion(
                        self.task, sources, selected, session="session-a"
                    )
                )


if __name__ == "__main__":
    unittest.main()
