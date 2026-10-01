#!/usr/bin/env python3
"""R2-02 harness: the same DOM-route Submit click, poll vs CDP-wake completion.

Run only inside cua-x11-session.sh (private Xvfb + dbus) and under the
quiet-lane lock. Reuses the jev-use Driver client, fixture server, candidate
builder and oracle; adds no service. Writes one JSONL receipt per trial.

  run_r2_02.py --driver <bin> --out <dir> [--pairs 24] [--controls 6] [--default-off 3]
               [--groups C3_early,C3u_early_unguarded]   # extension: only these control groups
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import threading
import time
import traceback
import uuid
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
JEV = HERE.parents[2] / "libs" / "cua-driver" / "examples" / "jev-use"
sys.path[:0] = [str(JEV / "python"), str(JEV)]

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

import fixture_server as fs  # noqa: E402
from driver_env import driver_environment  # noqa: E402
from run import Driver, select_tab_id, wait_for_window  # noqa: E402
from tasks import FixtureFormTask, fixture_sources  # noqa: E402

ENV_GATE = "CUA_DRIVER_EXP_R2_02_CDP_WAKE"
LOG_ENV = "CUA_DRIVER_EXP_R2_02_CDP_WAKE_LOG"
ARG = "exp_r2_02_cdp_wake"
DEADLINE_MS = 1000
POLL_READS = 20
POLL_SLEEP_S = 0.1
TERMINAL = {"verified", "refuted"}

BUTTON = b'<button type="submit">Submit</button>'
assert BUTTON in fs.PAGE
SPURIOUS = fs.PAGE.replace(
    BUTTON,
    b'<button type="button" onclick="sessionStorage.setItem(\'r2v\','
    b"this.form.elements['value'].value);location.href='/v/interstitial'\">Submit</button>",
)
INTERSTITIAL = (
    b"<!doctype html><title>interstitial</title><form method=post action=/submit>"
    b"<input type=hidden name=value></form><script>"
    b"document.forms[0].elements.value.value=sessionStorage.getItem('r2v');"
    b"setTimeout(()=>document.forms[0].submit(),300)</script>"
)
UNRELATED = fs.PAGE.replace(
    b'action="/submit"', b'action="/submit?delay_ms=150"'
).replace(
    b"</main>",
    b'<iframe src="/v/frame" title="side" style="width:120px;height:40px"></iframe>'
    b"<script>let n=0,t=null;document.querySelector('input').addEventListener('input',()=>{"
    b"if(!t)t=setInterval(()=>{document.querySelector('iframe').src='/v/frame?n='+(++n)},25)})"
    b"</script></main>",
)
FRAME = b"<!doctype html><title>frame</title><p>frame</p>"
INERT = fs.PAGE.replace(BUTTON, b'<button type="button">Submit</button>')
REFUTED = fs.PAGE.replace(
    b'<form method="post" action="/submit">',
    b'<form method="post" action="/submit" onsubmit="this.elements[\'value\'].value='
    b"'refuted-'+this.elements['value'].value\">",
)
assert b"delay_ms=150" in UNRELATED
for page in (SPURIOUS, UNRELATED, INERT, REFUTED):
    assert page != fs.PAGE
VARIANTS = {
    "spurious": SPURIOUS,
    "interstitial": INTERSTITIAL,
    "unrelated": UNRELATED,
    "frame": FRAME,
    "inert": INERT,
    "refuted": REFUTED,
}

# group -> (arm, variant, control); see PREREG.json "controls".
CONTROL_GROUPS = {
    "C1_lost": ("event", "normal", "suppress"),
    "C2_spurious": ("event", "spurious", "none"),
    "C3_early": ("event", "normal", "inject_early"),
    "C3u_early_unguarded": ("event", "normal", "inject_early_unguarded"),
    "C4_unrelated": ("event", "unrelated", "none"),
    "C5_stale": ("event", "normal", "inject_stale"),
    "C5u_stale_unguarded": ("event", "normal", "inject_stale_unguarded"),
    "C6_timeout_event": ("event", "inert", "none"),
    "C6p_timeout_poll": ("poll", "inert", None),
    "C7_refuted": ("event", "refuted", "none"),
}


class ExpHandler(fs.FixtureHandler):
    """The unchanged fixture handler plus control pages and a receipt journal."""

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path.startswith("/v/"):
            body = VARIANTS.get(path[3:])
            if body is None:
                self.send_error(404)
                return
            self._send(200, "text/html; charset=utf-8", body)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        # The unrelated-event control delays the commit target-side so child-frame
        # events have a post-dispatch window; /state semantics stay unchanged.
        if self.path == "/submit?delay_ms=150":
            time.sleep(0.15)
            self.path = "/submit"
        if self.path == "/submit":
            self.server.journal.append(time.monotonic_ns())  # immediately before the state commit
        super().do_POST()


class ExpServer(fs.FixtureServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0))
        self.RequestHandlerClass = ExpHandler
        self.journal: list[int] = []


def probe_record(log: pathlib.Path, nonce: int) -> dict[str, Any] | None:
    """The Driver's env-gated probe record for this call, matched by nonce."""
    if not log.exists():
        return None
    hits = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    hits = [h for h in hits if h.get("nonce") == nonce]
    assert len(hits) <= 1, f"duplicate probe records for nonce {nonce}"
    return hits[0] if hits else None


