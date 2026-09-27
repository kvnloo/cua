"""Live multi-task battery for kvnloo/cua#24.

Reuses the frozen caller rules from #4 and #5. Each workflow has its own
loopback oracle. A trial counts only after the expected route is observed.
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
from urllib.parse import parse_qs

REPS = 10
RULES = "1024f0627322b85b8b0dc3423abc2f7198133207"
DRIVER_SHA = "7ee9b37edc4ebc5f7f606682ae2699d1baa5d397"

PAGES = {
    "fill-submit": """<!doctype html><title>fill</title>
<form method="post" action="/event/fill">
<input name="value" aria-label="verification value">
<button type="submit">Submit</button></form>""",
    "toggle-confirm": """<!doctype html><title>toggle</title>
<input type="checkbox" aria-label="feature">
<button type="button" id="go">Confirm</button>
<script>
document.getElementById("go").onclick = () => {
  const on = document.querySelector("[aria-label=feature]").checked;
  fetch("/event/toggle", {method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded"},
    body:"checked="+(on?"1":"0")});
};
</script>""",
    "two-fields": """<!doctype html><title>fields</title>
<form method="post" action="/event/fields">
<input name="given" aria-label="given name">
<input name="family" aria-label="family name">
<button type="submit">Submit</button></form>""",
    "modal": """<!doctype html><title>modal</title>
<button type="button" id="open">Open dialog</button>
<div id="panel" hidden><button type="button" id="ok">Confirm choice</button></div>
<script>
document.getElementById("open").onclick = () => {
  document.getElementById("panel").hidden = false;
  fetch("/event/opened", {method:"POST"});
};
document.getElementById("ok").onclick = () => fetch("/event/modal", {method:"POST"});
</script>""",
    "ambiguous": """<!doctype html><title>ambiguous</title>
