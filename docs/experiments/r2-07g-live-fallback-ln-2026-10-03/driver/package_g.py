"""Package the lane's run outputs into the packet raw/ layout (run under hostless).

usage: python package_g.py --src <run root> --dst <packet>/raw --blocks <srcdir>=<block>,...
       [--ledger <lane lock ledger>] [--global-ledger <quiet-lane ledger>] [--provider-ledger <file>]
       [--unit <file>]... [--log <file>]...

The R2-07e driver/package_e.py, imported and run unchanged, with its global-ledger label prefix set to
this lane's ("r207g-"). Every text file is privacy-scanned; any hit aborts packaging.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "r2-07e-modal-gate-phase-l-2026-10-03" / "driver"))
import package_e as pe  # noqa: E402

pe.PREFIX = "r207g-"

if __name__ == "__main__":
    pe.main()
