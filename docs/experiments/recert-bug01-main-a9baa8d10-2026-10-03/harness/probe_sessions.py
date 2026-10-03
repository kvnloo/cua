"""BUG-01 part B: CDP session accumulation over one long Driver session (REAL/BENCHMARK).

Runs INSIDE the isolated X11 session with the jev-use venv (see run_in_session.sh),
under the EXCLUSIVE quiet-lane lock held by the caller. The Driver binary must
carry the env-gated counters (CUA_DRIVER_EXP_CDP_COUNTER_FILE); this probe sets
that variable per Driver process to a file in the output dir.

Series order L C C L L C (L = one Driver/browser for 300 calls; C = 30 fresh
Driver/browser blocks of 10 calls). Call k: even -> get_browser_state
semantic_v2, odd -> browser_click {No-op ref, input_route: dom_event}.

usage: probe_sessions.py --out <dir> [--series LCCLLC] [--long-calls 300]
                         [--blocks 30] [--block-calls 10] [--label measured]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from bug01_common import (
    Probe,
    ProbeServer,
    driver_environment,
    driver_version,
    find_ref,
    require_isolated_session,
    sanitize,
    sh,
    sha256_file,
    wait_for_window,
)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

COUNTER_ENV = "CUA_DRIVER_EXP_CDP_COUNTER_FILE"
NOOP_NAME = "No-op"


# ------------------------------------------------------------ /proc readers
def _ppid_map() -> dict[int, int]:
    out: dict[int, int] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as fh:
                stat = fh.read()
            ppid = int(stat[stat.rindex(")") + 2 :].split()[1])
            out[int(entry)] = ppid
        except (OSError, ValueError, IndexError):
            continue
    return out


def _status_kb(pid: int, key: str) -> int | None:
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith(key + ":"):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


def _pss_kb(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/smaps_rollup") as fh:
            for line in fh:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


def _cmd_type(pid: int) -> str:
    # Chrome rewrites child argv into one space-separated string, so search the whole cmdline.
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            raw = fh.read().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return "gone"
    m = re.search(r"--type=(\S+)", raw)
    return m.group(1) if m else ("browser" if raw.strip() else "?")


def chrome_tree_memory(root_pid: int) -> dict[str, Any]:
    """Read-only memory sample over the process tree rooted at this lane's browser pid."""
    ppid = _ppid_map()
    children: dict[int, list[int]] = {}
    for pid, parent in ppid.items():
        children.setdefault(parent, []).append(pid)
    tree, stack = [], [root_pid]
    while stack:
        pid = stack.pop()
        if pid in ppid or pid == root_pid:
            tree.append(pid)
            stack.extend(children.get(pid, []))
    procs = []
    for pid in tree:
        rss = _status_kb(pid, "VmRSS")
        if rss is None:
            continue
        procs.append({"type": _cmd_type(pid), "rss_kb": rss, "pss_kb": _pss_kb(pid)})
    renderers = [p for p in procs if p["type"] == "renderer"]
    return {
        "n_procs": len(procs),
        "rss_kb_total": sum(p["rss_kb"] for p in procs),
        "pss_kb_total": sum(p["pss_kb"] or 0 for p in procs),
        "renderer_rss_kb": sum(p["rss_kb"] for p in renderers),
        "renderer_pss_kb": sum(p["pss_kb"] or 0 for p in renderers),
        "n_renderers": len(renderers),
        "by_type": sorted({p["type"] for p in procs}),
    }


# ------------------------------------------------------------------ calls
def call_row(series: str, block: int, k: int | None, s: int | None, kind: str, r: dict[str, Any]) -> dict[str, Any]:
    st = r.get("structured") or {}
    return {
        "event": "call",
        "series": series,
        "block": block,
        "k": k,
        "s": s,
        "kind": kind,
        "tool": r["tool"],
        "t_start_ms": r["t_start_ms"],
        "t_end_ms": r["t_end_ms"],
        "elapsed_ms": r["elapsed_ms"],
        "accepted": r.get("accepted"),
        "is_error": r.get("is_error"),
        "refusal": r.get("refusal"),
        "transport_error": r.get("transport_error"),
        "loadavg1": os.getloadavg()[0],
        "route": st.get("route"),
        "effect": st.get("effect"),
        "status": st.get("status"),
        "ref_count": len(st.get("refs") or []) if isinstance(st.get("refs"), list) else None,
    }


