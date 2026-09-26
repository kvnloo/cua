"""Exact-head outcome A/B for trycua/cua#4165 lazy vision (kvnloo/cua#64).

HEAD pinned: 24aaf8d1965b3b7c1530cbb9d58758ec89472d92 (upstream main merge of
#4196, which salvaged #4165's lazy-parse ordering + invariance test).

Arm A (--visual-observation auto): #4165 lazy ordering - capture+parse only
    when the page structure offers no executable candidate.
Arm B (--visual-observation always): pre-#4165 behaviour, restored through the
    exact head's own flag - parse every step.

Both arms drive the exact head's `run.candidates_for_step`,
`run.observe_visual`, `core.build_candidates` and the mock chooser. The only
substitution is the Driver transport: this host has no Driver daemon, no
browser, and no cua-perception extension, so a fake async Driver stands in for
the cua-driver MCP stdio transport. It serves the exact page-structure
snapshot refs the real driver produces, a `parse_visual_regions` payload that
passes the head's `parse_visual_regions` validation, and performs real form
submissions against the real `fixture_server.py` over HTTP. The outcome
oracle (`/state` == token) is the fixture server's own.

Fixture matrices: default fixture (semantic Submit ref) x visual fixture
(--visual-fixture: role=presentation Submit, no DOM ref, visual path only).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import os

STUBS = Path(os.environ.get("AB64_STUBS", Path(__file__).resolve().parent / "stubs"))
HEAD = Path(os.environ.get("AB64_HEAD", Path(__file__).resolve().parent / "exact-head"))
PYTHON = HEAD / "libs" / "cua-driver" / "examples" / "jev-use" / "python"
EXAMPLE = HEAD / "libs" / "cua-driver" / "examples" / "jev-use"

sys.path.insert(0, str(STUBS))
sys.path.insert(0, str(PYTHON))
sys.path.insert(0, str(EXAMPLE))

import run  # noqa: E402  (exact head code under test)
from core import choose_mock, classify, validate_choice  # noqa: E402
from fixture_server import FixtureServer  # noqa: E402

PID = 4242
WINDOW_ID = 7
CAP_COUNTER = {"n": 0}


class FakeDriver:
    """Stand-in for the cua-driver MCP stdio transport (this host has none)."""

    def __init__(self, fixture_url: str, visual_fixture: bool):
        self.fixture_url = fixture_url.rstrip("/")
        self.visual_fixture = visual_fixture
        self.typed: str | None = None
        self.visual_tool_calls = 0  # get_window_state + parse_visual_regions calls

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "browser_prepare":
            return {"prepared_pid": PID}
        if name == "list_windows":
            return {
                "windows": [
                    {
                        "window_id": WINDOW_ID,
                        "is_on_screen": True,
                        "bounds": {"width": 1280, "height": 800},
                    }
                ]
            }
        if name == "browser_navigate":
            return {}
        if name == "get_browser_state":
            snapshot = arguments.get("snapshot_format")
            if snapshot == "semantic_v2":
                refs = [
                    {
                        "role": "textbox",
                        "name": "verification value",
                        "ref": "p1:0",
                        "value": self.typed,
                    }
                ]
                if not self.visual_fixture:
                    refs.append({"role": "button", "name": "Submit", "ref": "p1:1"})
                return {
                    "target_id": "target-1",
                    "tab_id": "tab-1",
                    "refs": refs,
                    "page": {"url": self.fixture_url + "/"},
                }
            return {
                "target_id": "target-1",
                "tabs": [{"tab_id": "tab-1", "active": True}],
            }
        if name == "get_window_state":
            self.visual_tool_calls += 1
            CAP_COUNTER["n"] += 1
            return {"capture_id": f"cap-{CAP_COUNTER['n']}", "pid": PID, "window_id": WINDOW_ID}
        if name == "parse_visual_regions":
            self.visual_tool_calls += 1
            capture_id = arguments["capture_id"]
            return {
                "schema": "cua.visual_regions_v1",
                "capture": {
                    "capture_id": capture_id,
                    "source": {"kind": "window", "pid": PID, "window_id": WINDOW_ID},
                    "screenshot": {
                        "mime_type": "image/png",
                        "reference": "fake-ref-1",
                        "width": 800,
                        "height": 600,
                    },
                    "action_coordinate_space": {"kind": "screenshot_pixels"},
                },
                "regions": [
                    {
                        "id": "r1",
                        "kind": "text",
                        "text": "Submit",
                        "label": None,
                        "confidence": 0.95,
                        "interactive": True,
                        "bounds": {"x": 320, "y": 400, "width": 160, "height": 48},
                    }
                ],
            }
        if name == "browser_type":
            self.typed = arguments["text"]
            return {}
        if name == "browser_click":
            # Semantic Submit: real drivers synthesize the DOM event; the
            # fake performs the equivalent form submission to the oracle.
            if self.visual_fixture:
                raise RuntimeError("browser_click has no Submit ref on the visual fixture")
            if self.typed is None:
                raise RuntimeError("no value typed")
            self._submit(self.typed)
            return {}
        if name == "click":
            # Capture-bound visual click on the unique Submit region.
            if self.typed is None:
                raise RuntimeError("no value typed")
            self._submit(self.typed)
            return {}
        raise RuntimeError(f"fake driver: unknown tool {name}")

    def _submit(self, value: str) -> None:
        body = urlencode({"value": value}).encode()
        request = Request(f"{self.fixture_url}/submit", data=body, method="POST")
        with urlopen(request, timeout=5) as response:
            response.read()


def fixture_state(fixture_url: str) -> dict[str, Any]:
    with urlopen(f"{fixture_url}/state", timeout=5) as response:
        return json.loads(response.read())


def serve_fixture(visual: bool, port: int) -> FixtureServer:
    server = FixtureServer(("127.0.0.1", port), visual=visual)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def reset_fixture(fixture_url: str) -> None:
    request = Request(f"{fixture_url}/reset", method="POST", data=b"")
    with urlopen(request, timeout=5) as response:
        if response.status != 204:
            raise RuntimeError(f"fixture reset failed: HTTP {response.status}")


async def run_arm(
    fixture_url: str,
    visual_fixture: bool,
    visual_mode: str,
    token: str,
    max_steps: int = 4,
) -> dict[str, Any]:
    """Faithful replication of run.py's main loop with the fake Driver.

    Replicates: oracle check at step start, semantic snapshot, exact
    `run.candidates_for_step`, mock chooser, `validate_choice`, action
    execution, submit-oracle polling after a submit candidate.
    """
    driver = FakeDriver(fixture_url, visual_fixture)
    history: list[dict[str, Any]] = []
    visual_records: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    reset_fixture(fixture_url)

    prepared = await driver.call("browser_prepare", {"allow_launch": True})
    pid = int(prepared["prepared_pid"])
    bound = await driver.call("get_browser_state", {"pid": pid})
    target_id, tab_id = bound["target_id"], bound["tabs"][0]["tab_id"]
    await driver.call(
        "browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": fixture_url}
    )

    for step in range(1, max_steps + 1):
        oracle = fixture_state(fixture_url)
        current = classify(oracle.get("submitted"), token, steps=step - 1, max_steps=max_steps)
        if current in {"verified", "refuted"}:
            outcome = current
            break

        snapshot = await driver.call(
            "get_browser_state",
            {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"},
        )
        candidates, visual, visual_record = await run.candidates_for_step(
            driver,
            snapshot,
            token,
            pid,
            WINDOW_ID,
            {"get_window_state", "parse_visual_regions"},
            True,  # capture_bound_click
            visual_mode=visual_mode,
        )
        visual_records.append({"step": step, **visual_record})
        if not candidates:
            outcome = "abstained"
            break

        choice, confidence, probabilities = choose_mock(candidates)
        if choice is None:
            outcome = "abstained"
            break
        candidate = validate_choice(
            choice, candidates, current_capture_id=visual.capture_id if visual else None
        )

        if candidate.id == "reobserve":
            history.append({"event": "step", "step": step, "candidate": candidate.id})
            continue
        if candidate.id == "abstain":
            outcome = "abstained"
            break

        started = time.perf_counter()
        await driver.call(candidate.tool, dict(candidate.arguments))
        action_ms = round((time.perf_counter() - started) * 1000, 2)
        event = {
            "event": "step",
            "step": step,
            "candidate": candidate.id,
            "tool": candidate.tool,
            "action_ms": action_ms,
            "visual": visual_record,
        }
        history.append(event)
        events.append(event)

        if candidate.id in run.SUBMIT_IDS:
            for _ in range(20):
                oracle = fixture_state(fixture_url)
                current = classify(
                    oracle.get("submitted"), token, steps=step, max_steps=max_steps
                )
                if current in {"verified", "refuted"}:
                    outcome = current
                    break
                await asyncio.sleep(0.1)
            if "outcome" in locals():
                break
    else:
        oracle = fixture_state(fixture_url)
        outcome = classify(
            oracle.get("submitted"), token, steps=max_steps, max_steps=max_steps
        )

    return {
        "outcome": outcome,
        "steps": len(events),
        "visual_records": visual_records,
        "visual_tool_calls": driver.visual_tool_calls,
        "tools_acted": [e["tool"] for e in events],
        "candidates_acted": [e["candidate"] for e in events],
    }


async def main() -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(HEAD),
        capture_output=True,
        text=True,
    ).stdout.strip()

    servers: dict[tuple[str, int], FixtureServer] = {}
    matrix = [
        ("auto", False, 8765),    # arm A, default fixture
        ("always", False, 8766),  # arm B, default fixture
        ("auto", True, 8767),     # arm A, visual fixture
        ("always", True, 8768),   # arm B, visual fixture
    ]
    for _, visual_fixture, port in matrix:
        servers[(str(visual_fixture), port)] = serve_fixture(visual_fixture, port)

    results = []
    for visual_mode, visual_fixture, port in matrix:
        fixture_url = f"http://127.0.0.1:{port}/"
        token = f"ab-{visual_mode}-{int(visual_fixture)}"
        started = time.perf_counter()
        result = await run_arm(fixture_url, visual_fixture, visual_mode, token)
        elapsed = round(time.perf_counter() - started, 3)
        results.append(
            {
                "visual_mode": visual_mode,
                "fixture": "visual" if visual_fixture else "default",
                "elapsed_s": elapsed,
                **result,
            }
        )

    print(json.dumps({"head": head, "results": results}, indent=2, sort_keys=False))

    # Hard assertions: the invariance claim the A/B exists to prove.
    by_key = {(r["visual_mode"], r["fixture"]): r for r in results}
    assert all(
        r["outcome"] == "verified" for r in results
    ), f"completed-task outcome must be verified in every arm: {results}"
    assert by_key[("auto", "default")]["visual_tool_calls"] == 0
    assert by_key[("auto", "visual")]["visual_tool_calls"] == 2  # one observation, two tool calls
    assert by_key[("always", "default")]["visual_tool_calls"] == 4  # two steps x two calls
    assert by_key[("always", "visual")]["visual_tool_calls"] == 4
    print("INVARIANCE_OK: all arms verified; visual spend auto<always on both fixtures")


if __name__ == "__main__":
    asyncio.run(main())
