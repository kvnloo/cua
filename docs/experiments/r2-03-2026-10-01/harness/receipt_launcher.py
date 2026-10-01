#!/usr/bin/env python3
"""Measurement-only launcher for the unmodified jev-use Python browser runner (R2-03).

usage: <examples>/.venv/bin/python receipt_launcher.py <examples-dir> [run.py args...]

It imports ``python/run.py`` from the tested source unchanged and calls ``run.main()``.
When ``R2_03_RECEIPT_LOG`` is set it first wraps, in this process only:

* ``httpx2.Client.request``: one ``http_attempt`` receipt per HTTP attempt the provider SDK
  makes (method, host, path, status, request-id presence and sha256 prefix, error class);
* ``typesafe_sdk.TypeSafeClient.system_one``: one ``provider_response`` receipt naming the
  responder (``typesafe`` when the SDK decoded a response), ``response.model``, token usage and
  the selected candidate id;
* ``run.choose_mock_for_task``: a ``provider_response`` receipt with ``backend=mock``;
* ``run.Driver.call``: one ``driver_call`` receipt per Driver MCP call (tool, monotonic span,
  error code, the ``ref`` argument only, Submit refs seen in semantic snapshots, and
  whitelisted scalar result fields).

Nothing here changes arguments, return values or exceptions. No headers, bodies, typed text or
credentials are recorded. Without ``R2_03_RECEIPT_LOG`` the launcher only runs ``run.main()``.
All timestamps are ``time.monotonic_ns()`` (CLOCK_MONOTONIC), the same clock the harness uses.
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

RESULT_SCALAR_KEYS = frozenset(
    {
        "effect", "route", "input_route", "status", "delivery", "delivery_mode", "verification",
        "action", "snapshot_id", "generation", "snapshot_generation", "format", "snapshot_format",
        "prepared_pid", "launched", "reused", "profile_mode", "browser", "product", "engine",
        "browser_version", "code",
    }
)


def _sanitize(value):
    if isinstance(value, str) and (value.startswith("/") or "/home/" in value or "/mnt/" in value):
        return "<abs-path>"
    return value


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


def _submit_refs(snapshot: dict) -> list[str]:
    refs = snapshot.get("refs") or []
    if not isinstance(refs, list):
        return []
    return [
        str(ref.get("ref"))
        for ref in refs
        if isinstance(ref, dict) and ref.get("role") == "button" and ref.get("name") == "Submit"
    ]


def _install(examples: Path) -> None:
    import httpx2
    import run as runner
    import typesafe_sdk

    original_request = httpx2.Client.request

    @functools.wraps(original_request)
    def request(self, method, url, *args, **kwargs):
        parts = urlsplit(str(url))
        record = {
            "kind": "http_attempt",
            "method": str(method),
            "host": parts.hostname,
            "path": parts.path,
            "t_start_ns": time.monotonic_ns(),
        }
        try:
            response = original_request(self, method, url, *args, **kwargs)
        except BaseException as error:
            record.update({"t_end_ns": time.monotonic_ns(), "error": type(error).__name__})
            _emit(record)
            raise
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
                    "backend": None,
                    "configured_backend": "typesafe",
                    "configured_host": base_host,
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
                "backend": "typesafe",
                "configured_backend": "typesafe",
                "configured_host": base_host,
                "ok": True,
                "model": getattr(response, "model", None),
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "request_id_sha256_16": _hash(request_id),
                "selected_id": getattr(answer, "choice", None),
                "confidence": getattr(answer, "confidence", None),
                "t_start_ns": started,
                "t_end_ns": time.monotonic_ns(),
            }
        )
        return response

    typesafe_sdk.TypeSafeClient.system_one = system_one

    original_mock = runner.choose_mock_for_task

    @functools.wraps(original_mock)
    def choose_mock(*args, **kwargs):
        started = time.monotonic_ns()
        result = original_mock(*args, **kwargs)
        _emit(
            {
                "kind": "provider_response",
                "backend": "mock",
                "configured_backend": "mock",
                "ok": True,
                "selected_id": result[0],
                "t_start_ns": started,
                "t_end_ns": time.monotonic_ns(),
            }
        )
        return result

    runner.choose_mock_for_task = choose_mock

    original_call = runner.Driver.call

    @functools.wraps(original_call)
    async def call(self, name, arguments):
        record = {"kind": "driver_call", "tool": name, "t_start_ns": time.monotonic_ns()}
        if isinstance(arguments, Mapping):
            for key in ("ref", "input_route", "snapshot_format"):
                if isinstance(arguments.get(key), str):
                    record[f"arg_{key}"] = arguments[key]
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
            record["result_keys"] = sorted(data)
            record["result"] = {
                key: _sanitize(value)
                for key, value in data.items()
                if key in RESULT_SCALAR_KEYS and (value is None or isinstance(value, (str, int, float, bool)))
            }
            delivery = data.get("delivery")
            if isinstance(delivery, dict):
                record["result_delivery"] = {
                    key: _sanitize(value)
                    for key, value in delivery.items()
                    if value is None or isinstance(value, (str, int, float, bool))
                }
            for key in ("binding_route", "binding_quality", "mutation_allowed", "refs_invalidated"):
                if isinstance(data.get(key), (str, int, float, bool)):
                    record["result"][key] = _sanitize(data[key])
            if name == "get_browser_state" and isinstance(arguments, Mapping) and arguments.get("snapshot_format"):
                record["submit_refs"] = _submit_refs(data)
                refs = data.get("refs")
                record["ref_count"] = len(refs) if isinstance(refs, list) else None
        _emit(record)
        return data

    runner.Driver.call = call


def main() -> None:
    global _LOG
    examples = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(examples / "python"))
    sys.argv = [str(examples / "python" / "run.py"), *sys.argv[2:]]
    log = os.environ.get("R2_03_RECEIPT_LOG")
    if log:
        _LOG = Path(log)
        _install(examples)
        _emit({"kind": "launcher_start", "t_ns": time.monotonic_ns(), "argv_flags": [a for a in sys.argv[1:] if a.startswith("--")]})
    import run as runner

    runner.main()


if __name__ == "__main__":
    main()
