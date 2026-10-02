#!/usr/bin/env python3
"""OWN-16: Linux observation-modality selector truth table at the producer boundary.

Runs INSIDE the isolated X11 session (cua-x11-session.sh). Starts the canonical
GTK3 fixture in its task mode (``CUA_GTK3_TASK_STATE``), opens Driver MCP stdio
session(s) and calls ``get_window_state`` on the task window with each modality
selector row. Per call it records the Driver's measurement-only producer marks
(``CUA_DRIVER_PHASE_TRACE_FILE``: capture_window / capture_root_region /
atspi_walk enter+exit with invocation ordinals), the response shape and
metadata verbatim, element/coordinate integrity, client wall time and MCP
response bytes.

Modes:
  measured  pre-registered rows: 1 cold call per row, then the warm block
            (n rounds, rotating row order) under the EXCLUSIVE quiet-lane lock,
            then the independent producer-boundary oracle block (X RECORD of
            GetImage/ShmGetImage + dbus-monitor on the private AT-SPI bus) and
            one usability action per session.
  negative  a session started without the private AT-SPI bus: accessibility
            requested; records what the metadata says and whether the walk ran.
  smoke     default-off smoke: the same binary with the marks unset (and set to
            an empty string), then set; plus the unmodified main binary.
            Compares response shape per row and checks that no trace file appears.

Nothing here changes Driver behaviour. The Driver gets jev-use's
``driver_environment()`` plus, when marks are on, CUA_DRIVER_PHASE_TRACE_FILE.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import fcntl
import hashlib
import json
import os
import re
import signal
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

FIXTURE_REL = "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
JEV_REL = "libs/cua-driver/examples/jev-use"
WINDOW_TITLE = "CuaTestHarness GTK3 Tasks"

# Pre-registered selector rows (PREREG.json "matrix").
ROWS: dict[str, dict[str, Any]] = {
    "both": {"include_accessibility_tree": True, "include_screenshot": True},
    "screenshot_only": {"include_accessibility_tree": False},
    "accessibility_only": {"include_screenshot": False},
    "neither": {"include_accessibility_tree": False, "include_screenshot": False},
    "legacy_omitted": {},
    "unknown_field": {"include_tree": False},
    "wrong_type_supplementary": {"include_screenshot": "false"},
}
ROW_ORDER = list(ROWS)
PRODUCER_SCOPES = ("capture_window", "capture_root_region", "atspi_walk")
META_KEYS = (
    "element_count", "total_element_count", "returned_element_count", "elements_complete",
    "truncated", "truncation_reason", "nodes_visited", "nodes_pending", "bounds_complete",
    "walk_elapsed_ms", "degraded", "degraded_reason", "escalation", "screenshot_width",
    "screenshot_height", "screenshot_frame_valid", "screenshot_error", "frame_scale",
    "screenshot_original_width", "screenshot_mime_type", "window_bounds", "code", "refusal",
    "coordinate_frame", "screenshot_composited", "popup",
)


def now() -> tuple[int, int]:
    return time.monotonic_ns(), time.time_ns()


def loadavg() -> list[float]:
    with open("/proc/loadavg", encoding="ascii") as stream:
        return [float(x) for x in stream.read().split()[:3]]


def read_state(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def a11y_address() -> str | None:
    try:
        out = subprocess.run(
            ["gdbus", "call", "--session", "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus",
             "--method", "org.a11y.Bus.GetAddress"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    match = re.search(r"'([^']+)'", out)
    return match.group(1) if match else None


def png_dims(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


# --------------------------------------------------------------------------- integrity
def integrity(structured: dict[str, Any], png: tuple[int, int] | None) -> dict[str, Any]:
    """Element frames inside the window bounds; screenshot frames inside the image and
    consistent with frame - window origin (scaled) when both modalities are present."""
    wb = structured.get("window_bounds") or {}
    elements = structured.get("elements")
    out: dict[str, Any] = {"window_bounds": wb or None}
    if not isinstance(elements, list):
        out["elements_present"] = False
        return out
    out["elements_present"] = True
    out["element_entries"] = len(elements)
    framed = [e for e in elements if isinstance(e.get("frame"), dict)]
    out["framed"] = len(framed)
    outside, overshoot = 0, 0.0
    sf_outside, sf_mismatch, sf_count = 0, 0, 0
    sw, sh = structured.get("screenshot_width"), structured.get("screenshot_height")
    scale = structured.get("frame_scale") or 1.0
    for e in framed:
        f = e["frame"]
        if wb:
            dx = [wb["x"] - f["x"], wb["y"] - f["y"],
                  (f["x"] + f["w"]) - (wb["x"] + wb["width"]), (f["y"] + f["h"]) - (wb["y"] + wb["height"])]
            worst = max(dx)
            if worst > 0:
                outside += 1
                overshoot = max(overshoot, worst)
        s = e.get("screenshot_frame")
        if isinstance(s, dict):
            sf_count += 1
            if sw is not None and (s["x"] < -0.5 or s["y"] < -0.5 or s["x"] + s["w"] > sw + 0.5
                                   or s["y"] + s["h"] > sh + 0.5):
                sf_outside += 1
            if wb:
                ex, ey = (f["x"] - wb["x"]) * scale, (f["y"] - wb["y"]) * scale
                if abs(s["x"] - ex) > 1.0 or abs(s["y"] - ey) > 1.0:
                    sf_mismatch += 1
    out.update({"frames_outside_window": outside, "max_overshoot_px": overshoot,
                "screenshot_frames": sf_count, "screenshot_frames_outside_image": sf_outside,
                "screenshot_frames_inconsistent": sf_mismatch})
    if sw is not None and wb:
        out["screenshot_matches_window"] = (abs(sw - wb["width"] * scale) <= 1.0
                                            and abs(sh - wb["height"] * scale) <= 1.0)
    if png is not None and sw is not None:
        out["png_matches_reported_dims"] = (png[0] == sw and png[1] == sh)
    canon = sorted(
        (e.get("element_index"), e.get("role"), e.get("label"), e.get("value"),
         json.dumps(e.get("frame"), sort_keys=True))
        for e in elements
    )
    out["elements_digest"] = hashlib.sha256(json.dumps(canon).encode()).hexdigest()[:16]
    return out


# --------------------------------------------------------------------------- oracle
def parse_monitor(text: str) -> list[dict[str, Any]]:
    header = re.compile(r"^(method call|method return|error|signal) time=(\d+)\.(\d+) sender=(\S+) -> "
                        r"destination=(.+?) serial=(\d+)(.*)$")
    out = []
    for line in text.splitlines():
        m = header.match(line)
        if not m:
            continue
        kind, sec, usec, sender, dest, serial, rest = m.groups()
        rec = {"type": kind, "t_ns": int(sec) * 1_000_000_000 + int(usec.ljust(6, "0")[:6]) * 1000,
               "sender": sender, "dest": dest.strip()}
        for key in ("interface", "member"):
            found = re.search(rf"{key}=([^;\s]+)", rest)
            if found:
                rec[key] = found.group(1)
        out.append(rec)
    return out


def bus_pid(address: str, name: str) -> int | None:
    try:
        out = subprocess.run(
            ["gdbus", "call", "--address", address, "--dest", "org.freedesktop.DBus",
             "--object-path", "/org/freedesktop/DBus", "--method",
             "org.freedesktop.DBus.GetConnectionUnixProcessID", name],
            capture_output=True, text=True, timeout=5).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    m = re.search(r"uint32 (\d+)", out)
    return int(m.group(1)) if m else None


def child_pids(comm_prefix: str) -> list[int]:
    me = os.getpid()
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            stat = Path(f"/proc/{entry}/stat").read_text()
        except OSError:
            continue
        comm = stat[stat.find("(") + 1:stat.rfind(")")]
        ppid = int(stat[stat.rfind(")") + 2:].split()[1])
        if ppid == me and comm.startswith(comm_prefix):
            found.append(int(entry))
    return found


class Oracle:
    """X RECORD (GetImage/ShmGetImage from all clients) + dbus-monitor on the a11y bus."""

    def __init__(self, out: Path, python: str, recorder: str, address: str | None) -> None:
        self.out = out
        self.address = address
        self.xlog = out / "xrecord.jsonl"
        self.dlog = out / "dbus-monitor.log"
        self.xproc = subprocess.Popen([python, recorder, str(self.xlog)],
                                      stdout=subprocess.DEVNULL, stderr=open(out / "xrecord.err", "w"))
        self.dstream = open(self.dlog, "w", encoding="utf-8")
        self.dproc = (subprocess.Popen(["dbus-monitor", "--address", address, "--monitor"],
                                       stdout=self.dstream, stderr=subprocess.STDOUT)
                      if address else None)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.xlog.exists() and "ready" in self.xlog.read_text():
                break
            time.sleep(0.02)
        time.sleep(0.3)

    def stop(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        time.sleep(0.2)
        for proc in (self.xproc, self.dproc):
            if proc is None:
                continue
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        self.dstream.close()
        xev = [json.loads(x) for x in self.xlog.read_text().splitlines() if x.strip()]
        dev = parse_monitor(self.dlog.read_text(errors="replace"))
        return xev, dev


# --------------------------------------------------------------------------- harness
class Lock:
    """The quiet-lane timing lock, held SHARED except for the warm block (EXCLUSIVE)."""

    def __init__(self, path: str | None) -> None:
        self.fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644) if path else None
        self.events: list[dict[str, Any]] = []

    def take(self, mode: str) -> None:
        if self.fd is None:
            return
        t0 = time.monotonic_ns()
        fcntl.flock(self.fd, fcntl.LOCK_EX if mode == "exclusive" else fcntl.LOCK_SH)
        self.events.append({"mode": mode, "wait_ms": (time.monotonic_ns() - t0) / 1e6,
                            "w_ns": time.time_ns(), "loadavg": loadavg()})


class MarkReader:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.offset = 0

    def take(self) -> list[dict[str, Any]]:
        if self.path is None or not self.path.exists():
            return []
        with open(self.path, "rb") as stream:
            stream.seek(self.offset)
            chunk = stream.read()
        complete = chunk[: chunk.rfind(b"\n") + 1] if b"\n" in chunk else b""
        self.offset += len(complete)
        return [json.loads(x) for x in complete.decode().splitlines() if x.strip()]


def producer_counts(marks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {s: sum(1 for m in marks if m["scope"] == s and m["mark"] == "enter") for s in PRODUCER_SCOPES}
    exits = {s: [m["mark"] for m in marks if m["scope"] == s and m["mark"] != "enter"] for s in PRODUCER_SCOPES}
    ordinals = {s: [m.get("n") for m in marks if m["scope"] == s and m["mark"] == "enter"] for s in PRODUCER_SCOPES}
    gws = [m for m in marks if m["scope"] == "get_window_state"]
    enter = next((m["wall_ns"] for m in gws if m["mark"] == "dispatch_enter"), None)
    exit_ = next((m["wall_ns"] for m in gws if m["mark"] == "dispatch_exit"), None)
    inside = all(enter is not None and exit_ is not None and enter <= m["wall_ns"] <= exit_
                 for m in marks if m["scope"] in PRODUCER_SCOPES)
    spans = {}
    for s in PRODUCER_SCOPES:
        ent = [m for m in marks if m["scope"] == s and m["mark"] == "enter"]
        ext = [m for m in marks if m["scope"] == s and m["mark"] != "enter"]
        spans[s] = [(x["mono_ns"] - e["mono_ns"]) / 1e6 for e, x in zip(ent, ext)]
    gmarks = {m["mark"]: m["mono_ns"] for m in gws}
    return {
        "capture": counts["capture_window"] + counts["capture_root_region"],
        "capture_window": counts["capture_window"], "capture_root_region": counts["capture_root_region"],
        "walk": counts["atspi_walk"], "exits": exits, "ordinals": ordinals,
        "producers_inside_dispatch": inside, "dispatch_marks": sorted(gmarks),
        "dispatch_ms": ((gmarks["dispatch_exit"] - gmarks["dispatch_enter"]) / 1e6
                        if {"dispatch_enter", "dispatch_exit"} <= gmarks.keys() else None),
        "invoke_ms": ((gmarks["invoke_end"] - gmarks["invoke_start"]) / 1e6
                      if {"invoke_start", "invoke_end"} <= gmarks.keys() else None),
        "producer_ms": spans,
        "other_marks": sorted({f'{m["scope"]}:{m["mark"]}' for m in marks
                               if m["scope"] not in PRODUCER_SCOPES and m["scope"] != "get_window_state"}),
    }


async def run(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / JEV_REL / "python"))
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    from driver_env import driver_environment  # noqa: E402

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    state_path = work / "gtk3-task-state.json"
    lock = Lock(args.lock)
    lock.take("shared")
    ledger = open(out / "calls.jsonl", "w", encoding="utf-8")

    def emit(rec: dict[str, Any]) -> None:
        ledger.write(json.dumps(rec, sort_keys=True) + "\n")
        ledger.flush()

    fixture_env = dict(os.environ)
    fixture_env["CUA_GTK3_TASK_STATE"] = str(state_path)
    fixture = subprocess.Popen(["/usr/bin/python3", str(wt / FIXTURE_REL)], env=fixture_env,
                               stdout=open(work / "fixture.log", "w"), stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 15
    while read_state(state_path) is None:
        if time.monotonic() > deadline or fixture.poll() is not None:
            raise RuntimeError("fixture did not publish its state file")
        time.sleep(0.05)
    time.sleep(1.0)
    address = a11y_address()
    emit({"event": "meta", "mode": args.mode, "label": args.label, "rotation": args.rotation,
          "warm_rounds": args.warm_rounds, "oracle_rounds": args.oracle_rounds,
          "fixture_pid": fixture.pid, "window_title": WINDOW_TITLE,
          "a11y_bus_address_kind": (address.split(":")[0] if address else None),
          "env_atspi_session": os.environ.get("CUA_SESSION_ATSPI"), "rows": ROWS,
          "loadavg": loadavg()})

    async def driver_session(binary: str, marks: str, tag: str, rows: list[str], plan) -> None:
        """marks: 'on' (file path), 'unset', 'empty'."""
        env = driver_environment()
        env.pop("CUA_DRIVER_PHASE_TRACE_FILE", None)
        phase_path = work / f"phase-{tag}.jsonl"
        if marks == "on":
            phase_path.write_text("", encoding="utf-8")
            env["CUA_DRIVER_PHASE_TRACE_FILE"] = str(phase_path)
        elif marks == "empty":
            env["CUA_DRIVER_PHASE_TRACE_FILE"] = ""
        reader = MarkReader(phase_path if marks == "on" else None)
        params = StdioServerParameters(command=binary, args=["mcp"], env=env)
        label = f"own16-{uuid.uuid4().hex[:8]}"
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                t0 = time.perf_counter_ns()
                await session.initialize()
                init_ms = (time.perf_counter_ns() - t0) / 1e6
                driver_pids = child_pids("cua-driver")
                window_id = None
                seen: list[Any] = []
                t_find = time.monotonic()
                for _ in range(args.window_attempts):
                    res = await session.call_tool("list_windows", {"pid": fixture.pid, "session": label})
                    wins = (res.structuredContent or {}).get("windows", [])
                    seen = [(w.get("title"), w.get("is_on_screen")) for w in wins]
                    hits = [w for w in wins if w.get("title") == WINDOW_TITLE and w.get("is_on_screen") is not False]
                    if hits:
                        window_id = int(hits[0]["window_id"])
                        break
                    await asyncio.sleep(0.25)
                if window_id is None:
                    emit({"event": "window_not_found", "tag": tag, "seen": seen, "is_error": bool(res.isError),
                          "content_head": [getattr(c, "text", "")[:300] for c in (res.content or [])]})
                    raise RuntimeError("task window did not appear")
                reader.take()
                emit({"event": "driver_session", "tag": tag, "binary": Path(binary).name, "marks": marks,
                      "init_ms": init_ms, "window_found": True, "driver_child_count": len(driver_pids),
                      "window_find_ms": (time.monotonic() - t_find) * 1e3})

                async def call(row: str, phase: str, index: int, rnd: int | None) -> dict[str, Any]:
                    arguments = {"pid": fixture.pid, "window_id": window_id, **ROWS[row], "session": label}
                    reader.take()
                    rec: dict[str, Any] = {"event": "call", "tag": tag, "row": row, "phase": phase,
                                           "index": index, "round": rnd, "loadavg": loadavg(),
                                           "arguments": {k: v for k, v in arguments.items() if k not in ("pid", "window_id", "session")}}
                    m0, w0 = now()
                    try:
                        result = await session.call_tool("get_window_state", arguments)
                        exc = None
                    except Exception as error:  # kept in the denominator
                        result, exc = None, f"{type(error).__name__}: {str(error)[:300]}"
                    m1, w1 = now()
                    rec.update({"m0": m0, "w0": w0, "m1": m1, "w1": w1, "wall_ms": (m1 - m0) / 1e6})
                    marks_now = reader.take()
                    if marks == "on":
                        rec["producers"] = producer_counts(marks_now)
                    if exc is not None:
                        rec["exception"] = exc
                        return rec
                    dumped = result.model_dump(mode="json", by_alias=True, exclude_none=True)
                    rec["response_bytes"] = len(json.dumps(dumped, separators=(",", ":")).encode())
                    rec["is_error"] = bool(result.isError)
                    structured = result.structuredContent if isinstance(result.structuredContent, dict) else {}
                    rec["structured_keys"] = sorted(structured)
                    parts, png = [], None
                    for part in result.content or []:
                        kind = getattr(part, "type", None)
                        if kind == "image":
                            raw = base64.b64decode(part.data)
                            png = png_dims(raw)
                            parts.append({"type": "image", "mime": part.mimeType, "bytes": len(raw),
                                          "sha256": hashlib.sha256(raw).hexdigest()[:16], "png_dims": png})
                        elif kind == "text":
                            parts.append({"type": "text", "chars": len(part.text),
                                          "head": part.text[:600] if result.isError else part.text[:80]})
                        else:
                            parts.append({"type": kind})
                    rec["content"] = parts
                    rec["meta"] = {k: structured.get(k) for k in META_KEYS if k in structured}
                    rec["has"] = {
                        "elements": isinstance(structured.get("elements"), list),
                        "tree_markdown": "tree_markdown" in structured,
                        "snapshot_id": "snapshot_id" in structured,
                        "image_part": any(p["type"] == "image" for p in parts),
                        "screenshot_fields": "screenshot_width" in structured,
                        "capture_id": "capture_id" in structured,
                        "screenshot_error": "screenshot_error" in structured,
                        "degraded": structured.get("degraded") is True,
                    }
                    rec["integrity"] = integrity(structured, png)
                    if result.isError:
                        rec["error_text"] = next((p["head"] for p in parts if p["type"] == "text"), None)
                    return rec

                await plan(call, tag, rows, session, label, window_id, driver_pids, reader)

    def rotated(rows: list[str], k: int) -> list[str]:
        k %= len(rows)
        return rows[k:] + rows[:k]

    try:
        if args.mode == "measured":
            async def plan(call, tag, rows, session, label, window_id, driver_pids, reader):
                index = 0
                # Cold: the first call of each row in this session (rows in rotated order).
                for row in rotated(rows, args.rotation):
                    emit(await call(row, "cold", index, None))
                    index += 1
                # Warm block under the EXCLUSIVE quiet-lane lock.
                lock.take("exclusive")
                emit({"event": "lock", **lock.events[-1]})
                for rnd in range(args.warm_rounds):
                    for row in rotated(rows, args.rotation + rnd):
                        emit(await call(row, "warm", index, rnd))
                        index += 1
                lock.take("shared")
                emit({"event": "lock", **lock.events[-1]})
                # Independent producer-boundary oracle block (perturbs timing: never timed).
                oracle_dir = out / "oracle"
                oracle_dir.mkdir(exist_ok=True)
                orc = Oracle(oracle_dir, args.oracle_python, args.recorder, address)
                idle0 = time.time_ns()
                await asyncio.sleep(1.0)
                idle1 = time.time_ns()
                windows = [{"kind": "idle", "w0": idle0, "w1": idle1}]
                for rnd in range(args.oracle_rounds):
                    for row in rotated(rows, args.rotation + rnd):
                        rec = await call(row, "oracle", index, rnd)
                        emit(rec)
                        windows.append({"kind": "call", "index": index, "row": row, "w0": rec["w0"], "w1": rec["w1"]})
                        index += 1
                        await asyncio.sleep(0.25)
                xev, dev = orc.stop()
                names = sorted({m["sender"] for m in dev if m["sender"].startswith(":")}
                               | {m["dest"] for m in dev if m["dest"].startswith(":")})
                pid_of = {n: bus_pid(address, n) for n in names} if address else {}
                fixture_names = [n for n, p in pid_of.items() if p == fixture.pid]
                driver_names = [n for n, p in pid_of.items() if p in driver_pids]
                grace = 30_000_000
                for wdw in windows:
                    lo, hi = wdw["w0"], wdw["w1"] + (grace if wdw["kind"] == "call" else 0)
                    x_in = [e for e in xev if "op" in e and lo <= e["t_ns"] <= hi]
                    d_in = [m for m in dev if lo <= m["t_ns"] <= hi and m["type"] == "method call"]
                    wdw["x_getimage"] = sum(1 for e in x_in if e["op"] == 73)
                    wdw["x_shmgetimage"] = sum(1 for e in x_in if e["op"] != 73)
                    wdw["atspi_calls_to_fixture"] = sum(1 for m in d_in if m["dest"] in fixture_names)
                    wdw["atspi_calls_from_driver"] = sum(1 for m in d_in if m["sender"] in driver_names)
                    wdw["atspi_calls_total"] = len(d_in)
                    emit({"event": "oracle_window", **wdw})
                unattributed = [e for e in xev if "op" in e and not any(
                    w["w0"] <= e["t_ns"] <= w["w1"] + grace for w in windows if w["kind"] == "call")]
                emit({"event": "oracle_summary", "x_events_total": sum(1 for e in xev if "op" in e),
                      "x_events_unattributed": len(unattributed), "x_ready": any(e.get("event") == "ready" for e in xev),
                      "dbus_messages_total": len(dev), "fixture_bus_names": len(fixture_names),
                      "driver_bus_names": len(driver_names), "a11y_bus": address is not None})
                # Usability of the remaining modality: act on an accessibility-only token.
                before = read_state(state_path) or {}
                rec = await call("accessibility_only", "usability", index, None)
                index += 1
                use: dict[str, Any] = {"event": "usability", "before_counter": before.get("counter"),
                                       "before_seq": before.get("seq"), "observe_index": rec["index"]}
                result = await session.call_tool("get_window_state", {
                    "pid": fixture.pid, "window_id": window_id, "include_screenshot": False, "session": label})
                structured = result.structuredContent or {}
                token = next((e.get("element_token") for e in structured.get("elements", [])
                              if e.get("label") == "Increment"), None)
                use["token_found"] = token is not None
                if token:
                    clk = await session.call_tool("click", {"pid": fixture.pid, "window_id": window_id,
                                                            "element_token": token, "delivery_mode": "background",
                                                            "session": label})
                    use["click_is_error"] = bool(clk.isError)
                    sc = clk.structuredContent or {}
                    use["click_structured"] = {k: sc.get(k) for k in ("path", "route", "effect", "verified") if k in sc}
                    end = time.monotonic() + 3
                    after = before
                    while time.monotonic() < end:
                        after = read_state(state_path) or {}
                        if after.get("seq", -1) > before.get("seq", -1):
                            break
                        time.sleep(0.005)
                    use["after_counter"] = after.get("counter")
                    use["after_seq"] = after.get("seq")
                    use["oracle_verified"] = (after.get("counter") == (before.get("counter") or 0) + 1
                                              and after.get("seq") == before.get("seq", -1) + 1)
                reader.take()
                emit(use)

            await driver_session(args.driver, "on", "m", ROW_ORDER, plan)

        elif args.mode == "negative":
            async def plan(call, tag, rows, session, label, window_id, driver_pids, reader):
                index = 0
                for rnd in range(args.warm_rounds + 1):
                    for row in rotated(rows, rnd):
                        emit(await call(row, "cold" if rnd == 0 else "warm", index, rnd))
                        index += 1
                emit({"event": "atspi_state", "a11y_bus_address_kind": (a11y_address() or "none").split(":")[0]})

            await driver_session(args.driver, "on", "n", ["both", "accessibility_only", "screenshot_only"], plan)

        elif args.mode == "smoke":
            async def plan(call, tag, rows, session, label, window_id, driver_pids, reader):
                index = 0
                for rnd in range(3):
                    for row in rotated(rows, rnd):
                        emit(await call(row, "smoke", index, rnd))
                        index += 1

            for tag, binary, marks in (("off_unset", args.driver, "unset"), ("off_empty", args.driver, "empty"),
                                       ("on", args.driver, "on"), ("main_unset", args.main_driver, "unset")):
                before_files = sorted(p.name for p in work.iterdir())
                await driver_session(binary, marks, tag, ROW_ORDER, plan)
                after_files = sorted(p.name for p in work.iterdir())
                emit({"event": "smoke_files", "tag": tag, "new_files": sorted(set(after_files) - set(before_files)),
                      "trace_file_exists": (work / f"phase-{tag}.jsonl").exists()})
    finally:
        fixture.terminate()
        try:
            fixture.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fixture.kill()
        emit({"event": "end", "loadavg": loadavg(), "lock_events": lock.events})
        ledger.close()
    print(f"done: {out / 'calls.jsonl'}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wt", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--main-driver", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--mode", choices=("measured", "negative", "smoke"), required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--rotation", type=int, default=0)
    parser.add_argument("--warm-rounds", type=int, default=20)
    parser.add_argument("--oracle-rounds", type=int, default=3)
    parser.add_argument("--lock", default=None)
    parser.add_argument("--window-attempts", type=int, default=60)
    parser.add_argument("--oracle-python", default=None)
    parser.add_argument("--recorder", default=None)
    args = parser.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ) \
            or not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: not inside the isolated X11 session")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
