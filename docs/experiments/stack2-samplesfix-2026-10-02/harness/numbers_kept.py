"""PREREG C6: every number in the SAMPLES README's original results tables is still in the corrected tables.

  python numbers_kept.py <old_readme.md> <new_readme.md> [out.json]

Tables compared (matched by header / generated block, rows matched by their label cell):
  workload table   all cells
  api table        Brier and log-loss cells (the old free-text note column was replaced by data columns)
  turn table       all cells
Numbers are normalized before comparison: U+2212 minus -> '-', leading '+' dropped, thousands
separators (space or comma between digit groups) removed, markdown bold removed. A new number printed
with more decimals matches when it rounds to the old one (0.2500 vs 0.25). A new row may hold
more numbers than the old one (for example the warm max column); a missing old number is a failure.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

NUM = re.compile(r"-?\d+(?:\.\d+)?")


def norm(cell: str) -> list[str]:
    c = cell.replace("−", "-").replace("**", "")
    c = re.sub(r"(?<=\d)[ ,](?=\d{3}\b)", "", c)
    c = re.sub(r"\+(?=\d)", "", c)
    return NUM.findall(c)


def same(old: str, new: str) -> bool:
    """Equal as printed, or the new value printed with more decimals rounds to the old one (0.25 vs 0.2500)."""
    if old == new:
        return True
    d_old = len(old.split(".")[1]) if "." in old else 0
    d_new = len(new.split(".")[1]) if "." in new else 0
    return d_new > d_old and f"{float(new):.{d_old}f}" == old


def rows_after(text: str, header_prefix: str) -> dict[str, list[str]]:
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(header_prefix))
    out = {}
    for l in lines[start + 2:]:
        if not l.startswith("|"):
            break
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        out[cells[0].replace("**", "")] = cells[1:]
    return out


def block(text: str, name: str) -> str:
    m = re.search(rf"<!-- BEGIN GENERATED {name} -->\n(.*?)\n<!-- END GENERATED {name} -->", text, re.S)
    return m.group(1)


def compare(old_text: str, new_text: str) -> dict:
    specs = [("workload", "| kind | run | oracle pass |", None), ("api", "| row | Brier | log-loss | note |", (0, 2)),
             ("turn", "| row | Brier | log-loss | ECE |", None)]
    result = {}
    for name, header, cols in specs:
        old = rows_after(old_text, header)
        new_block = block(new_text, name)
        new = rows_after(new_block, new_block.splitlines()[0][:12])
        table = {}
        for label, cells in old.items():
            use = cells[cols[0]:cols[1]] if cols else cells
            want = [n for c in use for n in norm(c)]
            have = [n for c in new.get(label, []) for n in norm(c)]
            pool = list(have)
            missing = []
            for n in want:
                hit = next((h for h in pool if same(n, h)), None)
                if hit is not None:
                    pool.remove(hit)
                else:
                    missing.append(n)
            table[label] = {"old_numbers": want, "row_found": label in new, "missing": missing}
        result[name] = table
    result["all_kept"] = all(r["row_found"] and not r["missing"] for t in result.values() if isinstance(t, dict) for r in t.values())
    return result


def main() -> None:
    res = compare(Path(sys.argv[1]).read_text(encoding="utf-8"), Path(sys.argv[2]).read_text(encoding="utf-8"))
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"all_kept": res["all_kept"],
                      "missing": {f"{t}/{l}": r["missing"] for t, v in res.items() if isinstance(v, dict)
                                  for l, r in v.items() if r["missing"] or not r["row_found"]}}))
    sys.exit(0 if res["all_kept"] else 1)


if __name__ == "__main__":
    main()
