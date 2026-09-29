#!/usr/bin/env python3
"""Can a guarded-completion plan (trycua/cua#4316) cross Cua sessions (#4317 topology)?

One MCP Driver process, named sessions A and B, isolated profiles, one target-owned fixture journal each.
Both sessions run the guarded runner's first step (the provider picks the typing mutation) and bind a
GuardedCompletionPlan. For each direction (owner -> executor):

  1. resolve the owner's plan under the executor's session and fresh candidates:
     must return None (session differs) so the executor falls back to an ordinary provider decision;
  2. informational: a caller that lies about its label (executor passes the owner's label) resolves
     using only the executor's OWN fresh snapshot and ref, never an owner-owned ref;
  3. dispatch the owner's valid guarded candidate through the executor's session: the Driver must
     refuse (browser_binding_stale) and neither journal may change.
Then each side completes through its own authority and the fixture journals must verify.

usage (inside the isolated X session, examples dir of the composed worktree):
  guarded_cross_session.py --examples-dir DIR --out FILE
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    ex = args.examples_dir.resolve()
    sys.path[:0] = [str(ex / "python"), str(ex)]
    result = asyncio.run(run(args.out))
    return 0 if result["ok"] else 1


async def run(out: Path) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from driver_env import driver_environment
    from guarded_completion import plan_guarded_completion, resolve_guarded_completion
    from jev_adapter import choose_mock_for_task
    from run import Driver, task_candidates_for_step
    from tasks import FixtureFormTask, fixture_state
    from verify_session_isolation import (
        _expect_foreign_refusal,
        _prepare,
        _snapshot,
    )
    from verify_setup import fixture

    rows: list[dict] = []
    record: dict = {"ok": False, "rows": rows, "error": None}
    params = StdioServerParameters(command=os.getenv("CUA_DRIVER_BIN", "cua-driver"), args=["mcp"],
                                   env=driver_environment())
    try:
        with fixture() as url_a, fixture() as url_b:
            urls = {"A": url_a, "B": url_b}
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = {t.name for t in (await session.list_tools()).tools}
                    labels = {"A": "guarded-x-a", "B": "guarded-x-b"}
                    drivers = {k: Driver(session, labels[k]) for k in "AB"}
                    bindings = {k: await _prepare(drivers[k], urls[k]) for k in "AB"}
                    tasks = {k: FixtureFormTask(f"tok-{k.lower()}-{int(time.time())}", urls[k], 4) for k in "AB"}
                    history: dict[str, list] = {"A": [], "B": []}
                    provider_calls = {"A": 0, "B": 0}
                    ref_owner: dict[str, str] = {}

                    async def observe(k: str):
                        snap = await _snapshot(bindings[k])
                        cands, sources, _ = await task_candidates_for_step(
                            drivers[k], tasks[k], snap, bindings[k].pid, bindings[k].window_id,
                            tools, False, visual_mode="off", visual_delivery="background")
                        for r in snap.get("refs") or []:
                            if r.get("ref"):
                                ref_owner[str(r["ref"])] = k
                        return snap, cands, sources

                    def provider(k: str, sources, cands):
                        provider_calls[k] += 1
                        choice, _, _ = choose_mock_for_task(tasks[k], sources, cands, history[k])
                        return next(c for c in cands if c.id == choice)

                    # step 1 in each session: provider chooses the first mutation, plan is bound
                    plans, step1 = {}, {}
                    for k in "AB":
                        _, cands, sources = await observe(k)
                        first = provider(k, sources, cands)
                        plans[k] = plan_guarded_completion(tasks[k], sources, first, session=labels[k])
                        if plans[k] is None:
                            raise RuntimeError(f"no guarded plan for {k}")
                        await drivers[k].call(first.tool, dict(first.arguments))
                        step1[k] = {"candidate": first.id, "plan_prior_ref": plans[k].prior_ref}
                    # step 2 observations (fresh, post-mutation) in each session
                    fresh = {k: await observe(k) for k in "AB"}
                    journals = lambda: {k: fixture_state(urls[k]) for k in "AB"}  # noqa: E731

                    for owner, executor in (("A", "B"), ("B", "A")):
                        plan = plans[owner]
                        _, cands_e, sources_e = fresh[executor]
                        _, cands_o, sources_o = fresh[owner]
                        j0 = journals()
                        calls0 = dict(provider_calls)
                        # 1. wrong-session resolve
                        crossed = resolve_guarded_completion(plan, tasks[executor], sources_e, cands_e,
                                                             session=labels[executor])
                        route = "guarded-completion" if crossed is not None else "provider"
                        fallback = None
                        if crossed is None:
                            fallback = provider(executor, sources_e, cands_e)
                        # 2. label spoof (informational)
                        spoof = resolve_guarded_completion(plan, tasks[executor], sources_e, cands_e,
                                                           session=labels[owner])
                        # 3. owner's valid guarded candidate dispatched through the executor's session
                        valid = resolve_guarded_completion(plan, tasks[owner], sources_o, cands_o,
                                                           session=labels[owner])
                        if valid is None:
                            raise RuntimeError(f"owner {owner} could not resolve its own plan")
                        code = await _expect_foreign_refusal(
                            drivers[executor], valid.tool, dict(valid.arguments))
                        j1 = journals()
                        rows.append({
                            "plan_owner_session": labels[owner], "executing_session": labels[executor],
                            "wrong_session_resolve": None if crossed is None else crossed.id,
                            "route_selected": route,
                            "provider_calls_added": provider_calls[executor] - calls0[executor],
                            "fallback_candidate": fallback.id if fallback else None,
                            "fallback_ref": fallback.arguments.get("ref") if fallback else None,
                            "fallback_ref_owner": ref_owner.get(str(fallback.arguments.get("ref"))) if fallback else None,
                            "spoofed_label_route": "guarded-completion" if spoof is not None else "provider",
                            "spoofed_label_ref": spoof.arguments.get("ref") if spoof else None,
                            "spoofed_label_ref_owner": ref_owner.get(str(spoof.arguments.get("ref"))) if spoof else None,
                            "owner_ref": valid.arguments.get("ref"),
                            "owner_ref_owner": ref_owner.get(str(valid.arguments.get("ref"))),
                            "owner_ref_fresh_vs_plan_prior": valid.arguments.get("ref") != plan.prior_ref,
                            "foreign_dispatch_refusal": code,
                            "driver_dispatch_reached_target": False,
                            "journals_before": j0, "journals_after": j1,
                            "journals_unchanged": j0 == j1,
                        })
                        if j0 != j1:
                            raise RuntimeError(f"journal changed during cross-session attempt {owner}->{executor}")
                        fresh[executor] = fresh[executor]  # unchanged, still usable
                        fresh[f"fallback_{executor}"] = fallback
                        fresh[f"valid_{owner}"] = valid
                    # each side completes through its own authority
                    for k in "AB":
                        cand = fresh[f"valid_{k}"]
                        await drivers[k].call(cand.tool, dict(cand.arguments))
                    record["final_journals"] = journals()
                    record["expected_tokens"] = {k: tasks[k].token for k in "AB"}
                    record["step1"] = step1
                    record["provider_calls_total"] = provider_calls
                    record["ok"] = all(
                        record["final_journals"][k] == {"submitted": tasks[k].token} for k in "AB"
                    ) and all(r["route_selected"] == "provider" and r["journals_unchanged"] for r in rows)
    except Exception as exc:  # recorded, never hidden
        record["error"] = f"{type(exc).__name__}: {exc}"
    out.write_text(json.dumps(record, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({"ok": record["ok"], "error": record["error"]}))
    return record


if __name__ == "__main__":
    raise SystemExit(main())
