#!/usr/bin/env python3
"""Post-hoc tool-call audit from the raw tool results in each run's private Hermes state.db (read-only).

Written after verification (correction round 1), not part of PREREG and not used by any scorer or oracle. It joins
every assistant tool call with its tool result by tool_call_id and classifies the result from the result body itself:

  capture           computer_use capture returned elements (or Hermes' byte-identical-result note for a capture)
  driver_ok         computer_use result with "ok": true (keeps the Driver's effect/route/focus_after)
  driver_refusal    computer_use result with "ok": false (keeps the Driver's refusal code)
  approval_blocked  Hermes' approval gate refused the action before it reached the Driver ("BLOCKED: ... requires approval")
  hermes_error      any other Hermes-side {"error": ...} (unknown action, missing argument, ...)
  file_ok / file_error   file tools: error/"success": false -> file_error, else file_ok
  no_result         a tool call with no tool result row (the timed-out turn)

Output keeps only classification fields and argument shape (never result text, paths or typed strings), so it is safe
to commit. state.db files are not committed; the derived per-call file is, and verify_artifacts.py checks that the
audit totals recompute from it.

Usage: tool_audit.py <runs_dir> <dataset/runs.jsonl> <out_calls.jsonl> <out_audit.json>
"""
from __future__ import annotations

import collections
import json
import sqlite3
import sys
from pathlib import Path

CUA = "computer_use"


def first_json(text: str | None):
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        obj, _ = json.JSONDecoder().raw_decode(text.lstrip())
        return obj
    except ValueError:
        return None


def classify(tool: str, args: dict, content: str | None) -> dict:
    if content is None:
        return {"result_class": "no_result"}
    body = first_json(content)
    if tool == CUA:
        if isinstance(body, dict):
            if body.get("ok") is True:
                meta = body.get("meta") or {}
                msg = body.get("message") or ""
                focus = "target" if "focus_after=target" in msg else ("other" if "focus_after=" in msg else None)
                return {"result_class": "driver_ok", "driver_action": body.get("action"),
                        "effect": body.get("effect") or meta.get("effect"),
                        "route": meta.get("route"), "delivery": (meta.get("delivery") or {}).get("mode"),
                        "focus_after": focus}
            if body.get("ok") is False:
                return {"result_class": "driver_refusal", "driver_action": body.get("action"),
                        "code": body.get("code") or (body.get("meta") or {}).get("code")}
            if "elements" in body:
                return {"result_class": "capture"}
            err = body.get("error")
            if isinstance(err, str):
                if err.startswith("BLOCKED:") and "requires approval" in err:
                    return {"result_class": "approval_blocked",
                            "single_query_mode": "single-query mode" in err}
                return {"result_class": "hermes_error", "code": err.split(":")[0][:60]}
        if content.startswith("[hermes note: this result is byte-identical"):
            return {"result_class": "capture" if args.get("action") == "capture" else "dedup_note"}
        return {"result_class": "unparsed"}
    if isinstance(body, dict) and (body.get("success") is False or isinstance(body.get("error"), str)):
        return {"result_class": "file_error"}
    return {"result_class": "file_ok"}


def arg_shape(tool: str, args: dict) -> dict:
    if tool != CUA:
        return {}
    out = {"action": args.get("action")}
    for k in ("element", "delivery_mode"):
        if args.get(k) is not None:
            out[k] = args[k]
    if "text" in args:
        out["text_len"] = len(str(args.get("text") or ""))
    if "keys" in args:
        out["keys_present"] = True
    if "value" in args:
        out["value_present"] = True
    return out


