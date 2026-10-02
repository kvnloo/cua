"""Build and optionally score the first z0 DecisionBackend shadow dataset.

Question family: api.attempt_will_fail
Gold label: objective Hermes observer event (api_request_error=True,
post_api_request=False).  The model prediction never controls Hermes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

QUESTION_ID = "api.attempt_will_fail"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _key(row: Mapping[str, Any]) -> tuple[str, int]:
    ident = row.get("identity") if isinstance(row.get("identity"), Mapping) else {}
    fields = row.get("fields") if isinstance(row.get("fields"), Mapping) else {}
    return str(ident.get("api_request_id") or ""), int(fields.get("api_call_count") or 0)


def request_for(pre: Mapping[str, Any]) -> dict[str, Any]:
    fields = pre.get("fields") if isinstance(pre.get("fields"), Mapping) else {}
    ident = pre.get("identity") if isinstance(pre.get("identity"), Mapping) else {}
    state = {
        "harness": "hermes",
        "provider": fields.get("provider"),
        "model": fields.get("model"),
        "api_mode": fields.get("api_mode"),
        "api_call_count": fields.get("api_call_count"),
        "retry_count": fields.get("retry_count"),
        "message_count": fields.get("message_count"),
        "tool_count": fields.get("tool_count"),
        "approx_input_tokens": fields.get("approx_input_tokens"),
        "request_char_count": fields.get("request_char_count"),
        "max_tokens": fields.get("max_tokens"),
        "platform": fields.get("platform"),
    }
    # Remove absent fields so "unknown" stays different from zero.
    state = {k: v for k, v in state.items() if v is not None}
    return {
        "state": state,
        "questions": [{
            "id": QUESTION_ID,
            "type": "boolean",
            "instructions": (
                "Predict whether this physical Hermes provider attempt will fail "
                "before a normalized successful response is returned."
            ),
            "criteria": {
                "false": "The attempt returns a normalized provider response.",
                "true": "The attempt emits api_request_error before success.",
            },
        }],
        "request_id": str(ident.get("api_request_id") or ""),
    }


def joined_examples(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    pending: dict[tuple[str, int], Mapping[str, Any]] = {}
    examples: list[dict[str, Any]] = []
    for row in rows:
        event = row.get("event")
        key = _key(row)
        if not key[0]:
            continue
        if event == "pre_api_request":
            pending[key] = row
            continue
        if event not in {"post_api_request", "api_request_error"}:
            continue
        pre = pending.pop(key, None)
        if pre is None:
            continue
        outcome = event == "api_request_error"
        examples.append({
            "schema": "z0int.hermes_shadow_example.v1",
            "question_id": QUESTION_ID,
            "identity": pre.get("identity"),
            "request": request_for(pre),
            "verified_outcome": outcome,
            "outcome_source": event,
        })
    return examples


def join_audit(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Denominators for ``joined_examples`` over the same rows: every pre and terminal is counted."""
    pending: dict[tuple[str, int], Mapping[str, Any]] = {}
    audit = {"n_pre": 0, "n_joined": 0, "n_positive": 0, "n_negative": 0, "n_orphan_pre_overwritten": 0,
             "n_orphan_pre_unclosed": 0, "n_terminal_without_pre": 0, "n_api_rows_without_request_id": 0,
             "observer_rows_dropped": 0}
    for row in rows:
        event = row.get("event")
        if event == "observer_rows_dropped":
            fields = row.get("fields") if isinstance(row.get("fields"), Mapping) else {}
            audit["observer_rows_dropped"] += int(fields.get("dropped_rows") or 0)
            continue
        if event not in {"pre_api_request", "post_api_request", "api_request_error"}:
            continue
        key = _key(row)
        if not key[0]:
            audit["n_api_rows_without_request_id"] += 1
            continue
        if event == "pre_api_request":
            audit["n_pre"] += 1
            if key in pending:
                audit["n_orphan_pre_overwritten"] += 1
            pending[key] = row
            continue
        if pending.pop(key, None) is None:
            audit["n_terminal_without_pre"] += 1
            continue
        audit["n_joined"] += 1
        audit["n_positive" if event == "api_request_error" else "n_negative"] += 1
    audit["n_orphan_pre_unclosed"] = len(pending)
    return audit


def _error(stage: str, exc: BaseException) -> dict[str, str]:
    return {"stage": stage, "type": type(exc).__name__, "message": str(exc)[:300]}


def _create_backend(backend_name: str):
    if backend_name.startswith("ollama:"):
        # Thin lab adapter: a real first-token distribution from local Ollama logprobs.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from ollama_logprob_backend import OllamaLogprobBackend
        return OllamaLogprobBackend(backend_name.split(":", 1)[1])
    from z0int.backends.registry import create_backend
    return create_backend(backend_name)


def score_examples(examples: list[dict[str, Any]], backend_name: str, z0int_root: Path | None) -> list[dict[str, Any]]:
    """Score every example; a backend failure is recorded on its row (decision=None), never dropped."""
    if z0int_root is not None:
        src = str((z0int_root / "src").resolve())
        if src not in sys.path:
            sys.path.insert(0, src)
    from z0int.backends.base import request_from_mapping, result_to_dict

    started = time.perf_counter()
    try:
        backend = _create_backend(backend_name)
        create_error = None
    except Exception as exc:  # outage: the whole cohort becomes a coverage gap
        backend, create_error = None, _error("create", exc)
    create_ms = (time.perf_counter() - started) * 1000.0
    out = []
    for index, example in enumerate(examples):
        row = dict(example)
        row["backend_arg"] = backend_name
        row["decision"] = None
        row["scorer_timing"] = {"index": index, "backend_create_ms": create_ms}
        if create_error is not None:
            row["backend_error"] = create_error
        else:
            call_started = time.perf_counter()
            try:
                row["decision"] = result_to_dict(backend.evaluate(request_from_mapping(example["request"])))
            except Exception as exc:
                row["backend_error"] = _error("evaluate", exc)
            row["scorer_timing"]["wall_ms"] = (time.perf_counter() - call_started) * 1000.0
        out.append(row)
    return out


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend")
    parser.add_argument("--z0int-root", type=Path, default=(Path(os.environ["Z0INT_ROOT"]) if os.environ.get("Z0INT_ROOT") else None))
    parser.add_argument("--audit-output", type=Path, help="write join denominators (join_audit) as JSON")
    args = parser.parse_args()

    events = read_jsonl(args.events)
    examples = joined_examples(events)
    rows = score_examples(examples, args.backend, args.z0int_root) if args.backend else examples
    write_jsonl(args.output, rows)
    if args.audit_output:
        args.audit_output.parent.mkdir(parents=True, exist_ok=True)
        args.audit_output.write_text(json.dumps(join_audit(events), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    errors = sum(1 for row in rows if row.get("backend_error"))
    print(json.dumps({"examples": len(rows), "backend": args.backend, "backend_errors": errors, "output": str(args.output)}))


if __name__ == "__main__":
    main()