def loadavg() -> list[float]:
    return [float(x) for x in pathlib.Path("/proc/loadavg").read_text().split()[:3]]


def ms(ns: int) -> float:
    return round(ns / 1e6, 3)


class Lane:
    def __init__(self, driver: Driver, server: ExpServer, base_url: str, target_id: str, tab_id: str,
                 probe_log: pathlib.Path):
        self.probe_log = probe_log
        self.driver = driver
        self.server = server
        self.base_url = base_url
        self.target_id = target_id
        self.tab_id = tab_id

    def tab(self) -> dict[str, str]:
        return {"target_id": self.target_id, "tab_id": self.tab_id}

    async def snapshot(self) -> dict[str, Any]:
        return await self.driver.call("get_browser_state", {**self.tab(), "snapshot_format": "semantic_v2"})

    async def trial(self, seq: int, kind: str, group: str, arm: str, variant: str, control: str | None,
                    probe_expected: bool) -> dict[str, Any]:
        token = f"r2-{uuid.uuid4().hex[:10]}"
        task = FixtureFormTask(token, self.base_url)
        rec: dict[str, Any] = {
            "schema": "cua.r2_02.trial.v1", "seq": seq, "kind": kind, "group": group, "arm": arm,
            "variant": variant, "control": control, "probe_env": probe_expected,
            "loadavg_before": loadavg(), "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            self.server.state.reset()
            self.server.journal.clear()
            url = self.base_url if variant == "normal" else f"{self.base_url}v/{variant}"
            await self.driver.call("browser_navigate", {**self.tab(), "url": url})
            snap = await self.snapshot()
            cands = {c.id: c for c in task.candidates(fixture_sources(snap))}
            typer = cands["type-verification-value"]
            await self.driver.call(typer.tool, typer.arguments)
            snap = await self.snapshot()
            cands = {c.id: c for c in task.candidates(fixture_sources(snap))}
            submit = cands["submit-form"]
            pre = task.classify(task.read_oracle(), steps=1)
            rec["pre_dispatch_oracle"] = pre
            args = dict(submit.arguments)
            rec["route_requested"] = args.get("input_route")
            if arm == "event":
                args[ARG] = {"deadline_ms": DEADLINE_MS, "control": control, "nonce": seq}

            reads: list[dict[str, Any]] = []

            def read(label: str) -> str:
                r0 = time.monotonic_ns()
                state = task.read_oracle()
                r1 = time.monotonic_ns()
                outcome = task.classify(state, steps=1)
                reads.append({"label": label, "t0_ns": r0, "t1_ns": r1, "outcome": outcome})
                return outcome

            t0 = time.monotonic_ns()
            result = await self.driver.call("browser_click", args)
            t1 = time.monotonic_ns()
            outcome = None
            first_after_call = None
            sleeps = 0
            if arm == "event":
                first_after_call = read("wake_reread")
                if first_after_call in TERMINAL:
                    outcome = first_after_call
            if outcome is None:
                for i in range(POLL_READS):
                    o = read(f"poll{i}")
                    if first_after_call is None:
                        first_after_call = o
                    if o in TERMINAL:
                        outcome = o
                        break
                    await asyncio.sleep(POLL_SLEEP_S)
                    sleeps += 1
            if outcome is None:
                o = read("final")
                outcome = o if o in TERMINAL else "timeout"
            t_done = reads[-1]["t1_ns"]
            journal = list(self.server.journal)
            rec.update({
                "outcome": outcome,
                "first_read_after_call": first_after_call,
                "oracle_reads_after_call": len(reads),
                "fixed_sleeps": sleeps,
                "tool_ms": ms(t1 - t0),
                "click_to_outcome_ms": ms(t_done - t0),
                "post_return_ms": ms(t_done - t1),
                "click_to_verified_ms": ms(t_done - t0) if outcome == "verified" else None,
                "submit_posts": len(journal),
                "effect_to_outcome_ms": ms(t_done - journal[0]) if journal else None,
                "click_to_effect_ms": ms(journal[0] - t0) if journal else None,
                "effect_before_tool_return": (journal[0] <= t1) if journal else None,
                "reads": [{"label": r["label"], "at_ms": ms(r["t1_ns"] - t0), "rtt_ms": ms(r["t1_ns"] - r["t0_ns"]),
                           "outcome": r["outcome"]} for r in reads],
                "driver_result": {
                    "status": result.get("status"), "effect": result.get("effect"), "route": result.get("route"),
                },
                "probe": probe_record(self.probe_log, seq),
                "probe_in_public_result": ARG in result,
            })
        except Exception as error:  # every failure stays in the denominator
            rec.update({"outcome": "error", "error_type": type(error).__name__,
                        "error": str(error)[:400], "trace_tail": traceback.format_exc()[-600:]})
        rec["loadavg_after"] = loadavg()
        return rec


async def session(driver_bin: str, env_on: bool, server: ExpServer, base_url: str, plan: list[tuple], out: pathlib.Path,
                  receipts: list[dict[str, Any]], seq0: int) -> int:
    env = driver_environment()
    env.pop(ENV_GATE, None)
    if env_on:
        env[ENV_GATE] = "1"
    # Set in both sessions: the default-off session must write nothing here.
    probe_log = out / ("driver-probe.jsonl" if env_on else "driver-probe-default-off.jsonl")
    env[LOG_ENV] = str(probe_log)
    params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
    seq = seq0
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as cs:
            await cs.initialize()
            driver = Driver(cs, f"r2-02-{uuid.uuid4().hex[:8]}")
            prepared = await driver.call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int(prepared["prepared_pid"])
            window = await wait_for_window(driver, pid)
            bound = await driver.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
            lane = Lane(driver, server, base_url, bound["target_id"], select_tab_id(bound["tabs"]), probe_log)
            for kind, group, arm, variant, control in plan:
                rec = await lane.trial(seq, kind, group, arm, variant, control, env_on)
                path = out / f"{seq:03d}-{group}-{arm}.jsonl"
                path.write_text(json.dumps(rec, sort_keys=True) + "\n")
                receipts.append(rec)
                print(json.dumps({k: rec.get(k) for k in ("seq", "group", "arm", "outcome", "click_to_outcome_ms",
                                                          "first_read_after_call")}), flush=True)
                seq += 1
    return seq


def build_plan(pairs: int, controls: int, groups: list[str] | None = None) -> list[tuple]:
    plan: list[tuple] = [("warmup", "warmup", "poll", "normal", None), ("warmup", "warmup", "event", "normal", "none")]
    for i in range(pairs):
        order = ("poll", "event") if i % 2 == 0 else ("event", "poll")
        for arm in order:
            plan.append(("pair", f"pair{i:02d}", arm, "normal", None if arm == "poll" else "none"))
    for _ in range(controls):
        for group, (arm, variant, control) in CONTROL_GROUPS.items():
            if groups is not None and group not in groups:
                continue
            plan.append(("control", group, arm, variant, control))
    return plan


async def main_async(args: argparse.Namespace) -> int:
    if not os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or any(
        k.startswith("HYPRLAND_") for k in os.environ
    ):
        print("refusing: not inside the isolated X11 session", file=sys.stderr)
        return 97
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    server = ExpServer()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_port}/"
    receipts: list[dict[str, Any]] = []
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    groups = args.groups.split(",") if args.groups else None
    assert groups is None or set(groups) <= set(CONTROL_GROUPS), groups
    plan = build_plan(args.pairs, args.controls, groups)
    seq = await session(args.driver, True, server, base_url, plan, out, receipts, 0)
    off_plan = [("control", "C0_default_off", "event", "normal", "none")] * args.default_off
    if off_plan:
        await session(args.driver, False, server, base_url, off_plan, out, receipts, seq)
    server.shutdown()
    (out / "run-meta.json").write_text(json.dumps({
        "started_utc": started, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trials": len(receipts), "pairs": args.pairs, "controls_per_group": args.controls,
        "default_off": args.default_off, "groups": groups, "deadline_ms": DEADLINE_MS, "poll_reads": POLL_READS,
        "poll_sleep_s": POLL_SLEEP_S, "fixture_origin": "http://127.0.0.1:<ephemeral>/",
    }, indent=1, sort_keys=True) + "\n")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--pairs", type=int, default=24)
    p.add_argument("--controls", type=int, default=6)
    p.add_argument("--default-off", type=int, default=3)
    p.add_argument("--groups", default=None, help="comma-separated control groups (extension runs)")
    raise SystemExit(asyncio.run(main_async(p.parse_args())))


if __name__ == "__main__":
    main()
