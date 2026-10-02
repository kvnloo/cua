"""N-01R: minimal X11 client (ctypes over libX11) for the focus-safety controls.

Runs only inside the isolated X11 session. Each object owns its own Display
connection and is used from one thread, so no XInitThreads is needed.

* ``FocusSampler``: an independent X client that samples ``XGetInputFocus`` and
  the root ``_NET_ACTIVE_WINDOW`` every 2 ms (the focus oracle).
* ``Decoy``: a pre-mapped plain X toplevel owned by the harness process; when
  armed it watches the trial's state file and, ``delay_ms`` after the app's
  state changes, activates itself (EWMH ``_NET_ACTIVE_WINDOW`` request, source
  2, plus raise and ``XSetInputFocus``): a late focus steal.
* ``client_list`` / ``active_window`` / ``activate``: one-shot reads and the
  pre-trial focus placement.

Nothing here talks to the Driver; it only observes and perturbs the private X
server.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import threading
import time
from typing import Any

_lib = ctypes.util.find_library("X11") or "libX11.so.6"
X = ctypes.CDLL(_lib)

Window = ctypes.c_ulong
Atom = ctypes.c_ulong


class XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", Window),
        ("message_type", Atom),
        ("format", ctypes.c_int),
        ("l", ctypes.c_long * 5),
    ]


class XEvent(ctypes.Union):
    _fields_ = [("xclient", XClientMessageEvent), ("pad", ctypes.c_long * 24)]


X.XOpenDisplay.restype = ctypes.c_void_p
X.XOpenDisplay.argtypes = [ctypes.c_char_p]
X.XCloseDisplay.argtypes = [ctypes.c_void_p]
X.XDefaultRootWindow.restype = Window
X.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
X.XInternAtom.restype = Atom
X.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
X.XGetInputFocus.argtypes = [ctypes.c_void_p, ctypes.POINTER(Window), ctypes.POINTER(ctypes.c_int)]
X.XGetWindowProperty.argtypes = [
    ctypes.c_void_p, Window, Atom, ctypes.c_long, ctypes.c_long, ctypes.c_int, Atom,
    ctypes.POINTER(Atom), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p),
]
X.XFree.argtypes = [ctypes.c_void_p]
X.XCreateSimpleWindow.restype = Window
X.XCreateSimpleWindow.argtypes = [
    ctypes.c_void_p, Window, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
    ctypes.c_uint, ctypes.c_ulong, ctypes.c_ulong,
]
X.XStoreName.argtypes = [ctypes.c_void_p, Window, ctypes.c_char_p]
X.XChangeProperty.argtypes = [
    ctypes.c_void_p, Window, Atom, Atom, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
]
X.XMapRaised.argtypes = [ctypes.c_void_p, Window]
X.XRaiseWindow.argtypes = [ctypes.c_void_p, Window]
X.XSetInputFocus.argtypes = [ctypes.c_void_p, Window, ctypes.c_int, ctypes.c_ulong]
X.XSendEvent.argtypes = [ctypes.c_void_p, Window, ctypes.c_int, ctypes.c_long, ctypes.POINTER(XEvent)]
X.XFlush.argtypes = [ctypes.c_void_p]
X.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
X.XDestroyWindow.argtypes = [ctypes.c_void_p, Window]

XA_CARDINAL = 6
XA_WINDOW = 33
ANY_PROPERTY_TYPE = 0
CLIENT_MESSAGE = 33
SUBSTRUCTURE_NOTIFY = 1 << 19
SUBSTRUCTURE_REDIRECT = 1 << 20
REVERT_TO_PARENT = 2


class Conn:
    def __init__(self) -> None:
        display = os.environ.get("DISPLAY", "").encode() or None
        self.dpy = X.XOpenDisplay(display)
        if not self.dpy:
            raise RuntimeError("cannot open the private DISPLAY")
        self.root = X.XDefaultRootWindow(self.dpy)
        self.a_active = X.XInternAtom(self.dpy, b"_NET_ACTIVE_WINDOW", 0)
        self.a_clients = X.XInternAtom(self.dpy, b"_NET_CLIENT_LIST", 0)
        self.a_pid = X.XInternAtom(self.dpy, b"_NET_WM_PID", 0)

    def close(self) -> None:
        if self.dpy:
            X.XCloseDisplay(self.dpy)
            self.dpy = None

    def _windows_prop(self, window: int, atom: int) -> list[int]:
        actual_type = Atom()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        after = ctypes.c_ulong()
        data = ctypes.c_void_p()
        status = X.XGetWindowProperty(
            self.dpy, window, atom, 0, 1024, 0, ANY_PROPERTY_TYPE, ctypes.byref(actual_type),
            ctypes.byref(actual_format), ctypes.byref(nitems), ctypes.byref(after), ctypes.byref(data),
        )
        if status != 0 or not data.value:
            return []
        try:
            if actual_format.value != 32:
                return []
            arr = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))
            return [int(arr[i]) for i in range(nitems.value)]
        finally:
            X.XFree(data)

    def focus(self) -> int:
        window = Window()
        revert = ctypes.c_int()
        X.XGetInputFocus(self.dpy, ctypes.byref(window), ctypes.byref(revert))
        return int(window.value)

    def active(self) -> int:
        values = self._windows_prop(self.root, self.a_active)
        return values[0] if values else 0

    def clients(self) -> list[int]:
        return self._windows_prop(self.root, self.a_clients)

    def window_pid(self, window: int) -> int | None:
        values = self._windows_prop(window, self.a_pid)
        return values[0] if values else None

    def request_activate(self, window: int) -> None:
        """EWMH activation request (source 2 = pager/user-level, honoured by openbox)."""
        event = XEvent()
        event.xclient.type = CLIENT_MESSAGE
        event.xclient.send_event = 1
        event.xclient.window = window
        event.xclient.message_type = self.a_active
        event.xclient.format = 32
        event.xclient.l[0] = 2
        event.xclient.l[1] = 0
        event.xclient.l[2] = 0
        X.XSendEvent(self.dpy, self.root, 0, SUBSTRUCTURE_NOTIFY | SUBSTRUCTURE_REDIRECT, ctypes.byref(event))
        X.XFlush(self.dpy)


def snapshot() -> dict[str, Any]:
    conn = Conn()
    try:
        clients = conn.clients()
        return {"focus": conn.focus(), "active": conn.active(), "clients": clients,
                "client_pids": {str(w): conn.window_pid(w) for w in clients}}
    finally:
        conn.close()


def activate_and_wait(window: int, timeout_s: float = 3.0) -> dict[str, Any]:
    """Pre-trial focus placement: ask the WM to activate ``window`` and wait until
    ``_NET_ACTIVE_WINDOW`` names it."""
    conn = Conn()
    try:
        t0 = time.monotonic()
        conn.request_activate(window)
        while time.monotonic() - t0 < timeout_s:
            if conn.active() == window:
                return {"ok": True, "waited_ms": round((time.monotonic() - t0) * 1000, 3),
                        "focus": conn.focus(), "active": conn.active()}
            time.sleep(0.005)
        return {"ok": False, "waited_ms": round((time.monotonic() - t0) * 1000, 3),
                "focus": conn.focus(), "active": conn.active()}
    finally:
        conn.close()


class FocusSampler(threading.Thread):
    """Samples (monotonic_ns, input focus, _NET_ACTIVE_WINDOW) every 2 ms; stores
    every sample's time and the value changes."""

    def __init__(self, period_s: float = 0.002) -> None:
        super().__init__(daemon=True)
        self.period = period_s
        self.stop_flag = threading.Event()
        self.samples = 0
        self.changes: list[list[int]] = []  # [mono_ns, focus, active]
        self.first_ns = 0
        self.last_ns = 0
        self.max_gap_ns = 0
        self.error: str | None = None

    def run(self) -> None:
        try:
            conn = Conn()
        except Exception as exc:  # recorded, never raised into the trial
            self.error = f"{type(exc).__name__}: {exc}"
            return
        try:
            last = None
            start = time.monotonic_ns()
            k = 0
            prev_ns = 0
            while not self.stop_flag.is_set():
                t = time.monotonic_ns()
                value = (conn.focus(), conn.active())
                if self.samples == 0:
                    self.first_ns = t
                elif t - prev_ns > self.max_gap_ns:
                    self.max_gap_ns = t - prev_ns
                prev_ns = t
                self.last_ns = t
                self.samples += 1
                if value != last:
                    self.changes.append([t, value[0], value[1]])
                    last = value
                k += 1
                delay = (start + k * int(self.period * 1e9) - time.monotonic_ns()) / 1e9
                if delay > 0:
                    time.sleep(delay)
        finally:
            conn.close()

    def stop(self) -> dict[str, Any]:
        self.stop_flag.set()
        self.join(timeout=2)
        return {"samples": self.samples, "first_ns": self.first_ns, "last_ns": self.last_ns,
                "max_gap_ms": round(self.max_gap_ns / 1e6, 3), "changes": self.changes, "error": self.error}


