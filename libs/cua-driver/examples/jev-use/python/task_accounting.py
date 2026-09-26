"""Separate the clocks from kvnloo/cua#10. Runner lifetime is not the oracle."""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class TrialClocks:
    cold_setup_ms: int
    verified_outcome_ms: int
    runner_lifetime_ms: int
    named_span_ms: int


def residual_ms(trial: TrialClocks) -> int:
    return trial.verified_outcome_ms - trial.named_span_ms


def phase0_spans_cover_outcome(trial: TrialClocks) -> bool:
    if trial.verified_outcome_ms <= 0:
        return False
    return trial.named_span_ms * 100 >= trial.verified_outcome_ms * 90


def outcome_time(trial: TrialClocks) -> int:
    """The number a report may call time-to-verified-outcome."""
    return trial.verified_outcome_ms


def event_schema() -> dict[str, object]:
    return {
        "fields": {item.name: "int" for item in fields(TrialClocks)},
        "forbidden": ["window_title", "token", "screenshot", "ocr_text", "prompt", "credential"],
    }


def project_event(raw: dict[str, object]) -> dict[str, int]:
    """Allowlist projection. Anything else, including marker text, is dropped."""
    schema = event_schema()
    projected: dict[str, int] = {}
    for key in schema["fields"]:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        projected[key] = value
    return projected
