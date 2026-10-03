"""FRESH-07: independent X11 window-tree reader (ctypes over libX11 + libXext).

Runs only inside the private Xvfb session (cua-x11-session.sh). It never talks to the Driver; it
reads the private X server the way `xwininfo -root -tree` / `xprop` would, plus the SHAPE extension
rectangle counts, and is the oracle for the overlay map-state facts.

read() returns one snapshot:
  overlays     every root child whose WM_NAME starts with "Cua.AgentCursorOverlay." with its
               map_state (UNMAPPED / UNVIEWABLE / VIEWABLE), override_redirect, geometry and the
               bounding / input shape rectangle counts
  focus        XGetInputFocus window and revert_to
  active       root _NET_ACTIVE_WINDOW
  stack_top    last entry of root _NET_CLIENT_LIST_STACKING
  mapped_or    mapped override-redirect root children (the Driver focus guard's popup view,
               platform-linux input/focus_guard.rs mapped_popups)
  pointer_child  XQueryPointer child of the root
Poller samples overlay map state every period and keeps every transition with CLOCK_MONOTONIC ns.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import threading
import time
from typing import Any

_x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
_xext = ctypes.CDLL(ctypes.util.find_library("Xext") or "libXext.so.6")

Window = ctypes.c_ulong
Atom = ctypes.c_ulong


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


class XRectangle(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short),
                ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]


XErrorHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


@XErrorHandler
def _ignore_error(_display: Any, _event: Any) -> int:  # windows can vanish between calls
    return 0


_x11.XSetErrorHandler(_ignore_error)
_x11.XOpenDisplay.restype = ctypes.c_void_p
_x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
_x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
_x11.XDefaultRootWindow.restype = Window
_x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
_x11.XQueryTree.argtypes = [ctypes.c_void_p, Window, ctypes.POINTER(Window), ctypes.POINTER(Window),
                            ctypes.POINTER(ctypes.POINTER(Window)), ctypes.POINTER(ctypes.c_uint)]
_x11.XGetWindowAttributes.argtypes = [ctypes.c_void_p, Window, ctypes.POINTER(XWindowAttributes)]
_x11.XFetchName.argtypes = [ctypes.c_void_p, Window, ctypes.POINTER(ctypes.c_char_p)]
_x11.XFree.argtypes = [ctypes.c_void_p]
_x11.XInternAtom.restype = Atom
_x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
_x11.XGetInputFocus.argtypes = [ctypes.c_void_p, ctypes.POINTER(Window), ctypes.POINTER(ctypes.c_int)]
_x11.XGetWindowProperty.argtypes = [
    ctypes.c_void_p, Window, Atom, ctypes.c_long, ctypes.c_long, ctypes.c_int, Atom,
    ctypes.POINTER(Atom), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p)]
_x11.XQueryPointer.argtypes = [ctypes.c_void_p, Window, ctypes.POINTER(Window), ctypes.POINTER(Window),
                               ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                               ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                               ctypes.POINTER(ctypes.c_uint)]
_x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
_xext.XShapeGetRectangles.restype = ctypes.POINTER(XRectangle)
_xext.XShapeGetRectangles.argtypes = [ctypes.c_void_p, Window, ctypes.c_int,
                                      ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]

MAP_STATE = {0: "UNMAPPED", 1: "UNVIEWABLE", 2: "VIEWABLE"}
SHAPE_BOUNDING, SHAPE_INPUT = 0, 2
OVERLAY_PREFIX = b"Cua.AgentCursorOverlay."


class Conn:
    def __init__(self) -> None:
        self.d = _x11.XOpenDisplay(None)
        if not self.d:
            raise RuntimeError("cannot open the private X display")
        self.root = _x11.XDefaultRootWindow(self.d)
        self.a_active = _x11.XInternAtom(self.d, b"_NET_ACTIVE_WINDOW", 0)
        self.a_stack = _x11.XInternAtom(self.d, b"_NET_CLIENT_LIST_STACKING", 0)

    def close(self) -> None:
        if self.d:
            _x11.XCloseDisplay(self.d)
            self.d = None

    def children(self) -> list[int]:
        root_ret, parent = Window(), Window()
        kids = ctypes.POINTER(Window)()
        n = ctypes.c_uint()
        if not _x11.XQueryTree(self.d, self.root, ctypes.byref(root_ret), ctypes.byref(parent),
                               ctypes.byref(kids), ctypes.byref(n)):
            return []
        out = [int(kids[i]) for i in range(n.value)]
        if kids:
            _x11.XFree(kids)
        return out

    def attrs(self, w: int) -> XWindowAttributes | None:
        a = XWindowAttributes()
        return a if _x11.XGetWindowAttributes(self.d, w, ctypes.byref(a)) else None

    def name(self, w: int) -> bytes:
        p = ctypes.c_char_p()
        if _x11.XFetchName(self.d, w, ctypes.byref(p)) and p.value is not None:
            value = p.value
            _x11.XFree(p)
            return value
        return b""

    def shape_count(self, w: int, kind: int) -> int:
        count, ordering = ctypes.c_int(), ctypes.c_int()
        rects = _xext.XShapeGetRectangles(self.d, w, kind, ctypes.byref(count), ctypes.byref(ordering))
        if rects:
            _x11.XFree(rects)
        return count.value

    def prop_windows(self, atom: int) -> list[int]:
        at, fmt, n, after = Atom(), ctypes.c_int(), ctypes.c_ulong(), ctypes.c_ulong()
        data = ctypes.c_void_p()
        rc = _x11.XGetWindowProperty(self.d, self.root, atom, 0, 4096, 0, 0, ctypes.byref(at),
                                     ctypes.byref(fmt), ctypes.byref(n), ctypes.byref(after),
                                     ctypes.byref(data))
        if rc != 0 or not data.value:
            return []
        try:
            if fmt.value != 32:
                return []
            arr = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))
            return [int(arr[i]) for i in range(n.value)]
        finally:
            _x11.XFree(data)

    def focus(self) -> tuple[int, int]:
        w, r = Window(), ctypes.c_int()
        _x11.XGetInputFocus(self.d, ctypes.byref(w), ctypes.byref(r))
        return int(w.value), int(r.value)

    def pointer_child(self) -> int:
        r, c = Window(), Window()
        rx, ry, wx, wy, m = ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_uint()
        _x11.XQueryPointer(self.d, self.root, ctypes.byref(r), ctypes.byref(c), ctypes.byref(rx),
                           ctypes.byref(ry), ctypes.byref(wx), ctypes.byref(wy), ctypes.byref(m))
        return int(c.value)

    def overlays(self, full: bool = True) -> list[dict[str, Any]]:
        out = []
        for w in self.children():
            nm = self.name(w)
            if not nm.startswith(OVERLAY_PREFIX):
                continue
            a = self.attrs(w)
            if a is None:
                continue
            row: dict[str, Any] = {"window": w, "map_state": MAP_STATE.get(a.map_state, str(a.map_state))}
            if full:
                row.update({"override_redirect": bool(a.override_redirect), "width": a.width,
                            "height": a.height, "bounding_rects": self.shape_count(w, SHAPE_BOUNDING),
                            "input_rects": self.shape_count(w, SHAPE_INPUT)})
            out.append(row)
        return out

    def read(self) -> dict[str, Any]:
        _x11.XSync(self.d, 0)
        mapped_or = []
        for w in self.children():
            a = self.attrs(w)
            if a is not None and a.override_redirect and a.map_state == 2:
                mapped_or.append({"window": w, "name": self.name(w).decode("utf-8", "replace")[:64]})
        stack = self.prop_windows(self.a_stack)
        active = self.prop_windows(self.a_active)
        focus, revert = self.focus()
        return {"t_mono_ns": time.monotonic_ns(), "overlays": self.overlays(), "focus": focus,
                "revert_to": revert, "active": active[0] if active else None,
                "stack_top": stack[-1] if stack else None, "stack_len": len(stack),
                "mapped_or": mapped_or, "pointer_child": self.pointer_child(),
                "root_children": len(self.children())}


def read() -> dict[str, Any]:
    c = Conn()
    try:
        return c.read()
    finally:
        c.close()


class Poller(threading.Thread):
    """Samples the overlay map state every period_s on its own X connection; keeps transitions."""

    def __init__(self, period_s: float = 0.002) -> None:
        super().__init__(daemon=True)
        self.period_s = period_s
        self.stop_evt = threading.Event()
        self.transitions: list[dict[str, Any]] = []
        self.samples = 0

    def run(self) -> None:
        c = Conn()
        last: tuple | None = None
        try:
            while not self.stop_evt.is_set():
                _x11.XSync(c.d, 0)
                state = tuple((o["window"], o["map_state"]) for o in c.overlays(full=False))
                self.samples += 1
                if state != last:
                    self.transitions.append({"t_mono_ns": time.monotonic_ns(),
                                             "overlays": [list(s) for s in state]})
                    last = state
                time.sleep(self.period_s)
        finally:
            c.close()

    def stop(self) -> dict[str, Any]:
        self.stop_evt.set()
        self.join(timeout=5)
        return {"samples": self.samples, "period_s": self.period_s, "transitions": self.transitions}
