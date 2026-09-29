"""Replay redacted retained logs through the exact verify() consumer.

This is a verifier adversary, NOT a Driver performance or optimization run.
The child is intentionally an untrusted producer; it can submit independently
of its claimed JSONL. No verifier subprocess/HTTP/oracle functions are mocked.
"""

from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import threading
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from unittest.mock import patch
from prepare import HERE, EXAMPLE, EVIDENCE, PIN, dump, sha

sys.path.insert(0, str(EXAMPLE))
from fixture_server import FixtureServer
from verify_setup import verify


def cases():
    # Existing explicit controls are registered in existing-controls.json and
    # exercised unchanged by run_retained_tests.py, not reimplemented here.
    accepted = [
        ("untouched", "baseline", None, None),
        ("fresh-ref-unobserved", "proof", "fresh_ref", "p999:777"),
        ("fresh-ref-whitespace", "proof", "fresh_ref", " "),
        ("prior-ref-unobserved", "proof", "prior_ref", "p888:777"),
        ("session-foreign", "proof", "session", "foreign-session"),
        ("session-whitespace", "proof", "session", " "),
        ("session-empty", "proof", "session", ""),
        ("proof-field-wrong", "proof", "verification_field", "unproven"),
        ("proof-status-wrong", "proof", "status", "declined"),
        ("proof-uniqueness-zero", "proof", "submit_matches", 0),
        ("proof-uniqueness-two", "proof", "submit_matches", 2),
        ("proof-uniqueness-bool", "proof", "submit_matches", True),
        ("proof-uniqueness-float", "proof", "submit_matches", 1.0),
        ("proof-extra-key", "proof", "not_a_proof_field", "redacted-audit-marker"),
        ("guarded-time-nonzero", "step", "provider_decision_ms", 1),
        ("guarded-time-bool", "step", "provider_decision_ms", False),
        ("guarded-dry-run", "step", "dry_run", True),
        ("guarded-action-error", "step", "action_error", "action_failed"),
        ("guarded-tool-none", "step", "tool", None),
        ("guarded-wrong-candidate", "step", "candidate", "reobserve"),
        ("step-number-repeated", "step", "step", 1),
        ("first-action-missing", "first", "tool", None),
        ("first-action-error", "first", "action_error", "action_failed"),
        ("provider-counter-zero", "step", "provider_calls", 0),
        ("provider-counter-extra", "step", "provider_calls", 7),
        ("duplicate-proof", "special", None, None),
        ("additional-outcome", "special", None, None),
        ("receipt-pin-wrong", "receipt", "exact_head", "0" * 40),
        ("receipt-mode-wrong", "receipt", "mode", "default"),
        ("receipt-steps-disagree", "special", None, None),
        ("journal-outcome-false", "special", None, None),
        ("journal-language-wrong", "special", None, None),
        ("journal-duplicate", "special", None, None),
        ("oracle-no-submit", "oracle", None, None),
        ("oracle-wrong-submit", "oracle", None, None),
    ]
    decline = [
        ("untouched", "baseline", None, None),
        ("decline-reason-extra", "proof", "reason", "submit_not_unique+ref_reused"),
        ("decline-proof-extra-key", "proof", "session", "foreign-session"),
        ("decline-status-wrong", "proof", "status", "accepted"),
        ("decline-counter-one", "step", "provider_calls", 1),
        ("decline-time-zero", "step", "provider_decision_ms", 0),
        ("decline-dry-run", "step", "dry_run", True),
        ("decline-step-number", "step", "step", -1),
    ]
    default = [
        ("untouched", "baseline", None, None),
        ("default-route-guarded", "step", "decision_route", "guarded-completion"),
        ("default-counter-zero", "step", "provider_calls", 0),
        ("default-time-zero", "step", "provider_decision_ms", 0),
    ]
    return (
        [("accepted", c) for c in accepted]
        + [("declined", c) for c in decline]
        + [("default", c) for c in default]
    )


def child():
    source, log, url, behavior = sys.argv[2:]
    value = os.environ["AUDIT_EPHEMERAL_VALUE"]
    if behavior != "oracle-no-submit":
        if behavior == "oracle-wrong-submit":
            value = secrets.token_hex(24)
        with urlopen(Request(url + "submit", data=urlencode({"value": value}).encode()), timeout=2):
            pass
    shutil.copyfile(source, log)


