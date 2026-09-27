"""Guarded-run A/B for kvnloo/cua#5.

Driver mode uses the same MCP/Chromium session shape as fast_path_live_ab.py.
Local mode drives the loopback fixture and the caller rule when that session
cannot be started. The provider is skipped only when bound_completion_id names
the single candidate required to finish a local obligation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
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
    execution: str = "loopback-fixture",
    prior_ref: str | None = None,
    dispatch_ref: str | None = None,
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
        "execution": execution,
        "stale_incidents": 1 if second_reason == "stale" else 0,
        "prior_ref": prior_ref,
        "dispatch_ref": dispatch_ref,
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
        churn = admit_guarded_run(
            [type_c, submit, reobserve],
            Decision("run", ("type-verification-value", "submit-form")),
            token=token,
            submit_ref="ref-before",
            target_role="button",
            target_name="Submit",
        )
        assert churn is not None
        churn_fresh = FreshObservation(
            token, "ref-after", "cap-2", role="button", name="Submit", match_count=1, resolved_ref="ref-after"
        )
        churn_evidence = explain_second_child("verified", churn_fresh, churn)
        churn_authority = explain_fast_path([submit], bound_completion_id=churn.second.candidate_id)
        if (
            churn_evidence.allowed
            and churn_evidence.dispatch_ref == "ref-after"
            and churn_authority.route == "fast-path"
        ):
            fixture.submit(token)
        elapsed = (time.perf_counter() - started) * 1000
        oracle = fixture.state()
        rows.append(
            _row(
                case="benign ref churn",
                arm="guarded-run",
                route=churn_authority.route,
                provider_calls=1,
                provider_called_on_second=False,
                second_dispatch=int(oracle.get("submitted") == token),
                second_reason=churn_evidence.reason,
                action_calls=1 if oracle.get("submitted") == token else 0,
                observations=2,
                outcome="verified" if oracle.get("submitted") == token else "refuted",
                oracle=oracle,
                token=token,
                elapsed_ms=elapsed,
                prior_ref="ref-before",
                dispatch_ref=churn_evidence.dispatch_ref,
            )
        )

        fixture.reset()
        started = time.perf_counter()
        rebound = admit_guarded_run(
            [type_c, submit, reobserve],
            Decision("run", ("type-verification-value", "submit-form")),
            token=token,
            submit_ref="ref-before",
            target_role="button",
            target_name="Submit",
        )
        assert rebound is not None
        rebound_fresh = FreshObservation(
            token, "ref-other", "cap-2", role="button", name="Other", match_count=1, resolved_ref="ref-other"
        )
        rebound_evidence = explain_second_child("verified", rebound_fresh, rebound)
        elapsed = (time.perf_counter() - started) * 1000
        rows.append(
            _row(
                case="true rebound",
                arm="guarded-run",
                route="fast-path",
                provider_calls=1,
                provider_called_on_second=False,
                second_dispatch=int(rebound_evidence.allowed),
                second_reason=rebound_evidence.reason,
                action_calls=0,
                observations=2,
                outcome="stopped",
                oracle=fixture.state(),
                token=token,
                elapsed_ms=elapsed,
                prior_ref="ref-before",
                dispatch_ref=rebound_evidence.dispatch_ref,
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


def _refs(snapshot: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    refs = snapshot.get("refs") or []
    field = next(
        (
            ref
            for ref in refs
            if ref.get("role") == "textbox" and ref.get("name") == "verification value"
        ),
        None,
    )
    button = next(
        (ref for ref in refs if ref.get("role") == "button" and ref.get("name") == "Submit"),
        None,
    )
    return field, button


async def driver_rows(
    *,
    evidence_root: Path,
    upstream_root: Path,
    driver_bin: str,
) -> list[dict[str, Any]]:
    """One real MCP/Chromium session per row. /state is the only success oracle."""
    import asyncio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    upstream_example = upstream_root / "libs/cua-driver/examples/jev-use"
    upstream_python = upstream_example / "python"
    evidence_python = evidence_root / "libs/cua-driver/examples/jev-use/python"
    sys.path.insert(0, str(upstream_python))
    sys.path.insert(0, str(upstream_example))
    import fixture_server  # type: ignore
    import run  # type: ignore

    sys.path.insert(0, str(evidence_python))
    from deterministic_fast_path import explain_fast_path
    from guarded_run import Decision, FreshObservation, admit_guarded_run, explain_second_child

    fixture = Fixture(lambda address: fixture_server.FixtureServer(address, visual=False))
    # The evidence Fixture class calls FixtureServer(address) without visual.
    # Rebuild against the upstream server, which requires the visual flag.
    fixture.close()
    server = fixture_server.FixtureServer(("127.0.0.1", 0), visual=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fixture_url = f"http://127.0.0.1:{server.server_port}/"
    rows: list[dict[str, Any]] = []

    async def one(case: str, arm: str) -> dict[str, Any]:
        token = f"guarded-{arm}-{case[:12]}-{time.time_ns()}"
        label = f"guarded-{uuid.uuid4().hex[:8]}"
        run.reset_fixture(fixture_url)
        started = time.perf_counter()
        provider_calls = 0
        observations = 0
        action_calls = 0
        second_dispatch = 0
        provider_called_on_second = False
        route = "chooser"
        reason = "not evaluated"
        outcome = "not evaluated"
        env = run.driver_environment()
        for key, value in os.environ.items():
            if key.startswith("CUA_E2E_"):
                env[key] = value
        params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                driver = run.Driver(session, label)
                prepared = await driver.call(
                    "browser_prepare",
                    {"allow_launch": True, "profile": {"mode": "isolated_new"}},
                )
                pid = int(prepared["prepared_pid"])
                window = await run.wait_for_window(driver, pid)
                bound = await driver.call(
                    "get_browser_state",
                    {"pid": pid, "window_id": window["window_id"]},
                )
                target_id = bound["target_id"]
                tab_id = run.select_tab_id(bound["tabs"])
                await driver.call(
                    "browser_navigate",
                    {"target_id": target_id, "tab_id": tab_id, "url": fixture_url},
                )
                snapshot = await driver.call(
                    "get_browser_state",
                    {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"},
                )
                observations += 1
                field, button = _refs(snapshot)
                if field is None or button is None:
                    raise RuntimeError(f"fixture snapshot missing field or submit: {case}")
                from core import Candidate

                type_c = Candidate("type-verification-value", "type", "browser_type", {})
                submit_c = Candidate("submit-form", "submit", "browser_click", {})
                prior_ref = str(button["ref"])
                plan = admit_guarded_run(
                    [type_c, submit_c],
                    Decision("run", ("type-verification-value", "submit-form")),
                    token=token,
                    submit_ref=prior_ref,
                    target_role=str(button.get("role")),
                    target_name=str(button.get("name")),
                )
                assert plan is not None
                provider_calls += 1
                typed = token if case != "refuted first postcondition" else "wrong-token"
                await driver.call(
                    "browser_type",
                    {
                        "target_id": target_id,
                        "tab_id": tab_id,
                        "ref": field["ref"],
                        "text": typed,
                        "replace": True,
                    },
                )
                action_calls += 1
                fresh_button = None
                if case == "missing observation":
                    fresh = None
                    status = "verified"
                else:
                    if case == "target disappears":
                        await driver.call(
                            "browser_navigate",
                            {"target_id": target_id, "tab_id": tab_id, "url": "about:blank"},
                        )
                    fresh_snapshot = await driver.call(
                        "get_browser_state",
                        {
                            "target_id": target_id,
                            "tab_id": tab_id,
                            "snapshot_format": "semantic_v2",
                        },
                    )
                    observations += 1
                    fresh_field, fresh_button = _refs(fresh_snapshot)
                    matches = [
                        ref
                        for ref in (fresh_snapshot.get("refs") or [])
                        if ref.get("role") == plan.target_role and ref.get("name") == plan.target_name
                    ]
                    status = "verified"
                    resolved = str(matches[0]["ref"]) if len(matches) == 1 else None
                    role = plan.target_role if matches else None
                    name = plan.target_name if matches else None
                    match_count = len(matches)
                    proposed = resolved
                    capture = "cap-live"
                    if case == "unknown first postcondition":
                        status = "unknown"
                    elif case == "target disappears":
                        status = "stale"
                        proposed = None
                        resolved = None
                        match_count = 0
                    elif case in {"target rebound", "true rebound"}:
                        role = "button"
                        name = "Rebound"
                        match_count = 0
                        proposed = None
                        resolved = None
                        fresh_button = None
                    elif case == "stale capture":
                        capture = None
                    elif case == "second action refusal":
                        status = "refused"
                    elif case == "mismatched submit ref":
                        proposed = prior_ref
                    elif case == "refuted first postcondition":
                        status = "refuted"
                    elif case == "one executable reobserve":
                        status = "verified"
                    fresh = FreshObservation(
                        None if fresh_field is None else fresh_field.get("value"),
                        proposed,
                        capture,
                        role=role,
                        name=name,
                        match_count=match_count,
                        resolved_ref=resolved,
                    )
                evidence = explain_second_child(status, fresh, plan)
                if case == "one executable reobserve":
                    authority = explain_fast_path(
                        [submit_c, Candidate("reobserve", "reobserve", None, {})]
                    )
                else:
                    authority = explain_fast_path(
                        [submit_c], bound_completion_id=plan.second.candidate_id
                    )
                route = authority.route if arm == "guarded-run" else "chooser"
                dispatch = evidence.allowed and (
                    arm == "baseline" or authority.route == "fast-path"
                )
                if arm == "baseline" and evidence.allowed:
                    provider_calls += 1
                    provider_called_on_second = True
                elif dispatch:
                    provider_called_on_second = False
                click_ref = evidence.dispatch_ref
                if (
                    dispatch
                    and click_ref
                    and fresh_button is not None
                    and click_ref == fresh_button["ref"]
                    and click_ref != prior_ref
                    and case != "one executable reobserve"
                ):
                    await driver.call(
                        "browser_click",
                        {
                            "target_id": target_id,
                            "tab_id": tab_id,
                            "ref": click_ref,
                            "input_route": "dom_event",
                        },
                    )
                    action_calls += 1
                    second_dispatch = 1
                reason = evidence.reason if case != "one executable reobserve" else "chooser"
                if case == "one executable reobserve":
                    route = authority.route
                    provider_called_on_second = bool(authority.provider_called)
                    second_dispatch = 0
                oracle = run.fixture_state(fixture_url)
                if oracle.get("submitted") == token:
                    outcome = "verified"
                elif second_dispatch == 0:
                    outcome = "stopped"
                else:
                    outcome = "refuted"
        return _row(
            case=case,
            arm=arm,
            route=route,
            provider_calls=provider_calls,
            provider_called_on_second=provider_called_on_second,
            second_dispatch=second_dispatch,
            second_reason=reason,
            action_calls=action_calls,
            observations=observations,
            outcome=outcome,
            oracle=oracle,
            token=token,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            execution="driver-mcp",
            prior_ref=prior_ref,
            dispatch_ref=evidence.dispatch_ref if second_dispatch else None,
        )

    try:
        negatives = (
            "refuted first postcondition",
            "unknown first postcondition",
            "target disappears",
            "target rebound",
            "stale capture",
            "second action refusal",
            "missing observation",
            "mismatched submit ref",
            "one executable reobserve",
            "benign ref churn",
            "true rebound",
        )
        for case in ("type then submit",):
            for arm in ("baseline", "guarded-run"):
                rows.append(await one(case, arm))
        for case in negatives:
            rows.append(await one(case, "guarded-run"))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--driver-bin", default="")
    parser.add_argument("--upstream-root", type=Path)
    args = parser.parse_args()
    evidence_root = args.evidence_root.resolve()
    rows: list[dict[str, Any]] = []
    driver_blocker = None
    driver_version = None
    if args.driver_bin and args.upstream_root is not None:
        import asyncio

        try:
            rows = asyncio.run(
                driver_rows(
                    evidence_root=evidence_root,
                    upstream_root=args.upstream_root.resolve(),
                    driver_bin=args.driver_bin,
                )
            )
            driver_version = args.driver_bin
        except Exception as exc:
            driver_blocker = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    elif not args.driver_bin:
        driver_blocker = "no --driver-bin; Driver/Chromium session was not started"
        rows = local_rows(evidence_root)
    else:
        driver_blocker = "no --upstream-root; product checkout was not available"
        rows = local_rows(evidence_root)
    report = {
        "evidence_kind": "guarded-run-ab",
        "authority_rule": "1024f0627322b85b8b0dc3423abc2f7198133207",
        "driver_execution": "completed" if driver_blocker is None else "not completed",
        "driver_bin": driver_version,
        "driver_blocker": driver_blocker,
        "rows": rows,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"event": "wrote", "rows": len(rows), "blocker": driver_blocker}))


if __name__ == "__main__":
    main()
