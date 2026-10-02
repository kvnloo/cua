"""Summarise one finished stack2-addr run dir (stdlib only; run under hostless).

Writes <run>/run_summary.json and <run>/tool_calls.jsonl. Sources are kept apart on purpose:
  * every computer_use call and its result  <- Hermes' own private state.db (paired by tool_call_id)
  * trace/turn identity, prompt tokens      <- observer spool (kvnloo/hermes-agent#385)
  * verdict                                 <- oracle.json (fixture-owned state read after Hermes exited)

Result classes (PREREG.json "tool_result_classes"; first match wins):
  addressing_refused   result message says the Driver refused an element-addressing argument name
                       ("unknown argument element_index|snapshot_id|from_element|to_element")
  token_unavailable    Hermes refused locally: code element_token_unavailable (no Driver call)
  stale_token          Driver: "element_token is stale"
  invalid_token        Driver: invalid token format / out of range / conflicts with window_id
  other_error          any other ok=false result, an {"error": ...} result, or a non-JSON result
  capture_ok           a capture result carrying a mode (or Hermes' byte-identical-result note)
  ok                   an action result with ok=true
tool error = any class other than capture_ok and ok.
usage: extract.py <run dir> [<run dir> ...]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

LIVE_MARKERS = tuple(m for m in os.environ.get("STACK_LIVE_MARKERS", "").split(":") if m)
ADDR_RE = re.compile(r"unknown argument (element_index|snapshot_id|from_element|to_element)\b")
STALE_RE = re.compile(r"element_token is stale")
INVALID_RE = re.compile(r"element_token has invalid format|element_token element_index \d+ out of range|"
                        r"element_token conflicts with window_id")
ELEMENT_KEYS = ("element", "from_element", "to_element")
GUI_ACTIONS = {"click", "double_click", "right_click", "middle_click", "triple_click", "scroll", "set_value", "drag"}


def jl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                out.append({"_unparseable": True})
    return out


def kv(p: Path) -> dict:
    return dict(line.split("=", 1) for line in p.read_text().splitlines() if "=" in line) if p.exists() else {}


def canon(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def classify(result: str | None) -> tuple[str, dict]:
    text = result or ""
    if text.startswith("[hermes note: this result is byte-identical"):
        return "capture_ok", {"duplicate_note": True}
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return "other_error", {"message": text[:240], "non_json": True}
    if not isinstance(obj, dict):
        return "other_error", {"message": text[:240]}
    message = str(obj.get("message") or obj.get("error") or "")
    meta = obj.get("meta") if isinstance(obj.get("meta"), dict) else {}
    refusal = meta.get("refusal") if isinstance(meta.get("refusal"), dict) else {}
    code = obj.get("code") or refusal.get("code")
    info = {"message": message[:240], "code": code, "effect": obj.get("effect"), "path": obj.get("path")}
    blob = message + " " + json.dumps(refusal)
    if ADDR_RE.search(blob):
        return "addressing_refused", info
    if code == "element_token_unavailable":
        return "token_unavailable", info
    if STALE_RE.search(blob):
        return "stale_token", info
    if INVALID_RE.search(blob):
        return "invalid_token", info
    if "mode" in obj and "ok" not in obj:
        return ("capture_ok" if not obj.get("error") else "other_error"), {"elements": len(obj.get("elements") or []),
                                                                             "total_elements": obj.get("total_elements")}
    if obj.get("ok") is True:
        return "ok", info
    return "other_error", info


def state_db(rd: Path) -> tuple[dict, list[dict]]:
    db = rd / "home" / ".hermes" / "state.db"
    if not db.exists():
        return {"present": False}, []
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    calls, results, texts = [], {}, []
    for role, content, tool_calls, tool_call_id in c.execute(
            "select role, content, tool_calls, tool_call_id from messages order by id"):
        if role == "assistant":
            for t in json.loads(tool_calls) if tool_calls else []:
                fn = t.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": fn.get("arguments")}
                calls.append({"id": t.get("id"), "name": fn.get("name"), "args": args})
            if content:
                texts.append(content)
        elif role == "tool":
            results[tool_call_id] = content
    rows = []
    for i, call in enumerate(calls):
        args = call["args"] if isinstance(call["args"], dict) else {}
        res = results.get(call["id"])
        cls, info = classify(res) if res is not None else ("no_result", {})
        action = args.get("action")
        rows.append({"seq": i, "tool": call["name"], "action": action, "args": canon(args),
                     # only pointer/value actions take an element or coordinate target (type/key ignore them)
                     "element_addressed": action in GUI_ACTIONS and any(isinstance(args.get(k), int) for k in ELEMENT_KEYS),
                     "coordinate_addressed": action in GUI_ACTIONS and any(args.get(k) is not None for k in
                                                                          ("coordinate", "from_coordinate")),
                     "result_class": cls, **info})
    sess = [dict(zip(("id", "system_prompt_hash", "input_tokens", "output_tokens", "api_call_count", "tool_call_count",
                      "end_reason", "model"), r)) for r in
            c.execute("select id, system_prompt_hash, input_tokens, output_tokens, api_call_count, tool_call_count, "
                      "end_reason, model from sessions")]
    seq = [[r["tool"], r["args"]] for r in rows]
    return {"present": True, "sessions": sess,
            "tool_sequence_sha256": hashlib.sha256(canon(seq).encode()).hexdigest(),
            "final_text_head": (texts[-1] if texts else "")[:160]}, rows


def tool_metrics(rows: list[dict]) -> dict:
    classes = Counter(r["result_class"] for r in rows)
    el = [r for r in rows if r["element_addressed"]]
    errors = sum(v for k, v in classes.items() if k not in ("capture_ok", "ok"))
    return {"tool_calls": len(rows), "result_classes": dict(classes), "tool_errors": errors,
            "successful_tool_calls": classes.get("capture_ok", 0) + classes.get("ok", 0),
            "element_actions": len(el), "element_actions_ok": sum(r["result_class"] == "ok" for r in el),
            "element_action_classes": dict(Counter(r["result_class"] for r in el)),
            "coordinate_actions": sum(r["coordinate_addressed"] and not r["element_addressed"] for r in rows),
            "gui_actions": sum(r["action"] in GUI_ACTIONS for r in rows)}


def summarise(rd: Path) -> tuple[dict, list[dict]]:
    run = json.loads((rd / "run.json").read_text())
    meta = rd / "meta"
    s: dict = {k: run[k] for k in ("run_id", "task", "arm", "pair", "driver_key", "set", "prompt_sha256", "hermes_head")}
    s["hermes_rc"] = int((meta / "exit_code").read_text()) if (meta / "exit_code").exists() else None
    try:
        s["hermes_wall_s"] = round(float((meta / "hermes.end").read_text()) - float((meta / "hermes.start").read_text()), 2)
    except Exception:
        s["hermes_wall_s"] = None
    s["oracle"] = json.loads((rd / "oracle.json").read_text()) if (rd / "oracle.json").exists() else {"verdict": "unknown"}
    mask = {k: int(v) for k, v in kv(meta / "mask.inside").items()}
    env_inside = (meta / "env.inside").read_text() if (meta / "env.inside").exists() else ""
    before = (meta / "live-home-stat.before").read_text().splitlines() if (meta / "live-home-stat.before").exists() else []
    after = (meta / "live-home-stat.after").read_text().splitlines() if (meta / "live-home-stat.after").exists() else []
    s["isolation"] = {
        "mask_inside": mask, "all_masked_empty": bool(mask) and all(v == 0 for v in mask.values()),
        "env_inside_live_refs": sum(m in env_inside for m in LIVE_MARKERS),
        "env_inside_host_display_vars": sum(x in env_inside for x in ("WAYLAND_DISPLAY=", "HYPRLAND_", "SWAYSOCK=")),
        "live_home_entries_changed_during_run": [b.split("|")[0].rsplit("/", 1)[-1] for b, a in zip(before, after) if b != a],
    }
    s["state_db"], rows = state_db(rd)
    s["tools"] = tool_metrics(rows)
    ev = jl(rd / "home" / ".hermes" / "plugin-data" / "z0-hermes-observer" / "events.jsonl")
    ident = [r.get("identity") or {} for r in ev]
    usage_pt = [int((r.get("usage") or {}).get("prompt_tokens") or 0) for r in ev if r.get("event") == "post_api_request"]
    s["observer"] = {
        "rows": len(ev), "events": dict(Counter(r.get("event") for r in ev)),
        "trace_ids": sorted({i.get("trace_id") for i in ident if i.get("trace_id") and i.get("turn_id")}),
        "peak_prompt_tokens": max(usage_pt) if usage_pt else None,
        "turn_exit_reason": next(((r.get("fields") or {}).get("turn_exit_reason") for r in ev
                                  if r.get("event") == "on_session_end"), None),
    }
    return s, rows


def main() -> None:
    for arg in sys.argv[1:]:
        rd = Path(arg)
        out, rows = summarise(rd)
        (rd / "run_summary.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        (rd / "tool_calls.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        t = out["tools"]
        print(rd.name, out["oracle"].get("verdict"), out["hermes_rc"], f"calls={t['tool_calls']} err={t['tool_errors']}",
              f"el={t['element_actions_ok']}/{t['element_actions']}", t["result_classes"])


if __name__ == "__main__":
    main()