def run_case(language, mode, spec, out):
    name, target, key, value = spec
    cell = f"audit001/retained/{language}/{mode}/{name}"
    trial = "trial-001"
    folder = out / language / mode / name
    folder.mkdir(parents=True, exist_ok=False)
    original = EVIDENCE / ("exact-" + mode)
    events = [
        json.loads(line) for line in (original / f"{language}-mock.jsonl").read_text().splitlines()
    ]
    receipt = json.loads((original / "receipt.json").read_text())
    journal = [
        json.loads(line) for line in (original / "fixture-journal.jsonl").read_text().splitlines()
    ]
    step = events[1]
    if target == "proof":
        step["guarded_completion"][key] = value
    elif target == "step":
        step[key] = value
    elif target == "first":
        events[0][key] = value
    elif target == "receipt":
        receipt[key] = value
    elif name == "duplicate-proof":
        events[0]["guarded_completion"] = copy.deepcopy(step["guarded_completion"])
    elif name == "additional-outcome":
        events.insert(1, {"event": "outcome", "outcome": "unknown"})
    elif name == "receipt-steps-disagree":
        receipt["steps"][language][1]["tool"] = "click"
    elif name.startswith("journal-"):
        selected = next(e for e in journal if e["language"] == language)
        if name == "journal-outcome-false":
            selected["committed_expected_value"] = False
        elif name == "journal-language-wrong":
            selected["language"] = "foreign-language"
        elif name == "journal-duplicate":
            journal.append(copy.deepcopy(selected))
    source = folder / "input.jsonl"
    source.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in events))
    dump(folder / "claimed-receipt.json", receipt)
    (folder / "claimed-journal.jsonl").write_text(
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in journal)
    )
    token = secrets.token_hex(24)
    captured = []
    with FixtureServer(("127.0.0.1", 0)) as server:
        original_submit = server.state.submit

        def observe_submit(received):
            original_submit(received)
            captured.append(
                {
                    "cell_key": cell,
                    "trial_key": trial,
                    "language": language,
                    "received_expected_value": received == token,
                    "committed_expected_value": server.state.snapshot() == {"submitted": token},
                }
            )

        server.state.submit = observe_submit
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/"
        try:
            with urlopen(url + "state", timeout=2) as r:
                initially_empty = json.load(r) == {"submitted": None}
            command = [
                sys.executable,
                "-B",
                str(Path(__file__).resolve()),
                "--child",
                str(source),
                str(folder / "output.jsonl"),
                url,
                name,
            ]
            # Transient environment, never argv, files, stdout or receipts.
            with patch.dict(os.environ, {"AUDIT_EPHEMERAL_VALUE": token}):
                try:
                    result = verify(
                        command,
                        url,
                        token,
                        folder / "output.jsonl",
                        require_guarded_completion=mode == "accepted",
                        require_guarded_decline=mode == "declined",
                    )
                    observed = {
                        "accepted": True,
                        "returned_outcome": result["outcome"],
                        "returned_path": result["acted_path"],
                        "returned_routes": result["decision_routes"],
                    }
                except Exception as e:
                    observed = {
                        "accepted": False,
                        "error_type": type(e).__name__,
                        "error": str(e).replace(token, "<redacted>"),
                    }
            with urlopen(url + "state", timeout=2) as r:
                final = json.load(r)
            independent = {
                "initially_empty": initially_empty,
                "state_matches_expected": final == {"submitted": token},
                "state_empty": final == {"submitted": None},
                "journal": captured,
                "oracle": "unmodified FixtureHandler /submit and independently fetched /state",
                "actor": "adversarial replay child, not Driver",
            }
        finally:
            server.shutdown()
            thread.join(timeout=5)
    assert token not in "".join(p.read_text() for p in folder.iterdir() if p.is_file())
    dump(folder / "independent-check.json", independent)
    record = {
        "cell_key": cell,
        "trial_key": trial,
        "language": language,
        "mode": mode,
        "mutation": name,
        "exact_head": PIN,
        "source_jsonl": str(original / f"{language}-mock.jsonl"),
        "source_jsonl_sha256": sha(original / f"{language}-mock.jsonl"),
        "checker": "unmodified verify_setup.verify",
        "checker_sha256": sha(EXAMPLE / "verify_setup.py"),
        "challenge_producer_sha256": sha(Path(__file__)),
        "reused_control": {
            "oracle-no-submit": "test_verify_setup.VerifySetupTests.test_required_guard_decline_keeps_the_independent_oracle",
            "oracle-wrong-submit": "test_verify_setup.VerifySetupTests.test_rejects_wrong_submission_despite_verified_event",
        }.get(name),
        "command": command,
        "retained": observed,
        "independent": independent,
        "scope": "FIX verifier challenge, not a new REAL run",
        "sidecars_consumed_by_retained_checker": False,
        "artifacts": {p.name: sha(p) for p in folder.iterdir() if p.is_file()},
    }
    dump(folder / "result.json", record)
    return record


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=HERE / "retained-matrix")
    args = p.parse_args()
    args.out.resolve().relative_to(HERE)
    # The registered negative controls ran before this matrix.
    tests = json.loads((HERE / "retained-tests.json").read_text())
    assert all(t["exit_code"] == 0 for t in tests)
    args.out.mkdir(parents=True, exist_ok=False)
    rows = []
    with (args.out / "results.jsonl").open("a") as result_file:
        for language in ["python", "typescript"]:
            for mode, spec in cases():
                row = run_case(language, mode, spec, args.out)
                rows.append(row)
                result_file.write(json.dumps(row, sort_keys=True) + "\n")
                result_file.flush()
    assert len({(r["cell_key"], r["trial_key"]) for r in rows}) == len(rows) == 2 * len(cases())
    summary = {
        "total": len(rows),
        "accepted": sum(r["retained"]["accepted"] for r in rows),
        "rejected": sum(not r["retained"]["accepted"] for r in rows),
        "mutations": {
            name: {
                lang: [
                    r["retained"]["accepted"]
                    for r in rows
                    if r["mutation"] == name and r["language"] == lang
                ]
                for lang in ["python", "typescript"]
            }
            for name in sorted({r["mutation"] for r in rows})
        },
    }
    dump(args.out / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "mutations"}))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        child()
    else:
        main()
