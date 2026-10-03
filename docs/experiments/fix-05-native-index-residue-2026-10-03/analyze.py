#!/usr/bin/env python3
"""FIX-05 analysis: every row, gate and E4 counter from raw/native/<arm>/<row>/b*.jsonl.

usage: python3 analyze.py [--raw raw] [--out-summary summary.json] [--out-dispositions dispositions.json]
       python3 analyze.py --inspect <file.jsonl>   (per-call view, used for shakedowns)

Definitions (pre-registered in PREREG.json):
  window state = the fixture's own per-window state (two-window: state.windows.w1 / w2; single: the top
  level). Keys compared: agreed, counter, size, note_saved, note_text, scroll_value, focus, focus_log
  ("active" and "open" are reported separately: activation is a window-manager side effect).
  cross-window effect (R rows, CT) = any compared key of w2 changed between the pre and post reads of A's
  call. Own effect = the call's tool key changed in the addressed window (click: agreed; scroll:
  scroll_value; set_value: note_text; hotkey: focus_log; type_text: note_text).
  tail ok = B's own-token call on w2 changed w2's tool key.
  receipt = A's MCP result: is_error, refusal code (structured refusal.code or code), effect, status.
"""

import argparse
import glob
import json
import os
import sys

KEYS = ("agreed", "counter", "size", "note_saved", "note_text", "scroll_value", "focus", "focus_log")
TOOL_KEY = {"click": "agreed", "scroll": "scroll_value", "set_value": "note_text", "hotkey": "focus_log",
            "type_text": "note_text", "press_key": "agreed"}
ROW_TOOL = {"CT": "type_text", "RPA": "click", "RSC": "scroll", "RSV": "set_value", "RCF": "hotkey"}


def win(state, key):
    state = state or {}
    if key == "w":
        return state
    return (state.get("windows") or {}).get(key) or {}


def changed(pre, post, keys=KEYS):
    return sorted(k for k in keys if pre.get(k) != post.get(k))


def receipt(call):
    sc = (call.get("response") or {}).get("structuredContent") or {}
    refusal = sc.get("refusal") if isinstance(sc.get("refusal"), dict) else {}
    return {"is_error": bool(call.get("is_error")), "code": refusal.get("code") or sc.get("code"),
            "effect": sc.get("effect"), "status": sc.get("status"),
            "text": next((c.get("text", "")[:240] for c in (call.get("response") or {}).get("content", [])
                          if c.get("type") == "text"), "")}


def call_view(call, own_key):
    pre, post = (call.get("pre") or {}).get("P"), (call.get("post") or {}).get("P")
    two = bool((pre or {}).get("two_windows"))
    view = {"step": call["step"], "actor": call["actor"], "tool": call["tool"], "receipt": receipt(call)}
    if two:
        for key in ("w1", "w2"):
            view[f"{key}_changed"] = changed(win(pre, key), win(post, key))
            view[f"{key}_active_changed"] = win(pre, key).get("active") != win(post, key).get("active")
    else:
        view["w_changed"] = changed(win(pre, "w"), win(post, "w"))
    view["own_key"] = own_key
    return view


def load(path):
    rows = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def acts(rec):
    return [c for c in rec.get("calls", []) if c["tool"] not in ("get_window_state", "list_windows")]


def grade_closed(rec, row):
    """CT and the R rows: A's call on its own closed-w1 token, then B's own-token tail on w2."""
    calls = acts(rec)
    a, tail = calls[0], calls[-1]
    va, vt = call_view(a, TOOL_KEY[a["tool"]]), call_view(tail, TOOL_KEY[tail["tool"]])
    cross = bool(va["w2_changed"])
    tail_ok = TOOL_KEY[tail["tool"]] in vt["w2_changed"]
    return {"attempt": rec["attempt"], "order": rec["order"], "w1_closed": bool(rec.get("w1_closed_confirmed")),
            "cross_window": cross, "cross_keys": va["w2_changed"], "w2_active_changed": va["w2_active_changed"],
            "a_receipt": va["receipt"], "tail_ok": tail_ok, "tail_receipt": vt["receipt"],
            "a_refused": va["receipt"]["is_error"] and not cross}


def grade_nc(rec):
    out = {"attempt": rec["attempt"], "order": rec["order"], "calls": []}
    for call in acts(rec):
        own = "w1" if call["actor"] == "A" else "w2"
        other = "w2" if own == "w1" else "w1"
        v = call_view(call, TOOL_KEY[call["tool"]])
        out["calls"].append({"tool": call["tool"], "actor": call["actor"], "window": own,
                             "own_effect": TOOL_KEY[call["tool"]] in v[f"{own}_changed"],
                             "other_changed": v[f"{other}_changed"], "receipt": v["receipt"]})
    return out


