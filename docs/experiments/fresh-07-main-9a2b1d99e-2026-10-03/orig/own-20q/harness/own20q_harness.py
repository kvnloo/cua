#!/usr/bin/env python3
"""OWN-20Q: focus-guard rows on the canonical GTK3 task fixture, mark-free (measurement only).

A new file derived from OWN-20G's ``own20g_harness.py`` (blob-identical, not modified): same fixture,
task window, observation, jev-use ``eligible_controls`` lookup, forced background element-token
AT-SPI click, 2 ms state-file oracle, X focus sampler and decoy window (``xprobe.py``), fresh Driver +
fresh fixture per trial, two Driver binaries per block (slots U and G, sha256-checked).

New here (PREREG.json): nothing is keyed on a Driver mark. ``markfree_proxy.py`` takes the trigger
from the DoAction reply routed by the private a11y bus. Every trial also records two more
target-owned oracles: X RECORD on the private display (``q_common.XRecord``) and a dbus-monitor of
the private a11y bus (``q_common.BusWatch``, the Driver's connections attributed by the bus daemon).

Kinds:
* ``mfstall`` (R1m): proxy ``stall`` (hold the guard's first new-client read >= 80 ms after R for
  2000 ms) and a steal at R + 217 ms;
* ``mfcal`` (calibration, marked twins): ``mfstall`` plus the Driver phase trace tailed by the proxy
  to record where the OWN-20P mark-keyed rule would have held;
* ``mfonly`` (control): proxy ``pass``, decoy mapped, no steal;
* ``dlgsteal`` (DLG): proxy ``lag`` (the Driver sees ``_NET_ACTIVE_WINDOW`` 1500 ms late) and a steal
  at R + 100 ms, inside the guard's settle watch;
* ``dlgdialog`` (DLG control): proxy ``lag``, the DLG fixture's "Open dialog" button, no steal;
* ``nosteal`` (normal path): no proxy, decoy mapped, sampler on, no steal.

Runs INSIDE cua-x11-session.sh with a private AT-SPI bus; refuses otherwise. No provider:
non-loopback connects are refused and counted.
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
import q_common  # noqa: E402
import xprobe  # noqa: E402
from own20g_harness import free_display_number, wait_focus_settled  # noqa: E402  (blob-identical)

ARMS: dict[str, dict[str, Any]] = {
    "P": {"fast_cursor": False},   # product defaults: no CUA_DRIVER_EXP_* variable, default cursor motion
    "PX": {"fast_cursor": True},   # product defaults + set_agent_cursor_motion(glide 1 ms, dwell 0)
}
FAST_MOTION = {"glide_duration_ms": 1, "dwell_after_click_ms": 0}
CONFIRM_DEADLINE_S = 6.0
POST_HOLD_S = 0.7
KINDS = ("mfstall", "mfcal", "mfonly", "dlgsteal", "dlgdialog", "nosteal")
PROXY_MODE = {"mfstall": "stall", "mfcal": "stall", "mfonly": "pass", "dlgsteal": "lag", "dlgdialog": "lag"}
STEAL_MS = {"mfstall": 217.0, "mfcal": 217.0, "dlgsteal": 100.0}
HOLD = {"hold_after_ms": 80.0, "pause_ms": 2000.0}
LAG_MS = 1500.0
LAG_QUIET_MARGIN_MS = 300.0


def arm_proxy(proxy: subprocess.Popen | None) -> int:
    """The click call is about to be issued: tell the proxy (stdin) and return the wall time."""
    now = time.time_ns()
    if proxy is not None and proxy.stdin is not None:
        proxy.stdin.write(f"click {now}\n")
        proxy.stdin.flush()
    return now


def driver_pid_of(path: str) -> int | None:
    me = os.getpid()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
            ppid = int(stat[stat.rindex(")") + 2:].split()[1])
            if ppid == me and os.path.realpath(entry / "exe") == path:
                return int(entry.name)
        except (OSError, ValueError, IndexError):
            continue
    return None


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
    address = q_common.a11y_address()
    pre = xprobe.snapshot()
    meta = {
        "event": "meta", "block": args.block, "kind": block["kind"], "label": args.label,
        "x_clients_at_start": pre["clients"], "display_collision": bool(pre["clients"]),
        "a11y_bus_found": bool(address), "loadavg": hc.loadavg(), "wall_ns": time.time_ns(),
        "driver_bins": {k: Path(v[0]).name for k, v in bins.items()},
        "driver_sha256": {k: v[1] for k, v in bins.items()}, "plan_sha256": args.plan_sha256, "pid": os.getpid(),
    }
    ledger_path = out / "trials.jsonl"
    ledger = open(ledger_path, "w", encoding="utf-8")
    ledger.write(q_common.dumps(meta) + "\n")
    ledger.flush()
    if meta["display_collision"] or not address:
        for t in block["trials"]:
            ledger.write(q_common.dumps({"event": "trial", **t, "failure": "display_collision" if pre["clients"]
                                         else "no a11y bus", "oracle_verified": False}) + "\n")
        ledger.write(q_common.dumps({"event": "end", "failures": len(block["trials"]), "net": hc.NET}) + "\n")
        ledger.close()
        return 3
    decoy = xprobe.Decoy()
    if any(t["kind"] in PROXY_MODE for t in block["trials"]):
        # The Driver reaches this private Xvfb through markfree_proxy.py (a path socket), so the server sees
        # the proxy as the client: allow this uid by server-interpreted local user on this private server
        # only. The command's output names the user and is not recorded (only its return code).
        res = subprocess.run(["xhost", f"+si:localuser:{os.environ.get('USER', '')}"],
                             capture_output=True, text=True, timeout=10)
        ledger.write(q_common.dumps({"event": "xhost", "rc": res.returncode}) + "\n")
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
        xrec: q_common.XRecord | None = None
        watch: q_common.BusWatch | None = None
        proxy: subprocess.Popen | None = None
        listen = ""
        clock_pairs: list[list[int]] = []
        env = hc.driver_env(driver_environment(), phase_path, {})
        env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "false"
        try:
            watch = q_common.BusWatch(address, "oracle")
            watch.start()
            watch.ready.wait(timeout=5)
            xrec = q_common.XRecord()
            xrec.start()
            xrec.ready.wait(timeout=5)
            rec["oracles_ready"] = {"bus": watch.ready.is_set() and not watch.error,
                                    "xrecord": xrec.ready.is_set() and not xrec.error}
            if kind == "dlgdialog":
                fixture = q_common.start_fixture_env(wt, state_path, tdir / "fixture.log",
                                                     {"OWN20Q_FIXTURE_MAIN": str(wt / hc.FIXTURE_REL)},
                                                     HERE / "dlg_fixture.py")
            else:
                fixture = q_common.start_fixture_env(wt, state_path, tdir / "fixture.log")
            before = hc.read_state(state_path) or {}
            rec["before"] = before
            rec["fixture_pid"] = fixture.pid
            if kind in PROXY_MODE:
                listen_n = free_display_number()
                listen = f"/tmp/.X11-unix/X{listen_n}"
                upstream = "/tmp/.X11-unix/X" + os.environ["DISPLAY"].split(":")[1].split(".")[0]
                cmd = [sys.executable, str(HERE / "markfree_proxy.py"), "--listen", listen, "--upstream", upstream,
                       "--mode", PROXY_MODE[kind], "--hold-after-ms", str(HOLD["hold_after_ms"]),
                       "--pause-ms", str(HOLD["pause_ms"]), "--lag-ms", str(LAG_MS),
                       "--decoy-window", str(decoy.window)]
                if kind in STEAL_MS:
                    cmd += ["--steal-ms", str(STEAL_MS[kind])]
                if kind == "mfcal":
                    cmd += ["--trace", str(phase_path)]
                penv = dict(os.environ)
                penv["OWN20Q_A11Y_ADDRESS"] = address
                proxy = subprocess.Popen(cmd, env=penv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True)
                rec["proxy_ready"] = proxy.stdout.readline().strip()[:200]  # type: ignore[union-attr]
                env["DISPLAY"] = f":{listen_n}"
                rec["driver_display"] = "proxy"
            rec["driver_env_exp"] = sorted(k for k in env if k.startswith("CUA_DRIVER_EXP_"))
            params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
            errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.list_tools()
                    rec["driver_pid"] = driver_pid_of(os.path.realpath(driver_bin))
                    driver = Driver(session, f"own20q-{uuid.uuid4().hex[:8]}")

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

                    rec["decoy_window"] = decoy.window
                    rec["focus_placement"] = xprobe.activate_and_wait(window_id)
                    focus = xprobe.FocusSampler()
                    focus.start()
                    rec["focus_reference"] = await asyncio.to_thread(wait_focus_settled, focus)
                    sampler = hc.StateSampler(state_path)
                    sampler.start()
                    while not sampler.t0:
                        await asyncio.sleep(0.001)
                    task = t["task"]
                    labels = {"checkbox": ["I agree"], "text": ["Note", "Save note"], "dialog": ["Open dialog"]}[task]
                    if task == "checkbox":
                        expected = {"agreed": not bool(before.get("agreed")), "seq": int(before["seq"]) + 1}
                    elif task == "dialog":
                        expected = {"dialog_open": True, "seq": int(before["seq"]) + 1}
                    else:
                        token = f"own20q-{t['id']}-{uuid.uuid4().hex[:6]}"
                        expected = {"note_saved": token, "seq": int(before["seq"]) + 1}
                    sampler.expected = expected
                    rec["expected"] = expected

                    t0m, t0w = hc.now()
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
                    if PROXY_MODE.get(kind) == "lag":
                        # the true _NET_ACTIVE_WINDOW must have been stable for the whole lag before the
                        # snapshot, so the Driver's lagged view and the live one agree at capture time
                        ref_ns = (rec["focus_reference"] or {}).get("ref_ns") or time.monotonic_ns()
                        wait_s = (ref_ns + (LAG_MS + LAG_QUIET_MARGIN_MS) * 1e6 - time.monotonic_ns()) / 1e9
                        rec["lag_quiet_wait_ms"] = round(max(wait_s, 0) * 1000, 3)
                        if wait_s > 0:
                            await asyncio.sleep(wait_s)
                    actions: list[dict[str, Any]] = []
                    if obs["error"] or not all(found.get(x) for x in labels):
                        rec["failure"] = "observe_error" if obs["error"] else "target_not_found"
                    elif task in ("checkbox", "dialog"):
                        rec["click_issued_w"] = arm_proxy(proxy)
                        actions.append(shape(await timed("click", {
                            **target, "element_token": found[labels[0]].element_token,
                            "delivery_mode": "background"}, raw=True)))
                    else:
                        sv = shape(await timed("set_value", {
                            **target, "element_token": found["Note"].element_token, "value": token}))
                        actions.append(sv)
                        if sv["error"] is None:
                            rec["click_issued_w"] = arm_proxy(proxy)
                            actions.append(shape(await timed("click", {
                                **target, "element_token": found["Save note"].element_token,
                                "delivery_mode": "background"}, raw=True)))
                    rec["actions"] = actions
                    if actions:
                        sampler.return_ns = actions[-1]["m1"]
                        await asyncio.to_thread(sampler.confirmed.wait, CONFIRM_DEADLINE_S)
                    await asyncio.sleep(POST_HOLD_S)
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
            if sampler is not None:
                rec["state_samples"] = sampler.stop()
                rec["confirmed_live"] = sampler.confirmed.is_set()
            if focus is not None:
                rec["focus_samples"] = focus.stop()
            if xrec is not None:
                rec["xrecord"] = xrec.stop()
            rec["fixture_rc"] = hc.stop_process(fixture)
            if watch is not None:
                rec["bus"] = watch.stop()
            rec["clock_pairs"] = clock_pairs
            try:
                rec["fixture_log"] = (tdir / "fixture.log").read_text(encoding="utf-8", errors="replace")[-1500:]
            except OSError:
                rec["fixture_log"] = ""
            rec["final_state"] = hc.read_state(state_path)
            rec["marks"] = hc.read_marks(phase_path)
            rec["w_end"] = time.time_ns()
        return rec

    try:
        for t in block["trials"]:
            r = await run_trial(t)
            r["oracle_verified"] = bool(r.get("confirmed_live")) and "failure" not in r
            failures += 0 if r.get("oracle_verified") else 1
            ledger.write(q_common.dumps(r) + "\n")
            ledger.flush()
    finally:
        decoy.close()
        ledger.write(q_common.dumps({"event": "end", "failures": failures, "loadavg": hc.loadavg(),
                                     "wall_ns": time.time_ns(), "net": hc.NET}) + "\n")
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
