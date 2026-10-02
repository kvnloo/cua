#!/usr/bin/env python3
"""transcript.py <private state.db> [--json out.json] : tool-call digest of a lane-private Hermes run.

Reads ONLY a lane-private state.db (never the live Hermes home). Emits per assistant tool call the action and
arguments, and per tool result its error/refusal markers (stale refs, Driver refusals, approval blocks), so the
grader can count stale refs and blocked actions without trusting the model's final text.
"""
import json
import re
import sqlite3
import sys

db = sys.argv[1]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
cols = [r[1] for r in con.execute("PRAGMA table_info(messages)")]
rows = con.execute(f"SELECT {', '.join(cols)} FROM messages ORDER BY rowid").fetchall()
MARK = re.compile(r"(stale|superseded|not found|no such element|refus|BLOCKED|denied|error|out of range|timed out)",
                  re.IGNORECASE)
calls, results = [], []
for row in rows:
    m = dict(zip(cols, row))
    role = m.get("role")
    if role == "assistant" and m.get("tool_calls"):
        try:
            tcs = json.loads(m["tool_calls"])
        except (TypeError, ValueError):
            tcs = []
        for tc in tcs:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {"_raw": fn.get("arguments")}
            calls.append({"name": fn.get("name"), "args": args})
    elif role == "tool":
        text = m.get("content") or ""
        if not isinstance(text, str):
            text = json.dumps(text)
        results.append({"len": len(text), "markers": sorted({x.lower() for x in MARK.findall(text)}),
                        "head": text[:300]})
final = next((dict(zip(cols, r)).get("content") for r in reversed(rows) if dict(zip(cols, r)).get("role") == "assistant"
              and dict(zip(cols, r)).get("content")), None)
out = {"n_messages": len(rows), "n_tool_calls": len(calls), "calls": calls, "results": results,
       "final_text": (final or "")[:500]}
if "--json" in sys.argv:
    json.dump(out, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
else:
    for c in calls:
        print("CALL", c["name"], json.dumps(c["args"])[:200])
    for r in results:
        print("RES ", r["markers"], r["head"][:200].replace("\n", " "))
    print("FINAL", out["final_text"][:200])
