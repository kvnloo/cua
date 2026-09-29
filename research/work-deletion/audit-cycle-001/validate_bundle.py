"""Verify the saved audit bundle and protected source evidence; optionally seal it."""

from __future__ import annotations
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

from auditor import audit_bound
from challenge_retained import cases
from prepare import HERE, ROOT, EXAMPLE, EVIDENCE, PIN, dump, git, sha


def bundle_files():
    return sorted(
        p
        for p in HERE.rglob("*")
        if p.is_file()
        and not {"tmp", "__pycache__"}.intersection(p.relative_to(HERE).parts)
        and p.name != "artifact-hashes.json"
    )


def verify_sources():
    initial = json.loads((HERE / "source-inventory.json").read_text())
    current = {str(p.relative_to(EVIDENCE)): sha(p) for p in EVIDENCE.rglob("*") if p.is_file()}
    assert current == {name: info["sha256"] for name, info in initial["retained_files"].items()}, (
        "protected retained evidence changed"
    )
    for name, digest in initial["example_files"].items():
        assert sha(ROOT / name) == digest, f"protected source changed: {name}"
    assert git("rev-parse", f"{PIN}:libs/cua-driver/rust") == initial["source_rust_tree"]
    assert (
        git("diff", PIN, "--", "libs/cua-driver/examples/jev-use", "libs/cua-driver/rust") == ""
    ), "shipped code modified"
    assert git("branch", "--show-current") == "research/guarded-receipt-audit-20260929"
    driver = json.loads((EVIDENCE / "driver-build-receipt.json").read_text())
    assert driver["sha256"] == sha(EVIDENCE / "cua-driver-current-main")
    assert driver["source_rust_tree"] == initial["source_rust_tree"]
    return {
        "protected_evidence_files_unchanged": len(current),
        "protected_example_files_unchanged": len(initial["example_files"]),
        "driver_sha256": driver["sha256"],
        "driver_rust_tree": driver["source_rust_tree"],
        "runner_pin": PIN,
        "source_example_tree": initial["source_example_tree"],
    }


def check_rows(directory, count):
    rows = [json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()]
    assert len(rows) == count == len({(r["cell_key"], r["trial_key"]) for r in rows})
    for row in rows:
        folder = directory
        if "language" in row:
            folder /= row["language"]
        folder = folder / row["mode"] / row["mutation"]
        assert json.loads((folder / "result.json").read_text()) == row
        assert row["exact_head"] == PIN
        for name, digest in row["artifacts"].items():
            assert sha(folder / name) == digest, (folder, name)
        if "checker_sha256" in row:
            assert row["checker_sha256"] == sha(EXAMPLE / "verify_setup.py")
            assert row["challenge_producer_sha256"] == sha(HERE / "challenge_retained.py")
            assert sha(Path(row["source_jsonl"])) == row["source_jsonl_sha256"]
            assert (folder / "input.jsonl").read_bytes() == (folder / "output.jsonl").read_bytes()
        else:
            assert row["auditor_sha256"] == sha(HERE / "auditor.py")
            assert row["matrix_producer_sha256"] == sha(HERE / "run_auditor_matrix.py")
            result = audit_bound(
                folder / "claim.json", folder / "custody.json", row["custody_sha256"]
            )
            assert result == row["cli_result"]
    return rows


def privacy_scan():
    # Values are used only in memory. Do not report them or their individual hashes.
    values = set()
    for mode in ["default", "accepted", "declined"]:
        summary = json.loads((EVIDENCE / f"exact-{mode}/summary.json").read_text())
        values.update(c["token"] for c in summary["checks"])
    node = ast.parse((EXAMPLE / "python/tests/test_guarded_runner.py").read_text())
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "token" for t in n.targets)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
            and len(n.value.value) >= 12
        ):
            values.add(n.value.value)
    source = (EXAMPLE / "typescript/run_guarded_completion.test.ts").read_text()
    match = re.search(r"const TOKEN = '([^']+)'", source)
    assert match is not None, "missing retained TypeScript canary declaration"
    values.add(match.group(1))
    for p in bundle_files():
        text = p.read_text()
        assert all(value not in text for value in values), f"field value leaked in {p.name}"
    return {
        "retained_values_and_runner_canaries_absent": True,
        "ephemeral_values_checked_at_capture": True,
        "raw_values_or_per_value_hashes_emitted": False,
    }


