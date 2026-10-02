"""Dry validation (0 HTTP) that the jev-use live-provider request builder accepts
the toggle->confirm and modal->act candidate sets.

For each recorded REAL semantic_v2 snapshot (raw/snapshots/, captured by the
shakedown run of this packet), this builds the step's candidates with the
packet's task specs, calls jev-use ``jev_adapter.choose_for_task`` (the exact
function ``choose_live_for_task`` calls with a real ``TypeSafeClient``) with a
recording client, encodes the captured request with the TypeSafe SDK's own
``prepare_system_one`` (dummy key and an unroutable base URL; nothing is sent),
and decodes the body against the SDK's ``SystemOneRequest`` schema. Every
socket connect is refused and counted; the result must show 0.

    JEV_USE_DIR=<jev-use> <jev-use>/.venv/bin/python validate_live_request.py --out raw/live-request-validation.json
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
JEV = Path(os.environ.get("JEV_USE_DIR", "")).resolve()
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(JEV / "python"))

CONNECTS = {"attempts": 0}


def _refuse(self: socket.socket, address: Any) -> None:  # noqa: ARG001
    CONNECTS["attempts"] += 1
    raise ConnectionRefusedError("validate_live_request: network disabled")


socket.socket.connect = _refuse  # type: ignore[method-assign]
socket.socket.connect_ex = _refuse  # type: ignore[method-assign]

import msgspec  # noqa: E402
from typesafe_sdk._core.config import Config  # noqa: E402
from typesafe_sdk._core.endpoints import prepare_system_one  # noqa: E402
from typesafe_sdk._schemas.models import SystemOneRequest  # noqa: E402

from b01_tasks import ModalTask, ToggleConfirmTask  # noqa: E402
from jev_adapter import choose_for_task  # noqa: E402
from tasks import fixture_sources  # noqa: E402


class RecordingClient:
    """Answer with the first executable candidate and keep each request exactly as sent."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def system_one(self, **request: Any) -> Any:
        self.requests.append(request)
        criteria = request["questions"]["driver_action"].criteria
        choice = next(iter(criteria))
        answer = SimpleNamespace(choice=choice, confidence=1.0, probabilities={choice: 1.0})
        return SimpleNamespace(choices={"driver_action": answer})


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshots", default=str(HERE / "raw" / "snapshots"))
    p.add_argument("--out", required=True)
    args = p.parse_args()
    config = Config("dummy-not-a-key", "http://192.0.2.1", "dry-run-model", 1.0, __import__("httpx2").Headers())
    rows = []
    for cls, task in (("toggle", ToggleConfirmTask("t", "http://127.0.0.1:9/")),
                      ("modal", ModalTask("t", "http://127.0.0.1:9/"))):
        history: list[dict[str, Any]] = []
        for step in (1, 2):
            snap = json.loads((Path(args.snapshots) / f"{cls}-step{step}.json").read_text())
            sources = fixture_sources(snap, None)
            candidates = task.candidates(sources)
            client = RecordingClient()
            choice, _, _ = choose_for_task(client, task, sources, candidates, history)
            request = client.requests[-1]
            prepared = prepare_system_one(config, request["state"], request["questions"], None, None, None, None)
            decoded = msgspec.json.decode(prepared.content, type=SystemOneRequest)
            body = json.loads(prepared.content)
            rows.append({
                "class": cls,
                "step": step,
                "candidate_ids": [c.id for c in candidates],
                "executable_ids": [c.id for c in candidates if c.tool],
                "criteria_ids": sorted(body["questions"]["driver_action"]["criteria"]),
                "question_type": body["questions"]["driver_action"]["type"],
                "state_form": body["state"]["observation"]["form"],
                "schema_valid": isinstance(decoded, SystemOneRequest),
                "body_bytes": len(prepared.content),
                "url_host_is_unroutable_doc_range": prepared.url.startswith("http://192.0.2.1"),
                "recorded_choice": choice,
            })
            history.append(task.history_entry(step, choice))
    result = {"rows": rows, "socket_connect_attempts": CONNECTS["attempts"],
              "provider_http_requests": 0 if CONNECTS["attempts"] == 0 else None,
              "all_schema_valid": all(r["schema_valid"] for r in rows)}
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"all_schema_valid": result["all_schema_valid"], "connects": CONNECTS["attempts"]}))


if __name__ == "__main__":
    main()
