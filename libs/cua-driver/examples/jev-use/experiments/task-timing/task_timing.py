"""Recipe-local timing; never an independent success oracle or Driver contract."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import time
import uuid
from typing import Any


class TaskTiming:
    def __init__(self, *, clock: Callable[[], int] = time.perf_counter_ns,
                 max_spans: int = 512) -> None:
        if max_spans < 0:
            raise ValueError("max_spans must be nonnegative")
        self.task_id = uuid.uuid4().hex
        self.clock_id = f"perf_counter_ns:{self.task_id}"
        self._clock = clock
        self._start = clock()
        self._spans: list[dict[str, Any]] = []
        self._max_spans = max_spans
        self._dropped = 0
        self._setup_end: float | None = None
        self._closed = False

    def _elapsed(self) -> float:
        return (self._clock() - self._start) / 1_000_000

    def setup_complete(self) -> None:
        if self._setup_end is None:
            self._setup_end = self._elapsed()

    @contextmanager
    def span(self, phase: str) -> Iterator[None]:
        start = self._elapsed()
        error_type = None
        try:
            yield
        except BaseException as error:
            error_type = type(error).__name__
            raise
        finally:
            event = {
                "event": "span", "task_id": self.task_id, "clock_id": self.clock_id,
                "phase": phase, "start_ms": start, "end_ms": self._elapsed(),
                "error_type": error_type,
            }
            if len(self._spans) < self._max_spans:
                self._spans.append(event)
            else:
                self._dropped += 1

    def finish(self, outcome: str, *, dry_run: bool = False,
               error_type: str | None = None) -> list[dict[str, Any]]:
        if self._closed:
            raise RuntimeError("task timing already closed")
        self._closed = True
        end = self._elapsed()
        return [*self._spans, {
            "event": "task_root", "task_id": self.task_id, "clock_id": self.clock_id,
            "start_ms": 0.0, "end_ms": end, "setup_ms": self._setup_end,
            "outcome": outcome, "outcome_source": "recipe_return_not_independent_oracle",
            "error_type": error_type, "dry_run": dry_run,
            "dropped_spans": self._dropped,
            "scope": "run_entry_through_context_cleanup_before_timing_flush",
        }]
