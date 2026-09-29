"""Materialize corrupt-evidence cases and exercise the downstream CLI/core.

Every input is labelled as an intentional mutation of captured FIX evidence.
Modified witness bytes never receive a replacement trusted hash. Core checks
are reported separately so integrity rejection cannot hide semantic gaps.
"""

from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
from auditor import audit_capture, audit_historical
from challenge_retained import cases
from prepare import HERE, PIN, dump, sha


def mutate(c, t, o, spec):
    name, target, key, value = spec
    step = c["events"][1]
    if target == "proof":
        step["guarded_completion"][key] = value
    elif target == "step":
        step[key] = value
    elif target == "first":
        c["events"][0][key] = value
    elif target == "receipt":
        c[key] = value
    elif name == "duplicate-proof":
        c["events"][0]["guarded_completion"] = copy.deepcopy(step["guarded_completion"])
    elif name == "additional-outcome":
        c["events"].insert(1, {"event": "outcome", "outcome": "unknown"})
    elif name == "journal-outcome-false":
        o["journal"][0]["committed_expected_value"] = False
    elif name == "journal-language-wrong":
        o["journal"][0]["language"] = "foreign-language"
    elif name == "journal-duplicate":
        o["journal"].append(copy.deepcopy(o["journal"][0]))
    elif name == "oracle-no-submit":
        o.update(state_matches_expected=False, journal=[])
    elif name == "oracle-wrong-submit":
        o["state_matches_expected"] = False
    elif name == "actual-counter-removed":
        t["events"] = [e for e in t["events"] if e["kind"] != "provider_call"]
    elif name == "reported-counter-extra":
        c["provider_count"] += 1
    elif name == "counter-claim-only":
        c["provider_count"] = 0
    elif name == "oracle-trial-foreign":
        o["trial_key"] = "foreign-trial"
    elif name == "transport-trial-foreign":
        t["events"][1]["trial_key"] = "foreign-trial"
    elif name == "dispatch-ref-foreign":
        t["events"][-1]["ref"] = "p999:777"
    elif name == "dispatch-session-foreign":
        t["events"][-1]["session"] = "foreign-session"
    elif name == "observation-field-unproven":
        t["events"][3]["field_contains_expected"] = False
    elif name == "claim-real-upgrade":
        c.update(real_driver=True, scope="REAL")
    elif name == "forced-guard-off":
        c["forced"]["guarded"] = False
    elif name == "wrong-decline-observation":
        t["events"][3]["submit_refs"] = ["p2:1"]
    # Mutate BOTH redundant copies for semantic challenges; only the explicit
    # receipt disagreement cell leaves the copies inconsistent.
    c["steps"] = copy.deepcopy([e for e in c["events"] if e.get("event") == "step"])
    if name == "receipt-steps-disagree":
        c["steps"][1]["tool"] = "click"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=HERE / "downstream-matrix")
    parser.add_argument("--captures", type=Path, default=HERE / "fix-captures")
    parser.add_argument("--retained", type=Path, default=HERE / "retained-matrix")
    args = parser.parse_args()
    args.out.resolve().relative_to(HERE)
    args.out.mkdir(parents=True, exist_ok=False)
    base = args.captures.resolve()
    original_custody = json.loads((base / "custody.json").read_text())
    extra = [
        ("accepted", (name, "special", None, None))
        for name in [
            "actual-counter-removed",
            "reported-counter-extra",
            "counter-claim-only",
            "oracle-trial-foreign",
            "transport-trial-foreign",
            "dispatch-ref-foreign",
            "dispatch-session-foreign",
            "observation-field-unproven",
            "claim-real-upgrade",
            "forced-guard-off",
        ]
    ]
    extra.append(("declined", ("wrong-decline-observation", "special", None, None)))
    rows = []
    for mode, spec in cases() + extra:
        name = spec[0]
        folder = args.out / mode / name
        folder.mkdir(parents=True, exist_ok=False)
        c, t, o = [
            json.loads((base / mode / f).read_text())
            for f in ["claim.json", "transport-witness.json", "oracle-witness.json"]
        ]
        mutate(c, t, o, spec)
        for file, obj in [
            ("claim.json", c),
            ("transport-witness.json", t),
            ("oracle-witness.json", o),
        ]:
            dump(folder / file, obj)
        binding = copy.deepcopy(
            next(
                b
                for b in original_custody["bindings"]
                if b["cell_key"] == f"audit001/fix/python/{mode}"
            )
        )
        binding["transport_path"] = "transport-witness.json"
        binding["oracle_path"] = "oracle-witness.json"
        # Same original witness hashes, never resealed to match corrupted bytes.
        dump(
            folder / "custody.json",
            {"schema": "owned-witness-custody-v1", "exact_head": PIN, "bindings": [binding]},
        )
        anchor = sha(folder / "custody.json")
        command = [
            sys.executable,
            "-B",
            str(HERE / "auditor.py"),
            "--claim",
            str(folder / "claim.json"),
            "--custody",
            str(folder / "custody.json"),
            "--custody-sha256",
            anchor,
        ]
        run = subprocess.run(command, capture_output=True, text=True, timeout=10)
        result = json.loads(run.stdout)
        expected = name in ["untouched", "decline-time-zero", "default-time-zero"]
        core = audit_capture(c, t, o)
        assert result["qualifying"] == expected and core["qualifying"] == expected, (
            mode,
            name,
            result,
            core,
        )
        assert run.returncode == (0 if expected else 1), (name, run.returncode)
        row = {
            "cell_key": f"audit001/downstream/python/{mode}/{name}",
            "trial_key": "trial-001",
            "mutation": name,
            "mode": mode,
            "exact_head": PIN,
            "base_capture": str(base / mode),
            "intentional_corrupt_evidence": not expected,
            "source_scope": "FIX only; never historical REAL",
            "auditor_sha256": sha(HERE / "auditor.py"),
            "matrix_producer_sha256": sha(Path(__file__)),
            "command": command,
            "exit_code": run.returncode,
            "custody_sha256": anchor,
            "cli_result": result,
            "core_result": core,
            "artifacts": {p.name: sha(p) for p in folder.iterdir() if p.is_file()},
        }
        dump(folder / "result.json", row)
        rows.append(row)
        with (args.out / "results.jsonl").open("a") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    assert (
        len(rows)
        == len({(r["cell_key"], r["trial_key"]) for r in rows})
        == len(cases()) + len(extra)
    )
    summary = {
        "total": len(rows),
        "qualifying_fix_controls": sum(r["cli_result"]["qualifying"] for r in rows),
        "nonqualifying_corruptions": sum(not r["cli_result"]["qualifying"] for r in rows),
        "all_core_and_cli_expectations_met": True,
    }
    dump(args.out / "summary.json", summary)
    historical = []
    for lang in ["python", "typescript"]:
        for mode in ["default", "accepted", "declined"]:
            folder = args.retained / lang / mode / "untouched"
            historical.append(
                {
                    "cell_key": f"audit001/historical/{lang}/{mode}",
                    "trial_key": "retrospective-label-not-original-attribution",
                    "audit": audit_historical(folder),
                    "note": "Uses retained original receipt/JSONL/journal, not the replay oracle or fresh FIX witnesses",
                    "receipt": str(folder / "claimed-receipt.json"),
                    "source_jsonl_sha256": json.loads((folder / "result.json").read_text())[
                        "source_jsonl_sha256"
                    ],
                }
            )
    dump(args.out / "historical-verdicts.json", historical)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
