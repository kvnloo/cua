#!/usr/bin/env python3
"""sampler.py <out.jsonl> <round-root-pid> <stop-file> [ollama-pid] : 1 Hz resource sampler for one round.

Per tick: for every direct child of <round-root-pid> (one per private session launcher) the summed
utime+stime ticks, RSS kB and process count of its whole descendant tree; the same for the model server
(<ollama-pid> and its runner children); GPU memory used / utilisation and per-process GPU memory (nvidia-smi).
Read-only /proc and nvidia-smi queries; stdlib only. Stops when <stop-file> exists.
"""
import json
import os
import subprocess
import sys
import time

out, root, stop = sys.argv[1], int(sys.argv[2]), sys.argv[3]
ollama = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else None
PAGE_KB = os.sysconf("SC_PAGE_SIZE") // 1024


def procs():
    table = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as f:
                s = f.read()
            rest = s[s.rindex(")") + 2:].split()
            ppid, ut, st, rss = int(rest[1]), int(rest[11]), int(rest[12]), int(rest[21])
            table[int(d)] = (ppid, ut + st, rss * PAGE_KB, s[s.index("(") + 1:s.rindex(")")])
        except (OSError, ValueError, IndexError):
            continue
    return table


def tree(table, top):
    kids = {}
    for pid, (ppid, *_r) in table.items():
        kids.setdefault(ppid, []).append(pid)
    seen, stack = [], [top]
    while stack:
        p = stack.pop()
        if p in table:
            seen.append(p)
            stack.extend(kids.get(p, []))
    return seen


def agg(table, pids):
    return {"ticks": sum(table[p][1] for p in pids), "rss_kb": sum(table[p][2] for p in pids), "nproc": len(pids)}


def gpu():
    try:
        g = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5).stdout.strip().split(",")
        a = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5).stdout.strip().splitlines()
        return {"mem_used_mib": int(g[0]), "util_pct": int(g[1]),
                "apps": [[int(x) for x in line.split(",")] for line in a if line.strip()]}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)[:200]}


with open(out, "a", buffering=1) as f:
    f.write(json.dumps({"kind": "meta", "clk_tck": os.sysconf("SC_CLK_TCK"), "root": root, "ollama": ollama,
                        "ncpu": os.cpu_count()}) + "\n")
    while not os.path.exists(stop):
        t = time.time()
        table = procs()
        sessions = {}
        for pid, (ppid, *_r) in table.items():
            if ppid == root:
                sessions[str(pid)] = agg(table, tree(table, pid))
        row = {"kind": "tick", "t": round(t, 3), "sessions": sessions,
               "round_tree": agg(table, tree(table, root)), "gpu": gpu()}
        if ollama:
            row["ollama"] = agg(table, tree(table, ollama))
        with open("/proc/loadavg") as la:
            row["loadavg"] = la.read().split()[:3]
        f.write(json.dumps(row) + "\n")
        time.sleep(max(0.0, 1.0 - (time.time() - t)))
