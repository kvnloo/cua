"""Architecture-cost rows for kvnloo/cua#45. Milliseconds were not measured."""

from __future__ import annotations

from pathlib import Path

PIN = "c5ee191c02b11448ffefcc38b78b064a87d8ef23"

# evidence path, and whether this branch added that mechanism
MECHANISMS = (
    ("lazy vision", "libs/cua-driver/examples/jev-use/python/lazy_vision.py", True),
    (
        "screenshot-only verifier projection",
        "libs/cua-driver/examples/jev-use/python/tests/test_verify_elapsed_order.py",
        True,
    ),
    (
        "settlement provenance",
        "libs/cua-driver/rust/crates/platform-macos/src/window_change_detector.rs",
        True,
    ),
    ("passive observations", "libs/cua-driver/examples/jev-use/python/passive_observation.py", True),
    ("guarded runs", "libs/cua-driver/examples/jev-use/python/guarded_run.py", True),
    ("batch actions", "libs/cua-driver/examples/jev-use/python/stale_batch.py", True),
    ("conditional observation", "scripts/repro/handoff/issue-30-transitions.md", False),
    (
        "shared helper extraction",
        "libs/cua-driver/examples/jev-use/python/extraction_inventory.py",
        False,
    ),
)

COLUMNS = (
    "mechanism",
    "evidence",
    "evidence_present",
    "public_fields_added",
    "loc",
    "model_calls_removed",
    "observation_calls_removed",
    "milliseconds_removed",
    "class",
    "pinned_upstream",
)


def cost_class(*, added: bool, public_fields_added: int) -> str:
    if not added:
        return "not added"
    if public_fields_added == 0:
        return "free consolidation: existing owner and no public surface"
    return "unmeasured"


def ledger_rows(root: Path) -> list[dict[str, str]]:
    rows = []
    for mechanism, evidence, added in MECHANISMS:
        path = root / evidence
        present = path.is_file()
        loc = 0
        if present:
            loc = len(path.read_text(encoding="utf-8").splitlines())
        public_fields = 0
        rows.append(
            {
                "mechanism": mechanism,
                "evidence": evidence,
                "evidence_present": str(present).lower(),
                "public_fields_added": str(public_fields),
                "loc": str(loc),
                "model_calls_removed": "not measured",
                "observation_calls_removed": "not measured",
                "milliseconds_removed": "not measured",
                "class": cost_class(added=added and present, public_fields_added=public_fields),
                "pinned_upstream": PIN,
            }
        )
    return rows


def ledger_tsv(root: Path) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in ledger_rows(root):
        lines.append("\t".join(row[column] for column in COLUMNS))
    return "\n".join(lines) + "\n"
