#!/usr/bin/env python3
"""OWN-75 mutation control (step 4): inject boundary bugs into a scratch copy of the PR's runners.

usage (under bin/hostless): mutate.py <pr-worktree> <scratch-root> <out-dir>

For every pre-registered mutation it copies examples/jev-use (sources only; .venv and node_modules
are symlinked), applies exactly one textual edit to python/run_native.py or typescript/run_native.ts
(each edit must match exactly once), runs that language's parity test
(python/tests/test_native_timing.py or typescript/native_timing.test.ts) with a scrubbed
environment, and records the exit code and the failing assertion. "none-*" rows are unmutated
copies (positive control: they must pass). The worktree itself is never modified.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PY = "python/run_native.py"
TS = "typescript/run_native.ts"

MUTATIONS: list[dict] = [
    {"id": "none-py", "file": PY, "edits": []},
    {"id": "none-ts", "file": TS, "edits": []},
    # M1 decision_ms boundary: start decision_ms after observation (excludes observe + visual).
    {"id": "M1-decision-boundary-py", "file": PY, "edits": [(
        "assert_in_scope(candidate, args.pid, window_id)\n"
        "                base_event.update(native_timing_fields(started, phase_timings, decide_ms))",
        "assert_in_scope(candidate, args.pid, window_id)\n"
        "                base_event.update(native_timing_fields(plan_started, phase_timings, decide_ms))")]},
    {"id": "M1-decision-boundary-ts", "file": TS, "edits": [(
        "assertInScope(candidate, args.pid, windowId);\n"
        "      Object.assign(baseEvent, nativeTimingFields(started, phaseTimings, providerDecisionMs));",
        "assertInScope(candidate, args.pid, windowId);\n"
        "      Object.assign(baseEvent, nativeTimingFields(planStarted, phaseTimings, providerDecisionMs));")]},
    # M2 dropped old field: the successful action step no longer emits act_ms.
    {"id": "M2-drop-act_ms-py", "file": PY, "edits": [(
        '"tool": candidate.tool, "act_ms": act_ms,\n                                       "action_ms": act_ms,',
        '"tool": candidate.tool,\n                                       "action_ms": act_ms,')]},
    {"id": "M2-drop-act_ms-ts", "file": TS, "edits": [(
        "...baseEvent, tool: candidate.tool, act_ms: actMs, action_ms: actMs,\n"
        "        total_step_ms: Math.round((performance.now() - started) * 100) / 100,\n        delivery_mode:",
        "...baseEvent, tool: candidate.tool, action_ms: actMs,\n"
        "        total_step_ms: Math.round((performance.now() - started) * 100) / 100,\n        delivery_mode:")]},
    # M3 visual_observe_ms widened to include the semantic observation.
    {"id": "M3-visual-includes-semantic-py", "file": PY, "edits": [(
        'visual_observe_ms=round(phase_timings.get("visual_observe_ms", 0.0), 2),',
        'visual_observe_ms=round(phase_timings.get("visual_observe_ms", 0.0)'
        ' + phase_timings.get("semantic_observe_ms", 0.0), 2),')]},
    {"id": "M3-visual-includes-semantic-ts", "file": TS, "edits": [(
        "visualObserveMs: phaseTimings.visual_observe_ms ?? 0,",
        "visualObserveMs: (phaseTimings.visual_observe_ms ?? 0) + (phaseTimings.semantic_observe_ms ?? 0),")]},
    # M4 visual_observe_scope="parse_only" dropped.
    {"id": "M4-drop-scope-py", "file": PY, "edits": [(
        '        "visual_observe_scope": "parse_only",\n    }', "    }")]},
    {"id": "M4-drop-scope-ts", "file": TS, "edits": [("    visual_observe_scope: 'parse_only',\n", "")]},
    # M5 total_step_ms ends before the action.
    {"id": "M5-total-excludes-action-py", "file": PY, "edits": [(
        '"total_step_ms": round((time.perf_counter() - started) * 1000, 2),\n'
        '                                       "delivery_mode"',
        '"total_step_ms": base_event["decision_ms"],\n                                       "delivery_mode"')]},
    {"id": "M5-total-excludes-action-ts", "file": TS, "edits": [(
        "total_step_ms: Math.round((performance.now() - started) * 100) / 100,\n        delivery_mode:",
        "total_step_ms: baseEvent.decision_ms,\n        delivery_mode:")]},
    # M6 the reobservation is left out of semantic_observe_ms.
    {"id": "M6-semantic-first-only-py", "file": PY, "edits": [(
        "        second = await observe(driver, task, pid, window_id, timeout_ms=REOBSERVE_TIMEOUT_MS)\n"
        '        add_phase(phase_timings, "semantic_observe_ms", observe_started)\n',
        "        second = await observe(driver, task, pid, window_id, timeout_ms=REOBSERVE_TIMEOUT_MS)\n")]},
    {"id": "M6-semantic-first-only-ts", "file": TS, "edits": [(
        "    const second = await observe(driver, task, pid, windowId, REOBSERVE_TIMEOUT_MS);\n"
        "    addPhase(phaseTimings, 'semantic_observe_ms', phaseStarted);\n",
        "    const second = await observe(driver, task, pid, windowId, REOBSERVE_TIMEOUT_MS);\n")]},
    # M7 parse_ms widened to include the semantic observation (parse_ms no longer parse-only).
    {"id": "M7-parse_ms-widened-py", "file": PY, "edits": [(
        'parse_ms = round(add_phase(phase_timings, "visual_observe_ms", started), 2)',
        'parse_ms = round(add_phase(phase_timings, "visual_observe_ms", started)'
        ' + phase_timings.get("semantic_observe_ms", 0.0), 2)')]},
    {"id": "M7-parse_ms-widened-ts", "file": TS, "edits": [(
        "const parseMs = Math.round(addPhase(phaseTimings, 'visual_observe_ms', started) * 100) / 100;",
        "const parseMs = Math.round((addPhase(phaseTimings, 'visual_observe_ms', started)"
        " + (phaseTimings?.semantic_observe_ms ?? 0)) * 100) / 100;")]},
    # M8 behaviour change (not timing): one extra get_window_state per step.
    {"id": "M8-extra-driver-call-py", "file": PY, "edits": [(
        "    first = await observe(driver, task, pid, window_id)\n",
        "    await observe(driver, task, pid, window_id)\n    first = await observe(driver, task, pid, window_id)\n")]},
    {"id": "M8-extra-driver-call-ts", "file": TS, "edits": [(
        "  const firstObservation = await observe(driver, task, pid, windowId);\n",
        "  await observe(driver, task, pid, windowId);\n"
        "  const firstObservation = await observe(driver, task, pid, windowId);\n")]},
]


def copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".venv", "node_modules", "__pycache__"))
    (target / ".venv").symlink_to(source / ".venv")
    (target / "node_modules").symlink_to(source / "node_modules")


def main() -> int:
    if os.environ.get("CUA_HOSTLESS") != "1":
        print("refusing: run under bin/hostless", file=sys.stderr)
        return 97
    worktree, scratch, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    source = worktree / "libs/cua-driver/examples/jev-use"
    out.mkdir(parents=True, exist_ok=True)
    node_bin = os.environ["OWN75_NODE_BIN"]
    rows = []
    for mutation in MUTATIONS:
        target = scratch / mutation["id"] / "jev-use"
        if target.parent.exists():
            shutil.rmtree(target.parent)
        target.parent.mkdir(parents=True)
        copy_tree(source, target)
        path = target / mutation["file"]
        text = path.read_text(encoding="utf-8")
        counts = []
        for old, new in mutation["edits"]:
            counts.append(text.count(old))
            text = text.replace(old, new, 1)
        applied = all(count == 1 for count in counts)
        path.write_text(text, encoding="utf-8")
        language = "python" if mutation["file"] == PY else "typescript"
        if language == "python":
            command = [str(target / ".venv/bin/python"), "-m", "unittest", "discover", "-s", "python/tests",
                       "-p", "test_native_timing.py", "-v"]
        else:
            command = ["node", "--import", "tsx", "--test", "--test-reporter=tap", "typescript/native_timing.test.ts"]
        home = scratch / mutation["id"] / "home"
        home.mkdir()
        env = {"HOME": str(home), "PATH": f"{node_bin}:/usr/bin:/bin", "LANG": "C.UTF-8", "TMPDIR": str(home)}
        completed = subprocess.run(command, cwd=target, env=env, capture_output=True, text=True, timeout=600)
        log = (completed.stdout + completed.stderr).replace(str(scratch), "<scratch>").replace(str(worktree), "<wt-head>")
        (out / f"{mutation['id']}.log").write_text(log, encoding="utf-8")
        assertion = next((line.strip() for line in log.splitlines()
                          if "AssertionError" in line or "assert" in line.lower() and "Error" in line), None)
        diff = subprocess.run(["git", "diff", "--no-index", "--", str(source / mutation["file"]), str(path)],
                              capture_output=True, text=True).stdout
        diff = diff.replace(str(source), "a").replace(str(target), "b")
        row = {
            "id": mutation["id"], "language": language, "file": mutation["file"],
            "edit_match_counts": counts, "applied": applied, "rc": completed.returncode,
            "tests_failed": completed.returncode != 0,
            "detected": (completed.returncode != 0) if mutation["edits"] else None,
            "control_pass": (completed.returncode == 0) if not mutation["edits"] else None,
            "first_assertion": assertion[:300] if assertion else None,
            "diff_lines": [line for line in diff.splitlines() if line.startswith(("+", "-"))
                           and not line.startswith(("+++", "---"))],
        }
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("id", "applied", "rc", "detected", "control_pass")}), flush=True)
        shutil.rmtree(target.parent)
    (out / "mutations.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
