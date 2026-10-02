"""B-02 non-browser blocks: admission-span A/B (H_V, per tools/call) and N-V envelopes.

Run inside the isolated X11 session with the jev-use virtualenv:

    JEV_USE_DIR=<jev-use> <venv>/python run_b02_admission.py --driver <bin> --out <dir> \
        --plan {vmicro|nv} [--rounds 20] [--lock <quiet-lane.lock>]

vmicro: run under ``quiet-timed`` (EXCLUSIVE lock held by the caller before any Driver
starts). 20 rounds x AB/BA pair of arms K5 (knobs unset) and K5V
(CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1). One trial = one fresh ``cua-driver mcp`` with
the phase trace on, a raw stdio JSON-RPC client, legacy initialize, tools/list, then
25 legacy-era and 25 modern-era ``tools/call get_config`` requests, one at a time. The
admission span of each call comes from the Driver's CLOCK_MONOTONIC marks
(mcp.line_read -> mcp.inner_validated); the client round trip is stamped too.

nv: invalid-call envelopes (wrong argument type, missing required argument, unknown
tool, arguments not an object; legacy and modern era), 5 trials per arm, the quiet
lock held SHARED for at most 10 trials per acquisition. Envelopes are kept byte-exact.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_b02 as b02  # noqa: E402  (arm knobs, env patching, nv_one)
import run_critpath as rc  # noqa: E402

CALLS_PER_ERA = 25


async def vmicro_one(spec: dict[str, Any], args: argparse.Namespace, out: Path) -> dict[str, Any]:
    name = spec["name"]
    trace_rel = f"trials/{name}.driver-trace.jsonl"
    env = rc.driver_environment()
    env.pop(rc.TRACE_ENV, None)
    env[rc.TRACE_ENV] = str(out / trace_rel)
    record: dict[str, Any] = {"trial": name, "arm": spec["arm"], "kind": "vmicro", "round": spec["round"],
                              "block": spec["block"], "lock_mode": spec["lock_mode"], "loadavg_before": rc.loadavg(),
                              "driver_trace": trace_rel,
                              "driver_env_knobs": {k: env[k] for k in b02.KNOB_ENVS if k in env}}
    proc = await asyncio.create_subprocess_exec(args.driver, "mcp", env=env, stdin=asyncio.subprocess.PIPE,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=64 * 1024 * 1024)
    calls: list[dict[str, Any]] = []

    async def rpc(msg: dict[str, Any], expect_reply: bool = True) -> tuple[int, int, str | None]:
        t0 = rc.now()
        proc.stdin.write((json.dumps(msg, separators=(",", ":")) + "\n").encode())
        await proc.stdin.drain()
        if not expect_reply:
            return t0, rc.now(), None
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=20)
        return t0, rc.now(), line.decode().rstrip("\n")

    try:
        await rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "b02-vmicro", "version": "0"}}})
        await rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_reply=False)
        await rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        rid = 10
        for era in ("legacy", "modern"):
            for _ in range(CALLS_PER_ERA):
                rid += 1
                params: dict[str, Any] = {"name": "get_config", "arguments": {}}
                if era == "modern":
                    params["_meta"] = b02.MODERN_META
                t0, t1, reply = await rpc({"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": params})
                ok = reply is not None and '"error"' not in reply.split('"result"')[0] and '"isError":true' not in reply
                calls.append({"era": era, "id": rid, "send_ns": t0, "recv_ns": t1, "ok": ok,
                              "reply_bytes": len(reply or "")})
    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=20)
        except asyncio.TimeoutError:
            proc.kill()
    record["calls"] = calls
    record["loadavg_after"] = rc.loadavg()
    with (out / f"trials/{name}.jsonl").open("w") as f:
        f.write(json.dumps({"event": "summary", **record}, sort_keys=True) + "\n")
    print(json.dumps({"trial": name, "ok_calls": sum(c["ok"] for c in calls)}), flush=True)
    return record


def build_plan(kind: str, rounds: int) -> list[list[dict[str, Any]]]:
    if kind == "vmicro":
        trials = []
        for r in range(rounds):
            for arm in (("K5", "K5V") if r % 2 == 0 else ("K5V", "K5")):
                trials.append({"arm": arm, "kind": "vmicro", "round": r, "block": "v",
                               "lock_mode": "exclusive_external", "cls": "none"})
        return [trials]
    if kind == "nv":
        trials = []
        for k in range(5):
            for arm in (("K5", "K5V") if k % 2 == 0 else ("K5V", "K5")):
                trials.append({"arm": arm, "kind": "nv", "round": k, "cls": "none"})
        blocks = []
        for i in range(0, len(trials), 10):
            chunk = trials[i:i + 10]
            for t in chunk:
                t.update({"block": f"n{i // 10}", "lock_mode": "shared"})
            blocks.append(chunk)
        return blocks
    raise ValueError(kind)


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    blocks = build_plan(args.plan, args.rounds)
    idx = 0
    for block in blocks:
        for spec in block:
            spec["name"] = f"{spec['block']}{idx:03d}-{spec['arm']}-{spec['kind']}"
            idx += 1
    manifest: dict[str, Any] = {"plan_kind": args.plan, "arm_knobs": {a: b02.ARM_KNOBS[a] for a in ("K5", "K5V")},
                                "blocks": [[s["name"] for s in b] for b in blocks], "started_utc": b02.utc(),
                                "started_mono_ns": rc.now(), "loadavg_start": rc.loadavg(), "locks": [],
                                "display": os.environ.get("DISPLAY"), "calls_per_era": CALLS_PER_ERA}
    try:
        for block in blocks:
            fd = None
            if block[0]["lock_mode"] == "shared":
                if not args.lock:
                    raise SystemExit("refusing: this plan needs --lock")
                fd = os.open(args.lock, os.O_RDONLY | os.O_CREAT, 0o644)
                u_req = b02.utc()
                fcntl.flock(fd, fcntl.LOCK_SH)
                lock_rec = {"mode": "shared", "requested_utc": u_req, "acquired_utc": b02.utc(),
                            "first": block[0]["name"], "last": block[-1]["name"], "trials": len(block)}
            try:
                for spec in block:
                    b02.CURRENT["knobs"] = dict(b02.ARM_KNOBS[spec["arm"]])
                    if spec["kind"] == "vmicro":
                        await vmicro_one(spec, args, out)
                    else:
                        await b02.nv_one(spec, args, out)
                    b02.CURRENT["knobs"] = {}
            finally:
                if fd is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                    lock_rec["released_utc"] = b02.utc()
                    manifest["locks"].append(lock_rec)
                    with (out / "lock-receipts.jsonl").open("a") as f:
                        f.write(json.dumps(lock_rec, sort_keys=True) + "\n")
    finally:
        manifest["ended_utc"] = b02.utc()
        manifest["ended_mono_ns"] = rc.now()
        manifest["loadavg_end"] = rc.loadavg()
        manifest["network"] = dict(rc.NETWORK)
        (out / f"run-manifest-{args.plan}.json").write_text(json.dumps(manifest, indent=1))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", choices=("vmicro", "nv"), required=True)
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--lock")
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: no DISPLAY (run inside cua-x11-session.sh)")
    for name in (rc.TRACE_ENV, *b02.KNOB_ENVS):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
