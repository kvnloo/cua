"""B-07 FIXTURE controls for the caller-side candidates (no Driver, no display, no network).

Runs the jev-use mcp client stack (harness/b07_stdio.py) against harness/neg_server.py:
1. Malformed frames (ROUTE_FAST negative control): every frame of neg_server.MALFORMED through
   ClientSession.call_tool with route=default and route=fast. The outcome per frame (result
   accepted, or the exception type) must be identical in both arms, and no malformed frame may be
   accepted. Read timeout 1.5 s (a frame whose id matches no waiter can only time out).
2. Request bytes (PREP_FAST equivalence and fallback): a fixed list of argument dicts, including
   non-ASCII, U+2028, control characters, quotes, nested values and the fallback types (float, None,
   int >= 2**53), through prep=default and prep=fast. Every request line the server received must be
   byte-identical between the arms and to the library serialisation of the same (name, arguments,
   id); plain cases must take the fast path and fallback cases the library path.

usage: b07_controls.py <out.json>   (jev-use venv python, under hostless)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import b07_stdio as bs  # noqa: E402
from mcp import types  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402
import neg_server  # noqa: E402

bs.install()

PREP_CASES: list[tuple[str, dict[str, Any], bool]] = [
    ("ascii", {"session": "jev-r210-abc", "ref": "s1:e3", "snapshot_format": "semantic_v2"}, True),
    ("non_ascii", {"text": "héllo ü 日本 \U0001F600"}, True),
    ("line_separators", {"text": "a b c"}, True),
    ("control_chars", {"text": "\x01\x08\t\n\r\x1f\x7f"}, True),
    ("quotes_slashes", {"text": "\"q\" \\ / </script>"}, True),
    ("ints_bools", {"n": 2 ** 53 - 1, "neg": -5, "zero": 0, "t": True, "f": False}, True),
    ("nested", {"nested": {"x": [1, "y", {"z": []}], "e": {}}, "list": []}, True),
    ("empty", {}, True),
    ("float", {"x": 1.5}, False),
    ("none", {"x": None}, False),
    ("big_int", {"x": 2 ** 60}, False),
]


def library_line(name: str, arguments: dict[str, Any], rid: int) -> str:
    req = types.ClientRequest(types.CallToolRequest(params=types.CallToolRequestParams(name=name, arguments=arguments)))
    data = req.model_dump(by_alias=True, mode="json", exclude_none=True)
    return types.JSONRPCMessage(types.JSONRPCRequest(jsonrpc="2.0", id=rid, **data)).model_dump_json(
        by_alias=True, exclude_none=True)


async def run(mode: str, prep: str, route: str, log: Path, calls: list[tuple[str, dict[str, Any]]],
              timeout_s: float | None) -> list[dict[str, Any]]:
    bs.STAMP.update({"prep": prep, "route": route})
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / "neg_server.py"), str(log), mode],
                                   env={"PYTHONDONTWRITEBYTECODE": "1"})
    out = []
    before = dict(bs.COUNTS)
    try:
        async with bs.stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for name, args in calls:
                    try:
                        kw = {"read_timeout_seconds": timedelta(seconds=timeout_s)} if timeout_s else {}
                        res = await session.call_tool(name, args, **kw)
                        out.append({"outcome": "accepted", "isError": res.isError,
                                    "text": [c.text for c in res.content if getattr(c, "text", None) is not None]})
                    except Exception as error:  # noqa: BLE001
                        out.append({"outcome": "rejected", "error": type(error).__name__})
    finally:
        bs.STAMP.update({"prep": "default", "route": "default"})
    counts = {k: bs.COUNTS[k] - before[k] for k in bs.COUNTS}
    return out + [{"counts": counts}]


async def main_async(out_path: Path) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="b07-controls-", dir=os.environ.get("TMPDIR")))
    result: dict[str, Any] = {"schema": "b-07.controls.v1"}
    # 1. malformed frames
    calls = [("echo", {"i": k}) for k in range(len(neg_server.MALFORMED))]
    mal = {}
    for route in ("default", "fast"):
        rows = await run("malformed", "default", route, tmp / f"mal-{route}.log", calls, 1.5)
        mal[route] = rows
    names = [n for n, _ in neg_server.MALFORMED]
    per = []
    for i, n in enumerate(names):
        a, b = mal["default"][i], mal["fast"][i]
        per.append({"frame": n, "default": a, "fast": b, "same": a == b})
    expected_accept = {"string_id"}  # the library normalises "3" -> 3; both arms must agree
    result["malformed"] = {
        "rows": per, "counts": {k: mal[k][-1]["counts"] for k in mal},
        "same_outcome_all": all(x["same"] for x in per),
        "malformed_rejected_all": all(x["default"]["outcome"] == "rejected" and x["fast"]["outcome"] == "rejected"
                                      for x in per if x["frame"] not in expected_accept),
        "n_frames": len(per)}
    # 2. request bytes
    pcalls = [("echo", args) for _, args, _ in PREP_CASES]
    logs = {}
    counts = {}
    for prep in ("default", "fast"):
        rows = await run("echo", prep, "default", tmp / f"prep-{prep}.log", pcalls, None)
        counts[prep] = rows[-1]["counts"]
        logs[prep] = [ln for ln in (tmp / f"prep-{prep}.log").read_text(encoding="utf-8").split("\n") if ln]
    reqs = {p: [ln for ln in logs[p] if json.loads(ln).get("method") == "tools/call"] for p in logs}
    cases = []
    for (cname, args, plain), ld, lf in zip(PREP_CASES, reqs["default"], reqs["fast"]):
        rid = json.loads(lf)["id"]
        lib = library_line("echo", args, rid)
        cases.append({"case": cname, "plain": plain, "default_eq_fast": ld == lf, "fast_eq_library": lf == lib,
                      "plain_json": bs.plain_json(args)})
    result["prep_bytes"] = {
        "cases": cases, "counts": counts,
        "all_identical": all(c["default_eq_fast"] and c["fast_eq_library"] for c in cases)
        and len(cases) == len(PREP_CASES) and logs["default"] == logs["fast"],
        "fast_path_taken": counts["fast"]["prep_fast"], "fallbacks": counts["fast"]["prep_fallback"],
        "expected_fast": sum(1 for c in PREP_CASES if c[2]), "expected_fallback": sum(1 for c in PREP_CASES if not c[2])}
    out_path.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"malformed_same": result["malformed"]["same_outcome_all"],
                      "malformed_rejected": result["malformed"]["malformed_rejected_all"],
                      "prep_all_identical": result["prep_bytes"]["all_identical"],
                      "prep_fast": result["prep_bytes"]["fast_path_taken"],
                      "prep_fallback": result["prep_bytes"]["fallbacks"]}))


if __name__ == "__main__":
    asyncio.run(main_async(Path(sys.argv[1])))
