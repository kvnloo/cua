"""Summarise one finished run dir (stdlib only; run under hostless). Writes <run>/run_summary.json.

Sources are kept apart on purpose:
  * tool-call sequence, system prompt hash, final text  <- Hermes' own private state.db (not the observer)
  * trace/turn identity, lifecycle counts                <- observer spool (kvnloo/hermes-agent#385)
  * shadow decisions                                     <- sidecar output + z0int receipts
  * verdict                                              <- oracle.json (fixture-owned state)
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

# Live-home / real-home path prefixes to look for in the Hermes environment (given by the operator, never committed).
LIVE_MARKERS = tuple(m for m in os.environ.get("STACK_LIVE_MARKERS", "").split(":") if m)


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
    if not p.exists():
        return {}
    return dict(line.split("=", 1) for line in p.read_text().splitlines() if "=" in line)


def canon(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


_IDS = re.compile(r"(\bpid\b[\"']?\s*[:=]?\s*|\bwindow_id\b[\"']?\s*[:=]?\s*)\d+|[0-9a-f]{32}|\b\d{5,}\b")


def norm(text: str) -> str:
    """Tool result with run-varying identifiers (pids, window ids, uuids, long numbers) masked."""
    return _IDS.sub(lambda m: (m.group(1) or "") + "<N>", text or "")


def state_db(rd: Path) -> dict:
    db = rd / "home" / ".hermes" / "state.db"
    if not db.exists():
        return {"present": False}
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    seq, texts = [], []
    for role, content, tool_calls in c.execute("select role, content, tool_calls from messages order by id"):
        if role == "assistant":
            for t in json.loads(tool_calls) if tool_calls else []:
                fn = t.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": fn.get("arguments")}
                seq.append([fn.get("name"), canon(args)])
            if content:
                texts.append(content)
    sess = [dict(zip(("id", "system_prompt_hash", "input_tokens", "output_tokens", "api_call_count", "tool_call_count",
                      "end_reason", "model"), r)) for r in
            c.execute("select id, system_prompt_hash, input_tokens, output_tokens, api_call_count, tool_call_count, "
                      "end_reason, model from sessions")]
    tool_results = [r for (r,) in c.execute("select content from messages where role='tool' order by id")]
    return {"present": True, "sessions": sess, "tool_sequence": seq,
            "tool_sequence_sha256": hashlib.sha256(canon(seq).encode()).hexdigest(),
            "final_text_sha256": hashlib.sha256((texts[-1] if texts else "").encode()).hexdigest(),
            "final_text_head": (texts[-1] if texts else "")[:160],
            "tool_result_sha256": [hashlib.sha256((r or "").encode()).hexdigest()[:16] for r in tool_results],
            "tool_result_norm_sha256": [hashlib.sha256(norm(r).encode()).hexdigest()[:16] for r in tool_results]}


def summarise(rd: Path) -> dict:
    run = json.loads((rd / "run.json").read_text())
    meta = rd / "meta"
    s: dict = {"run_id": run["run_id"], "task": run["task"], "arm": run["arm"], "pair": run["pair"],
               "driver_key": run["driver_key"], "set": run["set"], "prompt_sha256": run["prompt_sha256"]}
    s["hermes_rc"] = int((meta / "exit_code").read_text()) if (meta / "exit_code").exists() else None
    try:
        s["hermes_wall_s"] = round(float((meta / "hermes.end").read_text()) - float((meta / "hermes.start").read_text()), 2)
    except Exception:
        s["hermes_wall_s"] = None
    s["oracle"] = json.loads((rd / "oracle.json").read_text()) if (rd / "oracle.json").exists() else {"verdict": "unknown"}
    # isolation evidence
    mask = {k: int(v) for k, v in kv(meta / "mask.inside").items()}
    env_inside = (meta / "env.inside").read_text() if (meta / "env.inside").exists() else ""
    before = (meta / "live-home-stat.before").read_text().splitlines() if (meta / "live-home-stat.before").exists() else []
    after = (meta / "live-home-stat.after").read_text().splitlines() if (meta / "live-home-stat.after").exists() else []
    files_changed = [b.split("|")[0].rsplit("/", 1)[-1] for b, a in zip(before, after) if b != a]
    s["isolation"] = {
        "mask_inside": mask, "all_masked_empty": bool(mask) and all(v == 0 for v in mask.values()),
        "env_inside_live_refs": sum(m in env_inside for m in LIVE_MARKERS),
        "env_inside_host_display_vars": sum(x in env_inside for x in ("WAYLAND_DISPLAY=", "HYPRLAND_", "SWAYSOCK=")),
        "live_home_entries_changed_during_run": files_changed,
    }
    s["state_db"] = state_db(rd)
    # observer
    ev = jl(rd / "home" / ".hermes" / "plugin-data" / "z0-hermes-observer" / "events.jsonl")
    ident = [r.get("identity") or {} for r in ev]
    usage_pt = [int((r.get("usage") or {}).get("prompt_tokens") or 0) for r in ev if r.get("event") == "post_api_request"]
    s["observer"] = {
        "rows": len(ev), "events": dict(Counter(r.get("event") for r in ev)),
        "trace_ids": sorted({i.get("trace_id") for i in ident if i.get("trace_id") and i.get("turn_id")}),
        "turn_ids": sorted({i.get("turn_id") for i in ident if i.get("turn_id")}),
        "session_ids": sorted({i.get("session_id") for i in ident if i.get("session_id")}),
        "dropped_rows": sum(int((r.get("fields") or {}).get("dropped_rows") or 0) for r in ev
                            if r.get("event") == "observer_rows_dropped"),
        "peak_prompt_tokens": max(usage_pt) if usage_pt else None,
        "turn_exit_reason": next(((r.get("fields") or {}).get("turn_exit_reason") for r in ev
                                  if r.get("event") == "on_session_end"), None),
    }
    # shadow
    sh = rd / "shadow"
    rec = jl(sh / "z0int-home" / "receipts" / "decisions.jsonl")
    full = jl(sh / "decisions.full.jsonl")
    s["shadow"] = {
        "sidecar_summary": json.loads((sh / "sidecar_summary.json").read_text()) if (sh / "sidecar_summary.json").exists() else None,
        "backend_load": json.loads((sh / "backend_load.json").read_text()) if (sh / "backend_load.json").exists() else None,
        "receipts": len(rec), "receipt_statuses": dict(Counter((r.get("extra") or {}).get("shadow_status") for r in rec)),
        "receipt_capabilities": dict(Counter(r.get("capability_id") for r in rec)),
        "receipt_trace_ids": sorted({r.get("trace_id") for r in rec if r.get("trace_id")}),
        "receipt_turn_ids": sorted({(r.get("extra") or {}).get("turn_id") for r in rec if (r.get("extra") or {}).get("turn_id")}),
        "full_rows": len(full),
    }
    return s


def main() -> None:
    for arg in sys.argv[1:]:
        rd = Path(arg)
        out = summarise(rd)
        (rd / "run_summary.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        print(rd.name, out["oracle"].get("verdict"), out["hermes_rc"], out["observer"]["rows"], out["shadow"]["receipts"])


if __name__ == "__main__":
    main()
