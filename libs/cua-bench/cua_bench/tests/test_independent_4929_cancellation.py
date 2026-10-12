"""Evidence-only: fake desktop boundary, genuine adapter and offline verifier."""
import asyncio
import json

import pytest

from cua_bench.batch.action_evidence import EvidenceSession
from cua_bench.types import ClickAction
from cua_bench.verify_execution import verify_execution

from .test_verify_execution import make_receipts


class BoundaryDesktop:
    def __init__(self, outcome):
        self.outcome = outcome
        self.entered = asyncio.Event()
        self.unreleased = asyncio.Event()
        self.mutations = 0

    async def screenshot(self):
        return b"constant synthetic desktop observation"

    async def _perform(self):
        self.entered.set()
        if self.outcome == "cancel":
            await self.unreleased.wait()
        if self.outcome == "error":
            raise RuntimeError("controlled boundary error")
        self.mutations += 1
        return "boundary returned"

    async def execute_action(self, action):
        return await self._perform()

    async def click_element(self, pid, selector):
        return await self._perform()


async def produced_receipt(root, method, outcome):
    execution_id = "independent-cancellation-fixture"
    # Owner fixtures create structurally valid synthetic oracle/cleanup artifacts.
    # The adapter replaces their provisional action file with its actual output.
    make_receipts(root, execution_id)
    desktop = BoundaryDesktop(outcome)
    session = EvidenceSession(desktop, root / "task_0_agent_logs", execution_id)
    call = (session.execute_action(ClickAction(x=1, y=2)) if method == "execute_action"
            else session.click_element(1, "#synthetic-target"))
    task = asyncio.create_task(call)
    if outcome == "cancel":
        await asyncio.wait_for(desktop.entered.wait(), timeout=2)
        assert not desktop.unreleased.is_set()
        assert task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
        assert desktop.mutations == 0
    elif outcome == "error":
        with pytest.raises(RuntimeError, match="controlled boundary error"):
            await task
        assert desktop.mutations == 0
    else:
        assert await task == "boundary returned"
        assert desktop.mutations == 1
    rows = (root / "task_0_agent_logs" / "executed-actions.jsonl").read_text().splitlines()
    assert len(rows) == 1
    event = json.loads(rows[0])
    return event, desktop, verify_execution(root, 0, execution_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["execute_action", "click_element"])
@pytest.mark.parametrize("outcome", ["cancel", "return", "error"])
async def test_receipt_distinguishes_cancellation(tmp_path, method, outcome):
    event, desktop, report = await produced_receipt(tmp_path, method, outcome)
    print("EVIDENCE", json.dumps({"method": method, "outcome": outcome,
        "mutations": desktop.mutations, "event": event, "verifier": report}, sort_keys=True))
    if outcome == "return":
        assert event["execution_status"] == "returned"
        assert event["error_type"] is None
        assert report["run_accepted"] is True
    elif outcome == "error":
        assert event["execution_status"] == "failed"
        assert event["error_type"] == "RuntimeError"
        assert report["failed_action_count"] == 1
        assert report["run_accepted"] is False
    else:
        assert event["execution_status"] == "failed"
        assert event["error_type"] == "CancelledError"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["execute_action", "click_element"])
async def test_offline_verifier_rejects_actual_cancelled_receipt(tmp_path, method):
    event, desktop, report = await produced_receipt(tmp_path, method, "cancel")
    print("OFFLINE_EVIDENCE", json.dumps({"method": method, "mutations": desktop.mutations,
        "event": event, "verifier": report}, sort_keys=True))
    assert desktop.mutations == 0
    assert report["checks"]["oracle"] is True
    assert report["checks"]["cleanup"] is True
    assert report["checks"]["actions"] is True
    assert report["run_accepted"] is False
