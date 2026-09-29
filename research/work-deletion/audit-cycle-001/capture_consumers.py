"""Headless FIX consumer captures with independent oracle and call/dispatch sinks.

Reuse retained FixtureSession transport, pass through the real mock chooser,
call the genuine Python runner main()/parse_args(), and serve the unmodified
FixtureServer. This cannot establish a historical REAL route or performance.
"""

from __future__ import annotations
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import secrets
import sys
import threading
from urllib.request import urlopen
from unittest.mock import patch
from prepare import HERE, EXAMPLE, PIN, PYTHON, dump, sha

sys.path[:0] = [str(EXAMPLE / "python/tests"), str(EXAMPLE / "python"), str(EXAMPLE)]
from test_guarded_runner import FixtureSession, transport  # noqa: E402
import run  # noqa: E402
from fixture_server import FixtureServer  # noqa: E402
from verify_setup import verify  # noqa: E402


def child(mode, url, folder):
    token = os.environ["AUDIT_EPHEMERAL_VALUE"]
    cell = f"audit001/fix/python/{mode}"
    trace = []
    session = FixtureSession(url, token)
    call = session.call_tool
    observations = 0
    actions = 0

    def emit(kind, **fields):
        trace.append(
            {
                "seq": len(trace) + 1,
                "kind": kind,
                "cell_key": cell,
                "trial_key": "trial-001",
                **fields,
            }
        )

    async def call_tool(name, args):
        nonlocal observations, actions
        data = await call(name, args)
        if name == "get_browser_state" and args.get("snapshot_format") == "semantic_v2":
            observations += 1
            if mode == "declined" and session.value:
                # Evidence-only fixture fault after the provider's mutation;
                # no guard/provider/runner function is modified.
                data.structuredContent["refs"].append(
                    {"role": "button", "name": "Submit", "ref": "p2:2"}
                )
            refs = data.structuredContent["refs"]
            emit(
                "observation",
                observation=observations,
                after_actions=actions,
                session=args["session"],
                submit_refs=[
                    r["ref"]
                    for r in refs
                    if r.get("role") == "button" and r.get("name") == "Submit"
                ],
                field_contains_expected=any(
                    r.get("role") == "textbox" and r.get("value") == token for r in refs
                ),
            )
        elif name in ("browser_type", "browser_click"):
            actions += 1
            emit(
                "action",
                action=actions,
                tool=name,
                ref=args.get("ref"),
                session=args["session"],
                success=not data.isError,
            )
        return data

    session.call_tool = call_tool
    choose = run.choose_mock_for_task

    def counted(*args, **kwargs):
        emit("provider_call", after_actions=actions, after_observations=observations)
        return choose(*args, **kwargs)

    argv = [
        str(EXAMPLE / "python/run.py"),
        "--provider",
        "mock",
        "--fixture-url",
        url,
        "--max-steps",
        "4",
        "--log",
        str(folder / "events.jsonl"),
        "--token",
        token,
        "--visual-observation",
        "off",
    ]
    if mode != "default":
        argv.append("--guarded-completion")
    output = io.StringIO()
    with (
        patch.object(run, "stdio_client", transport),
        patch.object(run, "ClientSession", return_value=session),
        patch.object(run, "choose_mock_for_task", side_effect=counted),
        patch.object(sys, "argv", argv),
        contextlib.redirect_stdout(output),
    ):
        try:
            run.main()
        except SystemExit as e:
            status = e.code
    assert token not in output.getvalue()
    assert output.getvalue() == (folder / "events.jsonl").read_text()
    witness = {
        "cell_key": cell,
        "trial_key": "trial-001",
        "language": "python",
        "mode": mode,
        "exact_head": PIN,
        "scope": "FIX",
        "real_driver": False,
        "provider": "mock",
        "capture": "pass-through chooser entry counter and independent mock-transport dispatch/observation sink",
        "events": trace,
        "provider_count": sum(e["kind"] == "provider_call" for e in trace),
        "exit_code": status,
        "forced": {"guarded": mode != "default", "fixture_duplicate_submit": mode == "declined"},
    }
    dump(folder / "transport-witness.json", witness)
    raise SystemExit(status)


