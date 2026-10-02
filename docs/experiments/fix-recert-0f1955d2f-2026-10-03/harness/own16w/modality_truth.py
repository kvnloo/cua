#!/usr/bin/env python3
"""OWN-16W: observation-modality producer truth on headless sway (native Wayland + Xwayland) and X11.

Copied from the OWN-16 packet (7a4f3252a, docs/experiments/own-16-modality-truth-2026-10-02/
modality_truth.py, sha256 ead359ea...) and adapted; the diff is harness-origin.diff.

Runs INSIDE a private session (cua-sway-session.sh or cua-x11-session.sh). Starts the canonical
GTK3 fixture in task mode (CUA_GTK3_TASK_STATE), opens one Driver MCP stdio session and calls
get_window_state on the task window with each selector row. Per call it records the Driver's
measurement-only producer marks (CUA_DRIVER_PHASE_TRACE_FILE: capture_window /
capture_root_region / atspi_walk enter+exit with invocation ordinals), the response shape and
metadata verbatim, element/coordinate integrity, client wall time and MCP response bytes.

Environment modes (--env-mode):
  sway-wayland   GTK3 as a native Wayland client (GDK_BACKEND=wayland); Driver opted into its
                 native-Wayland backend (CUA_DRIVER_RS_ENABLE_WAYLAND=1, WAYLAND_DISPLAY, SWAYSOCK).
  sway-xwayland  GTK3 under the private Xwayland (GDK_BACKEND=x11, WAYLAND_DISPLAY removed);
                 Driver on its X11 backend (WAYLAND_DISPLAY removed, no opt-in).
  x11            private Xvfb (cua-x11-session.sh); as OWN-16.

Run modes (--mode):
  truth     1 cold call per row, then --warm-rounds rounds (row order rotated), with the
            independent oracles running for the WHOLE block so every counted call is covered:
            X RECORD (GetImage / ShmGetImage from all X clients), dbus-monitor on the private
            AT-SPI bus, and (sway, WAYLAND_DEBUG=server in the compositor) the compositor's own
            protocol log. 100 ms gap between calls for attribution. Then one token click.
  timing    no oracles: warm-up call per row, then --pairs AB/BA pairs per comparison
            (both vs screenshot_only, both vs accessibility_only).
  negative  session without the private AT-SPI registry: accessibility requested.
  smoke     default-off smoke: --driver with marks unset / empty / on, then --alt-driver unset.

Nothing here changes Driver behaviour.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
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

# Pre-registered selector rows (PREREG.json "rows").
ROWS: dict[str, dict[str, Any]] = {
    "both": {"include_accessibility_tree": True, "include_screenshot": True},
    "screenshot_only": {"include_accessibility_tree": False},
    "accessibility_only": {"include_screenshot": False},
    "neither": {"include_accessibility_tree": False, "include_screenshot": False},
    "legacy_omitted": {},
    "unknown_field": {"include_tree": False},
    "string_false": {"include_screenshot": "false"},
    "string_true": {"include_screenshot": "true"},
}
PRODUCER_SCOPES = ("capture_window", "capture_root_region", "atspi_walk")
META_KEYS = (
    "element_count", "total_element_count", "returned_element_count", "elements_complete",
    "truncated", "truncation_reason", "nodes_visited", "nodes_pending", "bounds_complete",
    "walk_elapsed_ms", "degraded", "degraded_reason", "escalation", "screenshot_width",
    "screenshot_height", "screenshot_frame_valid", "screenshot_error", "frame_scale",
    "screenshot_original_width", "screenshot_mime_type", "window_bounds", "code", "refusal",
    "coordinate_frame", "screenshot_composited", "popup",
)
CALL_GAP_S = 0.1
GRACE_NS = 30_000_000
# Compositor-side capture requests (wlr-screencopy and ext-image-copy-capture).
WL_CAPTURE_REQ = re.compile(
    r"^(zwlr_screencopy_manager_v1\.capture_output(_region)?"
    r"|ext_image_copy_capture_manager_v1\.create_session"
    r"|ext_output_image_capture_source_manager_v1\.create_source"
    r"|ext_foreign_toplevel_image_capture_source_manager_v1\.create_source)$")
WL_LINE = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\.(\d{6})\]\s+(->\s+)?([A-Za-z0-9_]+)#(\d+)\.([A-Za-z0-9_]+)\(")


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


def title_matches(title: Any) -> bool:
    # Native Wayland titles carry a " [app_id]" suffix (stack-sway finding).
    return isinstance(title, str) and (title == WINDOW_TITLE or title.startswith(WINDOW_TITLE + " ["))


# --------------------------------------------------------------------------- integrity
def integrity(structured: dict[str, Any], png: tuple[int, int] | None) -> dict[str, Any]:
    """Screenshot dims checks (always, fixing OWN-16 D1) + element frame checks when elements exist."""
    wb = structured.get("window_bounds") or {}
    elements = structured.get("elements")
    out: dict[str, Any] = {"window_bounds": wb or None}
    sw, sh = structured.get("screenshot_width"), structured.get("screenshot_height")
    scale = structured.get("frame_scale") or 1.0
    if sw is not None and wb:
        out["screenshot_matches_window"] = (abs(sw - wb["width"] * scale) <= 1.0
                                            and abs(sh - wb["height"] * scale) <= 1.0)
    if png is not None and sw is not None:
        out["png_matches_reported_dims"] = (png[0] == sw and png[1] == sh)
    if not isinstance(elements, list):
        out["elements_present"] = False
        return out
    out["elements_present"] = True
    out["element_entries"] = len(elements)
    framed = [e for e in elements if isinstance(e.get("frame"), dict)]
    out["framed"] = len(framed)
    outside, overshoot = 0, 0.0
    sf_outside, sf_mismatch, sf_count = 0, 0, 0
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
    canon = sorted(
        (e.get("element_index"), e.get("role"), e.get("label"), e.get("value"),
         json.dumps(e.get("frame"), sort_keys=True))
        for e in elements
    )
    out["elements_digest"] = hashlib.sha256(json.dumps(canon).encode()).hexdigest()[:16]
    out["frames"] = {str(e.get("label")): e.get("frame") for e in framed if e.get("label")}
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


def parse_wayland_log(lines: list[str], anchor_ns: int) -> list[dict[str, Any]]:
    """libwayland server debug lines '[HH:MM:SS.uuuuuu] iface#id.msg(' (UTC time of day; requests have
    no '->'). Converted to epoch ns on the UTC day of anchor_ns (next day if it wraps)."""
    day0 = (anchor_ns // 1_000_000_000) // 86400 * 86400
    out = []
    for line in lines:
        m = WL_LINE.match(line)
        if not m:
            continue
        hh, mm, ss, us, arrow, iface, _oid, msg = m.groups()
        sod = int(hh) * 3600 + int(mm) * 60 + int(ss)
        t_ns = (day0 + sod) * 1_000_000_000 + int(us) * 1000
        if t_ns < anchor_ns - 43200 * 10**9:
            t_ns += 86400 * 10**9
        out.append({"t_ns": t_ns, "dir": "event" if arrow else "request", "iface": iface,
                    "msg": msg, "sig": f"{iface}.{msg}"})
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
    """X RECORD (GetImage/ShmGetImage from all clients) + dbus-monitor on the a11y bus +
    the compositor's own protocol log (sway, WAYLAND_DEBUG=server)."""

    def __init__(self, out: Path, python: str, recorder: str, address: str | None,
                 wl_log: Path | None) -> None:
        self.out = out
        self.address = address
        self.xlog = out / "xrecord.jsonl"
        self.dlog = out / "dbus-monitor.log"
        self.wl_log = wl_log
        self.wl_offset = wl_log.stat().st_size if wl_log and wl_log.exists() else 0
        self.xproc = (subprocess.Popen([python, recorder, str(self.xlog)], stdout=subprocess.DEVNULL,
                                       stderr=open(out / "xrecord.err", "w"))
                      if os.environ.get("DISPLAY") else None)
        self.dstream = open(self.dlog, "w", encoding="utf-8")
        self.dproc = (subprocess.Popen(["dbus-monitor", "--address", address, "--monitor"],
                                       stdout=self.dstream, stderr=subprocess.STDOUT)
                      if address else None)
        deadline = time.monotonic() + 5
        while self.xproc is not None and time.monotonic() < deadline:
            if self.xlog.exists() and "ready" in self.xlog.read_text():
                break
            time.sleep(0.02)
        time.sleep(0.3)

    def stop(self, anchor_ns: int):
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
        xev = ([json.loads(x) for x in self.xlog.read_text().splitlines() if x.strip()]
               if self.xlog.exists() else [])
        dev = parse_monitor(self.dlog.read_text(errors="replace"))
        wev: list[dict[str, Any]] = []
        wl_meta: dict[str, Any] = {"enabled": False}
        if self.wl_log is not None and self.wl_log.exists():
            with open(self.wl_log, "rb") as stream:
                stream.seek(self.wl_offset)
                lines = stream.read().decode(errors="replace").splitlines()
            wev = parse_wayland_log(lines, anchor_ns)
            # Keep only capture-related protocol lines (sway's own log lines carry local paths).
            keep = [ln for ln in lines if WL_LINE.match(ln) and re.search(
                r"screencopy|image_copy_capture|image_capture_source", ln)]
            (self.out / "wayland-capture-lines.log").write_text("\n".join(keep) + ("\n" if keep else ""))
            wl_meta = {"enabled": True, "protocol_lines": len(wev), "capture_lines_kept": len(keep),
                       "requests": sum(1 for e in wev if e["dir"] == "request")}
        return xev, dev, wev, wl_meta


