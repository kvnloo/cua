#!/usr/bin/env python3
"""Run trycua/cua#4317's ``verify_session_isolation.run()`` with an independent server-side journal witness.

The unmodified proof script owns two in-process loopback fixtures (A, then B). This wrapper does not
change its behavior; it only records, on the fixture servers themselves, every state mutation that
actually lands (submit / reset) with a monotonic timestamp. That journal is the independent oracle: a
cross-session mutation is any submission on a fixture that its own session did not make.

Expected journals for a clean run (derived from the proof script's own steps):
    A: submit("session-a-owned"), reset
    B: submit("session-b-owned"), reset, submit("session-b-after-a-end")

usage: isolation_witness.py --examples-dir DIR --summary-out FILE --witness-out FILE
       (run inside the isolated X session, with CUA_DRIVER_BIN pointing at a Driver wrapper)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

EXPECTED = {
    "A": [("submit", "session-a-owned"), ("reset", None)],
    "B": [("submit", "session-b-owned"), ("reset", None), ("submit", "session-b-after-a-end")],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples-dir", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    parser.add_argument("--witness-out", type=Path, required=True)
    args = parser.parse_args()
    examples = args.examples_dir.resolve()
    # PYTHONPATH=python is what the unmodified script needs; make the same explicit, without editing it.
    sys.path[:0] = [str(examples / "python"), str(examples)]

    import fixture_server

    journal: list[dict] = []
    counter = {"n": 0}
    original_init = fixture_server.FixtureState.__init__
    original_submit = fixture_server.FixtureState.submit
    original_reset = fixture_server.FixtureState.reset

    def init(self):  # type: ignore[no-untyped-def]
        original_init(self)
        counter["n"] += 1
        self._witness_id = counter["n"]

    def submit(self, value):  # type: ignore[no-untyped-def]
        journal.append({"mono_ns": time.perf_counter_ns(), "fixture": "AB"[self._witness_id - 1] if self._witness_id <= 2 else "?",
                        "op": "submit", "value": value})
        original_submit(self, value)

    def reset(self):  # type: ignore[no-untyped-def]
        journal.append({"mono_ns": time.perf_counter_ns(), "fixture": "AB"[self._witness_id - 1] if self._witness_id <= 2 else "?",
                        "op": "reset", "value": None})
        original_reset(self)

    fixture_server.FixtureState.__init__ = init  # type: ignore[method-assign]
    fixture_server.FixtureState.submit = submit  # type: ignore[method-assign]
    fixture_server.FixtureState.reset = reset  # type: ignore[method-assign]

    import verify_session_isolation

    started_ns = time.perf_counter_ns()
    error = None
    summary = None
    try:
        summary = asyncio.run(verify_session_isolation.run(args.summary_out))
    except BaseException as exc:  # recorded, never hidden

        def leaves(item: BaseException):
            if isinstance(item, BaseExceptionGroup):
                for inner in item.exceptions:
                    yield from leaves(inner)
            else:
                yield item

        error = " | ".join(f"{type(leaf).__name__}: {leaf}" for leaf in leaves(exc))
        traceback.print_exc()
    ended_ns = time.perf_counter_ns()

    observed = {name: [(e["op"], e["value"]) for e in journal if e["fixture"] == name] for name in "AB"}
    foreign = [e for e in journal if e["op"] == "submit" and "foreign" in str(e["value"])]
    witness = {
        "started_mono_ns": started_ns,
        "ended_mono_ns": ended_ns,
        "fixture_order": {"1": "A", "2": "B"},
        "journal": journal,
        "observed": {k: [list(x) for x in v] for k, v in observed.items()},
        "expected": {k: [list(x) for x in v] for k, v in EXPECTED.items()},
        "journals_match_expected": observed == EXPECTED,
        "foreign_value_landed": bool(foreign),
        "cross_session_mutations": [e for e in journal if e["op"] == "submit" and (
            (e["fixture"] == "A" and e["value"] != "session-a-owned") or
            (e["fixture"] == "B" and e["value"] not in ("session-b-owned", "session-b-after-a-end")))],
        "script_summary_complete": bool(summary and summary.get("complete")),
        "error": error,
    }
    args.witness_out.write_text(json.dumps(witness, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: witness[k] for k in ("journals_match_expected", "foreign_value_landed", "script_summary_complete", "error")}))
    return 0 if (summary and summary.get("complete") and witness["journals_match_expected"] and not error) else 1


if __name__ == "__main__":
    raise SystemExit(main())
