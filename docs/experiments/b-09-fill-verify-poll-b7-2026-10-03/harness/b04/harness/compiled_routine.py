"""R2-07 compiled fill->submit routine: EXPERIMENT HARNESS CODE ONLY (never product code).

Three pieces, all caller-side and measurement-only:

* ``compile_trace`` turns one oracle-verified ordinary run's receipts into an artifact that
  stores only logical targets (role + accessible name), the action kind, a parameter slot,
  dependencies, preconditions, the expected outcome and fallback points.
* ``check_artifact_authority`` rejects any artifact that carries session-scoped authority:
  page refs, element tokens, capture ids, target/tab ids, session ids/epochs/generations,
  backend node ids, pids/window ids or coordinates.
* ``Routine.replay`` executes an admitted artifact. Before EVERY mutation it takes a fresh
  ``semantic_v2`` observation, binds the unique role+name match, checks the preconditions
  (and the dependency's postcondition), and dispatches with the ref minted by THAT
  observation. A Driver refusal (``isError``, ``status=refused`` or ``effect=refused``) is
  not an effect; ``browser_ref_stale`` gets exactly one rebind from a fresh observation.
  A transport failure after a mutation request may have landed: the step is ``unknown``
  and is reconciled with bounded oracle re-reads before anything else; unresolved stays
  ``unknown`` and is never replayed. A failed precondition hands the CURRENT state to the
  chooser (fallback point), never restarting at step 1. The run ends with a bounded
  re-read of the target-owned oracle (R2-06).

No routine engine, registry, router or service: one artifact, one task class, in-process.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlsplit

SCHEMA = "r2-07.compiled-routine.v1"
TASK_CLASS = "fill_submit"
FIELD_NAME = "verification value"  # tasks.FIELD_NAME (asserted at import by the harness)
LOOPBACK_ORIGIN_PATTERN = "http://127.0.0.1:*"

ALLOWED_KEYS = frozenset({
    "schema", "routine_id", "task_class", "compiled_from", "steps", "logical_target", "role", "name",
    "action", "param_slot", "precondition", "unique", "page_origin", "field_state", "input_route",
    "depends_on", "expected_outcome", "oracle", "journal_submits", "fallback_points",
    "learning_outcome", "learning_provider_decisions", "trace_mutations",
})
FORBIDDEN_KEYS = frozenset({
    "ref", "refs", "element_token", "element_index", "capture_id", "target_id", "tab_id", "session",
    "session_id", "session_epoch", "epoch", "generation", "snapshot_id", "backend_node_id",
    "backendnodeid", "node_id", "nodeid", "pid", "window_id", "x", "y", "coordinates", "bounds",
    "screenshot_reference", "frame_id", "loader_id", "cdp_session", "continuation",
})
FORBIDDEN_VALUE_PATTERNS = (
    ("page_ref", re.compile(r"^p\d+:\d+$")),
    ("target_id", re.compile(r"^bt-[0-9a-f-]{8,}")),
    ("tab_id", re.compile(r"^tab-[0-9a-f-]{8,}")),
    ("continuation", re.compile(r"^bc-[0-9a-f-]{8,}")),
    ("session_id", re.compile(r"^(mcp|jev-python|r207)-[0-9a-f-]{6,}")),
    ("uuid_like_capture", re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")),
    ("element_token", re.compile(r"^(et|el|ax)[-_:][0-9a-zA-Z]{6,}")),
)
ALLOWED_ACTIONS = frozenset({"browser_type", "browser_click"})

# B-09 (measurement only, env-gated, default-off): the verify-poll interval of ``bounded_read`` and caller
# stamps around every poll sleep and every routine oracle read. Unset env and STAMP None = unchanged behaviour.
POLL_ENV = "CUA_LANE_EXP_ROUTINE_POLL_MS"
STAMP: Callable[..., None] | None = None  # set by the runner to its recorder's ``add`` (time.monotonic_ns)


def verify_poll_interval_s(default_s: float) -> float:
    """Verify-poll interval: CUA_LANE_EXP_ROUTINE_POLL_MS in ms when set (0 = yield only), else ``default_s``."""
    raw = os.environ.get(POLL_ENV)
    if raw is None or not raw.strip():
        return default_s
    ms = float(raw)
    if not 0.0 <= ms <= 1000.0:
        raise ValueError(f"{POLL_ENV}={raw!r} outside [0, 1000]")
    return ms / 1000.0


def _stamp(name: str, **fields: Any) -> None:
    if STAMP is not None:
        STAMP(name, **fields)


class ArtifactAuthorityError(ValueError):
    pass


def check_artifact_authority(artifact: Any) -> list[str]:
    """Return every authority violation in ``artifact`` (empty list = clean)."""
    problems: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                lowered = str(key).lower()
                if lowered in FORBIDDEN_KEYS:
                    problems.append(f"{path}.{key}: forbidden authority key")
                elif key not in ALLOWED_KEYS:
                    problems.append(f"{path}.{key}: key not in the artifact schema")
                walk(item, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str):
            for label, pattern in FORBIDDEN_VALUE_PATTERNS:
                if pattern.search(value):
                    problems.append(f"{path}: value looks like a {label}")
        elif isinstance(value, float):
            problems.append(f"{path}: float value (coordinates are not allowed)")

    walk(artifact, "$")
    if isinstance(artifact, Mapping):
        if artifact.get("schema") != SCHEMA:
            problems.append("$.schema: wrong schema")
        if artifact.get("task_class") != TASK_CLASS:
            problems.append("$.task_class: not fill_submit")
        steps = artifact.get("steps")
        if not isinstance(steps, list) or not steps:
            problems.append("$.steps: missing")
        else:
            for index, step in enumerate(steps):
                if not isinstance(step, Mapping):
                    problems.append(f"$.steps[{index}]: not an object")
                    continue
                if step.get("action") not in ALLOWED_ACTIONS:
                    problems.append(f"$.steps[{index}].action: not allowed")
                target = step.get("logical_target")
                if not isinstance(target, Mapping) or set(target) != {"role", "name"}:
                    problems.append(f"$.steps[{index}].logical_target: must be exactly role+name")
                if not isinstance(step.get("precondition"), Mapping) or step["precondition"].get("unique") is not True:
                    problems.append(f"$.steps[{index}].precondition.unique must be true")
                dep = step.get("depends_on")
                if dep is not None and (not isinstance(dep, int) or not 0 <= dep < index):
                    problems.append(f"$.steps[{index}].depends_on: must name an earlier step")
    else:
        problems.append("$: not an object")
    return problems


def require_clean(artifact: Mapping[str, Any]) -> None:
    problems = check_artifact_authority(artifact)
    if problems:
        raise ArtifactAuthorityError("; ".join(problems))


# ----------------------------------------------------------------------------- compile


class CompileError(ValueError):
    pass


def _origin_pattern(url: str | None) -> str:
    parts = urlsplit(url or "")
    if parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost"}:
        return LOOPBACK_ORIGIN_PATTERN
    raise CompileError("learning trace page is not a loopback fixture origin")


def compile_trace(receipts: list[Mapping[str, Any]], *, learning_verified: bool, routine_id: str) -> dict[str, Any]:
    """Compile a verified learning trace (launcher receipts) into an authority-free artifact."""
    if not learning_verified:
        raise CompileError("learning run was not independently verified (G1)")
    latest_snapshot: Mapping[str, Any] | None = None
    steps: list[dict[str, Any]] = []
    decisions = sum(1 for r in receipts if r.get("kind") == "provider_response" and r.get("ok"))
    for receipt in receipts:
        if receipt.get("kind") != "driver_call" or not receipt.get("ok"):
            continue
        tool = receipt.get("tool")
        if tool == "get_browser_state" and receipt.get("arg_snapshot_format") == "semantic_v2":
            latest_snapshot = receipt
            continue
        if tool not in ALLOWED_ACTIONS:
            continue
        if latest_snapshot is None:
            raise CompileError(f"{tool} dispatched before any semantic observation")
        ref = receipt.get("arg_ref")
        entries = latest_snapshot.get("refs_logical") or []
        hit = [e for e in entries if e.get("ref") == ref]
        if len(hit) != 1:
            raise CompileError(f"{tool} ref not found in the preceding observation")
        role, name = hit[0].get("role"), hit[0].get("name")
        same = [e for e in entries if e.get("role") == role and e.get("name") == name]
        if len(same) != 1 or not role or not name:
            raise CompileError(f"{tool} target {role}/{name} was not unique in the trace")
        step: dict[str, Any] = {
            "logical_target": {"role": role, "name": name},
            "action": tool,
            "precondition": {"unique": True},
        }
        if tool == "browser_type":
            if not receipt.get("arg_text_is_token"):
                raise CompileError("typed text is not the task parameter; refusing to compile a literal")
            step["param_slot"] = "token"
            step["precondition"].update({
                "page_origin": _origin_pattern(latest_snapshot.get("page_url")),
                "field_state": hit[0].get("value_state") or "unknown",
            })
        else:
            step["input_route"] = receipt.get("arg_input_route") or "dom_event"
        if steps:
            step["depends_on"] = len(steps) - 1
        steps.append(step)
    if [s["action"] for s in steps] != ["browser_type", "browser_click"]:
        raise CompileError(f"trace mutations {[s['action'] for s in steps]} are not fill->submit")
    artifact = {
        "schema": SCHEMA,
        "routine_id": routine_id,
        "task_class": TASK_CLASS,
        "steps": steps,
        "expected_outcome": {"oracle": "/state.submitted == token", "journal_submits": 1},
        "fallback_points": ["before each mutation: provider chooser"],
        "compiled_from": {"learning_outcome": "verified", "learning_provider_decisions": decisions,
                          "trace_mutations": len(steps)},
    }
    require_clean(artifact)
    return artifact


# ----------------------------------------------------------------------------- replay


def refusal_code(error_or_result: Any) -> str | None:
    """Return a refusal code for a Driver result or error, else None."""
    code = getattr(error_or_result, "code", None)
    if isinstance(code, str) and code:
        return code
    if isinstance(error_or_result, Mapping):
        if error_or_result.get("effect") == "refused" or error_or_result.get("status") == "refused":
            summary = str(error_or_result.get("summary") or "")
            match = re.search(r"refused \(([a-z_]+)\)", summary)
            refusal = error_or_result.get("refusal")
            if isinstance(refusal, Mapping) and refusal.get("code"):
                return str(refusal["code"])
            return match.group(1) if match else "refused"
    text = str(error_or_result)
    match = re.search(r"refused \(([a-z_]+)\)", text)
    return match.group(1) if match else None


@dataclass
class ReplayContext:
    """Session-scoped runtime handles. Never written into the artifact."""

    driver: Any  # run.Driver
    target_id: str | None
    tab_id: str | None
    pid: int
    window_id: int
    fixture_url: str
    token: str
    read_oracle: Callable[[], Mapping[str, Any]]
    rebind: Callable[["ReplayContext"], Awaitable[None]] | None = None


@dataclass
class ReplayRecord:
    outcome: str = "running"  # verified | refuted | unknown | stopped | fallback_verified | ...
    stop_reason: str | None = None
    route: str = "compiled"
    events: list[dict[str, Any]] = field(default_factory=list)
    mutations: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    fallback_decisions: int = 0
    provider_decisions: int = 0
    reconcile_reads: list[dict[str, Any]] = field(default_factory=list)
    t0_ns: int = field(default_factory=time.monotonic_ns)

    def log(self, kind: str, **fields: Any) -> None:
        self.events.append({"kind": kind, "t_ms": round((time.monotonic_ns() - self.t0_ns) / 1e6, 3), **fields})

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome, "stop_reason": self.stop_reason, "route": self.route,
            "events": self.events, "mutations": self.mutations, "observations": self.observations,
            "fallback_decisions": self.fallback_decisions, "provider_decisions": self.provider_decisions,
            "reconcile_reads": self.reconcile_reads,
        }


def value_state(entry: Mapping[str, Any] | None, token: str) -> str:
    if entry is None:
        return "not_found"
    value = entry.get("value")
    if value in (None, ""):
        return "empty"
    return "param" if value == token else "other"


def _origin_ok(pattern: str, url: str | None) -> bool:
    parts = urlsplit(url or "")
    if pattern == LOOPBACK_ORIGIN_PATTERN:
        return parts.scheme == "http" and parts.hostname == "127.0.0.1" and parts.path in {"", "/"}
    return False


Hook = Callable[[str, int, "ReplayContext", "ReplayRecord"], Awaitable[None]]


class Routine:
    """Replays one admitted artifact with fresh binding before every mutation."""

    RECONCILE_DEADLINE_S = 3.0
    RECONCILE_INTERVAL_S = 0.05
    VERIFY_DEADLINE_S = 3.0
    VERIFY_INTERVAL_S = 0.01

    def __init__(self, artifact: Mapping[str, Any], *, fallback: Callable[..., Awaitable[str]] | None = None,
                 hook: Hook | None = None) -> None:
        require_clean(artifact)
        self.artifact = artifact
        self.fallback = fallback
        self.hook = hook

    async def observe(self, ctx: ReplayContext, rec: ReplayRecord, purpose: str) -> dict[str, Any]:
        if ctx.target_id is None or ctx.tab_id is None:
            if ctx.rebind is None:
                raise RuntimeError("no browser binding and no rebind")
            await ctx.rebind(ctx)
            rec.log("target_rebound", purpose=purpose)
        snap = await ctx.driver.call("get_browser_state", {
            "target_id": ctx.target_id, "tab_id": ctx.tab_id, "snapshot_format": "semantic_v2"})
        snapshot_id = (snap.get("snapshot") or {}).get("id")
        rec.observations.append({"purpose": purpose, "snapshot_id": snapshot_id,
                                 "t_ms": round((time.monotonic_ns() - rec.t0_ns) / 1e6, 3),
                                 "after_mutations": len(rec.mutations)})
        return snap

    @staticmethod
    def bind(snap: Mapping[str, Any], target: Mapping[str, str]) -> tuple[Mapping[str, Any] | None, int]:
        refs = [r for r in snap.get("refs") or [] if isinstance(r, Mapping)]
        matches = [r for r in refs if r.get("role") == target["role"] and r.get("name") == target["name"]]
        return (matches[0] if len(matches) == 1 else None), len(matches)

    def check_preconditions(self, step: Mapping[str, Any], index: int, snap: Mapping[str, Any],
                            entry: Mapping[str, Any], ctx: ReplayContext) -> str | None:
        pre = step.get("precondition") or {}
        page_url = (snap.get("page") or {}).get("url")
        if "page_origin" in pre and not _origin_ok(pre["page_origin"], page_url):
            return "page_origin"
        if "field_state" in pre and value_state(entry, ctx.token) != pre["field_state"]:
            return "field_state"
        needed = "type" if step["action"] == "browser_type" else "click"
        if needed not in (entry.get("actions") or []):
            return "action_not_declared"
        dep = step.get("depends_on")
        if dep is not None:
            prior = self.artifact["steps"][dep]
            prior_entry, count = self.bind(snap, prior["logical_target"])
            if prior.get("param_slot") == "token" and (prior_entry is None or value_state(prior_entry, ctx.token) != "param"):
                return "dependency_postcondition"
        return None

    async def dispatch(self, step: Mapping[str, Any], index: int, entry: Mapping[str, Any], snap: Mapping[str, Any],
                       ctx: ReplayContext, rec: ReplayRecord, attempt: int) -> tuple[str, Any]:
        args: dict[str, Any] = {"target_id": ctx.target_id, "tab_id": ctx.tab_id, "ref": entry["ref"]}
        if step["action"] == "browser_type":
            args.update({"text": ctx.token, "replace": True})
        else:
            args["input_route"] = step.get("input_route") or "dom_event"
        latest = rec.observations[-1]["snapshot_id"] if rec.observations else None
        mutation = {
            "step": index, "attempt": attempt, "action": step["action"],
            "ref_snapshot": str(entry["ref"]).split(":")[0], "latest_observation": latest,
            "fresh": str(entry["ref"]).split(":")[0] == latest and rec.observations[-1]["after_mutations"] == len(rec.mutations),
            "unique_matches": 1, "t_ms": round((time.monotonic_ns() - rec.t0_ns) / 1e6, 3),
        }
        if self.hook is not None:
            await self.hook("before_dispatch", index, ctx, rec)
        try:
            result = await ctx.driver.call(step["action"], args)
        except BaseException as error:  # noqa: BLE001
            if isinstance(error, KeyboardInterrupt):
                raise
            code = refusal_code(error)
            if code:
                mutation.update({"result": "refused", "code": code})
                rec.mutations.append(mutation)
                return "refused", code
            mutation.update({"result": "transport_failure", "error": type(error).__name__})
            rec.mutations.append(mutation)
            return "unknown", type(error).__name__
        code = refusal_code(result)
        if code:
            mutation.update({"result": "refused", "code": code, "effect": result.get("effect")})
            rec.mutations.append(mutation)
            return "refused", code
        mutation.update({"result": "accepted", "effect": result.get("effect"), "route": result.get("route")})
        rec.mutations.append(mutation)
        return "accepted", result

    async def bounded_read(self, ctx: ReplayContext, rec: ReplayRecord, deadline_s: float, interval_s: float,
                           purpose: str) -> str:
        started = time.monotonic()
        if purpose == "verify":
            interval_s = verify_poll_interval_s(interval_s)
        while True:
            _stamp("routine_read_send", purpose=purpose)
            try:
                state = await asyncio.to_thread(ctx.read_oracle)
                submitted = state.get("submitted")
            except Exception as error:  # noqa: BLE001
                submitted, state = None, {"error": type(error).__name__}
            seen = submitted == ctx.token
            other = submitted is not None and not seen
            _stamp("routine_read_return", purpose=purpose, effect_visible=seen)
            rec.reconcile_reads.append({"purpose": purpose, "t_ms": round((time.monotonic_ns() - rec.t0_ns) / 1e6, 3),
                                        "effect_visible": seen, "other_value": other})
            if seen:
                return "verified"
            if other:
                return "refuted"
            if time.monotonic() - started >= deadline_s:
                return "unknown"
            _stamp("poll_sleep_start", purpose=purpose, interval_ms=interval_s * 1000.0)
            await asyncio.sleep(interval_s if interval_s > 0 else 0)  # 0: a bare event-loop yield
            _stamp("poll_sleep_end", purpose=purpose)

    async def replay(self, ctx: ReplayContext, rec: ReplayRecord) -> ReplayRecord:
        steps = self.artifact["steps"]
        for index, step in enumerate(steps):
            if self.hook is not None:
                await self.hook("before_step", index, ctx, rec)
            rebinds = 0
            while True:
                snap = await self.observe(ctx, rec, f"step{index}")
                entry, count = self.bind(snap, step["logical_target"])
                if entry is None:
                    reason = "target_not_found" if count == 0 else "target_ambiguous"
                    rec.log("precondition_failed", step=index, reason=reason, matches=count)
                    return await self._fallback(ctx, rec, index, reason)
                failed = self.check_preconditions(step, index, snap, entry, ctx)
                if failed:
                    rec.log("precondition_failed", step=index, reason=failed)
                    return await self._fallback(ctx, rec, index, failed)
                status, detail = await self.dispatch(step, index, entry, snap, ctx, rec, attempt=rebinds + 1)
                if status == "accepted":
                    rec.log("dispatched", step=index, effect=detail.get("effect") if isinstance(detail, Mapping) else None)
                    break
                if status == "refused":
                    rec.log("dispatch_refused", step=index, code=detail)
                    if detail == "browser_ref_stale" and rebinds == 0:
                        rebinds += 1
                        continue  # exactly one rebind from a fresh observation
                    rec.outcome, rec.stop_reason = "stopped", f"refused:{detail}"
                    return rec
                # unknown: the request may have landed. Reconcile BEFORE anything else.
                rec.log("mutation_unknown", step=index, error=detail)
                if step["action"] == "browser_click":
                    result = await self.bounded_read(ctx, rec, self.RECONCILE_DEADLINE_S, self.RECONCILE_INTERVAL_S, "reconcile")
                    rec.outcome = {"verified": "verified_by_reconcile", "refuted": "refuted"}.get(result, "unknown")
                    rec.stop_reason = None if result == "verified" else "unresolved_after_reconcile"
                else:
                    rec.outcome, rec.stop_reason = "unknown", "type_effect_unknown_no_oracle"
                return rec
        result = await self.bounded_read(ctx, rec, self.VERIFY_DEADLINE_S, self.VERIFY_INTERVAL_S, "verify")
        rec.outcome = result
        if result != "verified":
            rec.stop_reason = "not_verified_after_bounded_read"
        return rec

    async def _fallback(self, ctx: ReplayContext, rec: ReplayRecord, index: int, reason: str) -> ReplayRecord:
        rec.route = "compiled+fallback"
        rec.log("fallback_point", step=index, reason=reason)
        if self.fallback is None:
            rec.outcome, rec.stop_reason = "stopped", f"precondition:{reason}:no_fallback"
            return rec
        outcome = await self.fallback(ctx, rec, index, reason)
        rec.outcome = outcome
        if outcome not in {"verified", "fallback_verified"}:
            rec.stop_reason = rec.stop_reason or f"fallback:{outcome}"
        return rec


# ----------------------------------------------------------------------------- fallback chooser


def make_chooser_fallback(*, runner: Any, task_factory: Callable[[str, str], Any], provider: str,
                          max_decisions: int = 2) -> Callable[..., Awaitable[str]]:
    """Fallback point: hand the CURRENT state to the ordinary chooser (mock or live).

    Candidates come from the unmodified task spec, then a uniqueness filter drops any page
    candidate whose role+name is not unique in the fresh observation (so the fallback can
    never make an ambiguous dispatch). Each mutation is preceded by a fresh observation and
    uses its fresh ref; a completion candidate ends with the bounded oracle re-read.
    """
    from jev_adapter import choose_live_for_task, choose_mock_for_task
    from tasks import TaskSources, fixture_sources

    async def fallback(ctx: ReplayContext, rec: ReplayRecord, index: int, reason: str) -> str:
        task = task_factory(ctx.token, ctx.fixture_url)
        history: list[dict[str, Any]] = []
        routine = Routine.__new__(Routine)
        for decision in range(1, max_decisions + 1):
            snap = await Routine.observe(routine, ctx, rec, f"fallback{decision}")
            sources: TaskSources = fixture_sources(snap, None)
            try:
                candidates = task.candidates(sources)
            except Exception as error:  # noqa: BLE001
                rec.log("fallback_candidates_error", error=type(error).__name__)
                return "stopped"
            refs = [r for r in snap.get("refs") or [] if isinstance(r, Mapping)]
            by_ref = {r.get("ref"): r for r in refs}
            safe = []
            for cand in candidates:
                ref = cand.arguments.get("ref") if cand.arguments else None
                if ref is None:
                    safe.append(cand)
                    continue
                entry = by_ref.get(ref)
                n = sum(1 for r in refs if entry is not None and r.get("role") == entry.get("role") and r.get("name") == entry.get("name"))
                if n == 1:
                    safe.append(cand)
                else:
                    rec.log("fallback_candidate_dropped_not_unique", candidate=cand.id, matches=n)
            rec.fallback_decisions += 1
            if provider == "live":
                choice, _, _ = await asyncio.to_thread(choose_live_for_task, task, sources, safe, history)
                rec.provider_decisions += 1
            else:
                choice, _, _ = choose_mock_for_task(task, sources, safe, history)
            rec.log("fallback_choice", decision=decision, choice=choice, offered=[c.id for c in safe])
            if choice is None or choice == "abstain":
                rec.stop_reason = "fallback_abstained"
                return "stopped"
            if choice == "reobserve":
                history.append(task.history_entry(len(history) + 1, choice))
                continue
            cand = next(c for c in safe if c.id == choice)
            latest = rec.observations[-1]["snapshot_id"]
            mutation = {"step": f"fallback{decision}", "attempt": 1, "action": cand.tool,
                        "ref_snapshot": str(cand.arguments.get("ref", "")).split(":")[0],
                        "latest_observation": latest, "fresh": str(cand.arguments.get("ref", "")).split(":")[0] == latest,
                        "unique_matches": 1, "t_ms": round((time.monotonic_ns() - rec.t0_ns) / 1e6, 3)}
            try:
                result = await ctx.driver.call(cand.tool, dict(cand.arguments))
            except BaseException as error:  # noqa: BLE001
                code = refusal_code(error)
                mutation.update({"result": "refused" if code else "transport_failure", "code": code})
                rec.mutations.append(mutation)
                if code:
                    rec.stop_reason = f"fallback_refused:{code}"
                    return "stopped"
                if cand.id in task.completion_candidate_ids:
                    out = await Routine.bounded_read(routine, ctx, rec, Routine.RECONCILE_DEADLINE_S, Routine.RECONCILE_INTERVAL_S, "reconcile")
                    return "fallback_verified" if out == "verified" else "unknown"
                return "unknown"
            code = refusal_code(result)
            mutation.update({"result": "refused" if code else "accepted", "code": code, "effect": result.get("effect")})
            rec.mutations.append(mutation)
            if code:
                rec.stop_reason = f"fallback_refused:{code}"
                return "stopped"
            history.append(task.history_entry(len(history) + 1, cand.id))
            if cand.id in task.completion_candidate_ids:
                out = await Routine.bounded_read(routine, ctx, rec, Routine.VERIFY_DEADLINE_S, Routine.VERIFY_INTERVAL_S, "verify")
                return "fallback_verified" if out == "verified" else out
        rec.stop_reason = "fallback_budget_exhausted"
        return "stopped"

    return fallback


def dumps(artifact: Mapping[str, Any]) -> str:
    return json.dumps(artifact, indent=1, sort_keys=True) + "\n"
