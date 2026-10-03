"""FIX-03 Parts C and D: pid-only snapshot_id routing across sessions, and the W2c/W2d variants.

Measurement only. Runs inside cua-x11-session.sh (private Xvfb + openbox + AT-SPI) under hostless, with
the shared quiet-lane lock held by the caller (locked_fix03.sh). Reuses, imported unchanged, the
RECERT-FIX two-window helpers (harness/w2/w2_rows.py: TwoWindowApp, Ctx, Att) and the wave-3 native
helpers they import (harness/fix02-w3/native/run_block.py: Topology T2, McpClient, element, compact).
Topology T2: one `cua-driver serve` daemon, two `mcp --socket` clients = sessions A and B (each
client's implicit transport session). Fixture: the GTK3 TaskWindow in two-window mode
(CUA_GTK3_TWO_WINDOWS=1), one process, windows w1 and w2, per-window keys in the app-owned state file.

Oracles (target-owned): the fixture's state file read before and after every call, and an X RECORD
stream on the private display (xrecord_focus.py: MapWindow, ConfigureWindow, SendEvent
_NET_ACTIVE_WINDOW, SetInputFocus requests from every client; FocusIn and ConfigureNotify as
delivered), attributed to each call by wall clock and to w1 / w2 by their client and frame ids.

Rows
  WR   A observes w1 (snapshot sA, token tA1); B observes w2 (token tB2). Steps:
         s0 B bring_to_front {pid, window_id: w2}                      (setup: w2 active)
         s1 B click {pid, snapshot_id: sA, element_token: tB2}         (spec row: A's snapshot_id + B's
                                                                        own valid token)
         s2 B bring_to_front {pid, snapshot_id: sA}                    (the pid-only routing reader's input)
         s3 B click {pid, element_token: sA:<idx>}                     (A's snapshot id inside a token)
         s4 B click {pid, element_token: tB2}                          (positive: B's own token verifies)
         s5 A bring_to_front {pid, window_id: w1}                      (oracle control: w1 activation seen)
         s6 A click {pid, element_token: tA1}                          (positive: A's own token verifies)
  W2cX A observes w2 (capture cA2); B observes w2 (its own capture cB2). B clicks w2's checkbox point
       presenting A's capture cA2 (cross-session capture); tail: B's own cB2 at the same point verifies.
  W2dX A observes w1 and w2; the harness closes w1 (SIGUSR1, confirmed on the state file); B dispatches
       A's w2 token (cross-session after a window-lifecycle change); tail: A's own w2 token verifies.
  WS   (pid, xid) side index, text rung: A observes w1, B observes w2; B type_text with its OWN w2 Note
       token, then A type_text with its OWN w1 Note token. Fresh daemon and fixture per attempt.
  WK   (pid, xid) side index, focus rung: as WS with press_key 'space' (delivery_mode foreground) on each
       session's OWN checkbox token. Fresh daemon and fixture per attempt.

usage: fix03_native.py --row WR|W2cX|W2dX|WS|WK --block <id> --attempts 0-9 --out <file>
         --oracle-python <venv python> [--recorder xrecord_focus.py]
Environment as w2_rows.py (OWN36_DRIVER, OWN36_FIXTURE, OWN36_WORK, OWN36_SCRUB, OWN36_PYTHON).
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
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "w2"))
import w2_rows as w2  # noqa: E402  (unchanged RECERT-FIX copy)

rb = w2.rb
RECORDER = os.path.join(HERE, "xrecord_focus.py")


class Recorder:
    def __init__(self, oracle_python, path):
        self.path = path
        self.proc = subprocess.Popen([oracle_python, RECORDER, "record", path],
                                     stdout=subprocess.DEVNULL, stderr=open(path + ".stderr", "ab"))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if os.path.exists(path) and '"ready"' in open(path, encoding="utf-8").read():
                # FIX-03 deviation 3: the context is enabled after "ready"; a recorder that died there
                # (F5-wr4: RECORD EnableContext XError) must fail the block, not run it unobserved.
                time.sleep(1.0)
                if self.proc.poll() is not None:
                    raise RuntimeError(f"X RECORD oracle exited after ready (rc={self.proc.returncode})")
                return
            time.sleep(0.05)
        raise RuntimeError("X RECORD oracle did not start")

    def stop(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


def frames(oracle_python, xids):
    result = subprocess.run([oracle_python, RECORDER, "tree", *[str(x) for x in xids]],
                            capture_output=True, text=True, timeout=20)
    return json.loads(result.stdout) if result.returncode == 0 else {"error": result.stderr[-400:]}


class Att(w2.Att):
    def call(self, actor, tool, args, expect, step, label=None, keep_tree=False):
        t0 = time.time_ns()
        result = super().call(actor, tool, args, expect, step, label=label, keep_tree=keep_tree)
        call = self.rec["calls"][-1]
        call["t_send_ns"] = t0
        call["t_settled_ns"] = time.time_ns()
        call["receipt_window_id"] = (result.get("structuredContent") or {}).get("window_id")
        return result

    def bring(self, actor, args, step):
        app = self.ctx.apps["P"]
        return self.call(actor, "bring_to_front", {"pid": app.pid, **args}, "none", step)


def checkbox_index(obs):
    chk = w2.rb.element(obs["result"], w2.CHECKBOX)
    return chk and chk.get("element_index")


def row_WR(ctx, index, order):
    att = Att(ctx, "WR", index, order)
    app = ctx.apps["P"]
    seq = [("A", "w1"), ("B", "w2")] if order == "AB" else [("B", "w2"), ("A", "w1")]
    obs = {}
    for actor, key in seq:
        obs[actor] = att.gws_w(actor, key, f"{actor}-observes-{key}")
    s_a = obs["A"]["snapshot_id"]
    idx = checkbox_index(obs["A"])
    att.rec["handles"] = {"sA": s_a, "tA1": obs["A"]["token"], "tB2": obs["B"]["token"],
                          "sB": obs["B"]["snapshot_id"], "A_checkbox_index": idx}
    att.bring("B", {"window_id": app.windows["w2"]}, "s0-B-activates-w2")
    att.call("B", "click", {"pid": app.pid, "snapshot_id": s_a, "element_token": obs["B"]["token"]},
             "none", "s1-B-click-A-snapshot-id-with-own-w2-token")
    att.bring("B", {"snapshot_id": s_a}, "s2-B-bring-to-front-A-snapshot-id")
    att.call("B", "click", {"pid": app.pid, "element_token": f"{s_a}:{idx}"},
             "none", "s3-B-click-A-snapshot-id-inside-token")
    att.click_tok("B", obs["B"]["token"], "change:P", "s4-B-clicks-own-w2-token")
    att.bring("A", {"window_id": app.windows["w1"]}, "s5-A-activates-w1-oracle-control")
    att.click_tok("A", obs["A"]["token"], "change:P", "s6-A-clicks-own-w1-token")
    att.done()


def row_W2cX(ctx, index, order):
    att = Att(ctx, "W2cX", index, order)
    seq = [("A", "w2"), ("B", "w2")] if order == "AB" else [("B", "w2"), ("A", "w2")]
    obs = {}
    for actor, key in seq:
        obs[actor] = att.gws_w(actor, key, f"{actor}-observes-{key}")
    att.rec["captures"] = {"cA2": obs["A"]["capture_id"], "cB2": obs["B"]["capture_id"]}
    att.click_cap("B", "w2", obs["B"]["frame"], obs["A"]["capture_id"], "none",
                  "B-clicks-w2-with-A-w2-capture")
    att.click_cap("B", "w2", obs["B"]["frame"], obs["B"]["capture_id"], "change:P",
                  "B-clicks-w2-with-own-w2-capture")
    att.done()


def row_W2dX(ctx, index, order):
    att = Att(ctx, "W2dX", index, order)
    keys = ("w1", "w2") if order == "AB" else ("w2", "w1")
    obs = {key: att.gws_w("A", key, f"A-observes-{key}") for key in keys}
    att.rec["tokens"] = {k: obs[k]["token"] for k in obs}
    att.rec["w1_closed_confirmed"] = ctx.apps["P"].close_w1()
    att.rec["state_after_close"] = ctx.apps["P"].read()
    att.click_tok("B", obs["w2"]["token"], "none", "B-uses-A-w2-token-after-w1-closed")
    att.click_tok("A", obs["w2"]["token"], "change:P", "A-uses-own-w2-token-after-w1-closed")
    att.done()


def note_token(obs):
    note = w2.rb.element(obs["result"], w2.rb.NOTE)
    return note and note.get("element_token")


def row_WS(ctx, index, order):
    """Side index (pid, xid) readers without an xid: an element-addressed type_text by each session into
    its OWN window's Note field. Oracle: each window's live Note text in the fixture state file."""
    att = Att(ctx, "WS", index, order)
    app = ctx.apps["P"]
    seq = [("A", "w1"), ("B", "w2")] if order == "AB" else [("B", "w2"), ("A", "w1")]
    obs = {}
    for actor, key in seq:
        obs[actor] = att.gws_w(actor, key, f"{actor}-observes-{key}")
    att.rec["handles"] = {"A_w1_note": note_token(obs["A"]), "B_w2_note": note_token(obs["B"])}
    att.call("B", "type_text", {"pid": app.pid, "element_token": note_token(obs["B"]), "text": "fix03B"},
             "change:P", "B-types-into-own-w2-note")
    att.call("A", "type_text", {"pid": app.pid, "element_token": note_token(obs["A"]), "text": "fix03A"},
             "change:P", "A-types-into-own-w1-note")
    att.done()


def row_WK(ctx, index, order):
    """Side index readers without an xid, keyboard rung: a foreground press_key 'space' by each session on
    its OWN window's checkbox token (AT-SPI GrabFocus on the indexed element, then an XTest key).
    Oracle: each window's `agreed` in the fixture state file."""
    att = Att(ctx, "WK", index, order)
    app = ctx.apps["P"]
    seq = [("A", "w1"), ("B", "w2")] if order == "AB" else [("B", "w2"), ("A", "w1")]
    obs = {}
    for actor, key in seq:
        obs[actor] = att.gws_w(actor, key, f"{actor}-observes-{key}")
    att.rec["handles"] = {"A_w1_checkbox": obs["A"]["token"], "B_w2_checkbox": obs["B"]["token"]}
    att.call("B", "press_key", {"pid": app.pid, "element_token": obs["B"]["token"], "key": "space",
                                "delivery_mode": "foreground"}, "change:P", "B-presses-space-on-own-w2-checkbox")
    att.call("A", "press_key", {"pid": app.pid, "element_token": obs["A"]["token"], "key": "space",
                                "delivery_mode": "foreground"}, "change:P", "A-presses-space-on-own-w1-checkbox")
    att.done()


