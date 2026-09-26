"""Which existing contract field gates each caller optimization. kvnloo/cua#27."""

from __future__ import annotations

from pathlib import Path

from core import Candidate
from deterministic_fast_path import single_executable_candidate
from guarded_run import Decision, admit_guarded_run
from lazy_vision import needs_visual_capture

PIN = "c5ee191c02b11448ffefcc38b78b064a87d8ef23"
CONTRACT_WINDOW = "libs/cua-driver/rust/crates/cua-driver-contract/src/windows.rs"
LINUX_STUB = "libs/cua-driver/rust/crates/platform-linux/src/tools/stubs.rs"
LINUX_IMPL = "libs/cua-driver/rust/crates/platform-linux/src/tools/impl_.rs"
VERIFY = "libs/cua-driver/rust/crates/cua-driver-contract/src/verification.rs"
CONTRACT_SRC = "libs/cua-driver/rust/crates/cua-driver-contract/src"

COLUMNS = (
    "optimization",
    "existing_contract_field",
    "contract",
    "linux_stub",
    "linux_impl",
    "verify_state",
    "rule",
    "caller_result",
    "live_tools_list",
)


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _presence(text: str, field: str) -> str:
    return "present" if field in text else "absent"


def _contract_has(root: Path, field: str) -> str:
    base = root / CONTRACT_SRC
    for path in sorted(base.glob("*.rs")):
        if field in path.read_text(encoding="utf-8"):
            return "present"
    return "absent"


def _caller_results() -> dict[str, str]:
    semantic = [Candidate("type-verification-value", "type", "browser_type", {})]
    visual = [Candidate("submit-form", "submit", "browser_click", {}, capture_id="cap-1")]
    admitted = single_executable_candidate(semantic)
    guarded = admit_guarded_run(
        [
            Candidate("type-verification-value", "type", "browser_type", {}),
            Candidate("submit-form", "submit", "browser_click", {}),
        ],
        Decision("run", ("type-verification-value", "submit-form")),
        token="proof",
        submit_ref="ref-submit",
    )
    return {
        "lazy": "semantic off" if not needs_visual_capture(semantic) else "semantic on",
        "visual_still_needs_capture": "true" if needs_visual_capture(visual) else "false",
        "fast": "chooser" if admitted is None else admitted.id,
        "guarded": "not admitted" if guarded is None else guarded.first.candidate_id,
    }


def matrix_rows(root: Path) -> list[dict[str, str]]:
    window = _read(root, CONTRACT_WINDOW)
    stub = _read(root, LINUX_STUB)
    live = _read(root, LINUX_IMPL)
    verify = _read(root, VERIFY)
    caller = _caller_results()
    settlement = _contract_has(root, "post_dispatch_observation")
    return [
        {
            "optimization": "omit accessibility traversal",
            "existing_contract_field": "get_window_state.include_accessibility_tree",
            "contract": _presence(window, "include_accessibility_tree"),
            "linux_stub": _presence(stub, "include_accessibility_tree"),
            "linux_impl": _presence(live, "include_accessibility_tree"),
            "verify_state": _presence(verify, "include_accessibility_tree"),
            "rule": "schema/property preflight",
            "caller_result": "stub schema omits the field"
            if _presence(stub, "include_accessibility_tree") == "absent"
            else "advertised",
            "live_tools_list": "not captured",
        },
        {
            "optimization": "omit screenshot",
            "existing_contract_field": "include_screenshot",
            "contract": _presence(window, "include_screenshot"),
            "linux_stub": _presence(stub, "include_screenshot"),
            "linux_impl": _presence(live, "include_screenshot"),
            "verify_state": _presence(verify, "include_screenshot"),
            "rule": "schema/property preflight",
            "caller_result": "present on get_window_state and verify_state",
            "live_tools_list": "not captured",
        },
        {
            "optimization": "bounded verification",
            "existing_contract_field": "verify_state.timeout_ms",
            "contract": _presence(window, "timeout_ms"),
            "linux_stub": _presence(stub, "timeout_ms"),
            "linux_impl": _presence(live, "timeout_ms"),
            "verify_state": _presence(verify, "timeout_ms"),
            "rule": "schema/property preflight",
            "caller_result": "stable_samples "
            + _presence(verify, "stable_samples"),
            "live_tools_list": "not captured",
        },
        {
            "optimization": "settlement or revision",
            "existing_contract_field": "none",
            "contract": settlement,
            "linux_stub": _presence(stub, "post_dispatch_observation"),
            "linux_impl": _presence(live, "post_dispatch_observation"),
            "verify_state": _presence(verify, "post_dispatch_observation"),
            "rule": "do not add a second capability registry",
            "caller_result": "no public field on this branch",
            "live_tools_list": "not captured",
        },
        {
            "optimization": "lazy visual skip",
            "existing_contract_field": "click.capture_id when advertised",
            "contract": "caller",
            "linux_stub": "caller",
            "linux_impl": "caller",
            "verify_state": "caller",
            "rule": "schema/property preflight",
            "caller_result": caller["lazy"] + "; visual candidate still needs capture " + caller["visual_still_needs_capture"],
            "live_tools_list": "not captured",
        },
        {
            "optimization": "fast path",
            "existing_contract_field": "none",
            "contract": "caller",
            "linux_stub": "caller",
            "linux_impl": "caller",
            "verify_state": "caller",
            "rule": "caller predicate; not a contract field",
            "caller_result": caller["fast"],
            "live_tools_list": "not captured",
        },
        {
            "optimization": "guarded run",
            "existing_contract_field": "none",
            "contract": "caller",
            "linux_stub": "caller",
            "linux_impl": "caller",
            "verify_state": "caller",
            "rule": "caller predicate; not a contract field",
            "caller_result": caller["guarded"],
            "live_tools_list": "not captured",
        },
        {
            "optimization": "conditional skip",
            "existing_contract_field": "none",
            "contract": "not enabled",
            "linux_stub": "not enabled",
            "linux_impl": "not enabled",
            "verify_state": "not enabled",
            "rule": "not enabled",
            "caller_result": "not enabled",
            "live_tools_list": "not captured",
        },
    ]


def matrix_tsv(root: Path) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in matrix_rows(root):
        lines.append("\t".join(row[column] for column in COLUMNS))
    lines.append(f"# pinned_upstream\t{PIN}")
    return "\n".join(lines) + "\n"
