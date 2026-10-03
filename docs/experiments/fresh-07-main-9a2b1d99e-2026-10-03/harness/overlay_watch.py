#!/usr/bin/env python3
"""FRESH-07R covariate: passive X11 map/unmap event log of the private session's override-redirect windows.

Runs only inside the private Xvfb session, next to a native harness (with_overlay_watch.sh starts and stops
it). It never talks to the Driver. It selects SubstructureNotify on the root window, which is a passive,
non-exclusive event selection: it never redirects, grabs or changes a window. It logs one JSON line per
Create/Map/Unmap/Destroy of a root child that is override-redirect, plus the initial snapshot. Window
names are written only for the Driver's own overlay ("Cua.AgentCursorOverlay.<session>"); every other
window is "other". Clocks: CLOCK_MONOTONIC ns (the harnesses' time.monotonic_ns()) and wall ns.

usage: overlay_watch.py <out.jsonl>     (SIGTERM / SIGINT ends it; a "ready" line is written first)
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import select
import signal
import sys
import time

_x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
Window = ctypes.c_ulong
PREFIX = b"Cua.AgentCursorOverlay."
SUBSTRUCTURE_NOTIFY = 1 << 19
CREATE, DESTROY, UNMAP, MAP = 16, 17, 18, 19
MAP_STATES = {0: "UNMAPPED", 1: "UNVIEWABLE", 2: "VIEWABLE"}


class XWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int), ("y", ctypes.c_int), ("width", ctypes.c_int), ("height", ctypes.c_int),
        ("border_width", ctypes.c_int), ("depth", ctypes.c_int), ("visual", ctypes.c_void_p),
        ("root", Window), ("class_", ctypes.c_int), ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int), ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong), ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int), ("colormap", ctypes.c_ulong), ("map_installed", ctypes.c_int),
        ("map_state", ctypes.c_int), ("all_event_masks", ctypes.c_long),
        ("your_event_mask", ctypes.c_long), ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int), ("screen", ctypes.c_void_p),
    ]


class XAnyWin(ctypes.Structure):  # common prefix of XMapEvent / XUnmapEvent / XDestroyWindowEvent
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p), ("event", Window), ("window", Window), ("flag", ctypes.c_int)]


class XCreate(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p), ("parent", Window), ("window", Window),
                ("x", ctypes.c_int), ("y", ctypes.c_int), ("width", ctypes.c_int), ("height", ctypes.c_int),
                ("border_width", ctypes.c_int), ("override_redirect", ctypes.c_int)]


class XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int), ("any", XAnyWin), ("create", XCreate), ("pad", ctypes.c_long * 24)]


ErrH = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


@ErrH
def _ignore(_d, _e):  # windows can vanish between the event and the name read
    return 0


_x11.XSetErrorHandler(_ignore)
_x11.XOpenDisplay.restype = ctypes.c_void_p
_x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
_x11.XDefaultRootWindow.restype = Window
_x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
_x11.XSelectInput.argtypes = [ctypes.c_void_p, Window, ctypes.c_long]
_x11.XConnectionNumber.argtypes = [ctypes.c_void_p]
_x11.XPending.argtypes = [ctypes.c_void_p]
_x11.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(XEvent)]
_x11.XFlush.argtypes = [ctypes.c_void_p]
_x11.XFetchName.argtypes = [ctypes.c_void_p, Window, ctypes.POINTER(ctypes.c_char_p)]
_x11.XFree.argtypes = [ctypes.c_void_p]
_x11.XQueryTree.argtypes = [ctypes.c_void_p, Window, ctypes.POINTER(Window), ctypes.POINTER(Window),
                            ctypes.POINTER(ctypes.POINTER(Window)), ctypes.POINTER(ctypes.c_uint)]
_x11.XGetWindowAttributes.argtypes = [ctypes.c_void_p, Window, ctypes.POINTER(XWindowAttributes)]

STOP = False


def _stop(*_a):
    global STOP
    STOP = True


def name_of(dpy, w) -> bytes | None:
    p = ctypes.c_char_p()
    if _x11.XFetchName(dpy, w, ctypes.byref(p)) and p.value is not None:
        v = p.value
        _x11.XFree(p)
        return v
    return None


def main() -> int:
    out = open(sys.argv[1], "a", buffering=1)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    dpy = _x11.XOpenDisplay(None)
    if not dpy:
        out.write(json.dumps({"ev": "error", "detail": "XOpenDisplay failed"}) + "\n")
        return 2
    root = _x11.XDefaultRootWindow(dpy)
    _x11.XSelectInput(dpy, root, SUBSTRUCTURE_NOTIFY)
    _x11.XFlush(dpy)
    names: dict[int, bytes | None] = {}
    orw: dict[int, bool] = {}

    def row(ev: str, w: int, **kw) -> None:
        nm = names.get(w)
        cls = "overlay" if nm and nm.startswith(PREFIX) else "other"
        r = {"m": time.monotonic_ns(), "w": time.time_ns(), "ev": ev, "win": w, "cls": cls}
        if cls == "overlay":
            r["name"] = nm.decode("utf-8", "replace")
        r.update(kw)
        out.write(json.dumps(r) + "\n")

    # initial snapshot of the root children
    r_root, r_parent = Window(), Window()
    kids = ctypes.POINTER(Window)()
    n = ctypes.c_uint()
    snap = []
    if _x11.XQueryTree(dpy, root, ctypes.byref(r_root), ctypes.byref(r_parent), ctypes.byref(kids), ctypes.byref(n)):
        for i in range(n.value):
            w = kids[i]
            a = XWindowAttributes()
            if not _x11.XGetWindowAttributes(dpy, w, ctypes.byref(a)):
                continue
            orw[w] = bool(a.override_redirect)
            if a.override_redirect:
                names[w] = name_of(dpy, w)
                nm = names[w]
                snap.append({"win": w, "cls": "overlay" if nm and nm.startswith(PREFIX) else "other",
                             "map_state": MAP_STATES.get(a.map_state, a.map_state),
                             **({"name": nm.decode("utf-8", "replace")} if nm and nm.startswith(PREFIX) else {})})
        if kids:
            _x11.XFree(kids)
    out.write(json.dumps({"m": time.monotonic_ns(), "w": time.time_ns(), "ev": "ready", "pid": os.getpid(),
                          "initial_override_redirect": snap}) + "\n")
    fd = _x11.XConnectionNumber(dpy)
    e = XEvent()
    while not STOP:
        try:
            select.select([fd], [], [], 0.5)
        except InterruptedError:
            continue
        while _x11.XPending(dpy) > 0:
            _x11.XNextEvent(dpy, ctypes.byref(e))
            t = e.type
            if t == CREATE:
                w = e.create.window
                orw[w] = bool(e.create.override_redirect)
                if orw[w]:
                    names[w] = name_of(dpy, w)
                    row("create", w)
            elif t in (MAP, UNMAP, DESTROY):
                w = e.any.window
                if t == MAP:
                    orw[w] = bool(e.any.flag)
                if not orw.get(w):
                    continue
                if t == MAP and not (names.get(w) or b"").startswith(PREFIX):
                    names[w] = name_of(dpy, w)
                row({MAP: "map", UNMAP: "unmap", DESTROY: "destroy"}[t], w)
                if t == DESTROY:
                    names.pop(w, None)
                    orw.pop(w, None)
    out.write(json.dumps({"m": time.monotonic_ns(), "w": time.time_ns(), "ev": "stop"}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