ROWS = {"WR": row_WR, "W2cX": row_W2cX, "W2dX": row_W2dX, "WS": row_WS, "WK": row_WK}
# Rows whose every attempt gets a fresh fixture (W2dX closes w1) or a fresh daemon + fixture (WS: the
# daemon-global side index's per-process order is part of the condition).
FRESH_APP = {"W2dX", "WS", "WK"}
FRESH_DAEMON = {"WS", "WK"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", required=True, choices=sorted(ROWS))
    parser.add_argument("--block", required=True)
    parser.add_argument("--attempts", default="0")
    parser.add_argument("--out", required=True)
    parser.add_argument("--oracle-python", required=True)
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
    xrec_path = os.path.join(rb.WORK, f"xrecord-{args.row}-{args.block}.jsonl")
    with open(args.out, "a", encoding="utf-8") as out:
        header = {"kind": "block", "topology": "T2", "row": args.row, "block": args.block,
                  "attempts": attempts, "display": os.environ.get("DISPLAY"),
                  "driver_sha256": sha, "driver_version": version, "fixture_sha256": fixture_sha,
                  "harness_sha256": {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest()
                                     for p in (__file__, RECORDER, w2.__file__, rb.__file__)},
                  "started_utc": rb.utc(),
                  "telemetry_env": {"DO_NOT_TRACK": os.environ.get("DO_NOT_TRACK"),
                                    "CUA_DRIVER_RS_TELEMETRY_ENABLED":
                                        os.environ.get("CUA_DRIVER_RS_TELEMETRY_ENABLED")}}
        out.write(json.dumps(header, sort_keys=True) + "\n")
        out.flush()
        recorder = Recorder(args.oracle_python, xrec_path)
        topo = rb.Topology("T2", args.block)
        app = w2.TwoWindowApp()
        ctx = w2.Ctx(topo, args.block, out, app)
        n = 0
        try:
            app.launch()
            topo.start()
            ctx.map_windows()
            for index in attempts:
                if args.row in FRESH_DAEMON and index != attempts[0]:
                    topo.close()
                    topo = rb.Topology("T2", f"{args.block}-{index}")
                    ctx.topo = topo
                if args.row in FRESH_APP and index != attempts[0]:
                    app.stop()
                    app.launch()
                if args.row in FRESH_DAEMON and index != attempts[0]:
                    topo.start()
                if args.row in FRESH_APP and index != attempts[0]:
                    ctx.map_windows()
                ids = dict(app.windows)
                out.write(json.dumps({"kind": "windows", "block": args.block, "attempt": index,
                                      "windows": ids, "frames": frames(args.oracle_python, ids.values())},
                                     sort_keys=True) + "\n")
                order = "AB" if index % 2 == 0 else "BA"
                ROWS[args.row](ctx, index, order)
                n += 1
        finally:
            topo.close()
            app.stop()
            recorder.stop()
            with open(xrec_path, encoding="utf-8") as stream:
                for line in stream:
                    out.write(json.dumps({"kind": "xrecord", "block": args.block,
                                          "item": json.loads(line)}, sort_keys=True) + "\n")
            out.write(json.dumps({"kind": "block_end", "block": args.block, "attempts_run": n,
                                  "ended_utc": rb.utc()}) + "\n")


if __name__ == "__main__":
    main()
