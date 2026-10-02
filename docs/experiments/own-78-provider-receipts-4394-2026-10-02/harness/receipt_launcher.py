#!/usr/bin/env python3
"""Measurement-only launcher for the unmodified jev-use Python browser runner (OWN-78).

usage: <examples>/.venv/bin/python receipt_launcher.py <examples-dir> [run.py args...]

Imports ``python/run.py`` from the tested source unchanged and calls ``run.main()``.
Pattern of the R2-03 launcher (exp/r2-03-guarded-live-20261001, read-only), adapted to the
PR 4394 module layout (``browser_provider`` owns provider dispatch).

When ``OWN78_RECEIPT_LOG`` is set it wraps, in this process only:

* ``httpx2.Client.request``: one ``http_attempt`` receipt per provider HTTP attempt (method,
  host, path, status, request-id presence and sha256 prefix, error class);
* ``typesafe_sdk.TypeSafeClient.system_one``: one ``provider_response`` receipt (responder,
  model, token usage, selected id, request-id sha256 prefix);
* ``browser_provider.choose_mock_for_task``: a ``provider_response`` receipt with responder=mock (falls back to ``run.choose_mock_for_task`` in the pre-PR runner);
* ``run.Driver.call``: one ``driver_call`` receipt per Driver MCP call (tool, ok/error, the
  ``ref`` argument only, whitelisted scalar result fields).

Optional seams (all env-gated, measurement-only):

* ``OWN78_SWITCH_BASE_URL``: after the first ``browser_type`` call returns ok, set
  ``TYPESAFE_BASE_URL`` in this process to that URL (R4). Emits a ``seam_switch`` receipt.
* ``OWN78_PROVIDER_REACH_ALLOWANCE``: refuse, before sending, any non-loopback provider attempt
  once this many attempts have reached the provider in this process (budget guard).

Nothing else changes arguments, return values or exceptions. No headers, bodies, typed text or
credentials are recorded. Timestamps are ``time.monotonic_ns()``.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

_LOCK = threading.Lock()
_LOG: Path | None = None
_SEQ = 0
_STATE = {"reached": 0, "switched": False}
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

RESULT_SCALAR_KEYS = frozenset(
    {"effect", "route", "status", "action", "prepared_pid", "refs_invalidated", "code"}
)


def _sanitize(value):
    """Whitelisted result scalars never carry paths; anything path-like is replaced."""
    if isinstance(value, str) and "/" in value:
        return "<path-like>"
    return value


def _emit(record: dict) -> None:
    global _SEQ
    if _LOG is None:
        return
    with _LOCK:
        _SEQ += 1
        record = {"seq": _SEQ, "runtime": "python", **record}
        with _LOG.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def _hash(value: str | None) -> str | None:
    return None if not value else hashlib.sha256(value.encode()).hexdigest()[:16]


TYPESAFE_API_HOST = "api.typesafe.ai"


def _responder(host: str | None) -> str:
    """Classify who answered from the HTTP host alone (never from configuration)."""
    if host == TYPESAFE_API_HOST:
        return "typesafe"
    if host in LOOPBACK:
        return "loopback_stub"
    return f"other_host"


class BudgetGuardRefused(ConnectionError):
    """Raised before sending when the trial's provider allowance is used up."""


