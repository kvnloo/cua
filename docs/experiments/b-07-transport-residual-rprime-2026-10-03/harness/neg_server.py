"""B-07 FIXTURE server for the caller-side controls (standard library only; no Driver, no display).

A minimal MCP stdio server. It answers initialize and tools/list like a server with one tool
("echo", no output schema), ignores notifications, appends every received request line verbatim
to the file named by argv[1], and answers each tools/call according to argv[2]:
  "echo"       a valid CallToolResult whose text is the call's arguments (canonical JSON);
  "malformed"  the next frame of MALFORMED (B-05's list from harness/b05/b05_floor.py, plus
               unknown_id and string_id), with the request's id substituted.
"""

from __future__ import annotations

import json
import sys

B05_MALFORMED = [  # verbatim from harness/b05/b05_floor.py
    ("truncated_json", '{{"jsonrpc":"2.0","id":{id},"result":{{"content":['),
    ("not_json", "garbage {id}"),
    ("wrong_version", '{{"jsonrpc":"1.0","id":{id},"result":{{"content":[]}}}}'),
    ("missing_jsonrpc", '{{"id":{id},"result":{{"content":[]}}}}'),
    ("result_is_list", '{{"jsonrpc":"2.0","id":{id},"result":[1,2]}}'),
    ("id_null", '{{"jsonrpc":"2.0","id":null,"result":{{"content":[]}}}}'),
    ("id_fraction", '{{"jsonrpc":"2.0","id":{id}.5,"result":{{"content":[]}}}}'),
    ("error_code_string", '{{"jsonrpc":"2.0","id":{id},"error":{{"code":"x","message":"m"}}}}'),
    ("batch_array", '[{{"jsonrpc":"2.0","id":{id},"result":{{"content":[]}}}}]'),
    ("content_not_list", '{{"jsonrpc":"2.0","id":{id},"result":{{"content":"notalist"}}}}'),
]

MALFORMED = list(B05_MALFORMED) + [
    ("unknown_id", '{{"jsonrpc":"2.0","id":{uid},"result":{{"content":[]}}}}'),
    ("string_id", '{{"jsonrpc":"2.0","id":"{id}","result":{{"content":[]}}}}'),
]


def main() -> None:
    log = open(sys.argv[1], "a", encoding="utf-8")
    mode = sys.argv[2]
    k = 0
    out = sys.stdout
    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line:
            continue
        msg = json.loads(line)
        if "id" not in msg:
            continue
        log.write(line + "\n")
        log.flush()
        rid, method = msg["id"], msg.get("method")
        if method == "initialize":
            res = {"protocolVersion": msg["params"]["protocolVersion"], "capabilities": {"tools": {}},
                   "serverInfo": {"name": "b07-neg", "version": "0"}}
            frame = json.dumps({"jsonrpc": "2.0", "id": rid, "result": res})
        elif method == "tools/list":
            frame = json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
                {"name": "echo", "inputSchema": {"type": "object"}}]}})
        elif method == "tools/call" and mode == "echo":
            text = json.dumps(msg["params"].get("arguments"), sort_keys=True, ensure_ascii=False)
            frame = json.dumps({"jsonrpc": "2.0", "id": rid,
                                "result": {"content": [{"type": "text", "text": text}], "isError": False}})
        elif method == "tools/call":
            name, tmpl = MALFORMED[k % len(MALFORMED)]
            k += 1
            frame = tmpl.format(id=rid, uid=rid + 1000)
        else:
            frame = json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "no"}})
        out.write(frame + "\n")
        out.flush()


if __name__ == "__main__":
    main()
