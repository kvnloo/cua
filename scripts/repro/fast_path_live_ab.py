"""Real Driver/MCP/Chromium A/B for kvnloo/cua#4 and #10.

The product checkout is an exact upstream CUA SHA. This harness imports its
jev-use runner/core unchanged, then injects only the downstream caller-local
single-executable-candidate admission rule from the evidence checkout.

No production source is patched. The fixture's /state endpoint is the outcome
oracle. The experiment proves route execution and decision-count behavior on
this fixture. It also records non-overlapping warm task spans, independent
verified-outcome time, and runner lifetime through MCP/session cleanup.

It does not establish that deleting provider reobserve/abstain authority is
safe on unrelated tasks, and mock chooser latency is not representative of a
live provider.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


UPSTREAM_SHA = "7ee9b37edc4ebc5f7f606682ae2699d1baa5d397"


def load_modules(upstream_root: Path, evidence_root: Path):
    upstream_example = upstream_root / "libs/cua-driver/examples/jev-use"
    upstream_python = upstream_example / "python"
    evidence_python = evidence_root / "libs/cua-driver/examples/jev-use/python"

    # Import upstream modules first so the downstream helper's "from core import"
    # resolves against the exact product candidate rather than the evidence tree.
    sys.path.insert(0, str(upstream_python))
    sys.path.insert(0, str(upstream_example))
    import core  # type: ignore
    import fixture_server  # type: ignore
    import run  # type: ignore
    from jev_adapter import choose_mock_adapter  # type: ignore

    sys.path.insert(0, str(evidence_python))
    from deterministic_fast_path import explain_fast_path  # type: ignore

    return core, fixture_server, run, choose_mock_adapter, explain_fast_path


class Fixture:
    def __init__(self, server_type: Any) -> None:
        self.server = server_type(("127.0.0.1", 0), visual=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/"

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


def add_elapsed(phases: dict[str, float], name: str, started: float) -> None:
    phases[name] += (time.perf_counter() - started) * 1000


async def run_trial(
    *,
    run: Any,
    core: Any,
    choose_mock_adapter: Any,
    explain_fast_path: Any,
    fixture_url: str,
    driver_bin: str,
    arm: str,
    trial: int,
    force_first_reobserve: bool = False,
) -> dict[str, Any]:
    token = f"fastpath-{arm}-{trial}-{uuid.uuid4().hex[:8]}"
    label = f"fastpath-{arm}-{uuid.uuid4().hex[:8]}"
    run.reset_fixture(fixture_url)

    params = StdioServerParameters(
        command=driver_bin,
        args=["mcp"],
        env=run.driver_environment(),
    )
    provider_calls = 0
    action_calls = 0
    semantic_observations = 0
    route_events: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    phases = {
        "oracle_precheck_ms": 0.0,
        "semantic_observe_ms": 0.0,
        "candidate_route_ms": 0.0,
        "local_admission_ms": 0.0,
        "provider_decision_ms": 0.0,
        "choice_validation_ms": 0.0,
        "action_ms": 0.0,
        "verify_ms": 0.0,
    }

    setup_started = time.perf_counter()
    task_started: float | None = None
    outcome_observed_at: float | None = None
    setup_ms = 0.0
    observed: dict[str, Any] = {"submitted": None}
    outcome = "budget_exhausted"

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            advertised_tools = (await session.list_tools()).tools
            available_tools = {tool.name for tool in advertised_tools}
            capture_bound_click = run.supports_capture_bound_click(advertised_tools)
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
            setup_ms = (time.perf_counter() - setup_started) * 1000
            task_started = time.perf_counter()

            for step in range(1, 5):
                phase = time.perf_counter()
                oracle = run.fixture_state(fixture_url)
                add_elapsed(phases, "oracle_precheck_ms", phase)
                current = core.classify(
                    oracle.get("submitted"), token, steps=step - 1, max_steps=4
                )
                if current in {"verified", "refuted"}:
                    outcome = current
                    outcome_observed_at = time.perf_counter()
                    break

                phase = time.perf_counter()
                snapshot = await driver.call(
                    "get_browser_state",
                    {
                        "target_id": target_id,
                        "tab_id": tab_id,
                        "snapshot_format": "semantic_v2",
                    },
                )
                add_elapsed(phases, "semantic_observe_ms", phase)
                semantic_observations += 1

                phase = time.perf_counter()
                candidates, visual, visual_record = await run.candidates_for_step(
                    driver,
                    snapshot,
                    token,
                    pid,
                    int(window["window_id"]),
                    available_tools,
                    capture_bound_click,
                    visual_mode="auto",
                )
                add_elapsed(phases, "candidate_route_ms", phase)

                phase = time.perf_counter()
                evidence = explain_fast_path(candidates)
                add_elapsed(phases, "local_admission_ms", phase)

                counterfactual_provider_choice = None
                if force_first_reobserve and step == 1:
                    # Controlled authority probe: record the choice the baseline
                    # provider would make on this exact candidate set.
                    counterfactual_provider_choice = "reobserve"

                phase = time.perf_counter()
                if arm == "fast-path" and evidence.route == "fast-path":
                    choice = evidence.candidate_id
                    confidence = 1.0
                    probabilities = {
                        candidate.id: float(candidate.id == choice)
                        for candidate in candidates
                    }
                    provider_called = False
                else:
                    provider_calls += 1
                    provider_called = True
                    if force_first_reobserve and step == 1:
                        choice = "reobserve"
                        confidence = 1.0
                        probabilities = {
                            candidate.id: float(candidate.id == choice)
                            for candidate in candidates
                        }
                    else:
                        choice, confidence, probabilities = choose_mock_adapter(
                            candidates, snapshot, visual, history
                        )
                add_elapsed(phases, "provider_decision_ms", phase)

                route_events.append(
                    {
                        "step": step,
                        "route": evidence.route if arm == "fast-path" else "chooser",
                        "executable_count": evidence.executable_count,
                        "candidate_id": evidence.candidate_id,
                        "provider_called": provider_called,
                        "provider_choice": choice,
                        "counterfactual_provider_choice": counterfactual_provider_choice,
                        "visual_status": visual_record.get("status"),
                    }
                )

                if choice is None:
                    outcome = "abstained"
                    outcome_observed_at = time.perf_counter()
                    break

                phase = time.perf_counter()
                candidate = core.validate_choice(
                    choice,
                    candidates,
                    current_capture_id=visual.capture_id if visual else None,
                )
                add_elapsed(phases, "choice_validation_ms", phase)

                if candidate.id == "reobserve":
                    history.append(
                        {"event": "step", "step": step, "candidate": candidate.id}
                    )
                    continue
                if candidate.id == "abstain":
                    outcome = "abstained"
                    outcome_observed_at = time.perf_counter()
                    break

                assert candidate.tool is not None
                phase = time.perf_counter()
                await driver.call(candidate.tool, dict(candidate.arguments))
                add_elapsed(phases, "action_ms", phase)
                action_calls += 1
                history.append(
                    {
                        "event": "step",
                        "step": step,
                        "candidate": candidate.id,
                        "tool": candidate.tool,
                    }
                )

                if candidate.id in core.SUBMIT_IDS:
                    phase = time.perf_counter()
                    for _ in range(20):
                        oracle = run.fixture_state(fixture_url)
                        current = core.classify(
                            oracle.get("submitted"), token, steps=step, max_steps=4
                        )
                        if current in {"verified", "refuted"}:
                            outcome = current
                            outcome_observed_at = time.perf_counter()
                            break
                        await asyncio.sleep(0.1)
                    add_elapsed(phases, "verify_ms", phase)
                    if outcome in {"verified", "refuted"}:
                        break

            # This extra read is retained as evidence but is deliberately after
            # outcome_observed_at, so it cannot make time-to-outcome look faster.
            observed = run.fixture_state(fixture_url)

    assert task_started is not None
    runner_finished_at = time.perf_counter()
    if outcome_observed_at is None:
        outcome_observed_at = runner_finished_at

    verified_outcome_ms = (outcome_observed_at - task_started) * 1000
    runner_lifetime_ms = (runner_finished_at - task_started) * 1000
    named_span_ms = sum(phases.values())
    residual_ms = verified_outcome_ms - named_span_ms
    coverage_pct = (
        named_span_ms / verified_outcome_ms * 100 if verified_outcome_ms > 0 else 0.0
    )

    return {
        "arm": arm,
        "trial": trial,
        "force_first_reobserve": force_first_reobserve,
        "outcome": outcome,
        "oracle": observed,
        "token": token,
        "cold_setup_ms": round(setup_ms, 2),
        "verified_outcome_ms": round(verified_outcome_ms, 2),
        "runner_lifetime_ms": round(runner_lifetime_ms, 2),
        "cleanup_after_outcome_ms": round(runner_lifetime_ms - verified_outcome_ms, 2),
        "named_span_ms": round(named_span_ms, 2),
        "residual_ms": round(residual_ms, 2),
        "named_span_coverage_pct": round(coverage_pct, 3),
        "phases_ms": {key: round(value, 2) for key, value in phases.items()},
        "provider_calls": provider_calls,
        "semantic_observations": semantic_observations,
        "action_calls": action_calls,
        "route_events": route_events,
    }


def arm_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row["arm"] == arm and not row["force_first_reobserve"]
    ]
    times = [float(row["verified_outcome_ms"]) for row in selected]
    lifetimes = [float(row["runner_lifetime_ms"]) for row in selected]
    coverage = [float(row["named_span_coverage_pct"]) for row in selected]
    return {
        "trials": len(selected),
        "verified": sum(row["outcome"] == "verified" for row in selected),
        "provider_calls_total": sum(int(row["provider_calls"]) for row in selected),
        "actions_total": sum(int(row["action_calls"]) for row in selected),
        "semantic_observations_total": sum(
            int(row["semantic_observations"]) for row in selected
        ),
        "verified_outcome_ms_median": round(statistics.median(times), 2),
        "verified_outcome_ms_max": round(max(times), 2),
        "runner_lifetime_ms_median": round(statistics.median(lifetimes), 2),
        "named_span_coverage_pct_median": round(statistics.median(coverage), 3),
        "phase0_over_90pct_trials": sum(value >= 90.0 for value in coverage),
    }


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "baseline": arm_summary(rows, "baseline"),
        "fast-path": arm_summary(rows, "fast-path"),
        "authority_probe": [row for row in rows if row["force_first_reobserve"]],
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--driver-bin", required=True)
    parser.add_argument("--trials", type=int, default=6)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    core, fixture_server, run, choose_mock_adapter, explain_fast_path = load_modules(
        args.upstream_root.resolve(), args.evidence_root.resolve()
    )
    fixture = Fixture(fixture_server.FixtureServer)
    rows: list[dict[str, Any]] = []
    try:
        # Interleave arms so host drift is not confounded with treatment.
        for trial in range(1, args.trials + 1):
            order = (
                ("baseline", "fast-path")
                if trial % 2
                else ("fast-path", "baseline")
            )
            for arm in order:
                row = await run_trial(
                    run=run,
                    core=core,
                    choose_mock_adapter=choose_mock_adapter,
                    explain_fast_path=explain_fast_path,
                    fixture_url=fixture.url,
                    driver_bin=args.driver_bin,
                    arm=arm,
                    trial=trial,
                )
                rows.append(row)
                print(json.dumps({"event": "trial", **row}, sort_keys=True), flush=True)

        # One explicit authority-divergence pair on the same real fixture.
        for arm in ("baseline", "fast-path"):
            row = await run_trial(
                run=run,
                core=core,
                choose_mock_adapter=choose_mock_adapter,
                explain_fast_path=explain_fast_path,
                fixture_url=fixture.url,
                driver_bin=args.driver_bin,
                arm=arm,
                trial=999,
                force_first_reobserve=True,
            )
            rows.append(row)
            print(json.dumps({"event": "authority", **row}, sort_keys=True), flush=True)
    finally:
        fixture.close()

    report = {
        "upstream_sha": UPSTREAM_SHA,
        "evidence_kind": "real-driver-mcp-chromium-fast-path-pilot",
        "rows": rows,
        "summary": summary(rows),
        "claim_boundary": (
            "Linux X11 canonical fixture pilot. Proves route execution, independent "
            "fixture outcome, decision-count delta, and clock accounting. Mock chooser "
            "latency is not representative of a live provider. The authority probe "
            "demonstrates a policy capability removed by the fast path rather than "
            "proving that removal safe on unrelated tasks. Phase-0 coverage is "
            "reported diagnostically and is not forced to pass."
        ),
    }

    # Hard route/outcome assertions for the normal A/B.
    normal = [row for row in rows if not row["force_first_reobserve"]]
    assert all(row["outcome"] == "verified" for row in normal), normal
    baseline = [row for row in normal if row["arm"] == "baseline"]
    treatment = [row for row in normal if row["arm"] == "fast-path"]
    assert all(row["provider_calls"] == 2 for row in baseline), baseline
    assert all(row["provider_calls"] == 0 for row in treatment), treatment
    assert all(
        row["oracle"]["submitted"] == row["token"] for row in normal
    ), normal
    assert all(
        all(event["provider_called"] is False for event in row["route_events"])
        for row in treatment
    ), treatment
    assert all(
        all(event["route"] == "fast-path" for event in row["route_events"])
        for row in treatment
    ), treatment

    authority = [row for row in rows if row["force_first_reobserve"]]
    baseline_authority = next(row for row in authority if row["arm"] == "baseline")
    treatment_authority = next(row for row in authority if row["arm"] == "fast-path")
    assert baseline_authority["route_events"][0]["provider_choice"] == "reobserve"
    assert (
        treatment_authority["route_events"][0]["counterfactual_provider_choice"]
        == "reobserve"
    )
    assert treatment_authority["route_events"][0]["provider_called"] is False

    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"event": "summary", **report["summary"]}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