def capture(mode, out):
    folder = out / mode
    folder.mkdir(parents=True, exist_ok=False)
    token = secrets.token_hex(24)
    cell, trial = f"audit001/fix/python/{mode}", "trial-001"
    journal = []
    with FixtureServer(("127.0.0.1", 0)) as server:
        submit = server.state.submit

        def observed_submit(value):
            submit(value)
            journal.append(
                {
                    "cell_key": cell,
                    "trial_key": trial,
                    "language": "python",
                    "event": "fixture_submit",
                    "received_expected_value": value == token,
                    "committed_expected_value": server.state.snapshot() == {"submitted": token},
                }
            )

        server.state.submit = observed_submit
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/"
        try:
            with urlopen(url + "state", timeout=2) as response:
                empty = json.load(response) == {"submitted": None}
            command = [
                str(PYTHON),
                "-B",
                str(Path(__file__).resolve()),
                "--child",
                mode,
                url,
                str(folder),
            ]
            with patch.dict(os.environ, {"AUDIT_EPHEMERAL_VALUE": token}):
                result = verify(
                    command,
                    url,
                    token,
                    folder / "events.jsonl",
                    require_guarded_completion=mode == "accepted",
                    require_guarded_decline=mode == "declined",
                )
            with urlopen(url + "state", timeout=2) as response:
                state_matches = json.load(response) == {"submitted": token}
        finally:
            server.shutdown()
            thread.join(timeout=5)
    oracle = {
        "cell_key": cell,
        "trial_key": trial,
        "language": "python",
        "exact_head": PIN,
        "initially_empty": empty,
        "state_matches_expected": state_matches,
        "journal": journal,
        "capture": "unmodified HTTP /submit handler observer and separately fetched /state; no helper initiates submission",
    }
    dump(folder / "oracle-witness.json", oracle)
    transport_witness = json.loads((folder / "transport-witness.json").read_text())
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
    claim = {
        "schema": "guarded-audit-v1",
        "cell_key": cell,
        "trial_key": trial,
        "language": "python",
        "mode": mode,
        "exact_head": PIN,
        "scope": "FIX",
        "real_driver": False,
        "provider": "mock",
        "provider_count": transport_witness["provider_count"],
        "forced": transport_witness["forced"],
        "events": events,
        "steps": [e for e in events if e["event"] == "step"],
        "outcome_verified": result["outcome"] == "verified",
    }
    dump(folder / "claim.json", claim)
    assert all(token not in p.read_text() for p in folder.iterdir() if p.is_file())
    command_template = [arg if arg != url else "<owned-loopback-origin>" for arg in command]
    dump(
        folder / "capture-receipt.json",
        {
            "cell_key": cell,
            "trial_key": trial,
            "exact_head": PIN,
            "entrypoint": "unmodified python/run.py main() -> parse_args() -> run()",
            "capture_producer_sha256": sha(Path(__file__)),
            "command": command_template,
            "retained_verify_accepted": True,
            "retained_verifier_sha256": sha(EXAMPLE / "verify_setup.py"),
            "runner_sha256": sha(EXAMPLE / "python/run.py"),
            "fixture_sha256": sha(EXAMPLE / "fixture_server.py"),
            "reused_transport_sha256": sha(EXAMPLE / "python/tests/test_guarded_runner.py"),
            "artifacts": {p.name: sha(p) for p in folder.iterdir() if p.is_file()},
            "field_contents_persisted": False,
            "live_provider": False,
            "gui_used": False,
        },
    )
    return {
        "cell_key": cell,
        "trial_key": trial,
        "transport_path": str((folder / "transport-witness.json").relative_to(out)),
        "transport_sha256": sha(folder / "transport-witness.json"),
        "oracle_path": str((folder / "oracle-witness.json").relative_to(out)),
        "oracle_sha256": sha(folder / "oracle-witness.json"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=HERE / "fix-captures")
    args = parser.parse_args()
    args.out.resolve().relative_to(HERE)
    args.out.mkdir(exist_ok=False)
    bindings = [capture(mode, args.out) for mode in ["default", "accepted", "declined"]]
    dump(
        args.out / "custody.json",
        {"schema": "owned-witness-custody-v1", "exact_head": PIN, "bindings": bindings},
    )
    print(
        json.dumps(
            {"captures": len(bindings), "scope": "FIX, not REAL/BENCH", "oracle_verified": True}
        )
    )


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        child(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
    else:
        main()
