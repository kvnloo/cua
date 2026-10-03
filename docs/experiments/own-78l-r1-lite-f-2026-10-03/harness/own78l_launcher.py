#!/usr/bin/env python3
"""OWN-78L launcher: OWN-78A's measurement-only launcher, imported unchanged (blob-checked by the
harness), plus one env-gated, default-off switch for the MOCK control.

usage: <examples>/.venv/bin/python own78l_launcher.py <examples-dir> [run.py args...]

* ``OWN78L_PROVIDER_OVERRIDE=mock``: replace the value of ``--provider`` with ``mock`` (the runner's
  own scripted backend) before the runner parses its arguments, and append one
  ``own78l_provider_override`` receipt (from/to provider names only). Any other value is refused.
  Unset (every live, stub and CAP-0 cell), argv passes through untouched.

Everything else (receipts, budget guard, ledgers) is OWN-78A's ``own78a_launcher.main()``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "own-78a-abstain-isolation-4394-2026-10-03" / "harness"))
import own78a_launcher  # noqa: E402


def main() -> None:
    override = os.environ.get("OWN78L_PROVIDER_OVERRIDE")
    if override:
        if override != "mock":
            raise SystemExit("own78l: only OWN78L_PROVIDER_OVERRIDE=mock is supported")
        index = sys.argv.index("--provider")
        previous = sys.argv[index + 1]
        sys.argv[index + 1] = "mock"
        log = os.environ.get("OWN78A_RECEIPT_LOG")
        if log:
            with Path(log).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"seq": 0, "kind": "own78l_provider_override", "from": previous,
                                         "to": "mock", "t_ns": time.monotonic_ns()}, sort_keys=True) + "\n")
    own78a_launcher.main()


if __name__ == "__main__":
    main()
