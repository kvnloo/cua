"""FIX-05 (kvnloo/cua#36, kvnloo/cua#73 E4): the native index-fallback residue left by FIX-04 F6c.

Measurement only. Runs inside cua-x11-session.sh (private Xvfb + openbox + AT-SPI) under hostless, with the
SHARED quiet-lane lock held by the caller (harness/qlock_fix05.sh, <= 300 s per block). Reuses, imported
unchanged, the blob-identical FIX-04 copy harness/copied/fix-04-.../harness/native/fix04_native.py
(observe_pair, close_w1) and through it the FIX-03 helpers (fix03_native.Att: per-call wall clock and
receipt window id; w2_rows.TwoWindowApp/Ctx; run_block.Topology T2 / element / compact). Topology T2: one
`cua-driver serve` daemon per block, two `mcp --socket` clients = sessions A and B. A fresh fixture per
attempt. Fixture: this packet's GTK3 copy (harness/gtk3_main_two_windows.py = the FIX-04 copy + the
opt-in FIX-05 scroll region and focus log, harness/gtk3_main_two_windows.fix05.diff) with
CUA_GTK3_NOTE_TEXT_STATE=1, CUA_GTK3_FOCUS_STATE=1, CUA_GTK3_SCROLL_STATE=1, CUA_GTK3_FOCUS_LOG=1.

Rows (two-window rows: A observes w1, B observes w2, observation order AB/BA alternating; w1 is closed by the
fixture itself on SIGUSR1, confirmed on its state file, then 0.5 s settle)
  RPA  A click {element_token: A's own w1 "I agree" token}   (the public element action tool; SOURCE: it
       resolves through perform_action_observed, not perform_action(pid, idx)). Tail: B clicks its own
       w2 checkbox token (must change w2).
  RSC  A scroll {element_token: A's own w1 "Scroll" token, direction down, amount 1}   (-> atspi::scroll_element).
       Tail: B scrolls its own w2 "Scroll" token (must change w2).
  RSV  A set_value {element_token: A's own w1 "Note" token, value "fix05A"}  (-> set_value_in, whose
       fallback is set_value(pid, idx)). Tail: B set_value its own w2 Note token "fix05B" (must change w2).
  RCF  A hotkey {element_token: A's own w1 "I agree" token, keys [ctrl, F12], delivery_mode foreground}
       (-> the up-front atspi::focus_element GrabFocus rung of hotkey). Tail: B clicks its own w2 checkbox.
  NC   negative control, both windows OPEN, every token live: A then B, each on its OWN window, with click
       (checkbox), scroll (Scroll), set_value (Note) and hotkey-focus (checkbox). Each must change only its
       own window.
  NS   single-window, single-session normal path (fixture without CUA_GTK3_TWO_WINDOWS): session A observes
       the window and runs click, scroll, set_value and hotkey-focus on its own tokens; each must change it.
Oracle (target-owned): the fixture's state file (per-window agreed / note_text / scroll_value / focus /
focus_log, written by the fixture process) read before and after every call; the tails are session B's own
reads of w2. A's receipt (status, effect, refusal code) is recorded for E4 accounting only.

usage: fix05_native.py --row RPA|RSC|RSV|RCF|NC|NS --block <id> --attempts 0-9 --out <file>
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
FIX04 = os.path.join(HERE, "..", "copied", "fix-04-unknown-delivery-effect-2026-10-03", "harness", "native")
sys.path.insert(0, FIX04)
import fix04_native as f4  # noqa: E402  (blob-identical FIX-04 copy; imports fix03_native, w2_rows, run_block)

f3 = f4.f3
w2 = f4.w2
rb = f4.rb
SCROLL = "Scroll"
HOTKEY = ["ctrl", "F12"]
FIXTURE_ENV = ("CUA_GTK3_NOTE_TEXT_STATE", "CUA_GTK3_FOCUS_STATE", "CUA_GTK3_SCROLL_STATE",
               "CUA_GTK3_FOCUS_LOG")


def handle(obs, label):
    item = rb.element(obs["result"], label) or {}
    return {"token": item.get("element_token"), "index": item.get("element_index"), "role": item.get("role")}


def handles(obs_a, obs_b):
    out = {}
    for actor, obs, key in (("A", obs_a, "w1"), ("B", obs_b, "w2")):
        for name, label in (("checkbox", w2.CHECKBOX), ("note", rb.NOTE), ("scroll", SCROLL)):
            out[f"{actor}_{key}_{name}"] = handle(obs, label)
    return out


def tool_call(name, pid, token, value):
    if name == "click":
        return "click", {"pid": pid, "element_token": token}
    if name == "scroll":
        return "scroll", {"pid": pid, "element_token": token, "direction": "down", "amount": 1}
    if name == "set_value":
        return "set_value", {"pid": pid, "element_token": token, "value": value}
    if name == "hotkey":
        return "hotkey", {"pid": pid, "element_token": token, "keys": HOTKEY, "delivery_mode": "foreground"}
    raise ValueError(name)


TARGET = {"click": "checkbox", "scroll": "scroll", "set_value": "note", "hotkey": "checkbox"}


def closed_row(row, tool, tail_tool):
    def run(ctx, index, order):
        att = f3.Att(ctx, row, index, order)
        app = ctx.apps["P"]
        obs = f4.observe_pair(att, order)
        att.rec["handles"] = handles(obs["A"], obs["B"])
        f4.close_w1(att, ctx)
        a = att.rec["handles"][f"A_w1_{TARGET[tool]}"]["token"]
        b = att.rec["handles"][f"B_w2_{TARGET[tail_tool]}"]["token"]
        name, args = tool_call(tool, app.pid, a, "fix05A")
        att.call("A", name, args, "none", f"A-{tool}-closed-w1-with-own-token")
        name, args = tool_call(tail_tool, app.pid, b, "fix05B")
        att.call("B", name, args, "change:P", f"B-{tail_tool}-own-w2-tail")
        att.done()
    return run


def row_NC(ctx, index, order):
    att = f3.Att(ctx, "NC", index, order)
    app = ctx.apps["P"]
    obs = f4.observe_pair(att, order)
    att.rec["handles"] = handles(obs["A"], obs["B"])
    for tool in ("click", "scroll", "set_value", "hotkey"):
        for actor, key in (("A", "w1"), ("B", "w2")):
            token = att.rec["handles"][f"{actor}_{key}_{TARGET[tool]}"]["token"]
            name, args = tool_call(tool, app.pid, token, f"nc{actor}")
            att.call(actor, name, args, "change:P", f"{actor}-{tool}-own-live-{key}")
    att.done()


def row_NS(ctx, index, order):
    att = f3.Att(ctx, "NS", index, order)
    app = ctx.apps["P"]
    result = att.call("A", "get_window_state", {"pid": app.pid, "window_id": app.windows["w"]}, "none",
                      "A-observes-single-window")
    obs = {"result": result}
    hs = {name: handle(obs, label) for name, label in
          (("checkbox", w2.CHECKBOX), ("note", rb.NOTE), ("scroll", SCROLL))}
    att.rec["handles"] = hs
    for tool in ("click", "scroll", "set_value", "hotkey"):
        name, args = tool_call(tool, app.pid, hs[TARGET[tool]]["token"], "nsA")
        att.call("A", name, args, "change:P", f"A-{tool}-own-single-window")
    att.done()


ROWS = {"RPA": closed_row("RPA", "click", "click"), "RSC": closed_row("RSC", "scroll", "scroll"),
        "RSV": closed_row("RSV", "set_value", "set_value"), "RCF": closed_row("RCF", "hotkey", "click"),
        "NC": row_NC, "NS": row_NS}


class SingleCtx(w2.Ctx):
    def map_windows(self):
        app = self.apps["P"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            _, result = self.topo.call("A", "list_windows", {"pid": app.pid})
            windows = (result.get("structuredContent") or {}).get("windows") or []
            for window in windows:
                if (window.get("title") or "") == w2.TITLE:
                    app.windows = {"w": window["window_id"]}
                    return windows
            time.sleep(0.2)
        raise RuntimeError("single window not listed")


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
    single = args.row == "NS"
    with open(args.out, "a", encoding="utf-8") as out:
        header = {"kind": "block", "topology": "T2", "row": args.row, "block": args.block,
                  "attempts": attempts, "display": os.environ.get("DISPLAY"),
                  "driver_sha256": sha, "driver_version": version, "fixture_sha256": fixture_sha,
                  "harness_sha256": {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest()
                                     for p in (__file__, f4.__file__, f3.__file__, w2.__file__, rb.__file__)},
                  "fixture_env": {k: os.environ.get(k) for k in FIXTURE_ENV},
                  "two_windows": not single, "close_settle_s": f4.CLOSE_SETTLE_S, "started_utc": rb.utc(),
                  "telemetry_env": {"DO_NOT_TRACK": os.environ.get("DO_NOT_TRACK"),
                                    "CUA_DRIVER_RS_TELEMETRY_ENABLED":
                                        os.environ.get("CUA_DRIVER_RS_TELEMETRY_ENABLED")}}
        out.write(json.dumps(header, sort_keys=True) + "\n")
        out.flush()
        topo = rb.Topology("T2", args.block)
        app = w2.TwoWindowApp(two=not single)
        ctx = (SingleCtx if single else w2.Ctx)(topo, args.block, out, app)
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
