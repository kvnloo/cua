"""R2-07c compiled toggle->confirm and modal->act routines: EXPERIMENT HARNESS CODE ONLY.

Caller-side, measurement-only extension of the R2-07b ``compiled_routine`` module (copied by
path, unchanged, from the R2-10 packet: harness/src/r2-10-composition-2026-10-02/harness/src/
r2-07-2026-10-02/harness/compiled_routine.py). Nothing here is product code: no routine engine,
registry, router or service; one artifact per task class, in process.

What is new for the two #24 classes:

* ``compile_trace_tm`` turns one oracle-verified training run's Driver-call receipts into an
  artifact with, per step: the logical target (role + accessible name), the action
  (``browser_click`` with its learned ``input_route``), preconditions, ``depends_on`` and a
  postcondition the NEXT step checks (the guarded continuation is the fallback point before
  every mutation). Preconditions are derived from the training observations only:
    - step 0: page origin (loopback) and page path;
    - a checkbox target's ``checked_state`` (toggle: ``"false"``);
    - every LATER step's target must be uniquely present (``requires_present``; toggle: Confirm)
      or absent (``requires_absent``; modal: "Confirm choice", i.e. the modal is not open) in
      the observation the step binds against;
    - postcondition of step k (checked by step k+1 on its own fresh observation): the
      checkbox's new ``checked_state`` (toggle: ``"true"``) and/or the later targets that the
      step revealed (modal: "Confirm choice" uniquely present).
  The artifact never holds refs, ids, epochs, snapshot ids, pids, coordinates, capture ids,
  tokens or capabilities; ``check_artifact_authority_tm`` scans for any such field or value.
* ``RoutineTM`` replays an admitted artifact with the base class's binding discipline: a fresh
  ``semantic_v2`` observation before EVERY mutation, the ref minted by THAT observation, exactly
  one rebind after ``browser_ref_stale``, reconcile-before-anything after a possibly landed
  click (never replayed), fallback from the CURRENT state on any failed precondition, and a
  bounded re-read of the target-owned oracle at the end.
"""

from __future__ import annotations

import re
import time
from typing import Any, Mapping
from urllib.parse import urlsplit

import compiled_routine as cr

SCHEMA = "r2-07c.compiled-routine.v1"
TASK_CLASSES: dict[str, dict[str, Any]] = {
    "toggle_confirm": {"oracle": "/state.checked == true", "completion_field": "checked"},
    "modal_act": {"oracle": "/state.opened == true and /state.modal == true", "completion_field": "modal"},
}
CLASS_OF = {"toggle": "toggle_confirm", "modal": "modal_act"}
ALLOWED_KEYS = cr.ALLOWED_KEYS | frozenset({
    "page_path", "checked_state", "requires_present", "requires_absent", "postcondition",
    "journal_updates", "completion_field",
})
ALLOWED_ACTIONS = frozenset({"browser_click"})
PAGE_PATH = re.compile(r"^/[a-z0-9-]*$")
CHECKED_VALUES = frozenset({"true", "false"})

ArtifactAuthorityError = cr.ArtifactAuthorityError
CompileError = cr.CompileError


def checked_state(entry: Mapping[str, Any] | None) -> str | None:
    """semantic_v2 ``states.checked`` as "true"/"false" (CDP AX tristate; absent = "false")."""
    if entry is None:
        return None
    states = entry.get("states") if isinstance(entry.get("states"), Mapping) else {}
    return "true" if str(states.get("checked")).lower() == "true" else "false"


def matches(refs: list[Mapping[str, Any]], target: Mapping[str, str]) -> list[Mapping[str, Any]]:
    return [r for r in refs if r.get("role") == target["role"] and r.get("name") == target["name"]]


