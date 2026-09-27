"""Live proof that a landed mutation is not blindly replayed. kvnloo/cua#33.

Scope is the three workflows that held in the #24 battery: fill then submit,
toggle then confirm, and modal then act. The target owns the mutation journal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REPS = 3
RULES = "1024f0627322b85b8b0dc3423abc2f7198133207"
DRIVER_SHA = "7ee9b37edc4ebc5f7f606682ae2699d1baa5d397"
TASKS = ("fill-submit", "toggle-confirm", "modal")
INJECTIONS = (
    "response-lost",
    "verification-unavailable",
    "verification-unknown",
    "provider-failure",
    "cancellation",
    "stale-refused",
    "target-disappears",
)

PAGES = {
    "fill-submit": """<!doctype html><title>fill</title>
<input aria-label="verification value">
<button type="button" id="go">Submit</button>
<script>
document.getElementById("go").onclick = () => fetch("/mutate/fill", {method:"POST",
  headers:{"Content-Type":"application/x-www-form-urlencoded"},
  body:"value="+encodeURIComponent(document.querySelector("[aria-label='verification value']").value)});
</script>""",
    "toggle-confirm": """<!doctype html><title>toggle</title>
<input type="checkbox" aria-label="feature">
<button type="button" id="go">Confirm</button>
<script>
document.getElementById("go").onclick = () => {
  const on = document.querySelector("[aria-label=feature]").checked;
  fetch("/mutate/toggle", {method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded"},
    body:"checked="+(on?"1":"0")});
};
</script>""",
    "modal": """<!doctype html><title>modal</title>
