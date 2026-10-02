#!/usr/bin/env python3
"""collect.py <runs-root> <packet raw/<name>> [--server-log <serve.log>] : copy receipts into the packet, sanitized.

Copies the oracle inputs and diagnostics of every round/agent/control (never the private Hermes sqlite files:
their messages table is exported to hermes/messages.jsonl instead). Text files get local path prefixes and the
host name masked; PNG screenshots are copied as-is. With --server-log, the shared model server's request lines
inside the measured window are copied to server-requests.log (request lines only) so the contamination count
can be re-derived.
"""
import os
import re
import shutil
import sqlite3
import json
import sys

SRC, DST = sys.argv[1].rstrip("/"), sys.argv[2].rstrip("/")
LOG = sys.argv[sys.argv.index("--server-log") + 1] if "--server-log" in sys.argv else None
MASK = [(re.compile(r"/mnt/[^/\s\"']+/cua-lane-tmp"), "<TMP>"), (re.compile(r"/mnt/[^/\s\"']+"), "<MNT>"),
        (re.compile(r"/home/[^/\s\"']+"), "<HOME>"), (re.compile(r"/workspace/[^/\s\"']+"), "<WORKSPACE>"),
        (re.compile(r"/tmp/claude-\d+/[^\s\"']*"), "<SCRATCH>")]
MASK.append((re.compile(r"\b%s\b" % re.escape(__import__("socket").gethostname())), "<HOST>"))
AGENT_FILES = ["journal.jsonl", "final-state.json", "session.txt", "tree-before.json", "tree-after.json",
               "seats-before.json", "seats-after.json", "prompt.txt", "agent_rc", "agent_start_epoch", "agent_end_epoch",
               "session_ready_epoch", "screen-after.png", "journal.jsonl.log", "driver.json", "driver.stdout"]
HERMES_META = ["exit_code", "start", "start_epoch", "end_epoch", "worktree-head", "worktree-status", "mask.inside",
               "stdout", "stderr"]
HERMES_HOME = [".hermes/config.yaml", ".hermes/plugin-data/z0-hermes-observer/events.jsonl", ".hermes/logs/agent.log",
               ".hermes/logs/errors.log"]
SKIP_DIRS = {"home", "tmp", "cwd"}


def mask(text):
    for pat, rep in MASK:
        text = pat.sub(rep, text)
    return text


def copy(src, dst):
    if not os.path.isfile(src):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if src.endswith(".png"):
        shutil.copyfile(src, dst)
        return
    with open(src, "rb") as f:
        data = f.read()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        shutil.copyfile(src, dst)
        return
    with open(dst, "w", encoding="utf-8") as f:
        f.write(mask(text))


def export_messages(db, out):
    if not os.path.exists(db):
        return
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        for role, content, tool_calls in con.execute("SELECT role, content, tool_calls FROM messages ORDER BY rowid"):
            f.write(json.dumps({"role": role, "content": mask(content) if isinstance(content, str) else content,
                                "tool_calls": mask(tool_calls) if isinstance(tool_calls, str) else tool_calls}) + "\n")


def agent(src, dst):
    for f in AGENT_FILES:
        copy(f"{src}/{f}", f"{dst}/{f}")
    for f in HERMES_META:
        copy(f"{src}/hermes/meta/{f}", f"{dst}/hermes/meta/{f}")
    for f in HERMES_HOME:
        copy(f"{src}/hermes/home/{f}", f"{dst}/hermes/home/{f}")
    export_messages(f"{src}/hermes/home/.hermes/state.db", f"{dst}/hermes/messages.jsonl")


def generic(src, dst):
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith((".lock", ".db", ".db-wal", ".db-shm")):
                continue
            rel = os.path.relpath(os.path.join(root, f), src)
            copy(os.path.join(root, f), os.path.join(dst, rel))


t_min, t_max = None, None
for kind in sorted(os.listdir(SRC)):
    kp = f"{SRC}/{kind}"
    if not os.path.isdir(kp):
        copy(kp, f"{DST}/{kind}")
        continue
    for rd in sorted(os.listdir(kp)):
        rp = f"{kp}/{rd}"
        if not os.path.isdir(rp):
            copy(rp, f"{DST}/{kind}/{rd}")
            continue
        rj = f"{rp}/round.json"
        if os.path.exists(rj):
            r = json.load(open(rj))
            t_min = r["t0"] if t_min is None else min(t_min, r["t0"])
            t_max = r["t1"] if t_max is None else max(t_max, r["t1"])
            for f in os.listdir(rp):
                p = f"{rp}/{f}"
                if os.path.isfile(p):
                    copy(p, f"{DST}/{kind}/{rd}/{f}")
            for a in r["agents"]:
                agent(f"{rp}/{a['aid']}", f"{DST}/{kind}/{rd}/{a['aid']}")
        else:
            generic(rp, f"{DST}/{kind}/{rd}")
if LOG and t_min is not None:
    import datetime as dt
    pat = re.compile(r'^\[GIN\] (\d{4}/\d{2}/\d{2} - \d{2}:\d{2}:\d{2}) ')
    lo = dt.datetime.fromtimestamp(t_min - 120).strftime("%Y/%m/%d - %H:%M:%S")
    hi = dt.datetime.fromtimestamp(t_max + 120).strftime("%Y/%m/%d - %H:%M:%S")
    with open(f"{DST}/server-requests.log", "w") as out:
        for line in open(LOG, errors="replace"):
            m = pat.match(line)
            if m and lo <= m.group(1) <= hi and "/v1/chat/completions" in line:
                out.write(mask(line))
print("collected", SRC, "->", DST)
