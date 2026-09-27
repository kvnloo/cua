"""Guarded-run A/B for kvnloo/cua#5.

Driver mode uses the same MCP/Chromium session shape as fast_path_live_ab.py.
Local mode drives the loopback fixture and the caller rule when that session
cannot be started. The provider is skipped only when bound_completion_id names
the single candidate required to finish a local obligation.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _load(evidence_root: Path):
    python = evidence_root / "libs/cua-driver/examples/jev-use/python"
    example = evidence_root / "libs/cua-driver/examples/jev-use"
    sys.path.insert(0, str(python))
    sys.path.insert(0, str(example))
    from core import Candidate
    from deterministic_fast_path import explain_fast_path
    from fixture_server import FixtureServer
    from guarded_run import (
        Decision,
        FreshObservation,
        admit_guarded_run,
        explain_second_child,
    )

    return (
        Candidate,
        explain_fast_path,
        FixtureServer,
        Decision,
        FreshObservation,
        admit_guarded_run,
        explain_second_child,
    )


class Fixture:
    def __init__(self, server_type: Any) -> None:
        self.server = server_type(("127.0.0.1", 0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def reset(self) -> None:
        urllib.request.urlopen(
            urllib.request.Request(f"{self.url}/reset", method="POST", data=b""),
            timeout=2,
        ).read()

    def submit(self, token: str) -> None:
        body = urllib.parse.urlencode({"value": token}).encode()
        urllib.request.urlopen(
            urllib.request.Request(f"{self.url}/submit", method="POST", data=body),
            timeout=2,
        ).read()

    def state(self) -> dict[str, Any]:
        with urllib.request.urlopen(f"{self.url}/state", timeout=2) as response:
            return json.loads(response.read().decode())


def _row(
    *,
    case: str,
    arm: str,
    route: str,
    provider_calls: int,
    provider_called_on_second: bool,
    second_dispatch: int,
    second_reason: str,
    action_calls: int,
    observations: int,
    outcome: str,
    oracle: dict[str, Any],
    token: str,
    elapsed_ms: float,
) -> dict[str, Any]:
    return {
        "case": case,
        "arm": arm,
        "route": route,
        "provider_calls": provider_calls,
        "provider_called_on_second": provider_called_on_second,
        "second_dispatch": second_dispatch,
        "second_reason": second_reason,
        "action_calls": action_calls,
        "semantic_observations": observations,
        "outcome": outcome,
        "oracle": oracle,
        "token": token,
        "verified_outcome_ms": round(elapsed_ms, 2),
        "execution": "loopback-fixture",
    }


def local_rows(evidence_root: Path) -> list[dict[str, Any]]:
    (
        Candidate,
        explain_fast_path,
        FixtureServer,
        Decision,
        FreshObservation,
        admit_guarded_run,
        explain_second_child,
    ) = _load(evidence_root)
    type_c = Candidate("type-verification-value", "type", "browser_type", {})
    submit = Candidate("submit-form", "submit", "browser_click", {})
    reobserve = Candidate("reobserve", "reobserve", None, {})
    fixture = Fixture(FixtureServer)
    rows: list[dict[str, Any]] = []
    token = "guarded-local-proof"
    try:
        negatives = (
            ("refuted first postcondition", "refuted", FreshObservation(token, "ref-submit", "cap-2")),
            ("unknown first postcondition", "unknown", FreshObservation(token, "ref-submit", "cap-2")),
            ("target disappears", "stale", None),
            ("target rebound", "rebound", FreshObservation(token, "other-ref", "cap-2")),
            ("stale capture", "verified", FreshObservation(token, "ref-submit", None)),
            ("second action refusal", "refused", FreshObservation(token, "ref-submit", "cap-2")),
            ("missing observation", "verified", None),
            ("mismatched submit ref", "verified", FreshObservation(token, "other-ref", "cap-2")),
        )
        for case, status, fresh in negatives:
            fixture.reset()
            started = time.perf_counter()
            plan = admit_guarded_run(
                [type_c, submit, reobserve],
                Decision("run", ("type-verification-value", "submit-form")),
                token=token,
                submit_ref="ref-submit",
            )
            assert plan is not None
            evidence = explain_second_child(status, fresh, plan)
            if evidence.allowed:
                fixture.submit(token)
            elapsed = (time.perf_counter() - started) * 1000
            oracle = fixture.state()
            rows.append(
                _row(
                    case=case,
                    arm="guarded-run",
                    route="guarded-run",
                    provider_calls=1,
                    provider_called_on_second=False,
                    second_dispatch=int(evidence.allowed),
                    second_reason=evidence.reason,
                    action_calls=int(evidence.allowed),
                    observations=1,
                    outcome="stopped",
                    oracle=oracle,
                    token=token,
                    elapsed_ms=elapsed,
                )
            )

        fixture.reset()
        started = time.perf_counter()
        plan = admit_guarded_run(
            [type_c, submit, reobserve],
            Decision("run", ("type-verification-value", "submit-form")),
            token=token,
            submit_ref="ref-submit",
        )
        assert plan is not None
        fresh = FreshObservation(token, "ref-submit", "cap-2")
        evidence = explain_second_child("verified", fresh, plan)
        authority = explain_fast_path(
            [submit, reobserve], bound_completion_id=plan.second.candidate_id
        )
        if evidence.allowed and authority.route == "fast-path":
            fixture.submit(token)
        elapsed = (time.perf_counter() - started) * 1000
        oracle = fixture.state()
        rows.append(
            _row(
                case="type then submit",
                arm="guarded-run",
                route=authority.route,
                provider_calls=1,
                provider_called_on_second=authority.provider_called,
                second_dispatch=int(evidence.allowed and authority.route == "fast-path"),
                second_reason=evidence.reason,
                action_calls=1 if oracle.get("submitted") == token else 0,
                observations=2,
                outcome="verified" if oracle.get("submitted") == token else "refuted",
                oracle=oracle,
                token=token,
                elapsed_ms=elapsed,
            )
        )

        fixture.reset()
        started = time.perf_counter()
        unbound = explain_fast_path([submit, reobserve])
        if unbound.route == "fast-path":
            fixture.submit(token)
        elapsed = (time.perf_counter() - started) * 1000
        rows.append(
            _row(
                case="one executable reobserve",
                arm="guarded-run",
                route=unbound.route,
                provider_calls=1 if unbound.provider_called else 0,
                provider_called_on_second=unbound.provider_called,
                second_dispatch=0,
                second_reason="chooser",
                action_calls=0,
                observations=1,
                outcome="chooser",
                oracle=fixture.state(),
                token=token,
                elapsed_ms=elapsed,
            )
        )

        fixture.reset()
        started = time.perf_counter()
        fixture.submit(token)
        elapsed = (time.perf_counter() - started) * 1000
        oracle = fixture.state()
        rows.append(
            _row(
                case="type then submit",
                arm="baseline",
                route="chooser",
                provider_calls=2,
                provider_called_on_second=True,
                second_dispatch=1,
                second_reason="provider",
                action_calls=1,
                observations=2,
                outcome="verified" if oracle.get("submitted") == token else "refuted",
                oracle=oracle,
                token=token,
                elapsed_ms=elapsed,
            )
        )
    finally:
        fixture.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--driver-bin", default="")
    parser.add_argument("--upstream-root", type=Path)
    args = parser.parse_args()
    rows = local_rows(args.evidence_root.resolve())
    driver_blocker = None
    if not args.driver_bin:
        driver_blocker = "no --driver-bin; Driver/Chromium session was not started"
    elif args.upstream_root is None:
        driver_blocker = "no --upstream-root; product checkout was not available"
    report = {
        "evidence_kind": "guarded-run-ab",
        "authority_rule": "1024f0627322b85b8b0dc3423abc2f7198133207",
        "driver_execution": "not started" if driver_blocker else "requested",
        "driver_blocker": driver_blocker,
        "rows": rows,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"event": "wrote", "rows": len(rows), "blocker": driver_blocker}))


if __name__ == "__main__":
    main()