def grade_ns(rec):
    out = {"attempt": rec["attempt"], "order": rec["order"], "calls": []}
    for call in acts(rec):
        v = call_view(call, TOOL_KEY[call["tool"]])
        out["calls"].append({"tool": call["tool"], "own_effect": TOOL_KEY[call["tool"]] in v["w_changed"],
                             "receipt": v["receipt"]})
    return out


def collect(raw):
    data = {}
    for path in sorted(glob.glob(os.path.join(raw, "native", "*", "*", "b*.jsonl"))):
        arm, row = path.split(os.sep)[-3], path.split(os.sep)[-2]
        entry = data.setdefault(row, {}).setdefault(arm, {"blocks": [], "attempts": []})
        for rec in load(path):
            if rec.get("kind") == "block":
                entry["blocks"].append({"file": os.path.relpath(path, os.path.dirname(raw.rstrip(os.sep)) or "."),
                                        "block": rec["block"], "driver_sha256": rec["driver_sha256"],
                                        "driver_version": rec["driver_version"],
                                        "fixture_sha256": rec["fixture_sha256"], "started_utc": rec["started_utc"]})
            elif rec.get("kind") == "attempt":
                if row in ("NC",):
                    entry["attempts"].append(grade_nc(rec))
                elif row == "NS":
                    entry["attempts"].append(grade_ns(rec))
                else:
                    entry["attempts"].append(grade_closed(rec, row))
    return data


def summarize(data):
    rows = {}
    for row, arms in sorted(data.items()):
        for arm, entry in sorted(arms.items()):
            atts = entry["attempts"]
            s = {"n": len(atts), "blocks": len(entry["blocks"]),
                 "driver_sha256": sorted({b["driver_sha256"] for b in entry["blocks"]}),
                 "driver_version": sorted({b["driver_version"] for b in entry["blocks"]})}
            if row in ("NC", "NS"):
                per_tool = {}
                for att in atts:
                    for c in att["calls"]:
                        key = f'{c["tool"]}:{c.get("window", "w")}'
                        t = per_tool.setdefault(key, {"n": 0, "own_effect": 0, "other_changed": 0,
                                                      "is_error": 0, "effects": {}})
                        t["n"] += 1
                        t["own_effect"] += c["own_effect"]
                        t["other_changed"] += bool(c.get("other_changed"))
                        t["is_error"] += c["receipt"]["is_error"]
                        eff = str(c["receipt"]["effect"])
                        t["effects"][eff] = t["effects"].get(eff, 0) + 1
                s["per_tool"] = per_tool
            else:
                s.update({
                    "w1_closed": sum(a["w1_closed"] for a in atts),
                    "cross_window": sum(a["cross_window"] for a in atts),
                    "w2_active_changed": sum(a["w2_active_changed"] for a in atts),
                    "tail_ok": sum(a["tail_ok"] for a in atts),
                    "a_is_error": sum(a["a_receipt"]["is_error"] for a in atts),
                    "a_codes": count(a["a_receipt"]["code"] for a in atts),
                    "a_effects": count(a["a_receipt"]["effect"] for a in atts),
                    "cross_keys": count(",".join(a["cross_keys"]) for a in atts if a["cross_keys"]),
                })
            rows.setdefault(row, {})[arm] = s
    return rows


def count(values):
    out = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def inspect(path):
    for rec in load(path):
        if rec.get("kind") != "attempt":
            print(json.dumps({k: rec.get(k) for k in ("kind", "block", "row", "driver_version")}))
            continue
        print(f'-- attempt {rec["attempt"]} {rec["order"]} handles={json.dumps(rec.get("handles"))[:400]}')
        for call in rec["calls"]:
            if call["tool"] in ("get_window_state",):
                continue
            v = call_view(call, TOOL_KEY.get(call["tool"]))
            print("  ", json.dumps(v)[:700])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw"))
    parser.add_argument("--inspect")
    parser.add_argument("--out-summary")
    args = parser.parse_args()
    if args.inspect:
        inspect(args.inspect)
        return
    data = collect(args.raw)
    summary = summarize(data)
    text = json.dumps(summary, indent=1, sort_keys=True)
    if args.out_summary:
        with open(args.out_summary, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