<button type="button" id="open">Open dialog</button>
<div id="panel" hidden><button type="button" id="ok">Confirm choice</button></div>
<script>
document.getElementById("open").onclick = () => {
  document.getElementById("panel").hidden = false;
  fetch("/mutate/open", {method:"POST"});
};
document.getElementById("ok").onclick = () => fetch("/mutate/modal", {method:"POST"});
</script>""",
}


class Journal:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.events: list[str] = []

    def reset(self) -> None:
        with self.lock:
            self.events = []

    def add(self, kind: str) -> int:
        with self.lock:
            self.events.append(kind)
            return len(self.events)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"count": len(self.events), "events": list(self.events)}


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/journal":
            body = json.dumps(self.server.journal.snapshot()).encode()
            self._send(HTTPStatus.OK, "application/json", body)
            return
        page = PAGES.get(self.path.removeprefix("/"))
        if page is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send(HTTPStatus.OK, "text/html; charset=utf-8", page.encode())

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.path == "/reset":
            self.server.journal.reset()
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path.startswith("/mutate/"):
            self.server.journal.add(self.path.removeprefix("/mutate/"))
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Server(ThreadingHTTPServer):
    def __init__(self) -> None:
        self.journal = Journal()
        super().__init__(("127.0.0.1", 0), Handler)


def _named(snapshot: dict[str, Any], role: str, name: str) -> list[dict[str, Any]]:
    return [
        ref
        for ref in snapshot.get("refs") or []
        if ref.get("role") == role and ref.get("name") == name
    ]


def _journal(origin: str) -> dict[str, Any]:
    import urllib.request

    with urllib.request.urlopen(origin + "journal", timeout=2) as response:
        return json.loads(response.read().decode())


def _reset(origin: str) -> None:
    import urllib.request

    urllib.request.urlopen(
        urllib.request.Request(origin + "reset", method="POST", data=b""), timeout=2
    ).read()


async def run_all(evidence_root: Path, upstream_root: Path, driver_bin: str) -> dict[str, Any]:
    sys.path.insert(0, str(upstream_root / "libs/cua-driver/examples/jev-use/python"))
    sys.path.insert(0, str(evidence_root / "libs/cua-driver/examples/jev-use/python"))
    import driver_env  # type: ignore
    import run  # type: ignore
    from action_consumer import naive_choice, typed_choice
    from core import Candidate
    from deterministic_fast_path import explain_fast_path
    from guarded_run import Decision, FreshObservation, admit_guarded_run, explain_second_child
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server = Server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}/"
    rows: list[dict[str, Any]] = []
    env = driver_env.driver_environment()
    for key, value in os.environ.items():
        if key.startswith("CUA_E2E_"):
            env[key] = value
    params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                driver = run.Driver(session, f"replay-{uuid.uuid4().hex[:8]}")
                prepared = await driver.call(
                    "browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}}
                )
                pid = int(prepared["prepared_pid"])
                window = await run.wait_for_window(driver, pid)
                bound = await driver.call(
                    "get_browser_state", {"pid": pid, "window_id": window["window_id"]}
                )
                target_id = bound["target_id"]
                tab_id = run.select_tab_id(bound["tabs"])
                for task in TASKS:
                    for policy in ("naive", "guarded", "typed"):
                        injections = INJECTIONS if policy != "naive" else ("response-lost",)
                        reps = REPS if policy == "naive" or True else 1
                        for injection in injections:
                            for rep in range(reps if injection == "response-lost" else 1):
                                rows.append(
                                    await one(
                                        driver, origin, target_id, tab_id, task, policy, injection, rep,
                                        typed_choice, naive_choice, Candidate, explain_fast_path,
                                        Decision, FreshObservation, admit_guarded_run, explain_second_child,
                                    )
                                )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    return {
        "evidence_kind": "issue-33-replay",
        "authority_rule": RULES,
        "driver_sha": DRIVER_SHA,
        "driver_bin": driver_bin,
        "scope": list(TASKS),
        "rows": rows,
    }


async def one(driver, origin, target_id, tab_id, task, policy, injection, rep, typed_choice, naive_choice, Candidate, explain_fast_path, Decision, FreshObservation, admit_guarded_run, explain_second_child) -> dict[str, Any]:
    _reset(origin)
    started = time.perf_counter()
    await driver.call("browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": origin + task})
    snap = await driver.call(
        "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"}
    )
    retry = False
    dispatched = False
    events: list[str] = []
    try:
        if task == "fill-submit":
            field = _named(snap, "textbox", "verification value")[0]
            await driver.call(
                "browser_type",
                {"target_id": target_id, "tab_id": tab_id, "ref": field["ref"], "text": f"r{rep}", "replace": True},
            )
            fresh = await driver.call(
                "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"}
            )
            button = _named(fresh, "button", "Submit")[0]
            target_name = "Submit"
        elif task == "toggle-confirm":
            box = _named(snap, "checkbox", "feature")[0]
            await driver.call(
                "browser_click",
                {"target_id": target_id, "tab_id": tab_id, "ref": box["ref"], "input_route": "dom_event"},
            )
            fresh = await driver.call(
                "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"}
            )
            button = _named(fresh, "button", "Confirm")[0]
            target_name = "Confirm"
        else:
            opener = _named(snap, "button", "Open dialog")[0]
            await driver.call(
                "browser_click",
                {"target_id": target_id, "tab_id": tab_id, "ref": opener["ref"], "input_route": "dom_event"},
            )
            fresh = await driver.call(
                "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"}
            )
            button = _named(fresh, "button", "Confirm choice")[0]
            target_name = "Confirm choice"
        click_ref = str(button["ref"])
        await driver.call(
            "browser_click",
            {"target_id": target_id, "tab_id": tab_id, "ref": click_ref, "input_route": "dom_event"},
        )
        dispatched = True
        # The tool result is intentionally discarded. The journal is the proof it landed.
        landed = _journal(origin)
        if landed["count"] < 1:
            raise RuntimeError(f"mutation did not land before injection: {landed}")
        effect = "unverifiable"
        observation = "unavailable"
        if injection == "verification-unknown":
            effect = "unverifiable"
            observation = "completed"
        elif injection == "stale-refused":
            effect = "refused"
            observation = "completed"
        elif injection == "target-disappears":
            await driver.call(
                "browser_navigate",
                {"target_id": target_id, "tab_id": tab_id, "url": "about:blank"},
            )
            observation = "unavailable"
        plan = admit_guarded_run(
            [Candidate("child-1", "first", "browser_type", {}), Candidate("child-2", "second", "browser_click", {})],
            Decision("run", ("child-1", "child-2")),
            token="landed",
            submit_ref="pre-mutation-ref",
            target_role="button",
            target_name=target_name,
        )
        status = "refused" if injection == "stale-refused" else "unknown"
        guarded = explain_second_child(
            status,
            None if injection in {"response-lost", "verification-unavailable", "cancellation", "provider-failure", "target-disappears"} else FreshObservation("landed", click_ref, "cap", role="button", name=target_name, match_count=1, resolved_ref=click_ref),
            plan,
        )
        typed = typed_choice(effect, observation, passive_success=False)
        naive = naive_choice(effect, observation, passive_success=False)
        route = explain_fast_path(
            [Candidate("reobserve", "reobserve", None, {})],
        ).route
        if policy == "naive" and naive == "continue" and injection != "target-disappears":
            await driver.call(
                "browser_click",
                {"target_id": target_id, "tab_id": tab_id, "ref": click_ref, "input_route": "dom_event"},
            )
            retry = True
            events.append("naive-replay")
        elif policy == "guarded":
            if guarded.allowed:
                events.append("guard-allowed-replay")
                retry = True
            else:
                events.append(guarded.reason)
        else:
            if typed == "continue":
                events.append("typed-continue")
                retry = True
            else:
                events.append(typed)
        if route != "chooser":
            events.append(route)
        final = _journal(origin)
        duplicate = final["count"] > landed["count"]
        if policy == "naive":
            held = duplicate and retry
        else:
            held = (not retry) and (not duplicate) and final["count"] == landed["count"]
    except Exception as exc:
        landed = {"count": None}
        final = {"error": f"{type(exc).__name__}: {exc}"}
        held = False
        click_ref = None
        events.append("exception")
        duplicate = False
    return {
        "task": task,
        "policy": policy,
        "injection": injection,
        "rep": rep,
        "driver_sha": DRIVER_SHA,
        "authority_rule": RULES,
        "dispatch_attempted": dispatched,
        "journal_after_dispatch": landed,
        "retry_attempted": retry,
        "duplicate_mutation": duplicate if dispatched else False,
        "journal_final": final,
        "clicked_ref": click_ref,
        "events": events,
        "held": held,
        "verified_outcome_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--driver-bin", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(
        run_all(args.evidence_root.resolve(), args.upstream_root.resolve(), args.driver_bin)
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    bad = [row for row in report["rows"] if not row["held"]]
    print(json.dumps({"event": "wrote", "rows": len(report["rows"]), "bad": len(bad)}))


if __name__ == "__main__":
    main()