def make_report():
    source = verify_sources()
    retained = check_rows(HERE / "retained-matrix", 2 * len(cases()))
    downstream = check_rows(HERE / "downstream-matrix", len(cases()) + 11)
    reused = [r for r in retained if r.get("reused_control")]
    controls = [
        r
        for r in retained
        if r["mutation"] in ["untouched", "decline-time-zero", "default-time-zero"]
    ]
    attacks = [r for r in retained if r not in controls]
    new_attacks = [r for r in attacks if not r.get("reused_control")]
    checks = []
    custody = HERE / "fix-captures/custody.json"
    for mode in ["default", "accepted", "declined"]:
        folder = HERE / "fix-captures" / mode
        result = audit_bound(folder / "claim.json", custody, sha(custody))
        assert result["qualifying"]
        receipt = json.loads((folder / "capture-receipt.json").read_text())
        assert receipt["capture_producer_sha256"] == sha(HERE / "capture_consumers.py")
        for name, digest in receipt["artifacts"].items():
            assert sha(folder / name) == digest
        trace = json.loads((folder / "transport-witness.json").read_text())
        checks.append(
            {
                "mode": mode,
                "cell_key": trace["cell_key"],
                "trial_key": trace["trial_key"],
                "provider_entries": trace["provider_count"],
                "scope": "FIX_ONLY",
                "verdict": result["verdict"],
            }
        )
    historical = json.loads((HERE / "downstream-matrix/historical-verdicts.json").read_text())
    assert len(historical) == 6 and all(not h["audit"]["qualifying"] for h in historical)
    for row in json.loads((HERE / "retained-tests.json").read_text()):
        assert row["exit_code"] == 0 and sha(HERE / row["log"]) == row["sha256"]
    node = Path("/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin/node")
    return {
        "verdict": "NONQUALIFYING_RETAINED_REAL_ROUTE",
        "meaning": "Recorded successful outcomes remain evidence of fixture success, not sufficient adversarial proof of intended route or provider-call deletion. No implementation defect or performance claim is made.",
        "source_checks": source,
        "retained_checker": {
            "total": len(retained),
            "accepted": sum(r["retained"]["accepted"] for r in retained),
            "rejected": sum(not r["retained"]["accepted"] for r in retained),
            "valid_controls": len(controls),
            "adversarial_trials": len(attacks),
            "adversarial_accepted": sum(r["retained"]["accepted"] for r in attacks),
            "adversarial_rejected": sum(not r["retained"]["accepted"] for r in attacks),
            "registered_oracle_controls_reused_on_corpus": len(reused),
            "new_adversarial_trials": len(new_attacks),
            "new_adversarial_accepted": sum(r["retained"]["accepted"] for r in new_attacks),
            "new_adversarial_rejected": sum(not r["retained"]["accepted"] for r in new_attacks),
            "categories": dict(
                Counter(r["mutation"] for r in attacks if r["retained"]["accepted"])
            ),
        },
        "downstream_auditor": {
            "total": len(downstream),
            "qualifying_fix_controls": sum(r["cli_result"]["qualifying"] for r in downstream),
            "nonqualifying_corruptions": sum(not r["cli_result"]["qualifying"] for r in downstream),
            "all_cli_and_core_checks_passed": True,
        },
        "captures": checks,
        "historical_real_rows_qualifying": 0,
        "historical_real_rows_examined": len(historical),
        "fixture_custody_sha256": sha(custody),
        "node_version": subprocess.check_output([str(node), "--version"], text=True).strip(),
        "node_sha256": sha(node),
        "privacy_checks": privacy_scan(),
        "limitations": [
            "No GUI, new REAL Driver execution, live provider, or speed benchmark.",
            "Fresh correlated FIX witnesses are not retroactive historical REAL evidence.",
            "Witness hash custody is a local integrity boundary, not authentication against a same-UID actor replacing the externally held root.",
            "Narrow auditor supports only the captured two-action Python mock-fixture schema; unsupported/missing evidence fails closed.",
            "Original journals lack trial IDs and original transport/provider counters. Session/proof labels alone do not bind actions.",
        ],
        "next_decision": "Parent independently verify, then optionally integrate this evidence-only auditor. Do not promote retained rows to route/provider-work-deletion proof. A future separately authorized REAL run needs passive counters/traces, action/session/ref binding and per-trial oracle attribution.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    report = make_report()
    if args.seal:
        dump(HERE / "audit-report.json", report)
        dump(
            HERE / "validation.json",
            {
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_checks": report["source_checks"],
                "privacy_checks": privacy_scan(),
                "canonical_matrices_verified": True,
            },
        )
        files = {str(p.relative_to(HERE)): sha(p) for p in bundle_files()}
        dump(
            HERE / "artifact-hashes.json",
            {
                "algorithm": "sha256",
                "files": files,
                "file_count": len(files),
                "excluded": [
                    "artifact-hashes.json (self-reference)",
                    "tmp/ (superseded local captures and ephemeral tests)",
                    "__pycache__/",
                ],
            },
        )
    else:
        manifest = json.loads((HERE / "artifact-hashes.json").read_text())
        assert manifest["files"] == {str(p.relative_to(HERE)): sha(p) for p in bundle_files()}, (
            "sealed artifact bytes changed"
        )
        assert manifest["file_count"] == len(manifest["files"])
        assert report == json.loads((HERE / "audit-report.json").read_text())
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "retained_trials": report["retained_checker"]["total"],
                "downstream_trials": report["downstream_auditor"]["total"],
                "protected_files_unchanged": report["source_checks"][
                    "protected_evidence_files_unchanged"
                ],
                "seal": args.seal,
            }
        )
    )


if __name__ == "__main__":
    main()
