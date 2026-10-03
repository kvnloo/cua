"""RECERT-FIX a3 Part B: kvnloo/cua#36 same-process two-window rows (W2a-W2d) and the fixture smokes.

Measurement only. Runs inside cua-x11-session.sh (private Xvfb + AT-SPI) under hostless, with the
shared quiet-lane lock held by the caller (locked_block.sh pattern). Reuses, imported unchanged, the
FIX-02 wave-3 native harness helpers (harness/fix02-w3/native: McpClient, Topology, compact, element,
refusal_code, is_error, scrub). The oracle is the GTK3 fixture's own state file in two-window mode
(CUA_GTK3_TWO_WINDOWS=1): one process, windows "w1" and "w2", each with its own key; read before and
after every call. The route comes from each call's receipt (structuredContent).

Rows (topology T2: one `cua-driver serve` daemon, two `mcp --socket` clients = sessions A and B):
  W2a  A observes w1, B observes w2; B dispatches A's w1 token (cross-session, same pid). Tails: A's
       own w1 token and B's own w2 token must verify.
  W2b  A observes w1, then w2, then uses its w1 token (must verify: per-window retirement must not
       retire the other window), then its w2 token (must verify).
  W2c  A observes w1 (capture c1) and w2 (capture c2); A clicks inside w2 (window_id w2, w2's checkbox
       point) presenting c1 (must be refused, 0 mutations); tail: the same point with c2 verifies.
  W2d  A observes w1 and w2; the harness closes w1 (SIGUSR1, fixture-owned close, confirmed on the
       state file); A's w1 token must be refused; A's w2 token must verify.
Smokes (not counted): S1 fixture without the env (one window, v1 state keys unchanged); S2 two-window
fixture: two windows listed, per-window tokens, a w1 click changes only w1, SIGUSR1 closes only w1.

usage: w2_rows.py --row W2a|W2b|W2c|W2d|S1|S2 --block <id> --attempts 0-9 --out <file>
Environment as run_block.py (OWN36_DRIVER, OWN36_FIXTURE, OWN36_WORK, OWN36_SCRUB, OWN36_PYTHON).
"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fix02-w3", "native"))
import run_block as rb  # noqa: E402  (unchanged wave-3 helpers)

CHECKBOX = rb.CHECKBOX
TITLE = "CuaTestHarness GTK3 Tasks"
V1_KEYS = ["agreed", "counter", "note_saved", "pid", "schema", "seq", "size"]


class TwoWindowApp:
    """One fixture process with two task windows (w1, w2)."""

    def __init__(self, tag="P", two=True):
        self.tag = tag
        self.two = two
        self.state_path = os.path.join(rb.WORK, f"state-{tag}.json")
        self.proc = None
        self.windows = {}

    def launch(self):
        if os.path.exists(self.state_path):
            os.remove(self.state_path)
        env = dict(os.environ, CUA_GTK3_TASK_STATE=self.state_path)
        env.pop("CUA_GTK3_TWO_WINDOWS", None)
        if self.two:
            env["CUA_GTK3_TWO_WINDOWS"] = "1"
        self.proc = subprocess.Popen(
            [os.environ.get("OWN36_PYTHON", "python3"), rb.FIX], env=env,
            stdout=open(os.path.join(rb.WORK, f"app-{self.tag}.log"), "ab"), stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = self.read()
            if state and state.get("pid") == self.proc.pid and (
                    not self.two or len(state.get("windows", {})) == 2):
                return
            time.sleep(0.1)
        raise RuntimeError("fixture did not publish state")

    @property
    def pid(self):
        return self.proc.pid

    def read(self):
        try:
            with open(self.state_path, encoding="utf-8") as stream:
                return json.load(stream)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def close_w1(self):
        os.kill(self.proc.pid, signal.SIGUSR1)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self.read() or {}
            if state.get("windows", {}).get("w1", {}).get("open") is False:
                return True
            time.sleep(0.05)
        return False

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


def win_state(state, key):
    return ((state or {}).get("windows") or {}).get(key)


class Ctx(rb.Ctx):
    def __init__(self, topo, block, out, app):
        self.topo = topo
        self.block = block
        self.out = out
        self.apps = {"P": app}

    def map_windows(self):
        app = self.apps["P"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            _, result = self.topo.call("A", "list_windows", {"pid": app.pid})
            windows = (result.get("structuredContent") or {}).get("windows") or []
            found = {}
            for window in windows:
                title = window.get("title") or ""
                for key in ("w1", "w2"):
                    if title == f"{TITLE} {key}":
                        found[key] = window["window_id"]
            if len(found) == 2:
                app.windows = found
                return windows
            time.sleep(0.2)
        raise RuntimeError("two windows not listed")


class Att(rb.Attempt):
    def gws_w(self, actor, key, step):
        app = self.ctx.apps["P"]
        result = self.call(actor, "get_window_state", {"pid": app.pid, "window_id": app.windows[key]},
                           "none", step)
        chk = rb.element(result, CHECKBOX)
        sc = result.get("structuredContent") or {}
        return {"snapshot_id": sc.get("snapshot_id"), "capture_id": sc.get("capture_id"),
                "window_id": sc.get("window_id"), "token": chk and chk.get("element_token"),
                "frame": chk and chk.get("screenshot_frame"), "result": result}

    def click_tok(self, actor, token, expect, step):
        return self.call(actor, "click", {"pid": self.ctx.apps["P"].pid, "element_token": token},
                         expect, step)

    def click_cap(self, actor, key, frame, capture_id, expect, step):
        app = self.ctx.apps["P"]
        x, y = frame["x"] + 10, frame["y"] + frame["h"] / 2
        return self.call(actor, "click", {"pid": app.pid, "window_id": app.windows[key], "x": x, "y": y,
                                          "capture_id": capture_id}, expect, step)


def row_W2a(ctx, index, order):
    att = Att(ctx, "W2a", index, order)
    seq = [("A", "w1"), ("B", "w2")] if order == "AB" else [("B", "w2"), ("A", "w1")]
    obs = {}
    for actor, key in seq:
        obs[actor] = att.gws_w(actor, key, f"{actor}-observes-{key}")
    att.rec["tokens"] = {"A_w1": obs["A"]["token"], "B_w2": obs["B"]["token"]}
    att.click_tok("B", obs["A"]["token"], "none", "B-uses-A-w1-token")
    att.click_tok("A", obs["A"]["token"], "change:P", "A-uses-own-w1-token")
    att.click_tok("B", obs["B"]["token"], "change:P", "B-uses-own-w2-token")
    att.done()


def row_W2b(ctx, index, order):
    att = Att(ctx, "W2b", index, order)
    o1 = att.gws_w("A", "w1", "A-observes-w1")
    o2 = att.gws_w("A", "w2", "A-observes-w2")
    # Fixed order by design (w1, then w2, then the w1 token); `order` is recorded only.
    att.rec["tokens"] = {"A_w1": o1["token"], "A_w2": o2["token"]}
    att.click_tok("A", o1["token"], "change:P", "A-uses-w1-token-after-observing-w2")
    att.click_tok("A", o2["token"], "change:P", "A-uses-w2-token")
    att.done()


def row_W2c(ctx, index, order):
    att = Att(ctx, "W2c", index, order)
    keys = ("w1", "w2") if order == "AB" else ("w2", "w1")
    obs = {key: att.gws_w("A", key, f"A-observes-{key}") for key in keys}
    att.rec["captures"] = {k: obs[k]["capture_id"] for k in obs}
    att.click_cap("A", "w2", obs["w2"]["frame"], obs["w1"]["capture_id"], "none",
                  "A-clicks-in-w2-with-w1-capture")
    att.click_cap("A", "w2", obs["w2"]["frame"], obs["w2"]["capture_id"], "change:P",
                  "A-clicks-in-w2-with-w2-capture")
    att.done()


def row_W2d(ctx, index, order):
    att = Att(ctx, "W2d", index, order)
    keys = ("w1", "w2") if order == "AB" else ("w2", "w1")
    obs = {key: att.gws_w("A", key, f"A-observes-{key}") for key in keys}
    att.rec["tokens"] = {k: obs[k]["token"] for k in obs}
    att.rec["w1_closed_confirmed"] = ctx.apps["P"].close_w1()
    att.rec["state_after_close"] = ctx.apps["P"].read()
    att.click_tok("A", obs["w1"]["token"], "none", "A-uses-closed-w1-token")
    att.click_tok("A", obs["w2"]["token"], "change:P", "A-uses-w2-token-after-w1-closed")
    att.done()


ROWS = {"W2a": row_W2a, "W2b": row_W2b, "W2c": row_W2c, "W2d": row_W2d}


def smoke(args, out):
    """S1 / S2 fixture smokes (not counted)."""
    emit = lambda r: (out.write(rb.scrub(json.dumps(r, sort_keys=True)) + "\n"), out.flush())
    app = TwoWindowApp(two=(args.row == "S2"))
    app.launch()
    topo = rb.Topology("T2", args.block)
    try:
        topo.start()
        rec = {"kind": "smoke", "row": args.row, "calls": []}
        _, listed = topo.call("A", "list_windows", {"pid": app.pid})
        windows = (listed.get("structuredContent") or {}).get("windows") or []
        rec["windows"] = [{"title": w.get("title"), "window_id": w.get("window_id")} for w in windows]
        rec["state_initial"] = app.read()
        if args.row == "S1":
            rec["state_keys"] = sorted(app.read())
            rec["checks"] = {"one_window": len(windows) == 1 and windows[0].get("title") == TITLE,
                             "v1_keys_unchanged": rec["state_keys"] == V1_KEYS}
        else:
            ctx = Ctx(topo, args.block, out, app)
            ctx.map_windows()
            att = Att(ctx, "S2", 0, "AB")
            o1 = att.gws_w("A", "w1", "observe-w1")
            o2 = att.gws_w("A", "w2", "observe-w2")
            att.click_tok("A", o1["token"], "change:P", "click-w1")
            after_click = app.read()
            closed = app.close_w1()
            after_close = app.read()
            _, listed2 = topo.call("A", "list_windows", {"pid": app.pid})
            rec.update(att.rec)
            rec["kind"] = "smoke"
            rec["windows_after_close"] = [w.get("title") for w in
                                          (listed2.get("structuredContent") or {}).get("windows") or []]
            rec["checks"] = {
                "two_windows_listed": sorted(app.windows) == ["w1", "w2"],
                "distinct_snapshots": o1["snapshot_id"] != o2["snapshot_id"],
                "tokens_present": bool(o1["token"] and o2["token"]),
                "w1_click_changes_only_w1": win_state(after_click, "w1")["agreed"] is True
                and win_state(after_click, "w2")["agreed"] is False,
                "sigusr1_closes_only_w1": closed and win_state(after_close, "w1")["open"] is False
                and win_state(after_close, "w2")["open"] is True and app.proc.poll() is None,
            }
        rec["ok"] = all(rec["checks"].values())
        emit(rec)
    finally:
        topo.close()
        app.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", required=True, choices=sorted(ROWS) + ["S1", "S2"])
    parser.add_argument("--block", required=True)
    parser.add_argument("--attempts", default="0")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    attempts = rb.parse_attempts(args.attempts)
    assert len(attempts) <= 10, "at most 10 attempts per lock acquisition"
    os.makedirs(rb.WORK, exist_ok=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(rb.DRV, "rb") as stream:
        sha = hashlib.sha256(stream.read()).hexdigest()
    version = subprocess.run([rb.DRV, "--version"], capture_output=True, text=True,
                             env=rb.driver_env()).stdout.strip()
    with open(rb.FIX, "rb") as stream:
        fixture_sha = hashlib.sha256(stream.read()).hexdigest()
    with open(args.out, "a", encoding="utf-8") as out:
        out.write(json.dumps({"kind": "block", "topology": "T2", "row": args.row, "block": args.block,
                              "attempts": attempts, "display": os.environ.get("DISPLAY"),
                              "driver_sha256": sha, "driver_version": version,
                              "fixture_sha256": fixture_sha, "started_utc": rb.utc(),
                              "telemetry_env": {"DO_NOT_TRACK": "1",
                                                "CUA_DRIVER_RS_TELEMETRY_ENABLED": "0"}},
                             sort_keys=True) + "\n")
        out.flush()
        if args.row in ("S1", "S2"):
            smoke(args, out)
            n = 1
        else:
            topo = rb.Topology("T2", args.block)
            app = TwoWindowApp()
            ctx = Ctx(topo, args.block, out, app)
            try:
                app.launch()
                topo.start()
                ctx.map_windows()
                for index in attempts:
                    if args.row == "W2d" and index != attempts[0]:
                        # W2d closes w1: every attempt gets a fresh fixture (same daemon, same clients).
                        app.stop()
                        app.launch()
                        ctx.map_windows()
                    order = "AB" if index % 2 == 0 else "BA"
                    ROWS[args.row](ctx, index, order)
                n = len(attempts)
            finally:
                topo.close()
                app.stop()
        out.write(json.dumps({"kind": "block_end", "block": args.block, "attempts_run": n,
                              "ended_utc": rb.utc()}) + "\n")


if __name__ == "__main__":
    main()
