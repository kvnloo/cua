#!/usr/bin/env python3
"""OWN-20G: the steal trigger, a separate process (measurement harness only).

It runs inside the isolated X11 session, next to the harness, and talks only to
the private X server. The harness starts one stealer per trial with a JSON plan
on argv; the stealer tails the trial's Driver phase trace and keys every action
on the Driver-side ``atspi_action do_action_replied`` mark (its ``wall_ns``), so
the schedule does not depend on when the stealer happens to notice the mark.

Modes:

* ``steal``: at ``mark + delay_ms`` steal the focus for the pre-mapped decoy
  window, exactly as N-02's decoy does (EWMH ``_NET_ACTIVE_WINDOW`` request with
  source 2, ``XRaiseWindow``, ``XSetInputFocus``), on the stealer's own X
  connection.
* ``stall``: reproduce trial c08-017. A grab connection issues ``XGrabServer``
  at ``mark + grab_at_ms`` and holds it for ``grab_ms``; a second connection
  issues the same decoy steal at ``mark + steal_ms`` (while the server is
  grabbed, so the steal is queued until the grab ends, like every other client's
  requests, including the guard's).
* ``none``: wait for the mark and record it (no-steal control).

It writes one JSON object (the schedule actually achieved, CLOCK_MONOTONIC and
CLOCK_REALTIME stamps) to stdout and exits. Nothing here reads or drives the
Driver, and nothing it records is used as an oracle: the focus oracle is the
harness's independent 2 ms sampler (``xprobe.FocusSampler``).
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xprobe  # noqa: E402  (verbatim N-02 module: libX11 bindings and Conn)

X = xprobe.X
X.XGrabServer.argtypes = [ctypes.c_void_p]
X.XUngrabServer.argtypes = [ctypes.c_void_p]

MARK_SCOPE = "atspi_action"
MARK_NAME = "do_action_replied"


def stamp() -> dict[str, int]:
    return {"mono_ns": time.monotonic_ns(), "wall_ns": time.time_ns()}


def sleep_until_wall(target_wall_ns: int) -> None:
    while True:
        remaining = (target_wall_ns - time.time_ns()) / 1e9
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.0005) if remaining < 0.003 else remaining - 0.002)


def wait_for_mark(trace: Path, deadline_s: float) -> tuple[int | None, dict[str, int] | None]:
    """Tail ``trace`` (0.5 ms poll) until the do_action_replied mark appears."""
    end = time.monotonic() + deadline_s
    offset = 0
    buf = ""
    while time.monotonic() < end:
        try:
            with open(trace, encoding="utf-8") as stream:
                stream.seek(offset)
                chunk = stream.read()
                offset = stream.tell()
        except OSError:
            chunk = ""
        if chunk:
            buf += chunk
            *lines, buf = buf.split("\n")
            for line in lines:
                if f'"mark":"{MARK_NAME}"' in line and f'"scope":"{MARK_SCOPE}"' in line:
                    seen = stamp()
                    return int(json.loads(line)["wall_ns"]), seen
        time.sleep(0.0005)
    return None, None


def steal(conn: xprobe.Conn, window: int) -> None:
    conn.request_activate(window)
    X.XRaiseWindow(conn.dpy, window)
    X.XSetInputFocus(conn.dpy, window, xprobe.REVERT_TO_PARENT, 0)
    X.XFlush(conn.dpy)


def main() -> None:
    plan = json.loads(sys.argv[1])
    out: dict = {"plan": plan, "started": stamp()}
    conns: list[xprobe.Conn] = []
    try:
        # ``steal_conn_at_ms`` (stall mode): open the steal connection only that long after
        # the mark, i.e. after the guard opened its own X connection at its start.
        late_conn = plan.get("steal_conn_at_ms") is not None
        steal_conn = None if late_conn else xprobe.Conn()
        if steal_conn is not None:
            conns.append(steal_conn)
        grab_conn = None
        if plan["mode"] in ("stall", "grabonly"):
            grab_conn = xprobe.Conn()
            conns.append(grab_conn)
        out["ready"] = stamp()
        print(json.dumps({"ready": True}), flush=True)
        mark_wall, seen = wait_for_mark(Path(plan["trace"]), float(plan.get("deadline_s", 15)))
        if mark_wall is None:
            out["error"] = "mark not seen"
            return
        out["mark_wall_ns"] = mark_wall
        out["mark_seen"] = seen
        out["detect_lag_ms"] = round((seen["wall_ns"] - mark_wall) / 1e6, 3)
        window = int(plan["decoy_window"])
        if plan["mode"] == "steal":
            target = mark_wall + int(float(plan["delay_ms"]) * 1e6)
            out["late_at_schedule"] = time.time_ns() > target
            sleep_until_wall(target)
            out["steal_issued"] = stamp()
            steal(steal_conn, window)
            out["steal_flushed"] = stamp()
        elif plan["mode"] in ("stall", "grabonly"):
            assert grab_conn is not None
            grab_at = mark_wall + int(float(plan["grab_at_ms"]) * 1e6)
            steal_at = mark_wall + int(float(plan["steal_ms"]) * 1e6)
            out["late_at_schedule"] = time.time_ns() > grab_at
            if late_conn:
                sleep_until_wall(mark_wall + int(float(plan["steal_conn_at_ms"]) * 1e6))
                steal_conn = xprobe.Conn()
                conns.append(steal_conn)
                out["steal_conn_opened"] = stamp()
            sleep_until_wall(grab_at)
            out["grab_issued"] = stamp()
            X.XGrabServer(grab_conn.dpy)
            X.XSync(grab_conn.dpy, 0)
            out["grab_synced"] = stamp()
            ungrab_at = out["grab_issued"]["wall_ns"] + int(float(plan["grab_ms"]) * 1e6)
            if plan["mode"] == "stall":
                sleep_until_wall(steal_at)
                out["steal_issued"] = stamp()
                steal(steal_conn, window)  # queued by the server until the grab ends
                out["steal_flushed"] = stamp()
            sleep_until_wall(ungrab_at)
            out["ungrab_issued"] = stamp()
            X.XUngrabServer(grab_conn.dpy)
            X.XSync(grab_conn.dpy, 0)
            out["ungrab_synced"] = stamp()
            X.XSync(steal_conn.dpy, 0)
            out["steal_synced"] = stamp()
        out["done"] = stamp()
    except Exception as exc:  # recorded, the harness keeps the trial
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for conn in conns:
            conn.close()
        print(json.dumps(out, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
