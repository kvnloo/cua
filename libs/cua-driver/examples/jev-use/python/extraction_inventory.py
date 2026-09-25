"""Count recipe call sites. kvnloo/cua#39.

A production file other than the module itself is a call site. Two such
files are the extraction threshold. Tests are harnesses, not a second recipe.
"""

from __future__ import annotations

from pathlib import Path

ABSTRACTIONS = (
    "deterministic_fast_path",
    "compiled_expectations",
    "guarded_run",
    "stale_batch",
    "lazy_vision",
    "browser_revision",
    "shadow_probe",
    "toggle_expectations",
    "toggle_run",
)


def inventory(root: Path) -> list[dict[str, object]]:
    base = root / "libs" / "cua-driver" / "examples" / "jev-use"
    rows: list[dict[str, object]] = []
    for stem in ABSTRACTIONS:
        production: list[str] = []
        harnesses: list[str] = []
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".ts"} or "__pycache__" in path.parts:
                continue
            if path.name in {f"{stem}.py", f"{stem}.ts", f"{stem}.test.ts"}:
                continue
            if path.name == "extraction_inventory.py":
                continue
            text = path.read_text(encoding="utf-8")
            if stem not in text:
                continue
            rel = str(path.relative_to(root))
            if "tests" in path.parts or path.name.endswith(".test.ts"):
                harnesses.append(rel)
            else:
                production.append(rel)
        independent = [
            path for path in production if not path.startswith("libs/cua-driver/examples/jev-use/")
        ]
        rows.append(
            {
                "abstraction": stem,
                "production_call_sites": sorted(production),
                "harness_call_sites": sorted(harnesses),
                "independent_harnesses": independent,
                "disposition": "recipe-local" if len(independent) < 2 else "extract now",
            }
        )
    return rows