class Decoy:
    """A pre-mapped harness-owned toplevel that steals the focus on cue."""

    def __init__(self) -> None:
        self.conn = Conn()
        dpy = self.conn.dpy
        self.window = int(X.XCreateSimpleWindow(dpy, self.conn.root, 1300, 600, 300, 200, 1, 0, 0xFFFFFF))
        X.XStoreName(dpy, self.window, b"N01R decoy")
        pid = (ctypes.c_ulong * 1)(os.getpid())
        X.XChangeProperty(dpy, self.window, self.conn.a_pid, XA_CARDINAL, 32, 0, pid, 1)
        X.XMapRaised(dpy, self.window)
        X.XSync(dpy, 0)
        self.thread: threading.Thread | None = None
        self.result: dict[str, Any] = {}
        self.lock = threading.Lock()

    def arm(self, state_path: str, baseline_seq: int, delay_ms: float, deadline_s: float = 6.0) -> None:
        """Watch ``state_path`` (1 ms poll); ``delay_ms`` after ``seq`` passes
        ``baseline_seq``, activate the decoy. Runs in a thread that uses its own
        connection-free logic and this object's connection only to steal."""
        self.result = {"armed": True, "delay_ms": delay_ms, "baseline_seq": baseline_seq}

        def watch() -> None:
            end = time.monotonic() + deadline_s
            seen_ns = None
            while time.monotonic() < end:
                try:
                    with open(state_path, encoding="utf-8") as stream:
                        seq = int(json.load(stream).get("seq", -1))
                except (OSError, ValueError):
                    seq = -1
                if seq > baseline_seq:
                    seen_ns = time.monotonic_ns()
                    break
                time.sleep(0.001)
            if seen_ns is None:
                self.result.update({"stolen": False, "reason": "state change not seen"})
                return
            target = seen_ns + int(delay_ms * 1e6)
            while time.monotonic_ns() < target:
                remaining = (target - time.monotonic_ns()) / 1e9
                time.sleep(min(max(remaining, 0), 0.0005))
            dpy = self.conn.dpy
            t_steal = time.monotonic_ns()
            self.conn.request_activate(self.window)
            X.XRaiseWindow(dpy, self.window)
            X.XSetInputFocus(dpy, self.window, REVERT_TO_PARENT, 0)
            X.XFlush(dpy)
            self.result.update({"stolen": True, "state_seen_ns": seen_ns, "steal_ns": t_steal,
                                "steal_wall_ns": time.time_ns()})

        self.thread = threading.Thread(target=watch, daemon=True)
        self.thread.start()

    def wait(self, timeout_s: float = 7.0) -> dict[str, Any]:
        if self.thread is not None:
            self.thread.join(timeout=timeout_s)
            self.thread = None
        return dict(self.result)

    def close(self) -> None:
        try:
            X.XDestroyWindow(self.conn.dpy, self.window)
            X.XSync(self.conn.dpy, 0)
        finally:
            self.conn.close()