# --------------------------------------------------------------------------- harness
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


def fixture_environment(env_mode: str) -> dict[str, str]:
    env = dict(os.environ)
    if env_mode == "sway-wayland":
        env["GDK_BACKEND"] = "wayland"
    elif env_mode == "sway-xwayland":
        env.pop("WAYLAND_DISPLAY", None)
        env["GDK_BACKEND"] = "x11"
    return env


def driver_env_for(env_mode: str, base: dict[str, str]) -> dict[str, str]:
    env = dict(base)
    env.pop("CUA_DRIVER_RS_ENABLE_WAYLAND", None)
    if env_mode == "sway-wayland":
        env["CUA_DRIVER_RS_ENABLE_WAYLAND"] = "1"
        if os.environ.get("SWAYSOCK"):
            env["SWAYSOCK"] = os.environ["SWAYSOCK"]
    elif env_mode == "sway-xwayland":
        env.pop("WAYLAND_DISPLAY", None)
    return env


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
    ledger = open(out / "calls.jsonl", "w", encoding="utf-8")
    rows_selected = args.rows.split(",") if args.rows else list(ROWS)
    for row in rows_selected:
        if row not in ROWS:
            raise SystemExit(f"unknown row {row}")

    def emit(rec: dict[str, Any]) -> None:
        ledger.write(json.dumps(rec, sort_keys=True) + "\n")
        ledger.flush()

    fixture_env = fixture_environment(args.env_mode)
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
    sway_run = os.environ.get("CUA_SWAY_RUN")
    wl_debug = "server" in os.environ.get("WAYLAND_DEBUG", "")
    wl_log = Path(sway_run) / "sway.log" if (sway_run and wl_debug) else None
    emit({"event": "meta", "mode": args.mode, "env_mode": args.env_mode, "label": args.label,
          "binary_tag": args.binary_tag, "rotation": args.rotation, "warm_rounds": args.warm_rounds,
          "pairs": args.pairs, "fixture_pid": fixture.pid, "window_title": WINDOW_TITLE,
          "fixture_gdk_backend": fixture_env.get("GDK_BACKEND"),
          "fixture_wayland_display_set": "WAYLAND_DISPLAY" in fixture_env,
          "a11y_bus_address_kind": (address.split(":")[0] if address else None),
          "env_atspi_session": os.environ.get("CUA_SESSION_ATSPI"), "rows": {r: ROWS[r] for r in rows_selected},
          "compositor_protocol_log": wl_log is not None, "loadavg": loadavg()})

    async def driver_session(binary: str, marks: str, tag: str, plan) -> None:
        """marks: 'on' (file path), 'unset', 'empty'."""
        env = driver_env_for(args.env_mode, driver_environment())
        env.pop("CUA_DRIVER_PHASE_TRACE_FILE", None)
        phase_path = work / f"phase-{tag}.jsonl"
        if marks == "on":
            phase_path.write_text("", encoding="utf-8")
            env["CUA_DRIVER_PHASE_TRACE_FILE"] = str(phase_path)
        elif marks == "empty":
            env["CUA_DRIVER_PHASE_TRACE_FILE"] = ""
        reader = MarkReader(phase_path if marks == "on" else None)
        params = StdioServerParameters(command=binary, args=["mcp"], env=env)
        label = f"own16w-{uuid.uuid4().hex[:8]}"
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                t0 = time.perf_counter_ns()
                await session.initialize()
                init_ms = (time.perf_counter_ns() - t0) / 1e6
                driver_pids = child_pids("cua-driver")
                window_id = None
                seen: list[Any] = []
                res = None
                t_find = time.monotonic()
                for _ in range(args.window_attempts):
                    res = await session.call_tool("list_windows", {"pid": fixture.pid, "session": label})
                    wins = (res.structuredContent or {}).get("windows", [])
                    seen = [(w.get("title"), w.get("is_on_screen")) for w in wins]
                    hits = [w for w in wins if title_matches(w.get("title")) and w.get("is_on_screen") is not False]
                    if hits:
                        window_id = int(hits[0]["window_id"])
                        break
                    await asyncio.sleep(0.25)
                if window_id is None:
                    emit({"event": "window_not_found", "tag": tag, "seen": seen,
                          "is_error": bool(res.isError) if res is not None else None,
                          "content_head": [getattr(c, "text", "")[:300] for c in ((res.content if res else None) or [])]})
                    raise RuntimeError("task window did not appear")
                reader.take()
                emit({"event": "driver_session", "tag": tag, "binary": Path(binary).name, "marks": marks,
                      "init_ms": init_ms, "window_found": True, "window_title_seen": seen,
                      "driver_child_count": len(driver_pids),
                      "driver_env_wayland_optin": env.get("CUA_DRIVER_RS_ENABLE_WAYLAND"),
                      "driver_env_wayland_display_set": "WAYLAND_DISPLAY" in env,
                      "driver_env_swaysock_set": "SWAYSOCK" in env,
                      "window_find_ms": (time.monotonic() - t_find) * 1e3})

                async def call(row: str, phase: str, index: int, rnd: int | None, **extra: Any) -> dict[str, Any]:
                    arguments = {"pid": fixture.pid, "window_id": window_id, **ROWS[row], "session": label}
                    reader.take()
                    rec: dict[str, Any] = {"event": "call", "tag": tag, "row": row, "phase": phase,
                                           "index": index, "round": rnd, "loadavg": loadavg(), **extra,
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

                await plan(call, tag, session, label, window_id, driver_pids, reader)

    def rotated(rows: list[str], k: int) -> list[str]:
        k %= len(rows)
        return rows[k:] + rows[:k]

    async def usability(call, session, label, window_id, index) -> None:
        """Act on an accessibility-only token; the fixture's own state file is the oracle."""
        before = read_state(state_path) or {}
        rec = await call("accessibility_only", "usability", index, None)
        emit(rec)
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
            use["click_structured"] = {k: sc.get(k) for k in ("path", "route", "effect", "verified", "code") if k in sc}
            if clk.isError:
                use["click_error_text"] = next((getattr(c, "text", "")[:600] for c in (clk.content or [])), None)
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
        emit(use)

    try:
        if args.mode == "truth":
            async def plan(call, tag, session, label, window_id, driver_pids, reader):
                index = 0
                oracle_dir = out / "oracle"
                oracle_dir.mkdir(exist_ok=True)
                anchor = time.time_ns()
                orc = Oracle(oracle_dir, args.oracle_python, args.recorder, address, wl_log)
                idle0 = time.time_ns()
                await asyncio.sleep(1.0)
                idle1 = time.time_ns()
                windows = [{"kind": "idle", "w0": idle0, "w1": idle1}]
                for rnd in range(args.warm_rounds + 1):
                    for row in rotated(rows_selected, args.rotation + rnd):
                        rec = await call(row, "cold" if rnd == 0 else "warm", index, rnd)
                        emit(rec)
                        windows.append({"kind": "call", "index": index, "row": row, "w0": rec["w0"], "w1": rec["w1"]})
                        index += 1
                        await asyncio.sleep(CALL_GAP_S)
                idle2 = time.time_ns()
                await asyncio.sleep(1.0)
                windows.append({"kind": "idle", "w0": idle2, "w1": time.time_ns()})
                xev, dev, wev, wl_meta = orc.stop(anchor)
                names = sorted({m["sender"] for m in dev if m["sender"].startswith(":")}
                               | {m["dest"] for m in dev if m["dest"].startswith(":")})
                pid_of = {n: bus_pid(address, n) for n in names} if address else {}
                fixture_names = [n for n, p in pid_of.items() if p == fixture.pid]
                driver_names = [n for n, p in pid_of.items() if p in driver_pids]
                wl_req = [e for e in wev if e["dir"] == "request"]
                for wdw in windows:
                    lo, hi = wdw["w0"], wdw["w1"] + (GRACE_NS if wdw["kind"] == "call" else 0)
                    x_in = [e for e in xev if "op" in e and lo <= e["t_ns"] <= hi]
                    d_in = [m for m in dev if lo <= m["t_ns"] <= hi and m["type"] == "method call"]
                    w_in = [e for e in wl_req if lo <= e["t_ns"] <= hi]
                    wdw["x_getimage"] = sum(1 for e in x_in if e["op"] == 73)
                    wdw["x_shmgetimage"] = sum(1 for e in x_in if e["op"] != 73)
                    wdw["atspi_calls_to_fixture"] = sum(1 for m in d_in if m["dest"] in fixture_names)
                    # Walk signature: per-node state reads. The native-Wayland window-identity lookup
                    # (crate::atspi::list_windows via list_windows_dispatch) sends no GetState.
                    wdw["atspi_getstate_to_fixture"] = sum(
                        1 for m in d_in if m["dest"] in fixture_names
                        and m.get("interface") == "org.a11y.atspi.Accessible" and m.get("member") == "GetState")
                    wdw["atspi_calls_from_driver"] = sum(1 for m in d_in if m["sender"] in driver_names)
                    wdw["atspi_calls_total"] = len(d_in)
                    wdw["wl_capture_requests"] = sum(1 for e in w_in if WL_CAPTURE_REQ.match(e["sig"]))
                    wdw["wl_capture_sigs"] = sorted({e["sig"] for e in w_in if WL_CAPTURE_REQ.match(e["sig"])})
                    wdw["wl_requests_total"] = len(w_in)
                    emit({"event": "oracle_window", **wdw})
                call_windows = [w for w in windows if w["kind"] == "call"]

                def attributed(t: int) -> bool:
                    return any(w["w0"] <= t <= w["w1"] + GRACE_NS for w in call_windows)
                emit({"event": "oracle_summary",
                      "x_events_total": sum(1 for e in xev if "op" in e),
                      "x_events_unattributed": sum(1 for e in xev if "op" in e and not attributed(e["t_ns"])),
                      "x_ready": any(e.get("event") == "ready" for e in xev),
                      "dbus_messages_total": len(dev), "fixture_bus_names": len(fixture_names),
                      "driver_bus_names": len(driver_names), "a11y_bus": address is not None,
                      "atspi_calls_to_fixture_unattributed": sum(
                          1 for m in dev if m["type"] == "method call" and m["dest"] in fixture_names
                          and not attributed(m["t_ns"])),
                      "atspi_getstate_to_fixture_unattributed": sum(
                          1 for m in dev if m["type"] == "method call" and m["dest"] in fixture_names
                          and m.get("member") == "GetState" and not attributed(m["t_ns"])),
                      "wl": wl_meta,
                      "wl_capture_requests_total": sum(1 for e in wl_req if WL_CAPTURE_REQ.match(e["sig"])),
                      "wl_capture_requests_unattributed": sum(
                          1 for e in wl_req if WL_CAPTURE_REQ.match(e["sig"]) and not attributed(e["t_ns"]))})
                await usability(call, session, label, window_id, index)
                reader.take()

            await driver_session(args.driver, "on", "t", plan)

        elif args.mode == "timing":
            async def plan(call, tag, session, label, window_id, driver_pids, reader):
                index = 0
                for row in ("both", "screenshot_only", "accessibility_only"):
                    emit(await call(row, "warmup", index, None))
                    index += 1
                comparisons = ["screenshot_only", "accessibility_only"]
                for p in range(args.pairs):
                    for comp in rotated(comparisons, p):
                        order = ["both", comp] if (p + args.rotation) % 2 == 0 else [comp, "both"]
                        for pos, row in enumerate(order):
                            emit(await call(row, "timed", index, p, pair=p, comparison=comp,
                                            order="AB" if order[0] == "both" else "BA", position=pos))
                            index += 1

            await driver_session(args.driver, "on", "b", plan)

        elif args.mode == "negative":
            async def plan(call, tag, session, label, window_id, driver_pids, reader):
                index = 0
                rows = ["both", "accessibility_only", "screenshot_only"]
                for rnd in range(args.warm_rounds + 1):
                    for row in rotated(rows, rnd):
                        emit(await call(row, "cold" if rnd == 0 else "warm", index, rnd))
                        index += 1
                emit({"event": "atspi_state", "a11y_bus_address_kind": (a11y_address() or "none").split(":")[0]})

            await driver_session(args.driver, "on", "n", plan)

        elif args.mode == "smoke":
            async def plan(call, tag, session, label, window_id, driver_pids, reader):
                index = 0
                for rnd in range(3):
                    for row in rotated(rows_selected, rnd):
                        emit(await call(row, "smoke", index, rnd))
                        index += 1

            for tag, binary, marks in (("off_unset", args.driver, "unset"), ("off_empty", args.driver, "empty"),
                                       ("on", args.driver, "on"), ("alt_unset", args.alt_driver, "unset")):
                before_files = sorted(p.name for p in work.iterdir())
                await driver_session(binary, marks, tag, plan)
                after_files = sorted(p.name for p in work.iterdir())
                emit({"event": "smoke_files", "tag": tag, "binary": Path(binary).name,
                      "new_files": sorted(set(after_files) - set(before_files)),
                      "trace_file_exists": (work / f"phase-{tag}.jsonl").exists()})
    finally:
        fixture.terminate()
        try:
            fixture.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fixture.kill()
        emit({"event": "end", "loadavg": loadavg()})
        ledger.close()
    print(f"done: {out / 'calls.jsonl'}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wt", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--alt-driver", default=None)
    parser.add_argument("--binary-tag", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--env-mode", choices=("sway-wayland", "sway-xwayland", "x11"), required=True)
    parser.add_argument("--mode", choices=("truth", "timing", "negative", "smoke"), required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--rows", default=None)
    parser.add_argument("--rotation", type=int, default=0)
    parser.add_argument("--warm-rounds", type=int, default=20)
    parser.add_argument("--pairs", type=int, default=21)
    parser.add_argument("--window-attempts", type=int, default=60)
    parser.add_argument("--oracle-python", default=None)
    parser.add_argument("--recorder", default=None)
    args = parser.parse_args()
    if any(k.startswith("HYPRLAND_") for k in os.environ):
        raise SystemExit("refusing: HYPRLAND_* set")
    if args.env_mode == "x11":
        if os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("DISPLAY"):
            raise SystemExit("refusing: not inside the isolated X11 session")
    else:
        run_dir = os.environ.get("CUA_SWAY_RUN", "")
        if not run_dir or not os.environ.get("XDG_RUNTIME_DIR", "").startswith(run_dir) \
                or not os.environ.get("WAYLAND_DISPLAY"):
            raise SystemExit("refusing: not inside the private sway session")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
