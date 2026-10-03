"""OWN-20Q: helpers shared by the new harness files (measurement only, nothing here is Driver code).

* ``BusWatch``: ``dbus-monitor --binary`` (BecomeMonitor) on one private AT-SPI bus. Every message
  header is parsed; kept are the ``org.a11y.atspi.Action.DoAction`` calls with their replies,
  ``NameOwnerChanged`` (new and lost unique names, each new name attributed to its pid by the bus
  daemon's own ``GetConnectionUnixProcessID``, asked over one persistent connection of
  ``bus_pid_helper.py``) and ``org.freedesktop.DBus.Peer`` calls. It is the
  dbus-monitor oracle of the a11y bus and, inside ``markfree_proxy.py``, the observation point of the
  mark-free trigger (the DoAction reply as routed by the bus). Bus addresses are never written out.
* ``XRecord``: an X RECORD client on the private display (libXtst through ctypes, two connections
  owned by one thread). It records SetInputFocus, ChangeProperty of ``_NET_ACTIVE_WINDOW`` /
  ``_NET_CLIENT_LIST_STACKING``, SendEvent ClientMessages, ConfigureWindow stacking requests and the
  delivered FocusIn/FocusOut events of every client: the server-side focus and stacking oracle.
* ``start_fixture_env``: the canonical GTK3 fixture launch of ``harness_common.start_fixture`` with
  extra environment and an optional fixture script.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import select
import struct
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

import harness_common as hc

# ----------------------------------------------------------------------------- D-Bus wire parsing


def _align(pos: int, n: int) -> int:
    return (pos + n - 1) // n * n


def dbus_message_size(buf: bytes) -> int | None:
    """Total size of the message at the start of ``buf`` (None until the fixed header is there)."""
    if len(buf) < 16:
        return None
    end = "<" if buf[0:1] == b"l" else ">"
    body_len, fields_len = struct.unpack(end + "I", buf[4:8])[0], struct.unpack(end + "I", buf[12:16])[0]
    return _align(16 + fields_len, 8) + body_len


def parse_dbus(msg: bytes) -> dict[str, Any]:
    """Header fields of one complete message (and the 'sss' body of NameOwnerChanged)."""
    end = "<" if msg[0:1] == b"l" else ">"
    out: dict[str, Any] = {"type": msg[1]}
    out["serial"] = struct.unpack(end + "I", msg[8:12])[0]
    fields_len = struct.unpack(end + "I", msg[12:16])[0]
    pos, stop = 16, 16 + fields_len
    names = {1: "path", 2: "interface", 3: "member", 4: "error", 5: "reply_serial", 6: "destination",
             7: "sender", 8: "signature", 9: "unix_fds"}
    try:
        while pos < stop:
            pos = _align(pos, 8)
            code, slen = msg[pos], msg[pos + 1]
            sig = msg[pos + 2:pos + 2 + slen].decode()
            pos += 3 + slen
            if sig in ("s", "o"):
                pos = _align(pos, 4)
                n = struct.unpack(end + "I", msg[pos:pos + 4])[0]
                value: Any = msg[pos + 4:pos + 4 + n].decode(errors="replace")
                pos += 5 + n
            elif sig == "g":
                n = msg[pos]
                value = msg[pos + 1:pos + 1 + n].decode(errors="replace")
                pos += 2 + n
            elif sig == "u":
                pos = _align(pos, 4)
                value = struct.unpack(end + "I", msg[pos:pos + 4])[0]
                pos += 4
            else:
                break
            out[names.get(code, str(code))] = value
    except (IndexError, struct.error, UnicodeDecodeError):
        out["parse_error"] = True
    if out.get("member") == "NameOwnerChanged" and out.get("signature") == "sss":
        body = msg[_align(stop, 8):]
        args, p = [], 0
        try:
            for _ in range(3):
                p = _align(p, 4)
                n = struct.unpack(end + "I", body[p:p + 4])[0]
                args.append(body[p + 4:p + 4 + n].decode(errors="replace"))
                p += 5 + n
            out["args"] = args
        except (IndexError, struct.error):
            out["parse_error"] = True
    return out


def a11y_address() -> str | None:
    """The private AT-SPI bus address (org.a11y.Bus.GetAddress on the session bus)."""
    try:
        res = subprocess.run(["gdbus", "call", "--session", "--dest", "org.a11y.Bus", "--object-path",
                              "/org/a11y/bus", "--method", "org.a11y.Bus.GetAddress"],
                             capture_output=True, text=True, timeout=2.0)
    except (subprocess.TimeoutExpired, OSError):
        return None
    out = res.stdout.strip()
    if res.returncode == 0 and out.startswith("('"):
        return out[2:out.rindex("'")]
    return None


MONITOR_RULES = [
    "type='method_call',interface='org.a11y.atspi.Action',member='DoAction'",
    "type='method_return'",
    "type='error'",
    "type='signal',interface='org.freedesktop.DBus',member='NameOwnerChanged'",
    "type='method_call',interface='org.freedesktop.DBus.Peer'",
]


class BusWatch(threading.Thread):
    """dbus-monitor --binary on one bus; see the module docstring."""

    def __init__(self, address: str, tag: str, on_reply: Callable[[dict], None] | None = None,
                 on_call: Callable[[dict], None] | None = None, attribute_pids: bool = True) -> None:
        super().__init__(daemon=True)
        self.address = address
        self.tag = tag
        self.on_reply = on_reply
        self.on_call = on_call
        self.attribute_pids = attribute_pids
        self.proc: subprocess.Popen | None = None
        self.calls: dict[tuple[str, int], dict] = {}
        self.do_action: list[dict] = []
        self.names: list[dict] = []
        self.pings: list[dict] = []
        self.pids: dict[str, int | None] = {}
        self.messages = 0
        self.error: str | None = None
        self.started_wall_ns = 0
        self.ready = threading.Event()
        self._lock = threading.Lock()
        self.helper: subprocess.Popen | None = None
        self.helper_name: str | None = None
        if attribute_pids:
            henv = dict(os.environ)
            henv["OWN20Q_BUS_ADDRESS"] = address
            try:
                self.helper = subprocess.Popen(["/usr/bin/python3", str(Path(__file__).resolve().parent /
                                                                        "bus_pid_helper.py")], env=henv,
                                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                               stderr=subprocess.DEVNULL, text=True, bufsize=1)
                first = self.helper.stdout.readline().split()  # type: ignore[union-attr]
                self.helper_name = first[1] if len(first) == 2 and first[0] == "self" else None
                threading.Thread(target=self._read_helper, daemon=True).start()
            except OSError as exc:
                self.error = f"helper: {type(exc).__name__}"
                self.helper = None

    def run(self) -> None:
        try:
            self.proc = subprocess.Popen(["stdbuf", "-o0", "dbus-monitor", "--address", self.address, "--binary",
                                          *MONITOR_RULES], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError as exc:
            self.error = f"{type(exc).__name__}"
            self.ready.set()
            return
        self.started_wall_ns = time.time_ns()
        fd = self.proc.stdout.fileno()  # type: ignore[union-attr]
        buf = b""
        while True:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            now = time.time_ns()
            buf += chunk
            while True:
                size = dbus_message_size(buf)
                if size is None or len(buf) < size:
                    break
                msg, buf = buf[:size], buf[size:]
                self.messages += 1
                if self.messages == 1:
                    self.ready.set()
                self._handle(parse_dbus(msg), now)
        self.ready.set()

    def _handle(self, m: dict, now: int) -> None:
        t = m["type"]
        if t == 1 and m.get("member") == "DoAction" and m.get("interface") == "org.a11y.atspi.Action":
            rec = {"wall_ns": now, "serial": m["serial"], "sender": m.get("sender"),
                   "destination": m.get("destination"), "path": m.get("path")}
            with self._lock:
                self.calls[(str(m.get("sender")), m["serial"])] = rec
                self.do_action.append(rec)
            if self.on_call:
                self.on_call(rec)
        elif t in (2, 3) and m.get("reply_serial") is not None:
            key = (str(m.get("destination")), m["reply_serial"])
            call = self.calls.get(key)
            if call is not None and "reply_wall_ns" not in call and m.get("sender") == call.get("destination"):
                call["reply_wall_ns"] = now
                call["reply_type"] = "return" if t == 2 else "error"
                if t == 3:
                    call["reply_error"] = m.get("error")
                if self.on_reply:
                    self.on_reply(call)
        elif t == 4 and m.get("member") == "NameOwnerChanged" and m.get("args"):
            name, old, new = m["args"]
            if name.startswith(":"):
                rec = {"wall_ns": now, "name": name, "event": "new" if new and not old else
                       ("lost" if old and not new else "moved")}
                with self._lock:
                    self.names.append(rec)
                if rec["event"] == "new" and self.helper is not None and name != self.helper_name:
                    try:
                        self.helper.stdin.write(name + "\n")  # type: ignore[union-attr]
                        self.helper.stdin.flush()  # type: ignore[union-attr]
                    except OSError:
                        pass
        elif t == 1 and m.get("interface") == "org.freedesktop.DBus.Peer":
            with self._lock:
                self.pings.append({"wall_ns": now, "sender": m.get("sender"), "destination": m.get("destination"),
                                   "member": m.get("member")})

    def _read_helper(self) -> None:
        for line in self.helper.stdout:  # type: ignore[union-attr]
            parts = line.split()
            if len(parts) == 2:
                with self._lock:
                    self.pids[parts[0]] = int(parts[1]) if parts[1].lstrip("-").isdigit() else None

    def stop(self) -> dict[str, Any]:
        time.sleep(0.2)  # let late pid lookups land
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.join(timeout=3)
        if self.helper is not None:
            try:
                self.helper.stdin.close()  # type: ignore[union-attr]
                self.helper.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                self.helper.kill()
                self.helper.wait()
        return self.summary()

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {"tag": self.tag, "messages": self.messages, "error": self.error,
                    "helper_connected": self.helper_name is not None,
                    "started_wall_ns": self.started_wall_ns, "do_action": list(self.do_action),
                    "names": [dict(n, pid=self.pids.get(n["name"])) for n in self.names],
                    "pings": list(self.pings)}


def connections_of(watch: dict[str, Any], pid: int) -> dict[str, Any]:
    """The unique names a pid opened on a watched bus, and the Peer pings they sent."""
    names = [n["name"] for n in watch.get("names") or [] if n["event"] == "new" and n.get("pid") == pid]
    lost = [n["name"] for n in watch.get("names") or [] if n["event"] == "lost" and n["name"] in names]
    pings = [p for p in watch.get("pings") or [] if p.get("sender") in names]
    return {"opened": len(names), "lost": len(lost), "pings": len(pings),
            "unattributed_new": sum(1 for n in watch.get("names") or [] if n["event"] == "new" and n.get("pid") is None),
            "first_opened_wall_ns": min((n["wall_ns"] for n in watch.get("names") or []
                                         if n["event"] == "new" and n.get("pid") == pid), default=None),
            "lost_wall_ns": [n["wall_ns"] for n in watch.get("names") or [] if n["event"] == "lost" and n["name"] in names]}


# ----------------------------------------------------------------------------- X RECORD oracle

_X = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
_XTST = ctypes.CDLL(ctypes.util.find_library("Xtst") or "libXtst.so.6")


class _R8(ctypes.Structure):
    _fields_ = [("first", ctypes.c_ubyte), ("last", ctypes.c_ubyte)]


class _R16(ctypes.Structure):
    _fields_ = [("first", ctypes.c_ushort), ("last", ctypes.c_ushort)]


class _ExtRange(ctypes.Structure):
    _fields_ = [("ext_major", _R8), ("ext_minor", _R16)]


class _XRecordRange(ctypes.Structure):
    _fields_ = [("core_requests", _R8), ("core_replies", _R8), ("ext_requests", _ExtRange),
                ("ext_replies", _ExtRange), ("delivered_events", _R8), ("device_events", _R8),
                ("errors", _R8), ("client_started", ctypes.c_int), ("client_died", ctypes.c_int)]


class _Intercept(ctypes.Structure):
    _fields_ = [("id_base", ctypes.c_ulong), ("server_time", ctypes.c_ulong), ("client_seq", ctypes.c_ulong),
                ("category", ctypes.c_int), ("client_swapped", ctypes.c_int),
                ("data", ctypes.POINTER(ctypes.c_ubyte)), ("data_len", ctypes.c_ulong)]


_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(_Intercept))
_X.XOpenDisplay.restype = ctypes.c_void_p
_X.XOpenDisplay.argtypes = [ctypes.c_char_p]
_X.XCloseDisplay.argtypes = [ctypes.c_void_p]
_X.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
_X.XConnectionNumber.argtypes = [ctypes.c_void_p]
_X.XInternAtom.restype = ctypes.c_ulong
_X.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
_X.XFree.argtypes = [ctypes.c_void_p]
_XTST.XRecordAllocRange.restype = ctypes.POINTER(_XRecordRange)
_XTST.XRecordCreateContext.restype = ctypes.c_ulong
_XTST.XRecordCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_ulong), ctypes.c_int,
                                       ctypes.POINTER(ctypes.POINTER(_XRecordRange)), ctypes.c_int]
_XTST.XRecordEnableContextAsync.argtypes = [ctypes.c_void_p, ctypes.c_ulong, _CALLBACK, ctypes.c_void_p]
_XTST.XRecordProcessReplies.argtypes = [ctypes.c_void_p]
_XTST.XRecordDisableContext.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
_XTST.XRecordFreeContext.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
_XTST.XRecordFreeData.argtypes = [ctypes.POINTER(_Intercept)]

SET_INPUT_FOCUS, CHANGE_PROPERTY, SEND_EVENT, CONFIGURE_WINDOW = 42, 18, 25, 12
FOCUS_IN, FOCUS_OUT, CLIENT_MESSAGE = 9, 10, 33


class XRecord(threading.Thread):
    """X RECORD oracle; see the module docstring. ``records`` rows: [wall_ns, kind, id_base, ...]."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.records: list[list[Any]] = []
        self.error: str | None = None
        self.ready = threading.Event()
        self.stop_flag = threading.Event()
        self.atoms: dict[str, int] = {}
        self._cb = _CALLBACK(self._on_data)

    def _on_data(self, _closure: Any, data_p: Any) -> None:
        try:
            d = data_p.contents
            now = time.time_ns()
            if d.category in (0, 1) and d.data_len:
                raw = ctypes.string_at(d.data, d.data_len * 4)
                self._decode(now, d.id_base, d.server_time, d.category, raw)
        finally:
            _XTST.XRecordFreeData(data_p)

    def _decode(self, now: int, base: int, stime: int, category: int, raw: bytes) -> None:
        u32 = lambda o: struct.unpack("<I", raw[o:o + 4])[0]  # noqa: E731 (little-endian clients only)
        if category == 1:  # from a client: a request
            op = raw[0]
            if op == SET_INPUT_FOCUS:
                self.records.append([now, "set_input_focus", base, stime, u32(4), raw[1]])
            elif op == CHANGE_PROPERTY and len(raw) >= 24:
                prop = u32(8)
                if prop in (self.atoms["active"], self.atoms["stacking"]) and raw[16] == 32:
                    n = u32(20)
                    vals = [u32(24 + 4 * i) for i in range(min(n, (len(raw) - 24) // 4))]
                    kind = "active" if prop == self.atoms["active"] else "stacking"
                    self.records.append([now, kind, base, stime, u32(4), vals[-1:] if kind == "stacking" else vals,
                                         len(vals)])
            elif op == SEND_EVENT and len(raw) >= 44:
                ev = raw[12:44]
                if (ev[0] & 0x7F) == CLIENT_MESSAGE and struct.unpack("<I", ev[8:12])[0] == self.atoms["active"]:
                    self.records.append([now, "activate_request", base, stime, struct.unpack("<I", ev[4:8])[0],
                                         struct.unpack("<I", ev[12:16])[0]])
            elif op == CONFIGURE_WINDOW and len(raw) >= 12:
                mask = struct.unpack("<H", raw[8:10])[0]
                if mask & 0x40:  # StackMode
                    nvals = bin(mask & 0x7F).count("1")
                    stack_mode = u32(12 + 4 * (nvals - 1)) if len(raw) >= 12 + 4 * nvals else None
                    self.records.append([now, "restack", base, stime, u32(4), stack_mode])
        else:  # from the server: a delivered event
            et = raw[0] & 0x7F
            if et in (FOCUS_IN, FOCUS_OUT) and len(raw) >= 32:
                self.records.append([now, "focus_in" if et == FOCUS_IN else "focus_out", base, stime, u32(4),
                                     raw[1], raw[8]])

    def run(self) -> None:
        display = os.environ.get("DISPLAY", "").encode() or None
        ctrl = _X.XOpenDisplay(display)
        data = _X.XOpenDisplay(display)
        if not ctrl or not data:
            self.error = "cannot open the private DISPLAY"
            self.ready.set()
            return
        try:
            self.atoms = {"active": int(_X.XInternAtom(ctrl, b"_NET_ACTIVE_WINDOW", 0)),
                          "stacking": int(_X.XInternAtom(ctrl, b"_NET_CLIENT_LIST_STACKING", 0))}
            specs = [("core_requests", SET_INPUT_FOCUS), ("core_requests", CHANGE_PROPERTY),
                     ("core_requests", SEND_EVENT), ("core_requests", CONFIGURE_WINDOW)]
            ranges = []
            for field, op in specs:
                r = _XTST.XRecordAllocRange()
                getattr(r.contents, field).first = op
                getattr(r.contents, field).last = op
                ranges.append(r)
            r = _XTST.XRecordAllocRange()
            r.contents.delivered_events.first = FOCUS_IN
            r.contents.delivered_events.last = FOCUS_OUT
            ranges.append(r)
            arr = (ctypes.POINTER(_XRecordRange) * len(ranges))(*ranges)
            clients = (ctypes.c_ulong * 1)(3)  # XRecordAllClients
            ctx = _XTST.XRecordCreateContext(ctrl, 0x01, clients, 1, arr, len(ranges))  # XRecordFromServerTime
            _X.XSync(ctrl, 0)
            if not ctx or not _XTST.XRecordEnableContextAsync(data, ctx, self._cb, None):
                self.error = "RECORD context could not be enabled"
                self.ready.set()
                return
            fd = _X.XConnectionNumber(data)
            self.ready.set()
            while not self.stop_flag.is_set():
                readable, _, _ = select.select([fd], [], [], 0.02)
                _XTST.XRecordProcessReplies(data)
            _XTST.XRecordDisableContext(ctrl, ctx)
            _X.XSync(ctrl, 0)
            end = time.monotonic() + 0.3
            while time.monotonic() < end:
                _XTST.XRecordProcessReplies(data)
                time.sleep(0.01)
            _XTST.XRecordFreeContext(ctrl, ctx)
            for r in ranges:
                _X.XFree(r)
        except Exception as exc:  # recorded, never raised into the trial
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            self.ready.set()
            _X.XCloseDisplay(ctrl)
            _X.XCloseDisplay(data)

    def stop(self) -> dict[str, Any]:
        self.stop_flag.set()
        self.join(timeout=3)
        return {"error": self.error, "atoms": self.atoms, "records": self.records}


def record_view(rec: dict[str, Any], since_wall_ns: int, reference_window: int, decoy: int) -> dict[str, Any]:
    """Server-side focus/stacking facts after ``since_wall_ns`` (the click call), from X RECORD."""
    rows = [r for r in rec.get("records") or [] if r[0] >= since_wall_ns]
    actives = [r for r in rows if r[1] == "active"]
    wm = {r[2] for r in actives}  # only the window manager writes _NET_ACTIVE_WINDOW
    stack = [r for r in rows if r[1] == "stacking"]
    focus_sets = [r for r in rows if r[1] == "set_input_focus"]
    decoy_set = next((r for r in focus_sets if r[4] == decoy and r[2] not in wm), None)
    steal_ns = decoy_set[0] if decoy_set else None
    after = [r for r in rows if steal_ns is not None and r[0] > steal_ns]
    restore_requests = [r for r in after if r[2] not in wm and (
        (r[1] == "activate_request" and r[4] == reference_window) or
        (r[1] == "set_input_focus" and r[4] == reference_window))]
    return {
        "error": rec.get("error"),
        "rows": len(rows),
        "steal_set_focus_wall_ns": steal_ns,
        "active_changes": [[r[0], r[5][0] if r[5] else 0] for r in actives],
        "final_active": (actives[-1][5] or [0])[0] if actives else None,
        "final_stacking_top": (stack[-1][5] or [0])[0] if stack else None,
        "restore_requests": len(restore_requests),
        "first_restore_request_wall_ns": restore_requests[0][0] if restore_requests else None,
        "focus_in_decoy": sum(1 for r in rows if r[1] == "focus_in" and r[4] == decoy),
    }


# ----------------------------------------------------------------------------- fixture


def start_fixture_env(wt: Path, state_path: Path, log_path: Path, extra: dict[str, str] | None = None,
                      script: Path | None = None) -> subprocess.Popen:
    fenv = dict(os.environ)
    fenv["CUA_GTK3_TASK_STATE"] = str(state_path)
    fenv.update(extra or {})
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(["/usr/bin/python3", str(script or (wt / hc.FIXTURE_REL))], env=fenv,
                            stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 15
    while hc.read_state(state_path) is None:
        if time.monotonic() > deadline or proc.poll() is not None:
            raise RuntimeError("fixture did not publish its state file")
        time.sleep(0.02)
    time.sleep(1.0)  # AT-SPI registration settle (as R2-04 / N-01R / N-02 / OWN-20G)
    return proc


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True)
