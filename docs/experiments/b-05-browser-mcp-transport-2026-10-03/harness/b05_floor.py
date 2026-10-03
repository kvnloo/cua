"""B-05 stdio floor harness (FIXTURE, measurement only).

The floor server (floor/floor_echo.rs, standard library Rust) replays the Driver's recorded response
frames for one Phase A trial, byte for byte, in request order, with one write(2) per response and no
JSON work. Two clients drive it with the trial's exact request sequence (same payload sizes per call):

  F1  the same caller stack as Phase A: b05_stdio.stdio_client (mcp 1.30 stdio_client + stamps),
      mcp ClientSession, the R2-10 compiled output validators (COMP), jev-use run.Driver and the R2-10
      RecDriver labels; spawned the same way (asyncio subprocess pipes).
  F0  a minimal synchronous client: os.write of the request line, os.read until the newline, json.loads.
      This is the pipe + framing + JSON-parse floor with no MCP client library.
  neg the negative control: 10 malformed response frames (pre-registered list) through every
      caller-side parser variant; each must be rejected (the call raises, no CallToolResult returned).

Every request line the server receives is compared with the recorded request (byte-identical check).
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import os
import struct
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "r2-10")]

import b05_browser as bb  # noqa: E402  (installs the instrumented client; imports R2-10 harness)
import b05_stdio as bs  # noqa: E402

r, rc = bb.r, bb.rc


def now() -> int:
    return time.monotonic_ns()


def load_frames(path: Path) -> list[tuple[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [(d["k"], d["line"]) for d in (json.loads(x) for x in f if x.strip())]


def pair_frames(frames: list[tuple[str, str]]) -> list[tuple[str, str | None]]:
    """Requests in send order, each with its response line (None for a notification)."""
    resp_by_id: dict[Any, str] = {}
    for kind, line in frames:
        if kind == "resp":
            try:
                mid = json.loads(line).get("id")
            except Exception:  # noqa: BLE001
                continue
            resp_by_id.setdefault(json.dumps(mid), line)
    pairs = []
    for kind, line in frames:
        if kind != "req":
            continue
        obj = json.loads(line)
        if "id" in obj:
            pairs.append((line, resp_by_id.get(json.dumps(obj["id"]))))
        else:
            pairs.append((line, None))
    return pairs


def write_bin(pairs: list[tuple[str, str | None]], path: Path) -> None:
    with path.open("wb") as f:
        for req, resp in pairs:
            rb_ = req.encode()
            f.write(struct.pack("<I", len(rb_)) + rb_)
            if resp is None:
                f.write(struct.pack("<I", 0xFFFFFFFF))
            else:
                sb = resp.encode()
                f.write(struct.pack("<I", len(sb)) + sb)


def read_stamps(path: Path) -> list[dict[str, Any]]:
    out = []
    if path.exists():
        for line in path.read_text().splitlines():
            i, tr, tw, m, n = line.split()
            out.append({"idx": int(i), "t_read": int(tr), "t_written": int(tw), "match": m == "1", "len": int(n)})
    return out


async def run_f1(pairs: list[tuple[str, str | None]], floor_bin: str, work: Path, tag: str) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters

    binp, stp = work / f"{tag}.bin", work / f"{tag}.stamps"
    write_bin(pairs, binp)
    rec = rc.Recorder()
    bs.STAMP["rec_fn"] = None
    bs.STAMP["rec"] = rec
    rc.CLIENT["rec"] = rec
    calls = [json.loads(q)["params"] for q, _ in pairs if json.loads(q).get("method") == "tools/call"]
    errors: list[str] = []
    params = StdioServerParameters(command=floor_bin, args=[str(binp), str(stp)], env={})
    try:
        async with bs.stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.list_tools()
                rc.compile_output_validators(session)  # COMP: compiled at tools/list, outside T
                label = (calls[0].get("arguments") or {}).get("session") if calls else "x"
                drv = r.RecDriver(rc.Driver(session, label), rec, "", None)
                for p in calls:
                    args = {k: v for k, v in (p.get("arguments") or {}).items() if k != "session"}
                    try:
                        await drv.call(p["name"], args)
                    except Exception as error:  # noqa: BLE001  (a recorded refusal replays as a refusal)
                        errors.append(f"{p['name']}:{type(error).__name__}")
    finally:
        bs.STAMP["rec"] = None
        rc.CLIENT["rec"] = None
        rc.CLIENT["compiled"] = None
        bs.STAMP["rec_fn"] = lambda: rc.CLIENT["rec"]
    stamps = read_stamps(stp)
    return {"events": rec.events, "server": stamps, "errors": errors,
            "requests": len(pairs), "matched": sum(1 for s in stamps if s["match"]),
            "received": len(stamps)}


def run_f0(pairs: list[tuple[str, str | None]], floor_bin: str, work: Path, tag: str) -> dict[str, Any]:
    binp, stp = work / f"{tag}.bin", work / f"{tag}.stamps"
    write_bin(pairs, binp)
    proc = subprocess.Popen([floor_bin, str(binp), str(stp)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            bufsize=0, env={})
    fin, fout = proc.stdin.fileno(), proc.stdout.fileno()
    rows = []
    buf = b""
    for i, (req, resp) in enumerate(pairs):
        obj_req = json.loads(req)
        t_s0 = now()
        json.dumps(obj_req, separators=(",", ":"))  # request serialize floor (stdlib, timed only)
        t_s1 = now()
        data = (req + "\n").encode()
        t0 = now()
        os.write(fin, data)
        t_w = now()
        if resp is None:
            rows.append({"idx": i, "t_send": t0, "t_written": t_w, "ser_ns": t_s1 - t_s0, "notification": True})
            continue
        t_first = None
        while b"\n" not in buf:
            chunk = os.read(fout, 65536)
            if t_first is None:
                t_first = now()
            if not chunk:
                break
            buf += chunk
        t_complete = now()
        line, _, buf = buf.partition(b"\n")
        obj = json.loads(line)
        t_parsed = now()
        rows.append({"idx": i, "t_send": t0, "t_written": t_w, "t_first": t_first, "t_complete": t_complete,
                     "t_parsed": t_parsed, "ser_ns": t_s1 - t_s0, "resp_len": len(line), "id": obj.get("id"),
                     "method": json.loads(req).get("method"),
                     "tool": (json.loads(req).get("params") or {}).get("name")})
    proc.stdin.close()
    proc.wait(timeout=10)
    stamps = read_stamps(stp)
    return {"rows": rows, "server": stamps, "requests": len(pairs),
            "matched": sum(1 for s in stamps if s["match"]), "received": len(stamps)}


MALFORMED = [
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


async def run_neg(pairs: list[tuple[str, str | None]], floor_bin: str, work: Path, parser: str) -> list[dict[str, Any]]:
    """Recorded initialize + tools/list replies, then one malformed reply per tools/call (ids 2..11)."""
    from mcp import ClientSession, StdioServerParameters

    init = [(q, s) for q, s in pairs if json.loads(q).get("method") in ("initialize", "notifications/initialized",
                                                                      "tools/list")][:3]
    rows = []
    neg_pairs = list(init)
    for k, (name, tmpl) in enumerate(MALFORMED):
        rid = 2 + k
        req = json.dumps({"method": "tools/call", "params": {"name": "get_config", "arguments": {}},
                          "jsonrpc": "2.0", "id": rid}, separators=(",", ":"))
        neg_pairs.append((req, tmpl.format(id=rid)))
    tag = f"neg-{parser}"
    binp, stp = work / f"{tag}.bin", work / f"{tag}.stamps"
    write_bin(neg_pairs, binp)
    rec = rc.Recorder()
    bs.STAMP["rec_fn"] = None
    bs.STAMP["rec"] = rec
    bs.STAMP["parser"] = parser
    params = StdioServerParameters(command=floor_bin, args=[str(binp), str(stp)], env={})
    try:
        async with bs.stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.list_tools()
                for name, _tmpl in MALFORMED:
                    n_fail = sum(1 for e in rec.events if e["event"] == "c.parse_failed")
                    try:
                        result = await session.call_tool("get_config", {},
                                                         read_timeout_seconds=timedelta(seconds=0.5))
                        rows.append({"frame": name, "parser": parser, "rejected": False,
                                     "result_type": type(result).__name__})
                    except Exception as error:  # noqa: BLE001
                        parse_failed = sum(1 for e in rec.events if e["event"] == "c.parse_failed") > n_fail
                        rows.append({"frame": name, "parser": parser, "rejected": True,
                                     "error": type(error).__name__, "parse_failed": parse_failed})
    finally:
        bs.STAMP["rec"] = None
        bs.STAMP["parser"] = "default"
        bs.STAMP["rec_fn"] = lambda: rc.CLIENT["rec"]
    return rows


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(os.environ.get("TMPDIR", "/nonexistent")) / "b05-floor"
    work.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(args.frames_dir).glob(args.glob))
    if args.limit:
        files = files[: args.limit]
    manifest = {"variant": args.variant, "files": [f.name for f in files], "started_utc": r.utc(),
                "loadavg_start": r.loadavg(), "reps": args.reps}
    if args.variant == "neg":
        import b05_variants  # noqa: F401  (registers the candidate parsers)

        pairs = pair_frames(load_frames(files[0]))
        rows = []
        for parser in args.parsers.split(","):
            rows += await run_neg(pairs, args.floor_bin, work, parser)
        (out / "neg-control.json").write_text(json.dumps({"source_trial": files[0].name, "rows": rows}, indent=1))
        print(json.dumps({"neg_rows": len(rows), "rejected": sum(1 for x in rows if x["rejected"])}), flush=True)
    else:
        with gzip.open(out / f"floor-{args.variant}-{args.prefix}.jsonl.gz", "wt", encoding="utf-8") as f:
            for rep in range(args.reps):
                for path in files:
                    pairs = pair_frames(load_frames(path))
                    trial = path.name.replace(".frames.jsonl.gz", "")
                    la = r.loadavg()
                    if args.variant == "F1":
                        res = await run_f1(pairs, args.floor_bin, work, f"{trial}-F1")
                    else:
                        res = run_f0(pairs, args.floor_bin, work, f"{trial}-F0")
                    f.write(json.dumps({"trial": trial, "variant": args.variant, "rep": rep, "loadavg": la, **res},
                                       default=str) + "\n")
                    print(json.dumps({"trial": trial, "variant": args.variant, "rep": rep,
                                      "matched": res["matched"], "requests": res["requests"],
                                      "errors": res.get("errors")}), flush=True)
    manifest.update({"ended_utc": r.utc(), "loadavg_end": r.loadavg()})
    (out / f"floor-manifest-{args.variant}-{args.prefix}.json").write_text(json.dumps(manifest, indent=1))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--floor-bin", required=True)
    p.add_argument("--frames-dir", required=True)
    p.add_argument("--glob", default="*.frames.jsonl.gz")
    p.add_argument("--out", required=True)
    p.add_argument("--variant", required=True, choices=("F1", "F0", "neg"))
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--prefix", default="x")
    p.add_argument("--parsers", default="default")
    args = p.parse_args()
    if os.environ.get("R2_10_OUTER_HOSTLESS") != "1":
        raise SystemExit("refusing: run through hostless (in_session.sh)")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
