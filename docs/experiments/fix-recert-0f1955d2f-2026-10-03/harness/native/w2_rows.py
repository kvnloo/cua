"""RECERT-FIX Part B: kvnloo/cua#36 same-process two-window rows (new file).

One GTK3 fixture PROCESS with two task windows (CUA_GTK3_TWO_WINDOWS=1, the env-gated fixture
variant): "CuaTestHarness GTK3 Tasks 1" and "... 2", each with its own "I agree" checkbox and its own
key ("window1", "window2") in the app-owned state file. Topology T2 only: one `cua-driver serve`
daemon and two `cua-driver mcp --socket` clients, sessions A and B (implicit transport sessions).

Oracle: the fixture's per-window state, read before and after EVERY call (target-owned). The
Driver's receipts give the route only. A call "mutated" a window when that window's entry changed.

Rows (one attempt = one row instance; even attempts observe A first, odd B first where both observe):
  W2a  A observes window 1, B observes window 2; B clicks A's window-1 token (pid only) -> expected
       none. Tails: A's own window-1 token -> change:window1; B's own window-2 token -> change:window2.
  W2b  A observes window 1 then window 2, then clicks its window-1 token -> change:window1 (per-window
       retirement must not retire the other window), then its window-2 token -> change:window2.
  W2c  A observes window 2 (frame), then window 1 (capture c1); A clicks with capture c1 at window 2's
       checkbox coordinates and window_id = window 2 -> expected none. Tail: c1 at window 1's checkbox
       with window_id = window 1 -> change:window1 (c1 was still live).
  W2d  fresh fixture; A observes window 1 and window 2; the harness closes window 1 (SIGUSR1, target
       side) and waits for window1.open == false; A clicks its window-1 token -> none; A clicks its
       window-2 token -> change:window2.
With --forged (W2a only), attempt k replaces A's window-1 token with run_block.FORGED_TOKENS[k].
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time

import run_block as rb

TITLE_PREFIX = "CuaTestHarness GTK3 Tasks "
KEYS = ("window1", "window2")


class TwoWindowApp:
    def __init__(self):
        self.state_path = os.path.join(rb.WORK, "state-two-window.json")
        self.proc = None
        self.windows = {}  # key -> window_id

    def launch(self):
        if os.path.exists(self.state_path):
            os.remove(self.state_path)
        env = dict(os.environ, CUA_GTK3_TASK_STATE=self.state_path, CUA_GTK3_TWO_WINDOWS="1")
        self.proc = subprocess.Popen([os.environ.get("OWN36_PYTHON", "python3"), rb.FIX], env=env,
                                     stdout=open(os.path.join(rb.WORK, "app-two-window.log"), "ab"),
                                     stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = self.read()
            if state and state.get("pid") == self.proc.pid and state.get("windows"):
                return
            time.sleep(0.1)
        raise RuntimeError("two-window fixture did not publish state")

    @property
    def pid(self):
        return self.proc.pid

    def read(self):
        try:
            with open(self.state_path, encoding="utf-8") as stream:
                return json.load(stream)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def window_state(self, key):
        return ((self.read() or {}).get("windows") or {}).get(key)

    def close_window1(self, timeout=5.0):
        os.kill(self.proc.pid, signal.SIGUSR1)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if (self.window_state("window1") or {}).get("open") is False:
                return True
            time.sleep(0.02)
        return False

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


class W2:
    def __init__(self, topo, block, out):
        self.topo, self.block, self.out = topo, block, out
        self.app = TwoWindowApp()

    def emit(self, record):
        self.out.write(rb.scrub(json.dumps(record, sort_keys=True)) + "\n")
        self.out.flush()

    def map_windows(self, tag="A"):
        deadline = time.monotonic() + 15
        last = None
        while time.monotonic() < deadline:
            _, result = self.topo.call(tag, "list_windows", {"pid": self.app.pid})
            windows = (result.get("structuredContent") or {}).get("windows") or []
            last = [{"window_id": w.get("window_id"), "title": w.get("title")} for w in windows]
            found = {}
            for w in windows:
                title = w.get("title") or ""
                if title.startswith(TITLE_PREFIX) and title[len(TITLE_PREFIX):] in ("1", "2"):
                    found["window" + title[len(TITLE_PREFIX):]] = w["window_id"]
            if len(found) == 2:
                self.app.windows = found
                return last
            time.sleep(0.2)
        raise RuntimeError(f"two windows not listed: {last}")

    def relaunch(self):
        self.app.stop()
        self.app.launch()
        return self.map_windows()


class Att:
    def __init__(self, w2, row, index, order, extra=None):
        self.w2 = w2
        self.rec = {"kind": "attempt", "topology": "T2", "row": row, "block": w2.block, "attempt": index,
                    "order": order, "display": os.environ.get("DISPLAY"), "started_utc": rb.utc(),
                    "pid": w2.app.pid, "windows": dict(w2.app.windows), "calls": [], **(extra or {})}

    def call(self, actor, tool, args, expect, step):
        app = self.w2.app
        pre = app.read()
        sent, result = self.w2.topo.call(actor, tool, args)
        if expect.startswith("change:"):
            key = expect.split(":", 1)[1]
            before = (pre or {}).get("windows", {}).get(key)
            deadline = time.monotonic() + rb.LAND_S
            while time.monotonic() < deadline and app.window_state(key) == before:
                time.sleep(0.02)
            time.sleep(0.2)  # catch any second (unexpected) write
        else:
            time.sleep(rb.SETTLE_S)
        post = app.read()
        self.rec["calls"].append({
            "step": step, "actor": actor, "tool": tool, "args": dict(sent), "expect": expect,
            "is_error": rb.is_error(result), "refusal_code": rb.refusal_code(result),
            "response": rb.compact(result), "pre": pre, "post": post, "utc": rb.utc()})
        return result

    def gws(self, actor, key, step):
        app = self.w2.app
        result = self.call(actor, "get_window_state", {"pid": app.pid, "window_id": app.windows[key]},
                           "none", step)
        chk = rb.element(result, rb.CHECKBOX)
        sc = result.get("structuredContent") or {}
        return {"snapshot_id": sc.get("snapshot_id"), "capture_id": sc.get("capture_id"),
                "window_id": sc.get("window_id"), "token": chk and chk.get("element_token"),
                "frame": chk and chk.get("screenshot_frame")}

    def click_token(self, actor, token, expect, step):
        return self.call(actor, "click", {"pid": self.w2.app.pid, "element_token": token}, expect, step)

    def click_capture(self, actor, key, frame, capture_id, expect, step):
        x, y = frame["x"] + 10, frame["y"] + frame["h"] / 2
        return self.call(actor, "click", {"pid": self.w2.app.pid, "window_id": self.w2.app.windows[key],
                                          "x": x, "y": y, "capture_id": capture_id}, expect, step)

    def done(self):
        self.rec["ended_utc"] = rb.utc()
        self.w2.emit(self.rec)


def row_W2a(w2, index, order, forge=None):
    att = Att(w2, "W2a", index, order, {"forged": forge is not None})
    obs = {}
    for tag in order:
        obs[tag] = att.gws(tag, "window1" if tag == "A" else "window2", f"{tag}-observes-"
                           + ("window1" if tag == "A" else "window2"))
    token = obs["A"]["token"]
    if forge is not None:
        token = rb.forge_token(forge, obs["A"]["snapshot_id"])
        att.rec["forged_value"] = token
    att.rec["A_window1_token"], att.rec["B_window2_token"] = obs["A"]["token"], obs["B"]["token"]
    att.click_token("B", token, "none", "B-uses-A-window1-token")
    att.click_token("A", obs["A"]["token"], "change:window1", "A-uses-own-window1-token")
    att.click_token("B", obs["B"]["token"], "change:window2", "B-uses-own-window2-token")
    att.done()


def row_W2b(w2, index, order, forge=None):
    att = Att(w2, "W2b", index, order)
    o1 = att.gws("A", "window1", "A-observes-window1")
    o2 = att.gws("A", "window2", "A-observes-window2")
    att.rec["tokens"] = {"window1": o1["token"], "window2": o2["token"]}
    att.click_token("A", o1["token"], "change:window1", "A-uses-window1-token-after-observing-window2")
    att.click_token("A", o2["token"], "change:window2", "A-uses-window2-token")
    att.done()


def row_W2c(w2, index, order, forge=None):
    att = Att(w2, "W2c", index, order)
    o2 = att.gws("A", "window2", "A-observes-window2")
    o1 = att.gws("A", "window1", "A-observes-window1")
    att.rec["captures"] = {"window1": o1["capture_id"], "window2": o2["capture_id"]}
    att.click_capture("A", "window2", o2["frame"], o1["capture_id"], "none",
                      "A-uses-window1-capture-at-window2-checkbox")
    att.click_capture("A", "window1", o1["frame"], o1["capture_id"], "change:window1",
                      "A-uses-window1-capture-in-window1")
    att.done()


def row_W2d(w2, index, order, forge=None):
    relaunch = w2.relaunch()
    att = Att(w2, "W2d", index, order, {"relaunched_windows": relaunch})
    o1 = att.gws("A", "window1", "A-observes-window1")
    o2 = att.gws("A", "window2", "A-observes-window2")
    att.rec["tokens"] = {"window1": o1["token"], "window2": o2["token"]}
    att.rec["window1_closed"] = w2.app.close_window1()
    att.rec["closed_utc"] = rb.utc()
    att.click_token("A", o1["token"], "none", "A-uses-window1-token-after-window1-closed")
    att.click_token("A", o2["token"], "change:window2", "A-uses-window2-token-after-window1-closed")
    att.done()


ROWS = {"W2a": row_W2a, "W2b": row_W2b, "W2c": row_W2c, "W2d": row_W2d}


def w2_block(args, out):
    topo = rb.Topology("T2", args.block)
    w2 = W2(topo, args.block, out)
    try:
        w2.app.launch()
        topo.start()
        listed = w2.map_windows()
        w2.emit({"kind": "setup", "row": args.row, "block": args.block, "pid": w2.app.pid,
                 "windows": dict(w2.app.windows), "listed": listed, "state": w2.app.read(),
                 "utc": rb.utc()})
        fn = ROWS[args.row]
        for index in args.attempt_list:
            order = "AB" if index % 2 == 0 else "BA"
            fn(w2, index, order, forge=index if args.forged else None)
    finally:
        topo.close()
        w2.app.stop()
    return len(args.attempt_list)