<button type="button" id="left">Submit</button>
<button type="button" id="right">Submit</button>
<script>
for (const id of ["left","right"]) {
  document.getElementById(id).onclick = () => fetch("/event/ambiguous", {method:"POST",
    headers:{"Content-Type":"application/x-www-form-urlencoded"}, body:"which="+id});
}
</script>""",
}


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.data: dict[str, Any] = {}

    def reset(self) -> None:
        with self.lock:
            self.data = {
                "filled": None,
                "checked": None,
                "given": None,
                "family": None,
                "opened": False,
                "modal": False,
                "ambiguous": None,
            }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.data)

    def update(self, **items: Any) -> None:
        with self.lock:
            self.data.update(items)


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/state":
            body = json.dumps(self.server.state.snapshot()).encode()
            self._send(HTTPStatus.OK, "application/json", body)
            return
        task = self.path.removeprefix("/")
        page = PAGES.get(task)
        if page is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send(HTTPStatus.OK, "text/html; charset=utf-8", page.encode())

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode())
        path = self.path
        state = self.server.state
        if path == "/reset":
            state.reset()
        elif path == "/event/fill":
            state.update(filled=(form.get("value") or [""])[0])
        elif path == "/event/toggle":
            state.update(checked=(form.get("checked") or ["0"])[0] == "1")
        elif path == "/event/fields":
            state.update(
                given=(form.get("given") or [""])[0],
                family=(form.get("family") or [""])[0],
            )
        elif path == "/event/opened":
            state.update(opened=True)
        elif path == "/event/modal":
            state.update(modal=True)
        elif path == "/event/ambiguous":
            state.update(ambiguous=(form.get("which") or [""])[0])
        else:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")

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
        self.state = State()
        self.state.reset()
        super().__init__(("127.0.0.1", 0), Handler)


def _named(snapshot: dict[str, Any], role: str, name: str) -> list[dict[str, Any]]:
    return [
        ref
        for ref in snapshot.get("refs") or []
        if ref.get("role") == role and ref.get("name") == name
    ]


def oracle_ok(task: str, state: dict[str, Any], token: str) -> bool:
    if task == "fill-submit":
        return state.get("filled") == token
    if task == "toggle-confirm":
        return state.get("checked") is True
    if task == "two-fields":
        return state.get("given") == token and state.get("family") == token + "-b"
    if task == "modal":
        return state.get("opened") is True and state.get("modal") is True
    if task == "ambiguous":
        return state.get("ambiguous") is None
    return False


def expected_route(task: str, arm: str) -> str:
    if task == "ambiguous":
        return "stop" if arm == "guarded-run" else "chooser"
    if task == "visual-only":
        return "pending"
    if arm == "baseline":
        return "chooser"
    if arm == "bound-fast-path":
        return "chooser"
    if arm == "guarded-run" and task in {"fill-submit", "toggle-confirm", "modal"}:
        return "fast-path"
    return "chooser"


async def _call(driver: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return await driver.call(name, arguments)


async def run_battery(evidence_root: Path, upstream_root: Path, driver_bin: str) -> dict[str, Any]:
    upstream_python = upstream_root / "libs/cua-driver/examples/jev-use/python"
    sys.path.insert(0, str(upstream_python))
    sys.path.insert(0, str(evidence_root / "libs/cua-driver/examples/jev-use/python"))
    import driver_env  # type: ignore
    import run  # type: ignore
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
    tasks = ("fill-submit", "toggle-confirm", "two-fields", "modal", "ambiguous")
    arms = ("baseline", "bound-fast-path", "guarded-run")
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                driver = run.Driver(session, f"battery-{uuid.uuid4().hex[:8]}")
                prepared = await _call(
                    driver, "browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}}
                )
                pid = int(prepared["prepared_pid"])
                window = await run.wait_for_window(driver, pid)
                bound = await _call(
                    driver, "get_browser_state", {"pid": pid, "window_id": window["window_id"]}
                )
                target_id = bound["target_id"]
                tab_id = run.select_tab_id(bound["tabs"])
                for task in tasks:
                    for arm in arms:
                        failures = 0
                        for rep in range(REPS):
                            if failures:
                                break
                            row = await one(
                                driver, run, origin, target_id, tab_id, task, arm, rep,
                                Candidate, explain_fast_path, Decision, FreshObservation,
                                admit_guarded_run, explain_second_child,
                            )
                            if row["correctness_failure"]:
                                failures += 1
                            rows.append(row)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    return {
        "evidence_kind": "issue-24-live-battery",
        "authority_rule": RULES,
        "driver_sha": DRIVER_SHA,
        "driver_bin": driver_bin,
        "visual_only": {
            "task": "visual-only",
            "status": "pending",
            "owner": "issue-2",
            "reason": "perception path was not exercised in this battery",
        },
        "rows": rows,
    }


async def one(driver, run, origin, target_id, tab_id, task, arm, rep, Candidate, explain_fast_path, Decision, FreshObservation, admit_guarded_run, explain_second_child) -> dict[str, Any]:
    token = f"t{rep}-{task[:6]}"
    import urllib.request
    urllib.request.urlopen(urllib.request.Request(origin + "reset", method="POST", data=b""), timeout=2).read()
    started = time.perf_counter()
    await _call(driver, "browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": origin + task})
    snap = await _call(driver, "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
    observations = 1
    actions = 0
    providers = 0
    clicked: list[str] = []
    prior: list[str] = []
    events: list[str] = []
    expected = expected_route(task, arm)
    observed = "chooser"
    route_ok = False
    correctness_failure = False

    async def click(ref: str) -> None:
        nonlocal actions
        await _call(driver, "browser_click", {"target_id": target_id, "tab_id": tab_id, "ref": ref, "input_route": "dom_event"})
        actions += 1
        clicked.append(ref)

    async def type_into(ref: str, text: str) -> None:
        nonlocal actions
        await _call(driver, "browser_type", {"target_id": target_id, "tab_id": tab_id, "ref": ref, "text": text, "replace": True})
        actions += 1

    def controls(snapshot: dict[str, Any]) -> list[Candidate]:
        found = []
        for ref in snapshot.get("refs") or []:
            if ref.get("role") == "textbox":
                found.append(Candidate(f"type-{ref.get('name')}", "type", "browser_type", {}))
            elif ref.get("role") in {"button", "checkbox"}:
                found.append(Candidate(f"click-{ref.get('name')}", "click", "browser_click", {}))
        found.append(Candidate("reobserve", "reobserve", None, {}))
        return found

    try:
        if task == "ambiguous":
            submits = _named(snap, "button", "Submit")
            if len(submits) < 2:
                raise RuntimeError(f"ambiguous page exposed {len(submits)} Submit buttons")
            authority = explain_fast_path(controls(snap), bound_completion_id="click-Submit")
            observed = authority.route
            providers += 1 if authority.provider_called else 0
            route_ok = observed == "chooser"
            if arm == "guarded-run":
                plan = admit_guarded_run(
                    controls(snap), Decision("run", ("click-Submit", "click-Submit")),
                    token=token, submit_ref=str(submits[0]["ref"]),
                    target_role="button", target_name="Submit",
                )
                fresh = FreshObservation(token, None, "cap-live", role="button", name="Submit", match_count=len(submits))
                evidence = explain_second_child("verified", fresh, plan) if plan else None
                observed = "stop" if evidence is None or not evidence.allowed else evidence.reason
                route_ok = evidence is not None and not evidence.allowed
                events.append("ambiguous-stop")
            if clicked:
                correctness_failure = True
                events.append("unauthorized-click")
        elif arm == "guarded-run" and task in {"fill-submit", "toggle-confirm", "modal"}:
            if task == "fill-submit":
                field = _named(snap, "textbox", "verification value")
                button = _named(snap, "button", "Submit")
                if len(field) != 1 or len(button) != 1:
                    raise RuntimeError("fill page identity was not unique")
                prior_ref = str(button[0]["ref"])
                providers += 1
                await type_into(str(field[0]["ref"]), token)
            elif task == "toggle-confirm":
                box = _named(snap, "checkbox", "feature")
                button = _named(snap, "button", "Confirm")
                if len(box) != 1 or len(button) != 1:
                    raise RuntimeError("toggle page identity was not unique")
                prior_ref = str(button[0]["ref"])
                providers += 1
                await click(str(box[0]["ref"]))
            else:
                opener = _named(snap, "button", "Open dialog")
                hidden = _named(snap, "button", "Confirm choice")
                if len(opener) != 1 or hidden:
                    raise RuntimeError("modal confirm was visible before open")
                prior_ref = str(opener[0]["ref"])
                providers += 1
                await click(str(opener[0]["ref"]))
            fresh_snap = await _call(driver, "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
            observations += 1
            target_name = "Submit" if task == "fill-submit" else "Confirm" if task == "toggle-confirm" else "Confirm choice"
            matches = _named(fresh_snap, "button", target_name)
            resolved = str(matches[0]["ref"]) if len(matches) == 1 else None
            plan = admit_guarded_run(
                controls(snap),
                Decision("run", ("child-1", "child-2")),
                token=token,
                submit_ref=prior_ref,
                target_role="button",
                target_name=target_name,
            )
            # The two child ids are the obligation, not snapshot candidate ids.
            if plan is None:
                type_c = Candidate("child-1", "first", "browser_type", {})
                click_c = Candidate("child-2", "second", "browser_click", {})
                plan = admit_guarded_run(
                    [type_c, click_c], Decision("run", ("child-1", "child-2")),
                    token=token, submit_ref=prior_ref, target_role="button", target_name=target_name,
                )
            field_value = token if task != "toggle-confirm" else token
            if task == "toggle-confirm":
                field_value = token
            fresh = FreshObservation(
                field_value, resolved, "cap-live", role="button" if matches else None,
                name=target_name if matches else None, match_count=len(matches), resolved_ref=resolved,
            )
            evidence = explain_second_child("verified", fresh, plan)
            authority = explain_fast_path(
                [Candidate("child-2", "second", "browser_click", {})],
                bound_completion_id=plan.second.candidate_id,
            )
            observed = authority.route if evidence.allowed else evidence.reason
            route_ok = evidence.allowed and authority.route == "fast-path" and evidence.dispatch_ref == resolved
            prior.append(prior_ref)
            if route_ok and resolved and resolved != prior_ref:
                await click(resolved)
            elif route_ok and resolved == prior_ref:
                correctness_failure = True
                events.append("stale-ref")
            else:
                events.append(evidence.reason)
        else:
            # Baseline and bound-fast-path, plus guarded on tasks it must not shorten.
            authority = explain_fast_path(controls(snap), bound_completion_id="click-Submit")
            observed = authority.route
            route_ok = observed == "chooser"
            if not route_ok:
                events.append("unexpected-fast-path")
                correctness_failure = True
            else:
                providers += 1
                if task == "fill-submit":
                    field = _named(snap, "textbox", "verification value")[0]
                    await type_into(str(field["ref"]), token)
                    fresh_snap = await _call(driver, "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
                    observations += 1
                    button = _named(fresh_snap, "button", "Submit")
                    old = _named(snap, "button", "Submit")[0]["ref"]
                    prior.append(str(old))
                    if len(button) != 1 or button[0]["ref"] == old:
                        correctness_failure = True
                        events.append("stale-ref")
                    else:
                        providers += 1
                        await click(str(button[0]["ref"]))
                elif task == "toggle-confirm":
                    box = _named(snap, "checkbox", "feature")[0]
                    await click(str(box["ref"]))
                    fresh_snap = await _call(driver, "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
                    observations += 1
                    button = _named(fresh_snap, "button", "Confirm")
                    old = _named(snap, "button", "Confirm")[0]["ref"]
                    prior.append(str(old))
                    if len(button) != 1:
                        correctness_failure = True
                        events.append("missing-target")
                    else:
                        providers += 1
                        if button[0]["ref"] == old:
                            events.append("ref-stable")
                        await click(str(button[0]["ref"]))
                elif task == "two-fields":
                    given = _named(snap, "textbox", "given name")[0]
                    family = _named(snap, "textbox", "family name")[0]
                    await type_into(str(given["ref"]), token)
                    fresh_snap = await _call(driver, "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
                    observations += 1
                    family_now = _named(fresh_snap, "textbox", "family name")
                    if len(family_now) != 1:
                        correctness_failure = True
                        events.append("missing-field")
                    else:
                        providers += 1
                        await type_into(str(family_now[0]["ref"]), token + "-b")
                        third = await _call(driver, "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
                        observations += 1
                        button = _named(third, "button", "Submit")
                        old = _named(snap, "button", "Submit")[0]["ref"]
                        prior.append(str(old))
                        if len(button) != 1 or button[0]["ref"] == old:
                            correctness_failure = True
                            events.append("stale-ref")
                        else:
                            providers += 1
                            await click(str(button[0]["ref"]))
                elif task == "modal":
                    opener = _named(snap, "button", "Open dialog")[0]
                    await click(str(opener["ref"]))
                    fresh_snap = await _call(driver, "get_browser_state", {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
                    observations += 1
                    button = _named(fresh_snap, "button", "Confirm choice")
                    if len(button) != 1:
                        correctness_failure = True
                        events.append("missing-target")
                    else:
                        providers += 1
                        await click(str(button[0]["ref"]))
                        prior.append(str(opener["ref"]))
        state = json.loads(urllib.request.urlopen(origin + "state", timeout=2).read().decode())
        verified = oracle_ok(task, state, token) and not correctness_failure and route_ok
    except Exception as exc:
        state = {"error": f"{type(exc).__name__}: {exc}"}
        verified = False
        correctness_failure = True
        events.append("exception")
        observed = observed or "exception"
    return {
        "task": task,
        "arm": arm,
        "rep": rep,
        "driver_sha": DRIVER_SHA,
        "authority_rule": RULES,
        "expected_route": expected,
        "observed_route": observed,
        "route_ok": route_ok,
        "provider_decisions": providers,
        "observations": observations,
        "actions": actions,
        "prior_refs": prior,
        "clicked_refs": clicked,
        "events": events,
        "verified_outcome_ms": round((time.perf_counter() - started) * 1000, 2),
        "oracle": state,
        "verified": verified,
        "correctness_failure": correctness_failure,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--driver-bin", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run_battery(args.evidence_root.resolve(), args.upstream_root.resolve(), args.driver_bin))
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    bad = [row for row in report["rows"] if row["correctness_failure"] or not row["route_ok"]]
    print(json.dumps({"event": "wrote", "rows": len(report["rows"]), "bad": len(bad)}))


if __name__ == "__main__":
    main()
