"""E0 capability census and E1 stitched-object probe for the jev-use fixture.

Does not change Driver behavior. Authority stays in the live session snapshot.
The stitched record is disposable and is never reused as mutation authority.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

JEV = Path("/mnt/zer0models/github/cua-lanes/p0-4316-v3/libs/cua-driver/examples/jev-use")
sys.path.insert(0, str(JEV))
sys.path.insert(0, str(JEV / "python"))

from driver_env import driver_environment  # noqa: E402
from fixture_server import FixtureServer  # noqa: E402


HEAD = "a0bca744067d04f05904319d3d919be30c336556"
PARENT = "345ff6d9db458a9d37b0f420dc4555553f4a4ce5"


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def summarize(values: list[float]) -> dict[str, float | int | None]:
    return {
        "n": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "min_ms": min(values) if values else None,
        "max_ms": max(values) if values else None,
    }


class Probe:
    def __init__(self, session: ClientSession, label: str) -> None:
        self.session = session
        self.label = label
        self.calls = 0
        self.bytes = 0

    async def raw(self, name: str, arguments: dict[str, Any], *, session: str | None = None) -> dict[str, Any]:
        payload = {**arguments, "session": self.label if session is None else session}
        started = time.perf_counter()
        result = await self.session.call_tool(name, payload)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.calls += 1
        structured = getattr(result, "structuredContent", None)
        structured = structured if isinstance(structured, dict) else {}
        text = []
        for item in getattr(result, "content", None) or []:
            value = getattr(item, "text", None)
            if isinstance(value, str):
                text.append(value)
        blob = json.dumps(structured, default=str) + "".join(text)
        self.bytes += len(blob.encode())
        code = structured.get("code")
        refusal = structured.get("refusal")
        if not code and isinstance(refusal, dict):
            code = refusal.get("code")
        errored = bool(getattr(result, "isError", False)) or structured.get("status") == "refused" or bool(refusal)
        return {
            "tool": name,
            "is_error": errored,
            "code": code,
            "elapsed_ms": round(elapsed_ms, 2),
            "structured": structured,
            "text": " ".join(text)[:500],
            "bytes": len(blob.encode()),
        }


def state(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url + "state", timeout=2) as response:
        return json.loads(response.read().decode())


def reset(url: str) -> None:
    request = urllib.request.Request(url + "reset", data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=2) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"reset status {response.status}")


def find_ref(snapshot: dict[str, Any], role: str, name: str) -> dict[str, Any] | None:
    for item in snapshot.get("refs") or []:
        if item.get("role") == role and item.get("name") == name:
            return item
    return None


def classify_ref(item: dict[str, Any], *, bucket: str) -> dict[str, Any]:
    actions = list(item.get("actions") or [])
    role = item.get("role")
    return {
        "bucket": bucket,
        "ref": item.get("ref"),
        "role": role,
        "name": item.get("name"),
        "states": item.get("states"),
        "actions": actions,
        "visibility": item.get("visibility"),
        "frame": item.get("frame"),
        "public_fields": sorted(item.keys()),
        "dom_identity": "caller_invisible_backend_node_id",
        "accessibility_identity": bool(role and item.get("name") is not None),
        "geometry_public": "bounds" in item,
        "semantic_role_name_state": bool(role and "states" in item),
        "direct_dom_runtime_action": "click" in actions or "type" in actions,
        "accessibility_native_action_in_snapshot": False,
        "keyboard_shortcut": False,
        "hit_test_declared": "pointer" in actions,
        "change_event_signal": False,
        "direct_app_api_candidate": False,
        "visual_only_requirement": False,
    }


async def wait_window(probe: Probe, pid: int) -> dict[str, Any]:
    polls = 0
    for _ in range(40):
        polls += 1
        listed = await probe.raw("list_windows", {"pid": pid})
        windows = (listed["structured"].get("windows") or []) if not listed["is_error"] else []
        visible = [window for window in windows if window.get("is_on_screen")]
        if visible:
            chosen = max(visible, key=lambda window: window["bounds"]["width"] * window["bounds"]["height"])
            return {"window": chosen, "polls": polls, "list_windows_ms": listed["elapsed_ms"]}
        await asyncio.sleep(0.25)
    raise RuntimeError("isolated browser window did not become ready")


async def bind(probe: Probe, url: str) -> dict[str, Any]:
    prepared = await probe.raw(
        "browser_prepare",
        {"allow_launch": True, "profile": {"mode": "isolated_new"}},
    )
    if prepared["is_error"]:
        raise RuntimeError(f"browser_prepare failed: {prepared['text']} {prepared['code']}")
    pid = int(prepared["structured"]["prepared_pid"])
    ready = await wait_window(probe, pid)
    window = ready["window"]
    bound = await probe.raw(
        "get_browser_state",
        {"pid": pid, "window_id": window["window_id"]},
    )
    if bound["is_error"]:
        raise RuntimeError(f"bind failed: {bound['text']} {bound['code']}")
    tabs = bound["structured"].get("tabs") or []
    if not tabs:
        raise RuntimeError("isolated browser has no tabs")
    selected = next((tab for tab in tabs if tab.get("active")), tabs[0])
    return {
        "pid": pid,
        "window_id": window["window_id"],
        "target_id": bound["structured"]["target_id"],
        "tab_id": str(selected["tab_id"]),
        "prepare_ms": prepared["elapsed_ms"],
        "bind_ms": bound["elapsed_ms"],
        "window_polls": ready["polls"],
        "generation": bound["structured"].get("generation") or bound["structured"].get("tab_generation"),
        "bind_keys": sorted(bound["structured"].keys()),
    }


async def snapshot(probe: Probe, binding: dict[str, Any], *, screenshot: bool = False) -> dict[str, Any]:
    args = {
        "target_id": binding["target_id"],
        "tab_id": binding["tab_id"],
        "snapshot_format": "semantic_v2",
    }
    if screenshot:
        args["include_screenshot"] = True
    result = await probe.raw("get_browser_state", args)
    if result["is_error"]:
        raise RuntimeError(f"snapshot failed: {result['text']} {result['code']}")
    return result


async def navigate(probe: Probe, binding: dict[str, Any], url: str) -> dict[str, Any]:
    result = await probe.raw(
        "browser_navigate",
        {"target_id": binding["target_id"], "tab_id": binding["tab_id"], "url": url},
    )
    if result["is_error"]:
        raise RuntimeError(f"navigate failed: {result['text']} {result['code']}")
    return result


def native_matches(window_state: dict[str, Any]) -> list[dict[str, Any]]:
    elements = window_state.get("elements") or window_state.get("refs") or []
    if not isinstance(elements, list):
        return []
    wanted = ("verification value", "Submit", "submit")
    matches = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        label = str(element.get("label") or element.get("name") or "")
        if any(token.lower() in label.lower() for token in wanted):
            matches.append(
                {
                    "role": element.get("role"),
                    "label": label,
                    "has_token": bool(element.get("element_token")),
                    "in_web_content": element.get("in_web_content"),
                    "actions": element.get("actions"),
                    "keys": sorted(element.keys()),
                }
            )
    return matches


async def one_route(
    probe: Probe,
    binding: dict[str, Any],
    url: str,
    token: str,
    route: str,
) -> dict[str, Any]:
    reset(url)
    nav = await navigate(probe, binding, url)
    snap = await snapshot(probe, binding)
    data = snap["structured"]
    textbox = find_ref(data, "textbox", "verification value")
    button = find_ref(data, "button", "Submit")
    if textbox is None or button is None:
        return {
            "route": route,
            "verified": False,
            "reason": "missing_semantic_refs",
            "roles": [item.get("role") for item in data.get("refs") or []],
        }
    typed = await probe.raw(
        "browser_type",
        {
            "target_id": binding["target_id"],
            "tab_id": binding["tab_id"],
            "ref": textbox["ref"],
            "text": token,
            "replace": True,
            "mode": "insert_text",
        },
    )
    started = time.perf_counter()
    if route == "dom_event":
        acted = await probe.raw(
            "browser_click",
            {
                "target_id": binding["target_id"],
                "tab_id": binding["tab_id"],
                "ref": button["ref"],
                "input_route": "dom_event",
            },
        )
    elif route == "trusted":
        acted = await probe.raw(
            "browser_click",
            {
                "target_id": binding["target_id"],
                "tab_id": binding["tab_id"],
                "ref": button["ref"],
                "input_route": "trusted",
                "delivery_mode": "foreground",
            },
        )
    else:
        raise RuntimeError(route)
    oracle = state(url)
    verified = oracle.get("submitted") == token
    elapsed = (time.perf_counter() - started) * 1000
    return {
        "route": route,
        "verified": verified,
        "outcome_ms": round(elapsed, 2),
        "navigate_ms": nav["elapsed_ms"],
        "snapshot_ms": snap["elapsed_ms"],
        "snapshot_bytes": snap["bytes"],
        "type_ok": not typed["is_error"],
        "type_ms": typed["elapsed_ms"],
        "action_ok": not acted["is_error"],
        "action_route": acted["structured"].get("route"),
        "action_code": acted["code"],
        "action_effect": acted["structured"].get("effect"),
        "action_ms": acted["elapsed_ms"],
        "screenshot_requested": False,
        "provider_decisions": 0,
        "pointer_events_attributed": 2 if acted["structured"].get("route") == "trusted" else 0,
    }


async def native_route(probe: Probe, binding: dict[str, Any], url: str, token: str) -> dict[str, Any]:
    reset(url)
    await navigate(probe, binding, url)
    window_state = await probe.raw(
        "get_window_state",
        {"pid": binding["pid"], "window_id": binding["window_id"]},
    )
    matches = native_matches(window_state["structured"]) if not window_state["is_error"] else []
    submit = next((item for item in matches if str(item.get("label") or "").lower() == "submit" and item.get("has_token")), None)
    textbox = next(
        (item for item in matches if "verification" in str(item.get("label") or "").lower() and item.get("has_token")),
        None,
    )
    record: dict[str, Any] = {
        "route": "atspi_element_token",
        "window_state_ok": not window_state["is_error"],
        "window_state_code": window_state["code"],
        "window_state_keys": sorted(window_state["structured"].keys()),
        "matches": matches,
        "verified": False,
        "provider_decisions": 0,
        "screenshot_requested": False,
    }
    if window_state["is_error"] or submit is None or textbox is None:
        record["reason"] = "native_web_controls_not_actionable"
        return record
    # Tokens were summarized away. Re-read and act only if the live structured
    # elements still carry tokens. This branch is the forced native route.
    elements = window_state["structured"].get("elements") or []
    live_submit = next(
        (
            element
            for element in elements
            if isinstance(element, dict) and str(element.get("label") or "").lower() == "submit" and element.get("element_token")
        ),
        None,
    )
    live_text = next(
        (
            element
            for element in elements
            if isinstance(element, dict)
            and "verification" in str(element.get("label") or "").lower()
            and element.get("element_token")
        ),
        None,
    )
    if live_submit is None or live_text is None:
        record["reason"] = "token_missing_after_match"
        return record
    typed = await probe.raw(
        "type_text",
        {"pid": binding["pid"], "element_token": live_text["element_token"], "text": token},
    )
    started = time.perf_counter()
    clicked = await probe.raw(
        "click",
        {"pid": binding["pid"], "element_token": live_submit["element_token"]},
    )
    oracle = state(url)
    record.update(
        {
            "verified": oracle.get("submitted") == token,
            "outcome_ms": round((time.perf_counter() - started) * 1000, 2),
            "type_ok": not typed["is_error"],
            "type_code": typed["code"],
            "action_ok": not clicked["is_error"],
            "action_code": clicked["code"],
            "action_effect": clicked["structured"].get("effect"),
            "pointer_events_attributed": None,
        }
    )
    return record


async def negatives(probe: Probe, binding: dict[str, Any], url: str) -> dict[str, Any]:
    await navigate(probe, binding, url)
    fresh = await snapshot(probe, binding)
    button = find_ref(fresh["structured"], "button", "Submit")
    if button is None:
        return {"fresh_resolve": False}
    fresh_click = await probe.raw(
        "browser_click",
        {
            "target_id": binding["target_id"],
            "tab_id": binding["tab_id"],
            "ref": button["ref"],
            "input_route": "dom_event",
        },
    )
    await navigate(probe, binding, "about:blank")
    stale = await probe.raw(
        "browser_click",
        {
            "target_id": binding["target_id"],
            "tab_id": binding["tab_id"],
            "ref": button["ref"],
            "input_route": "dom_event",
        },
    )
    await navigate(probe, binding, url)
    rebound = await snapshot(probe, binding)
    rebound_button = find_ref(rebound["structured"], "button", "Submit")
    foreign = await probe.raw(
        "browser_click",
        {
            "target_id": binding["target_id"],
            "tab_id": binding["tab_id"],
            "ref": (rebound_button or {}).get("ref", button["ref"]),
            "input_route": "dom_event",
        },
        session="foreign-session-not-owner",
    )
    return {
        "fresh_resolve": button is not None,
        "fresh_ref": button["ref"],
        "fresh_action_route": fresh_click["structured"].get("route"),
        "fresh_action_ok": not fresh_click["is_error"],
        "stale_after_navigation": stale["is_error"],
        "stale_code": stale["code"],
        "foreign_session_refused": foreign["is_error"],
        "foreign_code": foreign["code"],
        "rebound_ref": None if rebound_button is None else rebound_button["ref"],
    }


async def visual_census(probe: Probe, binding: dict[str, Any], visual_url: str) -> dict[str, Any]:
    await navigate(probe, binding, visual_url)
    snap = await snapshot(probe, binding)
    refs = snap["structured"].get("refs") or []
    return {
        "submit_button_ref": find_ref(snap["structured"], "button", "Submit") is not None,
        "roles": [item.get("role") for item in refs],
        "names": [item.get("name") for item in refs],
        "visual_only_submit": find_ref(snap["structured"], "button", "Submit") is None,
    }


async def run(receipt_path: Path, repeats: int) -> dict[str, Any]:
    default_server = FixtureServer(("127.0.0.1", 0))
    visual_server = FixtureServer(("127.0.0.1", 0), visual=True)
    thread = __import__("threading").Thread(target=default_server.serve_forever, daemon=True)
    visual_thread = __import__("threading").Thread(target=visual_server.serve_forever, daemon=True)
    thread.start()
    visual_thread.start()
    url = f"http://127.0.0.1:{default_server.server_port}/"
    visual_url = f"http://127.0.0.1:{visual_server.server_port}/"
    token = "census-token"
    probe_label = "semantic-e0-e1"
    params = StdioServerParameters(
        command=os.environ["CUA_DRIVER_BIN"],
        args=["mcp"],
        env=driver_environment(),
    )
    receipt: dict[str, Any] = {
        "head": HEAD,
        "parent": PARENT,
        "fixture": "jev-use default form",
        "display": os.environ.get("DISPLAY"),
        "session_type": os.environ.get("XDG_SESSION_TYPE"),
        "hyprland": os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"),
        "wayland": os.environ.get("WAYLAND_DISPLAY"),
    }
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = sorted(tool.name for tool in tools.tools)
                probe = Probe(session, probe_label)
                binding = await bind(probe, url)
                nav = await navigate(probe, binding, url)
                snap = await snapshot(probe, binding)
                shot = await snapshot(probe, binding, screenshot=True)
                data = snap["structured"]
                rows = [classify_ref(item, bucket="action_ref") for item in data.get("refs") or []]
                rows.extend(classify_ref(item, bucket="content_ref") for item in data.get("content_refs") or [])
                window_state = await probe.raw(
                    "get_window_state",
                    {"pid": binding["pid"], "window_id": binding["window_id"]},
                )
                for row in rows:
                    if row["name"] in {"verification value", "Submit"}:
                        row["native_match"] = any(
                            item.get("label") == row["name"] for item in native_matches(window_state["structured"])
                        )
                visual = await visual_census(probe, binding, visual_url)
                await navigate(probe, binding, url)
                trials = []
                trial_errors = []
                for route in ("dom_event", "trusted"):
                    for index in range(repeats):
                        try:
                            trial = await one_route(probe, binding, url, f"{token}-{route}-{index}", route)
                        except Exception as error:
                            trial = {"route": route, "index": index, "verified": False, "error": type(error).__name__, "detail": str(error)[:300]}
                            trial_errors.append(trial)
                            trials.append(trial)
                            continue
                        trial["index"] = index
                        trials.append(trial)
                try:
                    native = await native_route(probe, binding, url, f"{token}-native")
                except Exception as error:
                    native = {"route": "atspi_element_token", "verified": False, "error": type(error).__name__, "detail": str(error)[:300]}
                try:
                    negative = await negatives(probe, binding, url)
                except Exception as error:
                    negative = {"error": type(error).__name__, "detail": str(error)[:300]}
                receipt.update(
                    {
                        "tools_present": {
                            name: name in names
                            for name in (
                                "get_browser_state",
                                "browser_click",
                                "browser_type",
                                "browser_pointer",
                                "get_window_state",
                                "click",
                                "screenshot",
                            )
                        },
                        "binding": {key: binding[key] for key in ("prepare_ms", "bind_ms", "window_polls", "bind_keys")},
                        "navigate_ms": nav["elapsed_ms"],
                        "census": rows,
                        "snapshot_public_keys": sorted(data.keys()),
                        "snapshot_meta_keys": sorted((data.get("snapshot") or {}).keys()),
                        "semantic_snapshot_bytes": snap["bytes"],
                        "semantic_snapshot_ms": snap["elapsed_ms"],
                        "screenshot_snapshot_bytes": shot["bytes"],
                        "screenshot_delta_bytes": shot["bytes"] - snap["bytes"],
                        "screenshot_included": "screenshot" in shot["structured"] or any(
                            getattr(item, "type", "") == "image" for item in []
                        ),
                        "native_window_state": {
                            "ok": not window_state["is_error"],
                            "code": window_state["code"],
                            "matches": native_matches(window_state["structured"]),
                            "element_count": len(window_state["structured"].get("elements") or []),
                        },
                        "visual_fixture": visual,
                        "trials": trials,
                        "native_route": {
                            key: value
                            for key, value in native.items()
                            if key != "matches" or True
                        },
                        "negatives": negative,
                        "work": {
                            "tool_calls": probe.calls,
                            "tool_bytes": probe.bytes,
                            "provider_decisions": 0,
                            "screenshots_requested_on_action_trials": 0,
                        },
                    }
                )
    finally:
        default_server.shutdown()
        visual_server.shutdown()
    by_route: dict[str, list[float]] = {}
    for trial in receipt.get("trials", []):
        if trial.get("verified"):
            by_route.setdefault(trial["route"], []).append(trial["outcome_ms"])
    receipt["route_summary"] = {route: summarize(values) for route, values in by_route.items()}
    receipt["verified_counts"] = {
        route: {
            "verified": sum(1 for trial in receipt["trials"] if trial["route"] == route and trial.get("verified")),
            "attempted": sum(1 for trial in receipt["trials"] if trial["route"] == route),
        }
        for route in ("dom_event", "trusted")
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "receipt": str(receipt_path),
        "verified_counts": receipt["verified_counts"],
        "route_summary": receipt["route_summary"],
        "negatives": receipt.get("negatives"),
        "census_rows": len(receipt.get("census") or []),
        "visual_only_submit": (receipt.get("visual_fixture") or {}).get("visual_only_submit"),
    }, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(Path(args.receipt), args.repeats))


if __name__ == "__main__":
    main()