def snap_refs(snap: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [r for r in snap.get("refs") or [] if isinstance(r, Mapping)]


def verdict(task_class: str, state: Mapping[str, Any]) -> str:
    """Target-owned oracle (#24 ``oracle_ok`` semantics): verified / refuted / pending."""
    if task_class == "toggle_confirm":
        if state.get("checked") is True:
            return "verified"
        if state.get("checked") is False:
            return "refuted"
        return "pending"
    if task_class == "modal_act":
        return "verified" if state.get("opened") is True and state.get("modal") is True else "pending"
    raise ValueError(task_class)


# ----------------------------------------------------------------------------- authority scan


def check_artifact_authority_tm(artifact: Any) -> list[str]:
    """Every authority violation in ``artifact`` (empty list = clean)."""
    problems: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                lowered = str(key).lower()
                if lowered in cr.FORBIDDEN_KEYS:
                    problems.append(f"{path}.{key}: forbidden authority key")
                elif key not in ALLOWED_KEYS:
                    problems.append(f"{path}.{key}: key not in the artifact schema")
                walk(item, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str):
            for label, pattern in cr.FORBIDDEN_VALUE_PATTERNS:
                if pattern.search(value):
                    problems.append(f"{path}: value looks like a {label}")
        elif isinstance(value, float):
            problems.append(f"{path}: float value (coordinates are not allowed)")

    def target_ok(t: Any) -> bool:
        return isinstance(t, Mapping) and set(t) == {"role", "name"} and all(isinstance(v, str) and v for v in t.values())

    walk(artifact, "$")
    if not isinstance(artifact, Mapping):
        return problems + ["$: not an object"]
    if artifact.get("schema") != SCHEMA:
        problems.append("$.schema: wrong schema")
    if artifact.get("task_class") not in TASK_CLASSES:
        problems.append("$.task_class: not toggle_confirm/modal_act")
    steps = artifact.get("steps")
    if not isinstance(steps, list) or not steps:
        return problems + ["$.steps: missing"]
    for index, step in enumerate(steps):
        where = f"$.steps[{index}]"
        if not isinstance(step, Mapping):
            problems.append(f"{where}: not an object")
            continue
        if step.get("action") not in ALLOWED_ACTIONS:
            problems.append(f"{where}.action: not allowed")
        if not target_ok(step.get("logical_target")):
            problems.append(f"{where}.logical_target: must be exactly role+name")
        pre = step.get("precondition")
        if not isinstance(pre, Mapping) or pre.get("unique") is not True:
            problems.append(f"{where}.precondition.unique must be true")
            pre = {}
        if "page_origin" in pre and pre["page_origin"] != cr.LOOPBACK_ORIGIN_PATTERN:
            problems.append(f"{where}.precondition.page_origin: not the loopback pattern")
        if "page_path" in pre and not (isinstance(pre["page_path"], str) and PAGE_PATH.match(pre["page_path"])):
            problems.append(f"{where}.precondition.page_path: not a plain path")
        for block_name, block in (("precondition", pre), ("postcondition", step.get("postcondition") or {})):
            if not isinstance(block, Mapping):
                problems.append(f"{where}.{block_name}: not an object")
                continue
            if "checked_state" in block and block["checked_state"] not in CHECKED_VALUES:
                problems.append(f"{where}.{block_name}.checked_state: not true/false")
            for key in ("requires_present", "requires_absent"):
                if key in block and not (isinstance(block[key], list) and all(target_ok(t) for t in block[key])):
                    problems.append(f"{where}.{block_name}.{key}: must be a list of role+name targets")
        dep = step.get("depends_on")
        if dep is not None and (not isinstance(dep, int) or isinstance(dep, bool) or not 0 <= dep < index):
            problems.append(f"{where}.depends_on: must name an earlier step")
    return problems


def require_clean_tm(artifact: Mapping[str, Any]) -> None:
    problems = check_artifact_authority_tm(artifact)
    if problems:
        raise ArtifactAuthorityError("; ".join(problems))


# ----------------------------------------------------------------------------- compile


def compile_trace_tm(receipts: list[Mapping[str, Any]], *, learning_verified: bool, routine_id: str,
                     task_class: str) -> dict[str, Any]:
    """Compile a verified two-click training trace into an authority-free artifact."""
    if not learning_verified:
        raise CompileError("training run was not independently verified (G1)")
    if task_class not in TASK_CLASSES:
        raise CompileError(f"unknown task class {task_class}")
    decisions = sum(1 for r in receipts if r.get("kind") == "provider_response" and r.get("ok"))
    pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    latest: Mapping[str, Any] | None = None
    used = True
    for receipt in receipts:
        if receipt.get("kind") != "driver_call" or not receipt.get("ok"):
            continue
        tool = receipt.get("tool")
        if tool == "get_browser_state" and receipt.get("arg_snapshot_format") == "semantic_v2":
            latest, used = receipt, False
            continue
        if tool in ("browser_type", "browser_click"):
            if tool not in ALLOWED_ACTIONS:
                raise CompileError(f"{tool} is not a toggle/modal action")
            if latest is None or used:
                raise CompileError(f"{tool} not preceded by its own fresh semantic observation")
            pairs.append((latest, receipt))
            used = True
    if len(pairs) != 2:
        raise CompileError(f"trace has {len(pairs)} clicks; toggle/modal routines are exactly two clicks")
    targets: list[dict[str, str]] = []
    entries: list[Mapping[str, Any]] = []
    for obs, mut in pairs:
        refs = obs.get("refs_logical") or []
        hit = [e for e in refs if e.get("ref") == mut.get("arg_ref")]
        if len(hit) != 1:
            raise CompileError("clicked ref not found in the preceding observation")
        target = {"role": hit[0].get("role"), "name": hit[0].get("name")}
        if not target["role"] or not target["name"] or len(matches(refs, target)) != 1:
            raise CompileError(f"target {target} was not unique in the trace")
        targets.append(target)
        entries.append(hit[0])
    steps: list[dict[str, Any]] = []
    for i, (obs, mut) in enumerate(pairs):
        refs = obs.get("refs_logical") or []
        step: dict[str, Any] = {"logical_target": dict(targets[i]), "action": "browser_click",
                                "input_route": mut.get("arg_input_route") or "dom_event",
                                "precondition": {"unique": True}}
        pre = step["precondition"]
        if i == 0:
            pre["page_origin"] = cr._origin_pattern(obs.get("page_url"))
            pre["page_path"] = urlsplit(obs.get("page_url") or "").path or "/"
        if targets[i]["role"] == "checkbox":
            pre["checked_state"] = entries[i].get("checked_state") or "false"
        present, absent = [], []
        for later in targets[i + 1:]:
            n = len(matches(refs, later))
            if n == 1:
                present.append(dict(later))
            elif n == 0:
                absent.append(dict(later))
            else:
                raise CompileError(f"later target {later} ambiguous in the trace")
        if present:
            pre["requires_present"] = present
        if absent:
            pre["requires_absent"] = absent
        if i > 0:
            step["depends_on"] = i - 1
        if i + 1 < len(pairs):
            nxt = pairs[i + 1][0].get("refs_logical") or []
            post: dict[str, Any] = {}
            if targets[i]["role"] == "checkbox":
                after = matches(nxt, targets[i])
                if len(after) != 1:
                    raise CompileError("checkbox not uniquely observed after its click")
                post["checked_state"] = after[0].get("checked_state") or "false"
                if post["checked_state"] == pre.get("checked_state"):
                    raise CompileError("checkbox state did not change in the trace")
            revealed = [dict(t) for t in targets[i + 1:] if len(matches(refs, t)) == 0 and len(matches(nxt, t)) == 1]
            if revealed:
                post["requires_present"] = revealed
            if post:
                step["postcondition"] = post
        steps.append(step)
    artifact = {
        "schema": SCHEMA,
        "routine_id": routine_id,
        "task_class": task_class,
        "steps": steps,
        "expected_outcome": {"oracle": TASK_CLASSES[task_class]["oracle"], "journal_updates": 1,
                             "completion_field": TASK_CLASSES[task_class]["completion_field"]},
        "fallback_points": ["before each mutation: guarded continuation from the current state"],
        "compiled_from": {"learning_outcome": "verified", "learning_provider_decisions": decisions,
                          "trace_mutations": len(steps)},
    }
    require_clean_tm(artifact)
    return artifact


# ----------------------------------------------------------------------------- replay


class RoutineTM(cr.Routine):
    """Fresh-bound replay of an admitted toggle/modal artifact (base-class binding discipline)."""

    def __init__(self, artifact: Mapping[str, Any], *, fallback: Any = None, hook: Any = None) -> None:
        require_clean_tm(artifact)
        self.artifact = artifact
        self.task_class = artifact["task_class"]
        self.fallback = fallback
        self.hook = hook

    def check_preconditions(self, step: Mapping[str, Any], index: int, snap: Mapping[str, Any],
                            entry: Mapping[str, Any], ctx: cr.ReplayContext) -> str | None:
        pre = step.get("precondition") or {}
        refs = snap_refs(snap)
        if "page_origin" in pre:
            parts = urlsplit(((snap.get("page") or {}).get("url")) or "")
            if not (parts.scheme == "http" and parts.hostname == "127.0.0.1"
                    and (parts.path or "/") == pre.get("page_path", "/")):
                return "page_origin"
        if "checked_state" in pre and checked_state(entry) != pre["checked_state"]:
            return "checked_state"
        for target in pre.get("requires_present") or []:
            n = len(matches(refs, target))
            if n != 1:
                return "requires_present" if n == 0 else "requires_present_ambiguous"
        for target in pre.get("requires_absent") or []:
            if matches(refs, target):
                return "requires_absent"
        if "click" not in (entry.get("actions") or []):
            return "action_not_declared"
        dep = step.get("depends_on")
        if dep is not None:
            prior = self.artifact["steps"][dep]
            post = prior.get("postcondition") or {}
            if "checked_state" in post:
                found = matches(refs, prior["logical_target"])
                if len(found) != 1 or checked_state(found[0]) != post["checked_state"]:
                    return "dependency_postcondition"
            for target in post.get("requires_present") or []:
                if len(matches(refs, target)) != 1:
                    return "dependency_postcondition"
        return None

    async def bounded_read(self, ctx: cr.ReplayContext, rec: cr.ReplayRecord, deadline_s: float,
                           interval_s: float, purpose: str) -> str:
        started = time.monotonic()
        while True:
            try:
                state = await cr.asyncio.to_thread(ctx.read_oracle)
                result = verdict(self.task_class, state)
            except Exception as error:  # noqa: BLE001
                result, state = "pending", {"error": type(error).__name__}
            rec.reconcile_reads.append({"purpose": purpose,
                                        "t_ms": round((time.monotonic_ns() - rec.t0_ns) / 1e6, 3),
                                        "effect_visible": result == "verified", "other_value": result == "refuted"})
            if result in ("verified", "refuted"):
                return result
            if time.monotonic() - started >= deadline_s:
                return "unknown"
            await cr.asyncio.sleep(interval_s)


def dumps(artifact: Mapping[str, Any]) -> str:
    return cr.dumps(artifact)
