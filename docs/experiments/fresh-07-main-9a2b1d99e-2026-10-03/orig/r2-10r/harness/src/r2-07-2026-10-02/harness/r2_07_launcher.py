#!/usr/bin/env python3
"""Measurement-only launcher for R2-07 (derived from R2-03 harness/receipt_launcher.py,
branch exp/r2-03-guarded-live-20261001 commit 6bab214ab, sha256 67ea2d0f...).

usage:
  <examples>/.venv/bin/python r2_07_launcher.py <examples-dir> run [run.py args...]        (arms A, B)
  <examples>/.venv/bin/python r2_07_launcher.py <examples-dir> compiled --artifact <json>  (arm C)
        --fixture-url <url> --token <t> --fallback none|mock|live --log <jsonl>

Arms A/B import the tested ``python/run.py`` UNCHANGED and call ``run.main()``. Arm C runs the
packet's compiled routine with the same Driver setup sequence run.py uses (initialize,
list_tools, browser_prepare isolated_new, wait_for_window, get_browser_state, browser_navigate).

In every mode, in this process only:
* ``run.Driver.call`` is wrapped so that ``set_agent_cursor_enabled {enabled:false, session:<label>}``
  is sent before the first call of each Driver session label, i.e. right after MCP initialize +
  list_tools and before ``browser_prepare`` (feedback held OFF in all arms; receipt ``feedback_off``);
* with ``R2_07_RECEIPT_LOG`` set, receipts are written as in R2-03: ``http_attempt`` per provider
  HTTP attempt (host, path, status, request-id presence + sha256 prefix), ``provider_response``
  (backend, model, token usage, selected id), ``driver_call`` per Driver MCP call (tool, monotonic
  span, ref argument only, whitelisted scalar result fields, refusal code). For semantic_v2
  snapshots the receipt adds ``snapshot_id``, ``page_url`` and ``refs_logical``: per ref only
  {ref, role, name, value_state in empty|param|other}. Mutation receipts add ``arg_text_is_token``
  (a boolean). No headers, bodies, typed text, field values or credentials are recorded.

Nothing changes arguments, return values or exceptions of run.py's calls.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import hashlib
import json
import os
import re
import sys
import threading
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

_LOCK = threading.Lock()
_LOG: Path | None = None
_SEQ = 0
_TOKEN: str | None = None

RESULT_SCALAR_KEYS = frozenset({
    "effect", "route", "input_route", "status", "delivery", "delivery_mode", "verification", "action",
    "format", "snapshot_format", "prepared", "launched", "reused", "profile_mode", "code", "enabled",
})


def _emit(record: dict) -> None:
    global _SEQ
    if _LOG is None:
        return
    with _LOCK:
        _SEQ += 1
        record = {"seq": _SEQ, **record}
        with _LOG.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def _hash(value: str | None) -> str | None:
    return None if not value else hashlib.sha256(value.encode()).hexdigest()[:16]


def _value_state(value) -> str:
    if value in (None, ""):
        return "empty"
    return "param" if _TOKEN is not None and value == _TOKEN else "other"


def _refusal(data) -> str | None:
    if not isinstance(data, Mapping):
        return None
    if data.get("effect") == "refused" or data.get("status") == "refused":
        m = re.search(r"refused \(([a-z_]+)\)", str(data.get("summary") or ""))
        return m.group(1) if m else "refused"
    return None


def install_feedback_off(runner, emit=None) -> None:
    """Hold agent-cursor feedback OFF for every Driver session label.

    ``set_agent_cursor_enabled`` is scoped to a session label (its ``session`` field is
    required; without it the call lands on the implicit ``mcp-*`` session, which run.py never
    uses). So before the FIRST call a ``run.Driver`` instance makes (run.py: ``browser_prepare``
    right after MCP initialize + list_tools), send ``{enabled:false, session:<that label>}``.
    A new label (e.g. N5 session replacement) gets the same treatment. Fails closed.
    """
    emit = emit or _emit
    original = runner.Driver.call
    if getattr(original, "_r207_feedback_wrapper", False):
        return

    @functools.wraps(original)
    async def call(self, name, arguments):
        if getattr(self, "_r207_feedback_label", None) != self.label:
            self._r207_feedback_label = self.label
            started = time.monotonic_ns()
            res = await self.session.call_tool("set_agent_cursor_enabled", {"enabled": False, "session": self.label})
            structured = getattr(res, "structuredContent", None) or {}
            enabled = structured.get("enabled") if isinstance(structured, Mapping) else None
            label_ok = isinstance(structured, Mapping) and structured.get("session") == self.label
            emit({"kind": "feedback_off", "is_error": bool(res.isError), "enabled_after": enabled,
                  "session_label_matches": label_ok, "t_start_ns": started, "t_end_ns": time.monotonic_ns()})
            if res.isError or enabled is not False or not label_ok:
                raise RuntimeError("could not hold cursor feedback OFF for this session label")
        return await original(self, name, arguments)

    call._r207_feedback_wrapper = True
    runner.Driver.call = call


def _install_receipts() -> None:
    import httpx2
    import run as runner
    import typesafe_sdk

    original_request = httpx2.Client.request

    @functools.wraps(original_request)
    def request(self, method, url, *args, **kwargs):
        parts = urlsplit(str(url))
        record = {"kind": "http_attempt", "method": str(method), "host": parts.hostname, "path": parts.path,
                  "t_start_ns": time.monotonic_ns()}
        try:
            response = original_request(self, method, url, *args, **kwargs)
        except BaseException as error:
            record.update({"t_end_ns": time.monotonic_ns(), "error": type(error).__name__, "reached": False})
            _emit(record)
            raise
        request_id = response.headers.get("x-typesafe-request-id")
        record.update({"t_end_ns": time.monotonic_ns(), "status": response.status_code, "reached": True,
                       "request_id_present": bool(request_id), "request_id_sha256_16": _hash(request_id)})
        _emit(record)
        return response

    httpx2.Client.request = request

    original_system_one = typesafe_sdk.TypeSafeClient.system_one

    @functools.wraps(original_system_one)
    def system_one(self, *args, **kwargs):
        started = time.monotonic_ns()
        base_host = urlsplit(getattr(getattr(self, "_config", None), "base_url", "") or "").hostname
        try:
            response = original_system_one(self, *args, **kwargs)
        except BaseException as error:
            _emit({"kind": "provider_response", "backend": None, "configured_backend": "typesafe",
                   "configured_host": base_host, "ok": False, "error": type(error).__name__,
                   "t_start_ns": started, "t_end_ns": time.monotonic_ns()})
            raise
        usage = getattr(response, "usage", None)
        try:
            request_id = response.request_id
        except Exception:
            request_id = None
        choices = getattr(response, "choices", {}) or {}
        answer = next(iter(choices.values()), None)
        _emit({"kind": "provider_response", "backend": "typesafe", "configured_backend": "typesafe",
               "configured_host": base_host, "ok": True, "model": getattr(response, "model", None),
               "input_tokens": getattr(usage, "input_tokens", None), "output_tokens": getattr(usage, "output_tokens", None),
               "request_id_sha256_16": _hash(request_id), "selected_id": getattr(answer, "choice", None),
               "confidence": getattr(answer, "confidence", None), "t_start_ns": started, "t_end_ns": time.monotonic_ns()})
        return response

    typesafe_sdk.TypeSafeClient.system_one = system_one

    import jev_adapter

    for module in (runner, jev_adapter):
        original_mock = getattr(module, "choose_mock_for_task")

        def make(orig):
            @functools.wraps(orig)
            def choose_mock(*args, **kwargs):
                started = time.monotonic_ns()
                result = orig(*args, **kwargs)
                _emit({"kind": "provider_response", "backend": "mock", "configured_backend": "mock", "ok": True,
                       "selected_id": result[0], "t_start_ns": started, "t_end_ns": time.monotonic_ns()})
                return result
            return choose_mock

        setattr(module, "choose_mock_for_task", make(original_mock))

    original_call = runner.Driver.call

    @functools.wraps(original_call)
    async def call(self, name, arguments):
        record = {"kind": "driver_call", "tool": name, "t_start_ns": time.monotonic_ns()}
        if isinstance(arguments, Mapping):
            for key in ("ref", "input_route", "snapshot_format"):
                if isinstance(arguments.get(key), str):
                    record[f"arg_{key}"] = arguments[key]
            if name == "browser_type":
                record["arg_text_is_token"] = arguments.get("text") == _TOKEN
                record["arg_replace"] = arguments.get("replace")
        try:
            data = await original_call(self, name, arguments)
        except BaseException as error:
            record.update({"t_end_ns": time.monotonic_ns(), "ok": False, "error": type(error).__name__,
                           "error_code": getattr(error, "code", None)})
            _emit(record)
            raise
        record["t_end_ns"] = time.monotonic_ns()
        record["ok"] = True
        if isinstance(data, dict):
            record["result"] = {k: v for k, v in data.items()
                                if k in RESULT_SCALAR_KEYS and (v is None or isinstance(v, (str, int, bool)))}
            refusal = _refusal(data)
            if refusal:
                record["refusal_code"] = refusal
            if name == "get_browser_state" and isinstance(arguments, Mapping) and arguments.get("snapshot_format"):
                snap = data.get("snapshot") if isinstance(data.get("snapshot"), Mapping) else {}
                page = data.get("page") if isinstance(data.get("page"), Mapping) else {}
                record["snapshot_id"] = snap.get("id")
                url = page.get("url")
                parts = urlsplit(url or "")
                record["page_url"] = f"{parts.scheme}://{parts.hostname}:{parts.port}{parts.path}" if parts.hostname in {"127.0.0.1", "localhost"} else "<non-loopback>"
                refs = data.get("refs") if isinstance(data.get("refs"), list) else []
                record["refs_logical"] = [
                    {"ref": r.get("ref"), "role": r.get("role"), "name": r.get("name"), "value_state": _value_state(r.get("value"))}
                    for r in refs if isinstance(r, Mapping)
                ]
        _emit(record)
        return data

    runner.Driver.call = call


async def compiled_main(examples: Path, argv: list[str]) -> str:
    """Arm C: same Driver setup as run.py, then the compiled routine."""
    import run as runner
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from driver_env import driver_environment
    from tasks import FixtureFormTask, fixture_state

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import compiled_routine as cr

    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--fixture-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--fallback", choices=("none", "mock", "live"), default="none")
    parser.add_argument("--max-fallback-decisions", type=int, default=2)
    parser.add_argument("--log", required=True)
    args = parser.parse_args(argv)
    artifact = json.loads(Path(args.artifact).read_text())
    cr.require_clean(artifact)
    log = Path(args.log)
    log.write_text("", encoding="utf-8")
    task = FixtureFormTask(args.token, args.fixture_url)
    task.reset()
    fallback = None
    if args.fallback != "none":
        fallback = cr.make_chooser_fallback(runner=runner, task_factory=lambda t, u: FixtureFormTask(t, u),
                                            provider=args.fallback, max_decisions=args.max_fallback_decisions)
    routine = cr.Routine(artifact, fallback=fallback)
    rec = cr.ReplayRecord()
    label = f"jev-python-{uuid.uuid4().hex[:8]}"
    params = StdioServerParameters(command=os.getenv("CUA_DRIVER_BIN", "cua-driver"), args=["mcp"], env=driver_environment())
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.list_tools()
                driver = runner.Driver(session, label)
                prepared = await driver.call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
                pid = int(prepared["prepared_pid"])
                window = await runner.wait_for_window(driver, pid)
                bound = await driver.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
                target_id, tab_id = bound["target_id"], runner.select_tab_id(bound["tabs"])
                await driver.call("browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": args.fixture_url})
                ctx = cr.ReplayContext(driver=driver, target_id=target_id, tab_id=tab_id, pid=pid,
                                       window_id=int(window["window_id"]), fixture_url=args.fixture_url,
                                       token=args.token, read_oracle=lambda: fixture_state(args.fixture_url))
                rec.t0_ns = time.monotonic_ns()
                await routine.replay(ctx, rec)
                rec.log("replay_end")
    except BaseException as error:  # noqa: BLE001 - every failure stays in the denominator
        if isinstance(error, KeyboardInterrupt):
            raise
        if rec.outcome == "running":
            rec.outcome, rec.stop_reason = "error", type(error).__name__
        rec.log("process_exception", error=type(error).__name__)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": "compiled_replay", **rec.as_dict()}, sort_keys=True) + "\n")
    print(json.dumps({"event": "outcome", "outcome": rec.outcome, "stop_reason": rec.stop_reason}))
    return rec.outcome


def main() -> None:
    global _LOG, _TOKEN
    examples = Path(sys.argv[1]).resolve()
    mode = sys.argv[2]
    rest = sys.argv[3:]
    sys.path.insert(0, str(examples / "python"))
    if "--token" in rest:
        _TOKEN = rest[rest.index("--token") + 1]
    log = os.environ.get("R2_07_RECEIPT_LOG")
    if log:
        _LOG = Path(log)
    sys.argv = [str(examples / "python" / "run.py"), *rest]
    if _LOG is not None:
        _install_receipts()
        _emit({"kind": "launcher_start", "mode": mode, "t_ns": time.monotonic_ns(),
               "argv_flags": [a for a in rest if a.startswith("--")]})
    import run as runner

    install_feedback_off(runner)  # outermost: its call is not inside any driver_call receipt span
    if mode == "run":
        runner.main()
    elif mode == "compiled":
        outcome = asyncio.run(compiled_main(examples, rest))
        raise SystemExit(0 if outcome in {"verified", "fallback_verified"} else 1)
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
