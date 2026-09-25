"""Separate the clocks from kvnloo/cua#10. Runner lifetime is not the oracle."""

from __future__ import annotations

from dataclasses import dataclass


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
