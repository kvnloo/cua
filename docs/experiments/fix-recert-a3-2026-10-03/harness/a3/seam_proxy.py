#!/usr/bin/env python3
"""Process-level refusal seam for the TypeScript F3 rows (RECERT-FIX a3, new file).

The TypeScript runner (typescript/run.ts) spawns its Driver as `$CUA_DRIVER_BIN mcp` over stdio, so
the in-process Python seam (harness/fix02-w3/browser/refusal_seam.py) cannot wrap it. This proxy is
that seam at the process boundary: run.ts spawns a per-cell wrapper script that execs this file,
which spawns the real `cua-driver mcp` and relays newline-delimited JSON-RPC unchanged, except for
the FIRST `browser_click` after a successful `browser_type` (the Submit click), exactly as
refusal_seam.py does:

  pre   the click is NOT forwarded; the caller gets the injected refusal (nothing reaches the page);
  post  the click IS forwarded and dispatched; the Driver's response is dropped and the injected
        refusal is delivered in its place (the effect landed; delivery is unknown to the caller).

The injected results are refusal_seam.INJECTIONS (imported, unchanged wire shapes). The journal is
content-free: method, tool, argument keys, ids, is_error and the picked structured fields only.

usage: seam_proxy.py --real <cua-driver> --code stale|trust_unknown|none --journal <file> -- <args...>
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fix02-w3", "browser"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fix02-w3", "r2-07"))

# refusal_seam imports the mcp SDK and anyio at module level; the jev-use venv provides both.
from refusal_seam import INJECTIONS  # noqa: E402

RESULT_FIELDS = ("effect", "route", "status", "code", "verified", "outcome", "acted_path")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", required=True)
    ap.add_argument("--code", required=True, choices=["stale", "trust_unknown", "not_retryable", "none"])
    ap.add_argument("--journal", required=True)
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    rest = args.rest[1:] if args.rest[:1] == ["--"] else args.rest
    spec = INJECTIONS.get(args.code)
    t0 = time.monotonic_ns()
    journal = open(args.journal, "a", encoding="utf-8")
    jlock = threading.Lock()
    out_lock = threading.Lock()
    state = {"typed_ok": False, "fired": False, "post_id": None}
    pending = {}

    def log(kind, **fields):
        with jlock:
            journal.write(json.dumps({"kind": kind, "t_ms": round((time.monotonic_ns() - t0) / 1e6, 3),
                                      **fields}, sort_keys=True) + "\n")
            journal.flush()

    def to_caller(message):
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode()
        with out_lock:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()

    child = subprocess.Popen([args.real, *rest], stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
    log("proxy_start", code=args.code, argv_tail=rest)

    def c2s():
        for raw in sys.stdin.buffer:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                child.stdin.write(raw)
                child.stdin.flush()
                continue
            if "method" in message and "id" in message:
                params = message.get("params") or {}
                desc = {"id": message["id"], "method": message["method"]}
                if message["method"] == "tools/call":
                    desc["tool"] = params.get("name")
                    desc["arg_keys"] = sorted((params.get("arguments") or {}))
                pending[message["id"]] = desc
                is_submit = desc.get("tool") == "browser_click" and state["typed_ok"]
                if spec and is_submit and not state["fired"]:
                    state["fired"] = True
                    if spec["where"] == "pre":
                        pending.pop(message["id"], None)
                        log("click_not_forwarded_refusal_injected", code=spec["code"], **desc)
                        to_caller({"jsonrpc": "2.0", "id": message["id"], "result": spec["result"]})
                        continue
                    state["post_id"] = message["id"]
                    log("click_forwarded_refusal_will_replace_response", code=spec["code"], **desc)
                log("forwarded_request", **desc)
            else:
                log("forwarded_other", method=message.get("method"))
            child.stdin.write(line + b"\n")
            child.stdin.flush()
        log("caller_stdin_eof")
        try:
            child.stdin.close()
        except OSError:
            pass

    def s2c():
        for raw in child.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                with out_lock:
                    sys.stdout.buffer.write(line + b"\n")
                    sys.stdout.buffer.flush()
                continue
            rid = message.get("id")
            req = pending.pop(rid, None) if "method" not in message else None
            if req is None:
                to_caller(message)
                continue
            desc = {"id": rid, "for_tool": req.get("tool") or req.get("method")}
            if "error" in message:
                desc["jsonrpc_error_code"] = (message.get("error") or {}).get("code")
            else:
                result = message.get("result") or {}
                desc["is_error"] = bool(result.get("isError"))
                structured = result.get("structuredContent")
                if isinstance(structured, dict):
                    desc["structured"] = {k: structured[k] for k in RESULT_FIELDS
                                          if isinstance(structured.get(k), (bool, int, float))
                                          or (isinstance(structured.get(k), str) and len(structured[k]) <= 64)}
            if req.get("tool") == "browser_type" and not desc.get("is_error") and "jsonrpc_error_code" not in desc:
                state["typed_ok"] = True
            if spec and rid is not None and rid == state["post_id"]:
                log("driver_response_replaced_by_refusal", driver=desc, code=spec["code"])
                to_caller({"jsonrpc": "2.0", "id": rid, "result": spec["result"]})
                continue
            log("delivered_response", **desc)
            to_caller(message)

    reader = threading.Thread(target=s2c, daemon=True)
    reader.start()
    c2s()
    rc = child.wait()
    reader.join(timeout=5)
    log("proxy_exit", child_rc=rc, injected=state["fired"])
    journal.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
