"""Speculative visual capture for the Python jev-use observation path.

Mirrors typescript/speculate.ts: the chunk-10 bench measured the Python
loop's per-step cost as the RPC round trips themselves — gated-sequential
pays get_browser_state, then (when the visual fallback fires)
get_window_state + parse_visual_regions as two more sequential groups. The
capture does not depend on the snapshot, so it can fly alongside it — but
only the visual-submit fallback consumes it, so firing it unconditionally
wastes an RPC on every DOM-complete step.

The speculation policy: a sticky predictor. The visual need is sticky in
practice — when the DOM lacks an actionable candidate on step N, step N+1
usually needs the visual path too (the loop is still in the visual-submit
fallback). So: if the previous step needed visual, fire get_window_state
concurrently with this step's get_browser_state (via asyncio); when the
fallback fires again, only parse_visual_regions remains (2 round-trip
groups instead of 3). On a mispredicted step the capture is discarded (one
wasted RPC, recorded as discarded in the ledger — never as consumed
evidence); on a missed prediction the loop falls back to the sequential
path.

Miss-rate gate: the sticky predictor wastes exactly one capture per
isolated visual need. `confirmation_steps` gates speculation on a confirmed
run: speculate only when the last `confirmation_steps` steps all needed
visual. With 2, isolated needs (sparse) and flickering needs (alternating)
never trigger a wasted capture, at the cost of one sequential step at the
start of each sticky run. The default 1 preserves the original sticky
behavior; run.py wires 2 (measured on the TS side: sparse under contention
0.70x -> 1.20x; gate strictly >= sticky everywhere measured).

Measured in bench_observation_speculate.py against a fake driver with
virtual latencies and scripted visual-need sequences. Zero protocol change.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping, TypedDict

VISUAL_PARSE_KINDS = ("text", "icon")
VISUAL_PARSE_MIN_CONFIDENCE = 0.8
VISUAL_PARSE_MAX_REGIONS = 100


class ObserveStepArgs(TypedDict):
    pid: int
    window_id: int


CallFn = Callable[[str, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]


class VisualSpeculator:
    """Sticky predictor for "will this step need the visual path?".

    Starts cold (no speculation on the first step); thereafter follows the
    previous step's outcome. The gate (`confirmation_steps`) requires that
    many consecutive visual-needing steps before a speculative capture fires.
    Also tracks prediction accuracy so the loop's ledger can report how often
    speculation paid off, plus `suppressed` (the gate blocked a sticky-yes)
    and a rolling miss rate over actual speculations.

    Usage mirrors run.py: consult should_speculate() once per step, then
    observe() once. The decision is consumed by observe(); outcomes are
    counted against the actual decision, not the raw predictor.
    """

    def __init__(self, confirmation_steps: int = 1) -> None:
        self.confirmation_steps = max(1, int(confirmation_steps))
        self._last_needed: bool | None = None
        self._consecutive_needed = 0
        self._last_decision = False
        self.hits = 0
        self.false_positives = 0
        self.misses = 0
        self.suppressed = 0

    def should_speculate(self) -> bool:
        sticky_yes = self._last_needed is True
        decision = sticky_yes and self._consecutive_needed >= self.confirmation_steps
        self._last_decision = decision
        if sticky_yes and not decision:
            self.suppressed += 1
        return decision

    def observe(self, needed: bool) -> None:
        speculated = self._last_decision
        if speculated and needed:
            self.hits += 1
        elif speculated and not needed:
            self.false_positives += 1
        elif not speculated and needed:
            self.misses += 1
        if needed:
            self._consecutive_needed += 1
        else:
            self._consecutive_needed = 0
        self._last_needed = needed
        self._last_decision = False  # consume: one decision per step

    def stats(self) -> dict[str, int]:
        return {
            "hits": self.hits,
            "false_positives": self.false_positives,
            "misses": self.misses,
            "suppressed": self.suppressed,
        }

    def miss_rate(self) -> float | None:
        """False positives / total speculations so far; None before any.

        The gate's own health signal: a high rate means the predictor is
        firing into needs that aren't there.
        """
        total = self.hits + self.false_positives
        return None if total == 0 else self.false_positives / total


def start_speculative_capture(
    call: CallFn,
    args: ObserveStepArgs,
    speculate: bool,
) -> Awaitable[Mapping[str, Any]] | None:
    """Fire get_window_state alongside the snapshot when the predictor says yes.

    The caller still issues get_browser_state itself so both fly
    concurrently (snapshot issued first: on a FIFO transport it must not
    queue behind the capture).
    """
    if not speculate:
        return None
    return call(
        "get_window_state",
        {
            "pid": args["pid"],
            "window_id": args["window_id"],
            "include_accessibility_tree": False,
        },
    )


async def visual_from_capture(
    capture: Awaitable[Mapping[str, Any]],
    call: CallFn,
    args: ObserveStepArgs,
    parse_visual_regions: Callable[..., Any],
) -> Any:
    """Complete the visual observation from an in-flight speculative capture.

    Await the capture, then parse. One more round trip instead of two.
    """
    resolved = await capture
    capture_id = resolved.get("capture_id")
    if not isinstance(capture_id, str):
        raise ValueError("capture returned no capture_id")
    wire = await call(
        "parse_visual_regions",
        {
            "capture_id": capture_id,
            "options": {
                "kinds": list(VISUAL_PARSE_KINDS),
                "min_confidence": VISUAL_PARSE_MIN_CONFIDENCE,
                "max_regions": VISUAL_PARSE_MAX_REGIONS,
            },
        },
    )
    return parse_visual_regions(
        wire,
        expected_capture_id=capture_id,
        expected_pid=args["pid"],
        expected_window_id=args["window_id"],
    )


async def discard_capture(
    capture: Awaitable[Mapping[str, Any]] | None,
) -> None:
    """Discard an unused speculative capture.

    The RPC already flew, so this is pure hygiene: await it so an in-flight
    failure cannot surface as an unhandled coroutine/task warning later. The
    loop records the waste in its ledger (ObservationRecord.discarded),
    never as consumed evidence.
    """
    if capture is None:
        return
    try:
        await capture
    except Exception:
        # The RPC was paid for; its failure is irrelevant when unused.
        pass


__all__ = [
    "CallFn",
    "ObserveStepArgs",
    "VISUAL_PARSE_KINDS",
    "VISUAL_PARSE_MIN_CONFIDENCE",
    "VISUAL_PARSE_MAX_REGIONS",
    "VisualSpeculator",
    "start_speculative_capture",
    "visual_from_capture",
    "discard_capture",
]