class Runner:
    def __init__(self, out: Path, url: str, args: argparse.Namespace) -> None:
        self.out = out
        self.url = url
        self.args = args
        self.rows = (out / "calls.jsonl").open("a")

    def emit(self, row: dict[str, Any]) -> None:
        self.rows.write(json.dumps(sanitize(row), sort_keys=True) + "\n")
        self.rows.flush()

    async def driver_session(self, series: str, block: int, n_calls: int, s_offset: int, nav_probe_at: set[int], rss_every: int | None) -> None:
        counter_file = self.out / f"counters-{series}-b{block:02d}.jsonl"
        env = driver_environment()
        env[COUNTER_ENV] = str(counter_file)
        params = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=env)
        label = f"bug01b-{uuid.uuid4().hex[:8]}"
        meta: dict[str, Any] = {"event": "block", "series": series, "block": block, "label": label, "counter_file": counter_file.name, "t_start_ms": time.time() * 1000, "loadavg": os.getloadavg()}
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                meta["server_info"] = {"name": init.serverInfo.name, "version": init.serverInfo.version}
                probe = Probe(session, label)
                cur = await probe.call("set_agent_cursor_enabled", {"enabled": False})
                self.emit(call_row(series, block, None, None, "setup", cur))
                prep = await probe.call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
                self.emit(call_row(series, block, None, None, "setup", prep))
                pid = int((prep.get("structured") or {})["prepared_pid"])
                window = await wait_for_window(probe, pid)
                bound = await probe.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
                self.emit(call_row(series, block, None, None, "setup", bound))
                b = bound.get("structured") or {}
                tabs = b.get("tabs") or []
                tab = next((t for t in tabs if t.get("active")), tabs[0])
                target, tab_id = b["target_id"], str(tab["tab_id"])
                setup_nav = await probe.call("browser_navigate", {"target_id": target, "tab_id": tab_id, "url": self.url})
                self.emit(call_row(series, block, None, None, "nav_probe_setup", setup_nav))
                await asyncio.sleep(0.5)

                def rss(at_k: int) -> None:
                    self.emit({"event": "rss", "series": series, "block": block, "k": at_k, "t_ms": time.time() * 1000, "loadavg1": os.getloadavg()[0], **chrome_tree_memory(pid)})

                noop_ref: str | None = None
                rss(0)
                for k in range(n_calls):
                    if k in nav_probe_at:
                        nav = await probe.call("browser_navigate", {"target_id": target, "tab_id": tab_id, "url": self.url})
                        self.emit(call_row(series, block, k, None, "nav_probe", nav))
                        await asyncio.sleep(0.5)
                    if k % 2 == 0:
                        r = await probe.call("get_browser_state", {"target_id": target, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
                        found = find_ref(r.get("structured") or {}, "button", NOOP_NAME)
                        if found:
                            noop_ref = found
                        row = call_row(series, block, k, s_offset + k, "snapshot", r)
                        row["noop_ref_found"] = found is not None
                    else:
                        r = await probe.call("browser_click", {"target_id": target, "tab_id": tab_id, "ref": noop_ref, "input_route": "dom_event"})
                        row = call_row(series, block, k, s_offset + k, "click", r)
                    self.emit(row)
                    if rss_every and (k + 1) % rss_every == 0:
                        rss(k + 1)
                if n_calls in nav_probe_at:
                    nav = await probe.call("browser_navigate", {"target_id": target, "tab_id": tab_id, "url": self.url})
                    self.emit(call_row(series, block, n_calls, None, "nav_probe", nav))
                    await asyncio.sleep(0.5)
                if not rss_every or n_calls % rss_every:
                    rss(n_calls)
        meta["t_end_ms"] = time.time() * 1000
        self.emit(meta)

    async def long_series(self, series: str) -> None:
        n = self.args.long_calls
        await self.driver_session(series, 0, n, 0, {0, 100, 200, n} if n >= 300 else {0, n}, 25)

    async def control_series(self, series: str) -> None:
        for block in range(self.args.blocks):
            await self.driver_session(series, block, self.args.block_calls, block * self.args.block_calls, set(), None)


async def amain(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    binary = os.environ["CUA_DRIVER_BIN"]
    env = {"label": args.label, "driver_sha256": sha256_file(binary), "driver_version_in_session": driver_version(binary), "chrome_version_in_session": sh(["/opt/google/chrome/chrome", "--version"], timeout=20), "display": os.environ.get("DISPLAY"), "series": args.series, "long_calls": args.long_calls, "blocks": args.blocks, "block_calls": args.block_calls, "t_start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "loadavg_start": os.getloadavg(), "counter_env_in_probe_env": bool(os.environ.get(COUNTER_ENV))}
    with ProbeServer(("127.0.0.1", 0), instrumented=False, noop_button=True) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}/"
        runner = Runner(out, url, args)
        counts = {"L": 0, "C": 0}
        try:
            for arm in args.series:
                counts[arm] += 1
                name = f"{arm}{counts[arm]}"
                t0 = time.time()
                try:
                    if arm == "L":
                        await runner.long_series(name)
                    else:
                        await runner.control_series(name)
                except Exception as exc:  # keep failures in the record
                    runner.emit({"event": "series_harness_error", "series": name, "error": f"{type(exc).__name__}: {exc}"})
                print(json.dumps({"series": name, "seconds": round(time.time() - t0, 1)}), flush=True)
        finally:
            server.shutdown()
    env["t_end_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    env["loadavg_end"] = os.getloadavg()
    (out / "session-env.json").write_text(json.dumps(sanitize(env), indent=1, sort_keys=True) + "\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--series", default="LCCLLC")
    p.add_argument("--long-calls", type=int, default=300)
    p.add_argument("--blocks", type=int, default=30)
    p.add_argument("--block-calls", type=int, default=10)
    p.add_argument("--label", default="measured")
    args = p.parse_args()
    require_isolated_session()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
