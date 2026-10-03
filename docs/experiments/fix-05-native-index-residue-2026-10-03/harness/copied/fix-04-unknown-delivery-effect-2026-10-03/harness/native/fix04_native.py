"""FIX-04 Part C (kvnloo/cua#36): the native AT-SPI pid-wide fallbacks of type_into_editable_at and
focus_element, and the Part D W2dX discrimination control.

Measurement only. Runs inside cua-x11-session.sh (private Xvfb + openbox + AT-SPI) under hostless, with
the shared quiet-lane lock held by the caller (harness/qlock_fix04.sh). Reuses, imported unchanged from
the FIX-03 packet on this branch: harness/w2/w2_rows.py (TwoWindowApp, Ctx, Att, close_w1) and its
wave-3 helpers (harness/fix02-w3/native/run_block.py: Topology T2, McpClient, compact, element), and
harness/native/fix03_native.py (row_W2dX, unchanged). Topology T2: one `cua-driver serve` daemon, two
`mcp --socket` clients = sessions A and B. Fixture: this packet's GTK3 copy in two-window mode
(CUA_GTK3_TWO_WINDOWS=1) with CUA_GTK3_NOTE_TEXT_STATE=1 (per-window live Note text) and
CUA_GTK3_FOCUS_STATE=1 (per-window focused widget and active flag); one process, windows w1 and w2.

Forced path (SOURCE, atspi/mod.rs + native.rs): the window-scoped cached element of A's token (w1) is
gone because w1 was closed, so the cached AT-SPI write / GrabFocus fails and the code re-resolves the
element index against a fresh walk of the WHOLE application (pid-wide). Element indices are
application-wide; w1 is walked before w2, so after w1 closes w2's controls take w1's indices and the
index of A's w1 control names the same control of w2.

Rows (fresh fixture per attempt; w1 closed by the fixture itself on SIGUSR1, confirmed on its state file)
  CT  A observes w1 (A's Note token), B observes w2. Close w1. A type_text {element_token: A's w1
      Note, text "fix04A"} (background). Tail: B type_text its own w2 Note token ("fix04B") changes w2.
  CF  A observes w1 (A's checkbox token), B observes w2. Close w1. A press_key {element_token: A's w1
      checkbox, key space, delivery_mode foreground} (activate the token's window, AT-SPI GrabFocus on
      the indexed element, then an XTest key). Tail: B clicks its own w2 checkbox token (changes w2).
      Shakedown: the background variant is refused `background_unavailable` before the GrabFocus
      rung on this X11 session (no focus-free keyboard backend), so the counted row uses foreground.
  W2dX  FIX-03's row unchanged (A observes w1 and w2; close w1; B dispatches A's w2 token; tail A).
Oracle (target-owned): the fixture's state file read before and after every call. A cross-window
effect is any change of w2's keys during A's call.

usage: fix04_native.py --row CT|CF|W2dX --block <id> --attempts 0-9 --out <file>
Environment as w2_rows.py (OWN36_DRIVER, OWN36_FIXTURE, OWN36_WORK, OWN36_SCRUB, OWN36_PYTHON).
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FIX03 = os.path.join(HERE, "..", "..", "..", "fix-03-toctou-session-routing-2026-10-03", "harness")
sys.path.insert(0, os.path.join(FIX03, "native"))
import fix03_native as f3  # noqa: E402  (unchanged FIX-03 copy; imports w2_rows and run_block)

w2 = f3.w2
rb = f3.rb
CLOSE_SETTLE_S = 0.5  # after w1's close is confirmed, before A's call (pre-registered)


def note_token(obs):
    note = rb.element(obs["result"], rb.NOTE)
    return note and note.get("element_token")


def observe_pair(att, order):
    seq = [("A", "w1"), ("B", "w2")] if order == "AB" else [("B", "w2"), ("A", "w1")]
    return {actor: att.gws_w(actor, key, f"{actor}-observes-{key}") for actor, key in seq}


def close_w1(att, ctx):
    att.rec["w1_closed_confirmed"] = ctx.apps["P"].close_w1()
    time.sleep(CLOSE_SETTLE_S)
    att.rec["state_after_close"] = ctx.apps["P"].read()


def row_CT(ctx, index, order):
    att = f3.Att(ctx, "CT", index, order)
    app = ctx.apps["P"]
    obs = observe_pair(att, order)
    att.rec["handles"] = {"A_w1_note": note_token(obs["A"]), "B_w2_note": note_token(obs["B"]),
                          "A_w1_note_index": (rb.element(obs["A"]["result"], rb.NOTE) or {}).get("element_index"),
                          "B_w2_note_index": (rb.element(obs["B"]["result"], rb.NOTE) or {}).get("element_index")}
    close_w1(att, ctx)
    att.call("A", "type_text", {"pid": app.pid, "element_token": note_token(obs["A"]), "text": "fix04A"},
             "none", "A-types-into-closed-w1-note-with-own-token")
    att.call("B", "type_text", {"pid": app.pid, "element_token": note_token(obs["B"]), "text": "fix04B"},
             "change:P", "B-types-into-own-w2-note-tail")
    att.done()


def row_CF(ctx, index, order):
    att = f3.Att(ctx, "CF", index, order)
    app = ctx.apps["P"]
    obs = observe_pair(att, order)
    att.rec["handles"] = {"A_w1_checkbox": obs["A"]["token"], "B_w2_checkbox": obs["B"]["token"],
                          "A_w1_checkbox_index": f3.checkbox_index(obs["A"]),
                          "B_w2_checkbox_index": f3.checkbox_index(obs["B"])}
    close_w1(att, ctx)
    att.call("A", "press_key", {"pid": app.pid, "element_token": obs["A"]["token"], "key": "space",
                                "delivery_mode": "foreground"},
             "none", "A-presses-space-on-closed-w1-checkbox-with-own-token")
    att.click_tok("B", obs["B"]["token"], "change:P", "B-clicks-own-w2-checkbox-tail")
    att.done()


ROWS = {"CT": row_CT, "CF": row_CF, "W2dX": f3.row_W2dX}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", required=True, choices=sorted(ROWS))
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
        header = {"kind": "block", "topology": "T2", "row": args.row, "block": args.block,
                  "attempts": attempts, "display": os.environ.get("DISPLAY"),
                  "driver_sha256": sha, "driver_version": version, "fixture_sha256": fixture_sha,
                  "harness_sha256": {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest()
                                     for p in (__file__, f3.__file__, w2.__file__, rb.__file__)},
                  "fixture_env": {k: os.environ.get(k) for k in
                                  ("CUA_GTK3_NOTE_TEXT_STATE", "CUA_GTK3_FOCUS_STATE")},
                  "close_settle_s": CLOSE_SETTLE_S, "started_utc": rb.utc(),
                  "telemetry_env": {"DO_NOT_TRACK": os.environ.get("DO_NOT_TRACK"),
                                    "CUA_DRIVER_RS_TELEMETRY_ENABLED":
                                        os.environ.get("CUA_DRIVER_RS_TELEMETRY_ENABLED")}}
        out.write(json.dumps(header, sort_keys=True) + "\n")
        out.flush()
        topo = rb.Topology("T2", args.block)
        app = w2.TwoWindowApp()
        ctx = w2.Ctx(topo, args.block, out, app)
        n = 0
        try:
            app.launch()
            topo.start()
            ctx.map_windows()
            for index in attempts:
                if index != attempts[0]:
                    app.stop()
                    app.launch()
                    ctx.map_windows()
                out.write(json.dumps({"kind": "windows", "block": args.block, "attempt": index,
                                      "windows": dict(app.windows)}, sort_keys=True) + "\n")
                order = "AB" if index % 2 == 0 else "BA"
                ROWS[args.row](ctx, index, order)
                n += 1
        finally:
            topo.close()
            app.stop()
            out.write(json.dumps({"kind": "block_end", "block": args.block, "attempts_run": n,
                                  "ended_utc": rb.utc()}) + "\n")


if __name__ == "__main__":
    main()
