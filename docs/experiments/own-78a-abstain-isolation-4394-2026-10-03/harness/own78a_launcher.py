#!/usr/bin/env python3
"""Measurement-only launcher for the jev-use Python browser runner (OWN-78A).

usage: <examples>/.venv/bin/python own78a_launcher.py <examples-dir> [run.py args...]

Imports ``python/run.py`` from the given source tree unchanged and calls ``run.main()``. Derived
from the OWN-78 receipt launcher. When ``OWN78A_RECEIPT_LOG`` is set it wraps, in this process only:

* ``httpx2.Client.request``: one ``http_attempt`` receipt per provider HTTP attempt (method, host,
  path, status, request-id presence and sha256/16, latency). The attempt is counted BEFORE it is
  sent; a non-loopback attempt beyond ``OWN78A_ATTEMPT_ALLOWANCE`` attempts, or after
  ``OWN78A_REACH_ALLOWANCE`` attempts reached the provider, is refused before sending.
* ``typesafe_sdk.TypeSafeClient.system_one``: one ``provider_request`` receipt with the request's
  FIELD NAMES only (state key paths, question names, criteria ids, sha256/16 of the instructions and
  of the canonical state) and one ``provider_response`` receipt (responder from the HTTP host,
  model, token usage, selected id, request-id sha256/16).
* ``run.validate_choice``: one ``choice`` receipt (candidate id, tool, the ``ref`` argument only).
* ``run.Driver.call``: one ``driver_call`` receipt per Driver call (tool, ok/error, ``ref``
  argument only); for the semantic snapshot it records the ref index (ref, role, name; no values).

Optional seams (env-gated, measurement-only, default off):

* ``OWN78A_SEAM_ADD_FORM=1`` (arm A1): add ``observation.form = task.state_summary(sources)`` to
  the PR runner's TypeSafe observation, nothing else. Emits a ``seam_add_form`` receipt.
* ``OWN78A_FORBID_MUTATION=1`` (dry-run arms): refuse, before dispatch, any mutating Driver tool
  (backstop; the runner's own ``--dry-run`` already dispatches none). Emits ``mutation_refused``.

No headers, bodies, typed text, field values or credentials are recorded.
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
_STATE = {"attempts": 0, "reached": 0}
_LOCAL = threading.local()
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
TYPESAFE_API_HOST = "api.typesafe.ai"
MUTATING_TOOLS = frozenset({"browser_type", "browser_click", "click", "type_text", "press_key", "set_value"})


def _emit(record: dict) -> None:
    global _SEQ
    if _LOG is None:
        return
    with _LOCK:
        _SEQ += 1
        record = {"seq": _SEQ, **record}
        with _LOG.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def _hash(value) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _responder(host: str | None) -> str:
    if host == TYPESAFE_API_HOST:
        return "typesafe"
    if host in LOOPBACK:
        return "loopback_stub"
    return "other_host"


def key_paths(value, prefix: str = "", depth: int = 0) -> list[str]:
    """Dotted key paths of nested mappings (names only, never values); JSON strings are opened."""
    if isinstance(value, str) and value[:1] == "{" and depth > 0:
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, Mapping) or depth >= 3:
        return []
    out = []
    for key in value:
        path = f"{prefix}{key}"
        out.append(path)
        out.extend(key_paths(value[key], path + ".", depth + 1))
    return out


def _question_fields(questions) -> dict:
    out = {}
    for name, question in (questions or {}).items():
        instructions = getattr(question, "instructions", None)
        criteria = getattr(question, "criteria", None)
        if isinstance(question, Mapping):
            instructions = question.get("instructions", instructions)
            criteria = question.get("criteria", criteria)
        out[name] = {
            "instructions_sha256_16": _hash(instructions),
            "instructions_chars": len(instructions) if isinstance(instructions, str) else None,
            "criteria_ids": list(criteria) if isinstance(criteria, Mapping) else None,
        }
    return out


def _install() -> None:
    import httpx2
    import run as runner
    import typesafe_sdk

    attempt_allowance = int(os.environ.get("OWN78A_ATTEMPT_ALLOWANCE", "0"))
    reach_allowance = int(os.environ.get("OWN78A_REACH_ALLOWANCE", "0"))

    original_request = httpx2.Client.request

    @functools.wraps(original_request)
    def request(self, method, url, *args, **kwargs):
        parts = urlsplit(str(url))
        loopback = parts.hostname in LOOPBACK
        record = {"kind": "http_attempt", "method": str(method), "host": parts.hostname,
                  "loopback": loopback, "path": parts.path, "t_start_ns": time.monotonic_ns(),
                  "trial": os.environ.get("OWN78A_TRIAL")}
        if not loopback:
            if _STATE["attempts"] >= attempt_allowance or _STATE["reached"] >= reach_allowance:
                record.update({"t_end_ns": time.monotonic_ns(), "error": "BudgetGuardRefused", "guard_refused": True})
                _emit(record)
                raise httpx2.ConnectError("own78a budget guard: provider allowance used")
            _STATE["attempts"] += 1  # counted before sending
        try:
            response = original_request(self, method, url, *args, **kwargs)
        except BaseException as error:
            record.update({"t_end_ns": time.monotonic_ns(), "error": type(error).__name__})
            _emit(record)
            raise
        if not loopback:
            _STATE["reached"] += 1
        request_id = response.headers.get("x-typesafe-request-id")
        record.update({"t_end_ns": time.monotonic_ns(), "status": response.status_code,
                       "request_id_present": bool(request_id), "request_id_sha256_16": _hash(request_id)})
        record["latency_ms"] = round((record["t_end_ns"] - record["t_start_ns"]) / 1e6, 1)
        _emit(record)
        return response

    httpx2.Client.request = request

    original_system_one = typesafe_sdk.TypeSafeClient.system_one

    @functools.wraps(original_system_one)
    def system_one(self, *args, **kwargs):
        started = time.monotonic_ns()
        state = kwargs.get("state")
        _emit({"kind": "provider_request", "state_key_paths": key_paths(state),
               "state_sha256_16": _hash(state), "questions": _question_fields(kwargs.get("questions")),
               "t_ns": started})
        base_host = urlsplit(getattr(getattr(self, "_config", None), "base_url", "") or "").hostname
        try:
            response = original_system_one(self, *args, **kwargs)
        except BaseException as error:
            _emit({"kind": "provider_response", "responder": None, "responder_host": base_host,
                   "ok": False, "error": type(error).__name__, "t_start_ns": started,
                   "t_end_ns": time.monotonic_ns()})
            raise
        usage = getattr(response, "usage", None)
        try:
            request_id = response.request_id
        except Exception:
            request_id = None
        choices = getattr(response, "choices", {}) or {}
        answer = next(iter(choices.values()), None)
        probabilities = getattr(answer, "probabilities", None)
        _emit({"kind": "provider_response", "responder": _responder(base_host),
               "responder_host": base_host, "ok": True, "model": getattr(response, "model", None),
               "input_tokens": getattr(usage, "input_tokens", None),
               "output_tokens": getattr(usage, "output_tokens", None),
               "request_id_sha256_16": _hash(request_id), "selected_id": getattr(answer, "choice", None),
               "confidence": getattr(answer, "confidence", None),
               "probabilities": dict(probabilities) if isinstance(probabilities, Mapping) else None,
               "t_start_ns": started, "t_end_ns": time.monotonic_ns()})
        return response

    typesafe_sdk.TypeSafeClient.system_one = system_one

    if os.environ.get("OWN78A_SEAM_ADD_FORM") == "1":
        import browser_provider
        import decision_models

        original_choose = browser_provider.choose_browser_provider
        original_bounded = decision_models.choose_bounded_with_typesafe

        @functools.wraps(original_choose)
        def choose_browser_provider(provider, task, sources, candidates, history):
            _LOCAL.task_sources = (task, sources)
            try:
                return original_choose(provider, task, sources, candidates, history)
            finally:
                _LOCAL.task_sources = None

        @functools.wraps(original_bounded)
        def choose_bounded(client, *, goal, observation, criteria):
            task, sources = _LOCAL.task_sources
            observation = {**dict(observation), "form": task.state_summary(sources)}
            _emit({"kind": "seam_add_form", "added_keys": ["form"], "t_ns": time.monotonic_ns()})
            return original_bounded(client, goal=goal, observation=observation, criteria=criteria)

        browser_provider.choose_browser_provider = choose_browser_provider
        runner.choose_browser_provider = choose_browser_provider
        decision_models.choose_bounded_with_typesafe = choose_bounded

    original_validate = runner.validate_choice

    @functools.wraps(original_validate)
    def validate_choice(*args, **kwargs):
        candidate = original_validate(*args, **kwargs)
        arguments = getattr(candidate, "arguments", None) or {}
        _emit({"kind": "choice", "candidate": getattr(candidate, "id", None),
               "tool": getattr(candidate, "tool", None),
               "arg_ref": arguments.get("ref") if isinstance(arguments.get("ref"), str) else None,
               "t_ns": time.monotonic_ns()})
        return candidate

    runner.validate_choice = validate_choice

    forbid = os.environ.get("OWN78A_FORBID_MUTATION") == "1"
    original_call = runner.Driver.call

    @functools.wraps(original_call)
    async def call(self, name, arguments):
        record = {"kind": "driver_call", "tool": name, "t_start_ns": time.monotonic_ns()}
        if isinstance(arguments, Mapping) and isinstance(arguments.get("ref"), str):
            record["arg_ref"] = arguments["ref"]
        if forbid and name in MUTATING_TOOLS:
            record.update({"kind": "mutation_refused", "t_end_ns": time.monotonic_ns()})
            _emit(record)
            raise RuntimeError("own78a: mutation refused in a dry-run cell")
        try:
            data = await original_call(self, name, arguments)
        except BaseException as error:
            record.update({"t_end_ns": time.monotonic_ns(), "ok": False, "error": type(error).__name__})
            _emit(record)
            raise
        record.update({"t_end_ns": time.monotonic_ns(), "ok": True})
        if name == "get_browser_state" and isinstance(arguments, Mapping) and arguments.get("snapshot_format"):
            refs = data.get("refs") if isinstance(data, dict) else None
            if isinstance(refs, list):
                record["ref_index"] = [
                    {"ref": r.get("ref"), "role": r.get("role"), "name": r.get("name")}
                    for r in refs if isinstance(r, Mapping)
                ]
        _emit(record)
        return data

    runner.Driver.call = call


def main() -> None:
    global _LOG
    examples = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(examples / "python"))
    sys.argv = [str(examples / "python" / "run.py"), *sys.argv[2:]]
    log = os.environ.get("OWN78A_RECEIPT_LOG")
    if log:
        _LOG = Path(log)
        _install()
        _emit({"kind": "launcher_start", "t_ns": time.monotonic_ns(),
               "argv_flags": [a for a in sys.argv[1:] if a.startswith("--")],
               "seam_add_form": os.environ.get("OWN78A_SEAM_ADD_FORM") == "1",
               "forbid_mutation": os.environ.get("OWN78A_FORBID_MUTATION") == "1",
               "base_url_host": urlsplit(os.environ.get("TYPESAFE_BASE_URL", "")).hostname})
    import run as runner

    runner.main()


if __name__ == "__main__":
    main()
