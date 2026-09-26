"""Version questions for a field this experiment does not add. kvnloo/cua#38."""

from __future__ import annotations

from pathlib import Path

README = "libs/cua-driver/contract/README.md"
WINDOW_INPUT = "libs/cua-driver/rust/crates/cua-driver-contract/src/windows.rs"
VERIFY_INPUT = "libs/cua-driver/rust/crates/cua-driver-contract/src/verification.rs"
VERSION_FIELDS = (
    "contract_version",
    "tools_list_schema_version",
    "capability_version",
    "mcp_protocol_version",
)

COLUMNS = (
    "shape",
    "selected",
    "contract_version_bump",
    "capability_version_bump",
    "tools_list_schema_change",
    "bindings_regenerated",
    "compat_fixture_updated",
    "consumer_trial",
    "note",
)


def documented_versions(readme: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in readme.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] in VERSION_FIELDS:
            found[cells[0]] = cells[1]
    return found


def input_denies_unknown_fields(text: str, struct: str) -> bool:
    marker = f"pub struct {struct}"
    index = text.index(marker)
    return "deny_unknown_fields" in text[max(0, index - 200) : index]


def migration_rows(root: Path) -> list[dict[str, str]]:
    readme = (root / README).read_text(encoding="utf-8")
    versions = documented_versions(readme)
    window = (root / WINDOW_INPUT).read_text(encoding="utf-8")
    verify = (root / VERIFY_INPUT).read_text(encoding="utf-8")
    denies = input_denies_unknown_fields(window, "GetWindowStateInput") and input_denies_unknown_fields(
        verify, "VerifyStateInput"
    )
    denial = (
        "GetWindowStateInput and VerifyStateInput use deny_unknown_fields"
        if denies
        else "deny_unknown_fields was not found on those inputs"
    )
    contract = versions.get("contract_version", "missing")
    capability = versions.get("capability_version", "missing")
    return [
        {
            "shape": "additive optional field",
            "selected": "no",
            "contract_version_bump": "yes if it changes the generated SDK shape",
            "capability_version_bump": "no",
            "tools_list_schema_change": "yes",
            "bindings_regenerated": "not done",
            "compat_fixture_updated": "not done",
            "consumer_trial": "not run",
            "note": denial,
        },
        {
            "shape": "new nested typed record",
            "selected": "no",
            "contract_version_bump": "yes if it changes the generated SDK shape",
            "capability_version_bump": "no",
            "tools_list_schema_change": "yes",
            "bindings_regenerated": "not done",
            "compat_fixture_updated": "not done",
            "consumer_trial": "not run",
            "note": f"contract_version documented as {contract}",
        },
        {
            "shape": "capability-gated variant",
            "selected": "no",
            "contract_version_bump": "no",
            "capability_version_bump": "yes",
            "tools_list_schema_change": "yes",
            "bindings_regenerated": "not done",
            "compat_fixture_updated": "not done",
            "consumer_trial": "not run",
            "note": f"capability_version documented as {capability}",
        },
        {
            "shape": "new tool or result type",
            "selected": "no",
            "contract_version_bump": "yes if it changes the generated SDK shape",
            "capability_version_bump": "yes",
            "tools_list_schema_change": "yes",
            "bindings_regenerated": "not done",
            "compat_fixture_updated": "not done",
            "consumer_trial": "not run",
            "note": denial,
        },
        {
            "shape": "no field added",
            "selected": "yes",
            "contract_version_bump": "no",
            "capability_version_bump": "no",
            "tools_list_schema_change": "no",
            "bindings_regenerated": "no",
            "compat_fixture_updated": "no",
            "consumer_trial": "not run",
            "note": "this experiment adds no production field; daemon consumer trials were not run",
        },
    ]


def migration_tsv(root: Path) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in migration_rows(root):
        lines.append("\t".join(row[column] for column in COLUMNS))
    return "\n".join(lines) + "\n"
