#!/usr/bin/env python3
"""export_messages.py <private state.db> <out messages.jsonl> : the messages table (role, content, tool_calls) of a
lane-private Hermes run, in rowid order, with local path prefixes masked, so the packet can ship transcripts without
the sqlite file (which also stores session cwd/system-prompt metadata). Grading reads it exactly like state.db."""
import json, re, sqlite3, sys
MASK = [(re.compile(r"/mnt/[^/\s\"']+/cua-lane-tmp"), "<TMP>"), (re.compile(r"/mnt/[^/\s\"']+"), "<MNT>"),
        (re.compile(r"/home/[^/\s\"']+"), "<HOME>")]
def mask(x):
    if not isinstance(x, str):
        return x
    for pat, rep in MASK:
        x = pat.sub(rep, x)
    return x
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
with open(sys.argv[2], "w") as f:
    for role, content, tool_calls in con.execute("SELECT role, content, tool_calls FROM messages ORDER BY rowid"):
        f.write(json.dumps({"role": role, "content": mask(content), "tool_calls": mask(tool_calls)}) + "\n")