def audit_run(db_path: Path) -> list[dict]:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    calls, results = [], {}
    for role, content, tool_calls, tool_call_id in db.execute(
            "select role, content, tool_calls, tool_call_id from messages order by id"):
        if role == "assistant" and tool_calls:
            for tc in json.loads(tool_calls):
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {"_unparsed": True}
                calls.append((tc.get("id") or tc.get("call_id"), fn.get("name"), args if isinstance(args, dict) else {}))
        elif role == "tool" and tool_call_id:
            results[tool_call_id] = content
    db.close()
    out = []
    for i, (cid, name, args) in enumerate(calls):
        row = {"call_index": i, "tool": name}
        row.update(arg_shape(name, args))
        row.update(classify(name, args, results.get(cid)))
        out.append(row)
    return out


def summarize(rows: list[dict], runs: dict) -> dict:
    by_class = collections.Counter()
    refusals = collections.Counter()
    blocks = collections.Counter()
    hermes_err = collections.Counter()
    type_shape = collections.Counter()
    per_run = {}
    for r in rows:
        kind = "cua" if r["tool"] == CUA else "file"
        by_class[f"{kind}:{r['result_class']}"] += 1
        if r["result_class"] == "driver_refusal":
            refusals[f"{r.get('driver_action')}:{r.get('code')}"] += 1
        if r["result_class"] == "approval_blocked":
            blocks[f"{r.get('action')}:{r.get('delivery_mode') or 'background'}"] += 1
        if r["result_class"] == "hermes_error":
            hermes_err[r.get("code")] += 1
        if r["tool"] == CUA and r.get("action") == "type":
            type_shape[(f"element={'yes' if 'element' in r else 'no'}"
                        f",text={'yes' if r.get('text_len') else 'no'},keys={'yes' if r.get('keys_present') else 'no'}"
                        f",mode={r.get('delivery_mode') or 'background'}->{r['result_class']}"
                        + (f":{r.get('code')}" if r.get("code") else "")
                        + (f":focus_after={r.get('focus_after')}" if r.get("focus_after") else ""))] += 1
    for rid, meta in runs.items():
        if meta["kind"] != "cua":
            continue
        rr = [r for r in rows if r["run_id"] == rid and r["tool"] == CUA]
        per_run[rid] = {
            "family": meta["family"], "verified_success": meta["verified_success"],
            "calls": [{k: v for k, v in r.items() if k not in ("run_id", "tool")} for r in rr],
            "approval_blocked": sorted({r["action"] for r in rr if r["result_class"] == "approval_blocked"}),
            "driver_refusal_codes": sorted({r.get("code") for r in rr if r["result_class"] == "driver_refusal"}),
        }
    cua_fail = {k: v for k, v in per_run.items() if not v["verified_success"]}
    return {
        "schema": "stack2-confirm.tool_audit.v1",
        "source": "role=tool rows of each run's private state.db (read-only), joined by tool_call_id",
        "n_calls": len(rows),
        "by_class": dict(sorted(by_class.items())),
        "driver_refusals_by_action_code": dict(sorted(refusals.items())),
        "approval_blocks_by_action_mode": dict(sorted(blocks.items())),
        "hermes_errors": dict(sorted(hermes_err.items())),
        "type_calls_by_shape": dict(sorted(type_shape.items())),
        "cua_runs_with_approval_block": sorted(k for k, v in per_run.items() if v["approval_blocked"]),
        "cua_failed_runs_with_approval_block": sorted(k for k, v in cua_fail.items() if v["approval_blocked"]),
        "cua_runs": per_run,
    }


def main() -> None:
    runs_dir, runs_jsonl, out_calls, out_audit = map(Path, sys.argv[1:5])
    runs = {}
    for line in runs_jsonl.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            runs[r["run_id"]] = {"kind": r["kind"], "family": r["family"], "verified_success": r["verified_success"]}
    rows = []
    for rid in sorted(runs):
        db = runs_dir / rid / "home" / ".hermes" / "state.db"
        if not db.exists():
            raise SystemExit(f"missing state.db for {rid}")
        for r in audit_run(db):
            rows.append({"run_id": rid, **r})
    out_calls.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    out_audit.write_text(json.dumps(summarize(rows, runs), indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