def _install() -> None:
    import httpx2
    import run as runner
    import typesafe_sdk

    try:  # PR 4394 layout; absent in the pre-PR runner used by the R0 control
        import browser_provider
    except ImportError:
        browser_provider = None

    allowance_env = os.environ.get("OWN78_PROVIDER_REACH_ALLOWANCE")
    allowance = int(allowance_env) if allowance_env else None
    switch_url = os.environ.get("OWN78_SWITCH_BASE_URL") or None

    original_request = httpx2.Client.request

    @functools.wraps(original_request)
    def request(self, method, url, *args, **kwargs):
        parts = urlsplit(str(url))
        record = {
            "kind": "http_attempt",
            "method": str(method),
            "host": parts.hostname,
            "loopback": parts.hostname in LOOPBACK,
            "path": parts.path,
            "t_start_ns": time.monotonic_ns(),
        }
        if allowance is not None and parts.hostname not in LOOPBACK and _STATE["reached"] >= allowance:
            record.update({"t_end_ns": time.monotonic_ns(), "error": "BudgetGuardRefused", "guard_refused": True})
            _emit(record)
            raise httpx2.ConnectError("own78 budget guard: provider allowance used")
        try:
            response = original_request(self, method, url, *args, **kwargs)
        except BaseException as error:
            record.update({"t_end_ns": time.monotonic_ns(), "error": type(error).__name__})
            _emit(record)
            raise
        if parts.hostname not in LOOPBACK:
            _STATE["reached"] += 1
        request_id = response.headers.get("x-typesafe-request-id")
        record.update(
            {
                "t_end_ns": time.monotonic_ns(),
                "status": response.status_code,
                "request_id_present": bool(request_id),
                "request_id_sha256_16": _hash(request_id),
            }
        )
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
            _emit(
                {
                    "kind": "provider_response",
                    "responder": None,
                    "responder_host": base_host,
                    "ok": False,
                    "error": type(error).__name__,
                    "t_start_ns": started,
                    "t_end_ns": time.monotonic_ns(),
                }
            )
            raise
        usage = getattr(response, "usage", None)
        try:
            request_id = response.request_id
        except Exception:
            request_id = None
        choices = getattr(response, "choices", {}) or {}
        answer = next(iter(choices.values()), None)
        _emit(
            {
                "kind": "provider_response",
                "responder": _responder(base_host),
                "evidence": "typesafe_sdk decoded a response from responder_host",
                "responder_host": base_host,
                "ok": True,
                "model": getattr(response, "model", None),
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "request_id_sha256_16": _hash(request_id),
                "selected_id": getattr(answer, "choice", None),
                "t_start_ns": started,
                "t_end_ns": time.monotonic_ns(),
            }
        )
        return response

    typesafe_sdk.TypeSafeClient.system_one = system_one

    mock_owner = browser_provider if browser_provider is not None else runner
    original_mock = mock_owner.choose_mock_for_task

    @functools.wraps(original_mock)
    def choose_mock(*args, **kwargs):
        started = time.monotonic_ns()
        result = original_mock(*args, **kwargs)
        _emit(
            {
                "kind": "provider_response",
                "responder": "mock",
                "evidence": "in-process mock policy returned",
                "ok": True,
                "selected_id": result[0],
                "t_start_ns": started,
                "t_end_ns": time.monotonic_ns(),
            }
        )
        return result

    mock_owner.choose_mock_for_task = choose_mock

    original_call = runner.Driver.call

    @functools.wraps(original_call)
    async def call(self, name, arguments):
        record = {"kind": "driver_call", "tool": name, "t_start_ns": time.monotonic_ns()}
        if isinstance(arguments, Mapping) and isinstance(arguments.get("ref"), str):
            record["arg_ref"] = arguments["ref"]
        try:
            data = await original_call(self, name, arguments)
        except BaseException as error:
            record.update(
                {
                    "t_end_ns": time.monotonic_ns(),
                    "ok": False,
                    "error": type(error).__name__,
                    "error_code": getattr(error, "code", None),
                }
            )
            _emit(record)
            raise
        record["t_end_ns"] = time.monotonic_ns()
        record["ok"] = True
        if isinstance(data, dict):
            record["result"] = {
                key: _sanitize(value)
                for key, value in data.items()
                if key in RESULT_SCALAR_KEYS and (value is None or isinstance(value, (str, int, float, bool)))
            }
        _emit(record)
        if switch_url and name == "browser_type" and not _STATE["switched"]:
            _STATE["switched"] = True
            os.environ["TYPESAFE_BASE_URL"] = switch_url
            _emit(
                {
                    "kind": "seam_switch",
                    "after_tool": "browser_type",
                    "to_host": urlsplit(switch_url).hostname,
                    "t_ns": time.monotonic_ns(),
                }
            )
        return data

    runner.Driver.call = call


def main() -> None:
    global _LOG
    examples = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(examples / "python"))
    sys.argv = [str(examples / "python" / "run.py"), *sys.argv[2:]]
    log = os.environ.get("OWN78_RECEIPT_LOG")
    if log:
        _LOG = Path(log)
        _install()
        _emit(
            {
                "kind": "launcher_start",
                "t_ns": time.monotonic_ns(),
                "argv_flags": [a for a in sys.argv[1:] if a.startswith("--")],
                "base_url_host_at_start": urlsplit(os.environ.get("TYPESAFE_BASE_URL", "")).hostname,
                "switch_armed": bool(os.environ.get("OWN78_SWITCH_BASE_URL")),
            }
        )
    import run as runner

    runner.main()


if __name__ == "__main__":
    main()
