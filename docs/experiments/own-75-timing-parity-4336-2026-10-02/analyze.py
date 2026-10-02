#!/usr/bin/env python3
"""OWN-75 trace normalization and behaviour-identity analysis (stdlib only; pre-registered).

usage: analyze.py <raw/real dir> [--json-out <summary.json>]

For every trial in <raw/real>/trials.jsonl it loads trials/<id>/events.jsonl.gz (runner log) and
trials/<id>/mcp.jsonl.gz (tee trace), applies the PREREG normalization, and builds:

  primary   = runner events (timing stripped, ids normalized)
            + every client->Driver request (method, tool name, normalized arguments)
            + every action receipt (normalized result of each tools/call except the observation
              tools get_window_state and list_windows)
            + the runner outcome and the fixture's own final state (the oracle)
  secondary = normalized observation responses (get_window_state, list_windows)

and compares head vs m0 per cell (runner, task). Timing VALUES are never reported.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Keys the PR adds to native step events (fixtures/native/timing-contract-v1.json common_fields plus
# visual_observe_scope). Every key ending in "_ms" is a timing field and is stripped as well.
PR_TIMING_KEYS = {
    "semantic_observe_ms", "visual_observe_ms", "candidate_build_ms", "provider_decision_ms",
    "decision_ms", "action_ms", "total_step_ms", "visual_observe_scope",
}
OBSERVATION_TOOLS = {"get_window_state", "list_windows"}
CAPTURE_RE = re.compile(r"capture_[0-9a-f]{32}_(\d+)")
SESSION_RE = re.compile(r"(jev-native-(?:python|typescript))-[0-9a-f]{6,}")
MS_TEXT_RE = re.compile(r"\b(walk_ms|elapsed_ms|took)=\d+(\.\d+)?")


def is_timing_key(key: str) -> bool:
    return key in PR_TIMING_KEYS or key.endswith("_ms")


class Normalizer:
    """Per-trial normalization: pid and window_id become placeholders; random ids lose their entropy."""

    def __init__(self, pid: int | None, window_id: int | None) -> None:
        self.pid, self.window_id = pid, window_id

    def text(self, value: str) -> str:
        value = CAPTURE_RE.sub(r"capture_<id>_\1", value)
        value = SESSION_RE.sub(r"\1-<id>", value)
        value = MS_TEXT_RE.sub(r"\1=<ms>", value)
        if self.pid is not None:
            value = re.sub(rf"\b{self.pid}\b", "<pid>", value)
        if self.window_id is not None:
            value = re.sub(rf"\b{self.window_id}\b", "<window_id>", value)
        return value

    def __call__(self, value: object, key: str | None = None) -> object:
        if isinstance(value, dict):
            if "_sha256" in value and "_len" in value and "_tool_names" not in value:
                return "<blob>"  # screenshot data and other long strings (hashed by the tee)
            return {k: self(v, k) for k, v in value.items() if not is_timing_key(k)}
        if isinstance(value, list):
            return [self(item) for item in value]
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            if key == "pid" and value == self.pid:
                return "<pid>"
            if key == "window_id" and value == self.window_id:
                return "<window_id>"
            return value
        if isinstance(value, str):
            return self.text(value)
        return value


def load_jsonl_gz(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def timing_keys_present(events: list[dict]) -> list[str]:
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                if is_timing_key(k):
                    found.add(k)
                walk(v)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(events)
    return sorted(found)


def build_traces(trial_dir: Path, record: dict) -> tuple[dict, dict, dict]:
    events = load_jsonl_gz(trial_dir / "events.jsonl.gz")
    mcp = load_jsonl_gz(trial_dir / "mcp.jsonl.gz")
    start = next((e for e in events if e.get("event") == "start"), {})
    norm = Normalizer(start.get("pid"), start.get("window_id"))
    requests, receipts, observations = [], [], []
    tool_by_id: dict[object, str] = {}
    for entry in mcp:
        message = entry["msg"]
        if entry["dir"] == "c2s":
            item = {"method": message.get("method"), "id": message.get("id")}
            if message.get("method") == "tools/call":
                params = message.get("params", {})
                tool_by_id[message.get("id")] = params.get("name")
                item.update({"tool": params.get("name"), "arguments": norm(params.get("arguments", {}))})
            elif message.get("method") == "initialize":
                item["params"] = norm(message.get("params", {}))
            requests.append(item)
        else:
            tool = tool_by_id.get(message.get("id"))
            if tool is None:
                continue  # initialize / tools/list responses are Driver metadata, not per-step behaviour
            result = message.get("result", {})
            body = {"id": message.get("id"), "tool": tool, "isError": result.get("isError", False),
                    "error": norm(message.get("error")) if "error" in message else None,
                    "structuredContent": norm(result.get("structuredContent")),
                    "content": norm(result.get("content"))}
            (observations if tool in OBSERVATION_TOOLS else receipts).append(body)
    primary = {
        "events": norm(events),
        "requests": requests,
        "receipts": receipts,
        "runner_outcome": record.get("runner_outcome"),
        "runner_rc": record.get("runner_rc"),
        "oracle_verified": record.get("oracle_verified"),
        "oracle_state": record.get("oracle_state"),
    }
    secondary = {"observations": observations}
    info = {
        "timing_keys": timing_keys_present(events),
        "step_events": sum(1 for e in events if e.get("event") == "step"),
        "pr_fields_on_steps": sorted({k for e in events if e.get("event") == "step" for k in e if k in PR_TIMING_KEYS}),
        "legacy_fields_on_steps": sorted({k for e in events if e.get("event") == "step"
                                          for k in ("decide_ms", "act_ms") if k in e}
                                         | ({"observation.observe_ms"} if any(
                                             "observe_ms" in e.get("observation", {}) for e in events
                                             if e.get("event") == "step") else set())),
        "visual_observe_scope_values": sorted({str(e.get("visual_observe_scope")) for e in events
                                               if e.get("event") == "step" and "visual_observe_scope" in e}),
        "tools_called": [r.get("tool") for r in requests if r.get("tool")],
    }
    return primary, secondary, info


def first_difference(a: object, b: object, path: str = "$") -> str | None:
    if type(a) is not type(b):
        return f"{path}: type {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return f"{path}.{key}: present only in {'second' if key not in a else 'first'}"
            found = first_difference(a[key], b[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} != {len(b)}"
        for index, (x, y) in enumerate(zip(a, b)):
            found = first_difference(x, y, f"{path}[{index}]")
            if found:
                return found
        return None
    return None if a == b else f"{path}: {json.dumps(a)[:120]} != {json.dumps(b)[:120]}"


def analyze(real: Path) -> dict:
    records = [json.loads(line) for line in (real / "trials.jsonl").read_text().splitlines() if line.strip()]
    cells: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    per_trial = []
    for record in records:
        cell = f"{record['runner']}:{record['task']}"
        trial_dir = real / "trials" / record["trial_id"]
        if record.get("harness_error"):
            primary = secondary = {"harness_error": record["harness_error"]}
            info: dict = {"timing_keys": [], "pr_fields_on_steps": [], "legacy_fields_on_steps": [],
                          "visual_observe_scope_values": [], "tools_called": [], "step_events": 0}
        else:
            primary, secondary, info = build_traces(trial_dir, record)
        row = {
            "trial_id": record["trial_id"], "arm": record["arm"], "cell": cell, "pair": record.get("pair"),
            "primary_digest": digest(primary), "secondary_digest": digest(secondary),
            "oracle_verified": bool(record.get("oracle_verified")), "runner_outcome": record.get("runner_outcome"),
            "netguard_armed": record.get("netguard_armed", 0), "netguard_refused": record.get("netguard_refused", 0),
            **info,
        }
        per_trial.append(row)
        cells[cell][record["arm"]].append((row, primary, secondary))
    result_cells = {}
    for cell, arms in sorted(cells.items()):
        head, m0 = arms.get("head", []), arms.get("m0", [])
        head_digests = Counter(r["primary_digest"] for r, _, _ in head)
        m0_digests = Counter(r["primary_digest"] for r, _, _ in m0)
        all_digests = head_digests + m0_digests
        reference = m0_digests.most_common(1)[0][0] if m0_digests else None
        ref_primary = next((p for r, p, _ in m0 if r["primary_digest"] == reference), None)
        diffs = []
        for r, p, _ in head + m0:
            if r["primary_digest"] != reference:
                diffs.append({"trial_id": r["trial_id"], "arm": r["arm"],
                              "first_difference": first_difference(ref_primary, p)})
        sec_head = Counter(r["secondary_digest"] for r, _, _ in head)
        sec_m0 = Counter(r["secondary_digest"] for r, _, _ in m0)
        sec_ref = sec_m0.most_common(1)[0][0] if sec_m0 else None
        sec_ref_obj = next((s for r, _, s in m0 if r["secondary_digest"] == sec_ref), None)
        sec_diffs = [{"trial_id": r["trial_id"], "arm": r["arm"],
                      "first_difference": first_difference(sec_ref_obj, s)}
                     for r, _, s in head + m0 if r["secondary_digest"] != sec_ref]
        result_cells[cell] = {
            "n_head": len(head), "n_m0": len(m0),
            "verified_head": sum(r["oracle_verified"] for r, _, _ in head),
            "verified_m0": sum(r["oracle_verified"] for r, _, _ in m0),
            "distinct_primary_digests": len(all_digests),
            "reference_primary_digest": reference,
            "head_matching_reference": head_digests.get(reference, 0),
            "m0_matching_reference": m0_digests.get(reference, 0),
            "primary_identical_all": len(all_digests) == 1 and len(head) > 0 and len(m0) > 0,
            "primary_digest_sets_equal": set(head_digests) == set(m0_digests),
            "primary_differences": diffs,
            "secondary_distinct_digests": len(sec_head + sec_m0),
            "secondary_head_matching_reference": sec_head.get(sec_ref, 0),
            "secondary_m0_matching_reference": sec_m0.get(sec_ref, 0),
            "secondary_differences": sec_diffs[:10],
            "pr_fields_on_steps_head": sorted({f for r, _, _ in head for f in r["pr_fields_on_steps"]}),
            "pr_fields_on_steps_m0": sorted({f for r, _, _ in m0 for f in r["pr_fields_on_steps"]}),
            "legacy_fields_head": sorted({f for r, _, _ in head for f in r["legacy_fields_on_steps"]}),
            "legacy_fields_m0": sorted({f for r, _, _ in m0 for f in r["legacy_fields_on_steps"]}),
            "head_trials_with_all_legacy_fields": sum(
                set(r["legacy_fields_on_steps"]) >= {"decide_ms", "act_ms", "observation.observe_ms"}
                for r, _, _ in head),
            "head_trials_with_all_pr_fields": sum(set(r["pr_fields_on_steps"]) == PR_TIMING_KEYS for r, _, _ in head),
            "visual_observe_scope_values_head": sorted({v for r, _, _ in head for v in r["visual_observe_scope_values"]}),
        }
    return {
        "schema": "cua.own75.analysis.v1",
        "trials": len(records),
        "trials_verified": sum(r["oracle_verified"] for r in per_trial),
        "netguard_refused_total": sum(r["netguard_refused"] for r in per_trial),
        "netguard_armed_trials": sum(1 for r in per_trial if r["netguard_armed"] >= 1),
        "cells": result_cells,
        "per_trial": per_trial,
    }


def main() -> None:
    real = Path(sys.argv[1])
    out = analyze(real)
    if "--json-out" in sys.argv:
        Path(sys.argv[sys.argv.index("--json-out") + 1]).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    brief = {cell: {k: v for k, v in c.items() if k not in ("primary_differences", "secondary_differences")}
             for cell, c in out["cells"].items()}
    print(json.dumps({"trials": out["trials"], "verified": out["trials_verified"],
                      "netguard_refused_total": out["netguard_refused_total"], "cells": brief}, indent=1))
    for cell, c in out["cells"].items():
        for d in c["primary_differences"][:5]:
            print("PRIMARY-DIFF", cell, json.dumps(d))
        for d in c["secondary_differences"][:3]:
            print("SECONDARY-DIFF", cell, json.dumps(d))


if __name__ == "__main__":
    main()
