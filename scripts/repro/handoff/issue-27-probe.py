"""Print the issue 27 matrix by reading the contract sources and the caller gates."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "libs/cua-driver/examples/jev-use/python"))

from compatibility_matrix import matrix_tsv


def main() -> None:
    sys.stdout.write(matrix_tsv(ROOT))


if __name__ == "__main__":
    main()
