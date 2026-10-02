#!/usr/bin/env python3
"""R2-10 Phase 0 (b) and (e): the accepted FIX-01 harness, unchanged, re-pointed at binary R.

harness/src/fix-01-detached-node-refusal-2026-10-02/harness/fix01_harness.py (copied by path from
4a301d32a) checks that the worktree's libs/cua-driver/rust tree is FIX-01's tested tree and that
the U control is FIX-01's U binary. For R2-10 the tested tree is R's (989cc76ce + the listed
commits) and the U control is the B-02 binary (560bd8247, pre-FIX-01). Only those two expected
values are replaced here; every row, oracle and pass rule is FIX-01's.

usage: same arguments as fix01_harness.py, plus the two expected values from the environment:
  R2_10_RUST_TREE=<tree sha of R's libs/cua-driver/rust>  R2_10_U_SHA256=<U binary sha256>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX01 = HERE / "src" / "fix-01-detached-node-refusal-2026-10-02" / "harness"
sys.path.insert(0, str(FIX01))

import fix01_harness as f  # noqa: E402

f.FIX_A_RUST_TREE = os.environ["R2_10_RUST_TREE"]
f.BINARIES["U"] = os.environ["R2_10_U_SHA256"]

if __name__ == "__main__":
    raise SystemExit(f.main())
