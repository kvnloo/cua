#!/usr/bin/env python3
"""OWN-20G: focus-guard rows on the canonical GTK3 task fixture (measurement only).

Derived from the N-02 harness (same fixture, task window, observation, jev-use
``eligible_controls`` lookup, forced background element-token AT-SPI route, 2 ms
state-file oracle, fresh Driver + fresh fixture per trial, and N-02's X focus
sampler and decoy window from ``xprobe.py``, verbatim). Changes for OWN-20G
(pre-registered in PREREG.json):

* two Driver binaries per block, U and G, chosen per trial (AB/BA order in the
  plan), each checked against its sha256 before the block starts;
* the steal is triggered by a separate process (``stealer.py``) that tails the
  Driver phase trace and keys on the Driver-side ``atspi_action
  do_action_replied`` mark; the decoy window stays a pre-mapped harness window;
* kinds: ``stall`` (R1: XGrabServer ~2.0 s from ~100 ms, steal issued at ~217 ms),
  ``stallonly`` (R1 control: the same grab, no steal), ``steal`` (R2: one steal at
  a set delay after the mark), ``nosteal`` (R2 control: decoy mapped, sampler on,
  no steal), ``timing`` (no decoy, no sampler) and ``smoke`` (default-off);
* the focus reference is the sampler's value once GTK has settled: the first
  sample of the first 300 ms run without a change after the pre-trial placement.

Runs INSIDE cua-x11-session.sh with a private AT-SPI bus; refuses otherwise. No
provider: non-loopback connects are refused and counted.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness_common as hc  # noqa: E402
import xprobe  # noqa: E402

SLEEP_ENV = "CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS"
CLAMP_ENV = "CUA_DRIVER_EXP_FOCUS_GUARD_CLAMP"
ARMS: dict[str, dict[str, Any]] = {
    "S0": {"fast_cursor": False, "env": {SLEEP_ENV: "0"}},
    "S0+CL": {"fast_cursor": False, "env": {SLEEP_ENV: "0", CLAMP_ENV: "1"}},
    "X": {"fast_cursor": True, "env": {SLEEP_ENV: "0"}},
    "X+CL": {"fast_cursor": True, "env": {SLEEP_ENV: "0", CLAMP_ENV: "1"}},
    "D": {"fast_cursor": False, "env": {}},  # default-off smoke: no CUA_DRIVER_EXP_* at all
}
FAST_MOTION = {"glide_duration_ms": 1, "dwell_after_click_ms": 0}
CONFIRM_DEADLINE_S = 6.0
POST_HOLD_S = {"timing": 0.15, "smoke": 0.15, "steal": 0.7, "nosteal": 0.7, "stall": 0.7, "stallonly": 0.7,
               "replystall": 0.7, "replyonly": 0.7}
FOCUS_KINDS = ("steal", "nosteal", "stall", "stallonly", "replystall", "replyonly")
REPLY_KINDS = ("replystall", "replyonly")
REPLY = {"hold_after_ms": 80.0, "pause_ms": 2000.0, "steal_ms": 217.0}
SETTLE_QUIET_S = 0.3
SETTLE_CAP_S = 3.0
STALL = {"grab_at_ms": 100.0, "grab_ms": 2000.0, "steal_ms": 217.0}


def stacking_atom() -> int:
    conn = xprobe.Conn()
    try:
        return int(xprobe.X.XInternAtom(conn.dpy, b"_NET_CLIENT_LIST_STACKING", 0))
    finally:
        conn.close()


def free_display_number() -> int:
    """A display number M with no abstract @/tmp/.X11-unix/XM and no /tmp/.X11-unix/XM file."""
    own = "X" + os.environ["DISPLAY"].split(":")[1].split(".")[0]
    foreign = [e.name for e in Path("/tmp/.X11-unix").iterdir() if e.name != own and not e.name[1:].isdigit()
               or (e.name != own and int(e.name[1:]) < 600)]
    if foreign:  # the private tmpfs must hold only this session's display (and our own proxies)
        raise RuntimeError(f"refusing: /tmp/.X11-unix is not the session's private tmpfs ({foreign})")
    with open("/proc/net/unix", encoding="ascii", errors="replace") as stream:
        names = {line.split()[-1] for line in stream if line.strip().split()[-1].startswith("@/tmp/.X11-unix/X")}
    for n in range(600 + os.getpid() % 200, 1000):
        if f"@/tmp/.X11-unix/X{n}" not in names and not Path(f"/tmp/.X11-unix/X{n}").exists():
            return n
    raise RuntimeError("no free display number for the stall proxy")


def wait_focus_settled(sampler: xprobe.FocusSampler) -> dict[str, Any]:
    """The reference: the first sample of the first SETTLE_QUIET_S run without a change."""
    t0 = time.monotonic_ns()
    while True:
        changes = list(sampler.changes)
        nowns = time.monotonic_ns()
        if changes and nowns - changes[-1][0] >= SETTLE_QUIET_S * 1e9:
            last = changes[-1]
            return {"ok": True, "ref_ns": last[0], "focus": last[1], "active": last[2],
                    "waited_ms": round((nowns - t0) / 1e6, 3), "changes_before": len(changes)}
        if nowns - t0 > SETTLE_CAP_S * 1e9:
            last = changes[-1] if changes else [0, 0, 0]
            return {"ok": False, "ref_ns": last[0], "focus": last[1], "active": last[2],
                    "waited_ms": round((nowns - t0) / 1e6, 3), "changes_before": len(changes)}
        time.sleep(0.01)


async def run(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / hc.JEV_REL / "python"))
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    from driver_env import driver_environment  # noqa: E402
    from native import NativeObservation, eligible_controls  # noqa: E402
    from run import Driver, DriverToolError  # noqa: E402

    sys.setswitchinterval(0.0005)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    block = next(b for b in plan["blocks"] if b["block"] == args.block)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    bins = {"U": (str(Path(args.driver_u).resolve()), args.driver_u_sha256),
            "G": (str(Path(args.driver_g).resolve()), args.driver_g_sha256)}
    for name, (path, sha) in bins.items():
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        if actual != sha:
            raise SystemExit(f"refusing: driver {name} sha256 {actual} != {sha}")

    pre = xprobe.snapshot()
    meta = {
        "event": "meta", "block": args.block, "kind": block["kind"], "label": args.label,
        "display": os.environ.get("DISPLAY"), "x_clients_at_start": pre["clients"],
        "display_collision": bool(pre["clients"]), "loadavg": hc.loadavg(), "wall_ns": time.time_ns(),
        "driver_bins": {k: Path(v[0]).name for k, v in bins.items()},
        "driver_sha256": {k: v[1] for k, v in bins.items()}, "plan_sha256": args.plan_sha256,
        "pid": os.getpid(),
    }
    ledger_path = out / "trials.jsonl"
    ledger = open(ledger_path, "w", encoding="utf-8")
    ledger.write(json.dumps(meta, sort_keys=True) + "\n")
    ledger.flush()
    if meta["display_collision"]:
        for t in block["trials"]:
            ledger.write(json.dumps({"event": "trial", **t, "failure": "display_collision",
                                     "oracle_verified": False}) + "\n")
        ledger.write(json.dumps({"event": "end", "failures": len(block["trials"]), "net": hc.NET}) + "\n")
        ledger.close()
        return 3

    decoy = xprobe.Decoy() if any(t["kind"] in FOCUS_KINDS for t in block["trials"]) else None
    xhost = None
    if any(t["kind"] in REPLY_KINDS for t in block["trials"]):
        # The Driver reaches this private Xvfb through xstall_proxy.py (a path socket), so the
        # server sees the proxy as the client: allow this uid by server-interpreted local user
        # (this private server only), instead of copying the session's auth cookie.
        res = subprocess.run(["xhost", f"+si:localuser:{os.environ.get('USER', '')}"],
                             capture_output=True, text=True, timeout=10)
        xhost = {"rc": res.returncode, "out": (res.stdout + res.stderr).strip()[:200]}
        ledger.write(json.dumps({"event": "xhost", **xhost}) + "\n")
    failures = 0

    async def run_trial(t: dict[str, Any]) -> dict[str, Any]:
        kind = t["kind"]
        arm = ARMS[t["arm"]]
        driver_bin, driver_sha = bins[t["bin"]]
        rec: dict[str, Any] = {"event": "trial", **t, "loadavg": hc.loadavg(), "w_begin": time.time_ns(),
                               "driver_bin": Path(driver_bin).name, "driver_sha256": driver_sha}
        tdir = work / t["id"]
        tdir.mkdir(parents=True, exist_ok=True)
        state_path = tdir / "state.json"
        phase_path = tdir / "phase.jsonl"
        phase_path.write_text("", encoding="utf-8")
        fixture = None
        sampler: hc.StateSampler | None = None
        focus: xprobe.FocusSampler | None = None
        stealer: subprocess.Popen | None = None
        anchor = None
        clock_pairs: list[list[int]] = []
        env = hc.driver_env(driver_environment(), phase_path, arm["env"])
        proxy: subprocess.Popen | None = None
        listen = ""
        if kind in REPLY_KINDS:
            # The proxy listens on a FILESYSTEM socket in the session's private /tmp/.X11-unix
            # (hostless-strict tmpfs) and the Driver gets DISPLAY=:M. x11rb tries the abstract
            # name @/tmp/.X11-unix/XM first: M is chosen so that no such abstract socket exists
            # anywhere (checked here); hostless's Landlock scope refuses foreign ones regardless.
            listen_n = free_display_number()
            listen = f"/tmp/.X11-unix/X{listen_n}"
            rec["proxy_display_number"] = listen_n
            upstream = "/tmp/.X11-unix/X" + os.environ["DISPLAY"].split(":")[1].split(".")[0]
            proxy = subprocess.Popen(
                [sys.executable, str(HERE / "xstall_proxy.py"), "--listen", listen, "--upstream", upstream,
                 "--trace", str(phase_path), "--mode", "stall" if kind == "replystall" else "passthrough",
                 "--hold-after-ms", str(REPLY["hold_after_ms"]), "--pause-ms", str(REPLY["pause_ms"]),
                 "--stacking-atom", str(stacking_atom())],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            rec["proxy_ready"] = proxy.stdout.readline().strip()[:200]  # type: ignore[union-attr]
            env["DISPLAY"] = f":{listen_n}"
            rec["driver_display"] = "proxy"
        rec["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
        try:
            fixture = hc.start_fixture(wt, state_path, tdir / "fixture.log")
            before = hc.read_state(state_path) or {}
            rec["before"] = before
            rec["fixture_pid"] = fixture.pid
            params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
            errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.list_tools()
                    driver = Driver(session, f"own20g-{uuid.uuid4().hex[:8]}")

                    async def find_window(pid: int) -> int:
                        for _ in range(60):
                            wins = (await driver.call("list_windows", {"pid": pid})).get("windows", [])
                            hits = [w for w in wins if w.get("title") == hc.WINDOW_TITLE
                                    and w.get("is_on_screen") is not False]
                            if hits:
                                return int(hits[0]["window_id"])
                            await asyncio.sleep(0.25)
                        raise RuntimeError("task window did not appear")

                    window_id = await find_window(fixture.pid)
                    rec["window_id"] = window_id
                    target = {"pid": fixture.pid, "window_id": window_id}
                    await driver.call("set_agent_cursor_motion", dict(FAST_MOTION) if arm["fast_cursor"] else {})

                    async def timed(name: str, arguments: dict[str, Any], raw: bool = False) -> dict[str, Any]:
                        m0, w0 = hc.now()
                        error = None
                        payload: dict[str, Any] = {}
                        content_text: list[str] = []
                        try:
                            if raw:
                                res = await session.call_tool(name, {**arguments, "session": driver.label})
                                payload = res.structuredContent if isinstance(res.structuredContent, dict) else {}
                                content_text = [getattr(c, "text", "")[:600] for c in (res.content or [])]
                                if res.isError:
                                    error = {"code": payload.get("code"), "is_error": True}
                            else:
                                payload = await driver.call(name, arguments)
                        except DriverToolError as exc:
                            error = {"code": exc.code, "message": str(exc)[:400]}
                        m1, w1 = hc.now()
                        clock_pairs.extend([[m0, w0], [m1, w1]])
                        return {"tool": name, "m0": m0, "w0": w0, "m1": m1, "w1": w1,
                                "wrapper_ms": (m1 - m0) / 1e6, "error": error, "payload": payload,
                                "content_text": content_text}

                    def shape(a: dict[str, Any]) -> dict[str, Any]:
                        p = a.pop("payload")
                        a["structured"] = {k: v for k, v in p.items()
                                           if k not in ("screenshot", "image", "tree", "elements")}
                        return a

                    if kind in FOCUS_KINDS:
                        assert decoy is not None
                        rec["decoy_window"] = decoy.window
                        rec["focus_placement"] = xprobe.activate_and_wait(window_id)
                        focus = xprobe.FocusSampler()
                        focus.start()
                        rec["focus_reference"] = await asyncio.to_thread(wait_focus_settled, focus)
                        splan: dict[str, Any] = {"trace": str(phase_path), "decoy_window": decoy.window,
                                                 "deadline_s": 20}
                        if kind == "steal":
                            splan.update({"mode": "steal", "delay_ms": float(t["delay_ms"])})
                        elif kind == "stall":
                            splan.update({"mode": "stall", **STALL})
                            if t.get("steal_conn_at_ms") is not None:
                                splan["steal_conn_at_ms"] = float(t["steal_conn_at_ms"])
                        elif kind == "replystall":
                            splan.update({"mode": "steal", "delay_ms": REPLY["steal_ms"]})
                        elif kind == "stallonly":
                            splan.update({"mode": "grabonly", **STALL})
                        else:
                            splan.update({"mode": "none"})
                        rec["stealer_plan"] = splan
                        stealer = subprocess.Popen(
                            [sys.executable, str(HERE / "stealer.py"), json.dumps(splan)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                        ready = await asyncio.to_thread(stealer.stdout.readline)  # type: ignore[union-attr]
                        rec["stealer_ready"] = ready.strip()[:200]
                    sampler = hc.StateSampler(state_path)
                    sampler.start()
                    while not sampler.t0:
                        await asyncio.sleep(0.001)
                    task = t["task"]
                    labels = {"checkbox": ["I agree"], "text": ["Note", "Save note"]}[task]
                    if task == "checkbox":
                        expected = {"agreed": not bool(before.get("agreed")), "seq": int(before["seq"]) + 1}
                    else:
                        token = f"own20g-{t['id']}-{uuid.uuid4().hex[:6]}"
                        expected = {"note_saved": token, "seq": int(before["seq"]) + 1}
                    sampler.expected = expected
                    rec["expected"] = expected

                    t0m, t0w = hc.now()
                    anchor = t0m
                    rec["T0_m"], rec["T0_w"] = t0m, t0w
                    obs = await timed("get_window_state", {
                        **target, "include_accessibility_tree": True, "include_screenshot": True})
                    payload = obs.pop("payload")
                    rec["observe"] = {k: obs[k] for k in ("m0", "m1", "wrapper_ms", "error")}
                    found: dict[str, Any] = {}
                    if obs["error"] is None:
                        nobs = NativeObservation.from_window_state(payload, expected_pid=fixture.pid,
                                                                   expected_window_id=window_id)
                        controls = eligible_controls(nobs, "linux").controls
                        for label in labels:
                            matches = [c for c in controls if c.label == label]
                            found[label] = matches[0] if len(matches) == 1 else None
                    actions: list[dict[str, Any]] = []
                    if obs["error"] or not all(found.get(x) for x in labels):
                        rec["failure"] = "observe_error" if obs["error"] else "target_not_found"
                    elif task == "checkbox":
                        actions.append(shape(await timed("click", {
                            **target, "element_token": found["I agree"].element_token,
                            "delivery_mode": "background"}, raw=True)))
                    else:
                        sv = shape(await timed("set_value", {
                            **target, "element_token": found["Note"].element_token, "value": token}))
                        actions.append(sv)
                        if sv["error"] is None:
                            actions.append(shape(await timed("click", {
                                **target, "element_token": found["Save note"].element_token,
                                "delivery_mode": "background"}, raw=True)))
                    rec["actions"] = actions
                    if actions:
                        sampler.return_ns = actions[-1]["m1"]
                        await asyncio.to_thread(sampler.confirmed.wait, CONFIRM_DEADLINE_S)
                    if stealer is not None:
                        try:
                            tail = await asyncio.to_thread(stealer.communicate, None, 25)
                            text = (tail[0] or "").strip().splitlines()
                            rec["stealer"] = json.loads(text[-1]) if text else {"error": "no output"}
                        except (subprocess.TimeoutExpired, ValueError) as exc:
                            rec["stealer"] = {"error": f"{type(exc).__name__}: {exc}"}
                    await asyncio.sleep(POST_HOLD_S[kind])
                    for _ in range(3):
                        clock_pairs.append(list(hc.now()))
        except Exception as exc:  # retained in the denominator
            rec["failure"] = rec.get("failure") or f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            if proxy is not None:
                proxy.terminate()
                try:
                    Path(listen).unlink(missing_ok=True)
                except OSError:
                    pass
                try:
                    pout = proxy.communicate(timeout=10)[0] or ""
                    lines = pout.strip().splitlines()
                    rec["proxy"] = json.loads(lines[-1]) if lines else {"error": "no output"}
                except (subprocess.TimeoutExpired, ValueError) as exc:
                    proxy.kill()
                    rec["proxy"] = {"error": f"{type(exc).__name__}: {exc}"}
            if stealer is not None and stealer.poll() is None:
                stealer.kill()
                stealer.wait()
                rec.setdefault("stealer", {"error": "killed after the trial"})
            if sampler is not None:
                rec["state_samples"] = sampler.stop()
                rec["confirmed_live"] = sampler.confirmed.is_set()
            if focus is not None:
                rec["focus_samples"] = focus.stop()
            rec["anchor_ns"] = anchor
            rec["clock_pairs"] = clock_pairs
            rec["fixture_rc"] = hc.stop_process(fixture)
            try:
                rec["fixture_log"] = (tdir / "fixture.log").read_text(encoding="utf-8", errors="replace")[-2000:]
            except OSError:
                rec["fixture_log"] = ""
            rec["marks"] = hc.read_marks(phase_path)
            rec["w_end"] = time.time_ns()
        return rec

    try:
        for t in block["trials"]:
            r = await run_trial(t)
            r["oracle_verified"] = bool(r.get("confirmed_live")) and "failure" not in r
            failures += 0 if r.get("oracle_verified") else 1
            ledger.write(json.dumps(r, sort_keys=True) + "\n")
            ledger.flush()
    finally:
        if decoy is not None:
            decoy.close()
        ledger.write(json.dumps({"event": "end", "failures": failures, "loadavg": hc.loadavg(),
                                 "wall_ns": time.time_ns(), "net": hc.NET}, sort_keys=True) + "\n")
        ledger.close()
    print(f"done: {ledger_path} failures={failures} net_refused={hc.NET['refused_non_loopback_connects']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("wt", "driver-u", "driver-u-sha256", "driver-g", "driver-g-sha256", "plan",
                 "plan-sha256", "block", "label", "out", "work"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    hc.refuse_outside_session()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
