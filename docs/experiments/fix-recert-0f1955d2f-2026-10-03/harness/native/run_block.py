"""OWN-36 block runner: cross-session capture / element-token ownership on Linux X11 GTK3.

FIX-02 copy: copied by path from ff77554f4 (docs/experiments/own-36-session-isolation-native-
2026-10-02/harness/run_block.py). FIX-02 changes, all marked "FIX-02": I2d falls back to a
harness-supplied handle when the refusal discloses none (so the minted token is still presented);
I5p runs the 'same' observation order in every attempt; new row I5pt relaunches A with a different
tree (CUA_GTK3_TASK_DENSITY=12) between Driver generations. Everything else is unchanged.

One invocation = one block (at most 10 attempts) run inside a private X11 session
(cua-x11-session.sh under hostless) while the caller holds the shared quiet-lane lock.
Measurement only: the Driver binary is unmodified; the GTK3 task fixture's own state
file (CUA_GTK3_TASK_STATE) is the independent oracle, read before and after every call.

Topologies
  T1  one `cua-driver mcp` process, sessions A and B are public `session` labels
  T2  one `cua-driver serve` daemon, two `cua-driver mcp --socket` MCP clients;
      A and B are each client's implicit transport session (I5 adds a label on A)
  T3  sequential / concurrent separate `cua-driver mcp` processes (I5p, X1 only)

Usage: run_block.py --topology T1 --row I2 --block 3 --attempts 0-9 --out <file>
"""

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpclient import McpClient, text_of  # noqa: E402

DRV = os.environ["OWN36_DRIVER"]
FIX = os.environ["OWN36_FIXTURE"]
WORK = os.environ["OWN36_WORK"]  # per-block scratch dir (never committed)
SCRUB = [p for p in (os.environ.get("OWN36_SCRUB", "").split(":")) if p]
SETTLE_S = 0.8  # wait after a call expected to change nothing
LAND_S = 3.0  # poll budget for a call expected to change the fixture
CHECKBOX = "I agree"
NOTE = "Note"
SAVE = "Save note"


def utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def scrub(text):
    for i, prefix in enumerate(sorted(SCRUB, key=len, reverse=True)):
        text = text.replace(prefix, f"<scrubbed{i}>")
    return text


# ── fixture ───────────────────────────────────────────────────────────────────
class App:
    def __init__(self, tag):
        self.tag = tag
        self.state_path = os.path.join(WORK, f"state-{tag}.json")
        self.proc = None
        self.window_id = None

    def launch(self, extra_env=None):
        if os.path.exists(self.state_path):
            os.remove(self.state_path)
        env = dict(os.environ, CUA_GTK3_TASK_STATE=self.state_path, **(extra_env or {}))  # FIX-02
        self.proc = subprocess.Popen(
            [os.environ.get("OWN36_PYTHON", "python3"), FIX],
            env=env,
            stdout=open(os.path.join(WORK, f"app-{self.tag}.log"), "ab"),
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = self.read()
            if state and state.get("pid") == self.proc.pid:
                return
            time.sleep(0.1)
        raise RuntimeError(f"fixture {self.tag} did not publish state")

    @property
    def pid(self):
        return self.proc.pid

    def read(self):
        try:
            with open(self.state_path, encoding="utf-8") as stream:
                return json.load(stream)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


# ── topologies ────────────────────────────────────────────────────────────────
def driver_env():
    return dict(os.environ, DO_NOT_TRACK="1", CUA_DRIVER_RS_TELEMETRY_ENABLED="0")


class Topology:
    """call(tag, tool, args) routes a call as session `tag` (A or B)."""

    def __init__(self, kind, block):
        self.kind = kind
        self.block = block
        self.labels = {"A": None, "B": None}
        self.clients = {}
        self.daemon = None
        self.sock = os.path.join(WORK, "own36.sock")
        self._n = 0

    def _client(self, name, argv):
        self._n += 1
        client = McpClient(argv, os.path.join(WORK, f"{name}-{self._n}.stderr"), env=driver_env())
        client.initialize()
        return client

    def start(self):
        if self.kind == "T1":
            shared = self._client("mcp", [DRV, "mcp"])
            self.clients = {"A": shared, "B": shared}
            self.labels = {"A": f"own36-A-{self.block}", "B": f"own36-B-{self.block}"}
        elif self.kind == "T2":
            self.daemon = subprocess.Popen(
                [DRV, "serve", "--socket", self.sock],
                env=driver_env(),
                stdout=open(os.path.join(WORK, "serve.out"), "ab"),
                stderr=open(os.path.join(WORK, "serve.err"), "ab"),
            )
            deadline = time.monotonic() + 15
            while not os.path.exists(self.sock):
                if time.monotonic() > deadline:
                    raise RuntimeError("daemon socket missing")
                time.sleep(0.1)
            for tag in "AB":
                self.clients[tag] = self._client(f"proxy{tag}", [DRV, "mcp", "--socket", self.sock])
        else:
            raise ValueError(self.kind)

    def reconnect(self, tag):
        """T2: replace one MCP client (new transport session)."""
        assert self.kind == "T2"
        self.clients[tag].close()
        self.clients[tag] = self._client(f"proxy{tag}", [DRV, "mcp", "--socket", self.sock])

    def call(self, tag, tool, args, label=None):
        args = dict(args)
        session = label if label is not None else self.labels[tag]
        if session:
            args["session"] = session
        return args, self.clients[tag].call(tool, args)

    def close(self):
        seen = set()
        for client in self.clients.values():
            if id(client) not in seen:
                seen.add(id(client))
                client.close()
        if self.daemon:
            subprocess.run([DRV, "stop", "--socket", self.sock], env=driver_env(), timeout=30,
                           capture_output=True)
            try:
                self.daemon.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.daemon.terminate()
                self.daemon.wait()


# ── response handling ─────────────────────────────────────────────────────────
GWS_KEEP = ("snapshot_id", "capture_id", "window_id", "pid", "element_count", "screenshot_width",
            "screenshot_height")


def compact(result, keep_tree=False):
    """Response as recorded: image payloads replaced by their length; for
    get_window_state only identity fields plus the two fixture elements."""
    result = json.loads(json.dumps(result))
    for item in result.get("content", []):
        if item.get("type") == "image":
            item["data"] = f"<image {len(item.get('data', ''))} b64 chars>"
    sc = result.get("structuredContent")
    if isinstance(sc, dict) and "elements" in sc and not keep_tree:
        elements = {e.get("label"): e for e in sc.get("elements", [])}
        result["structuredContent"] = {k: sc.get(k) for k in GWS_KEEP}
        result["structuredContent"]["elements_kept"] = {
            name: elements.get(name) for name in (CHECKBOX, NOTE, SAVE)
        }
        result["content"] = [
            item if item.get("type") != "text" or "Invalidated" in item.get("text", "")
            else {"type": "text", "text": "<gws text omitted>"}
            for item in result.get("content", [])
        ]
    return result


def element(result, label):
    sc = result.get("structuredContent") or {}
    for item in sc.get("elements", []):
        if item.get("label") == label:
            return item
    return None


def refusal_code(result):
    sc = result.get("structuredContent") or {}
    if isinstance(sc.get("refusal"), dict):
        return sc["refusal"].get("code")
    return sc.get("code")


def is_error(result):
    return bool(result.get("isError")) or "rpc_error" in result


# ── attempt recorder ─────────────────────────────────────────────────────────
class Attempt:
    def __init__(self, ctx, row, index, order, extra=None):
        self.ctx = ctx
        self.rec = {
            "kind": "setup" if row == "setup" else "attempt", "topology": ctx.topo.kind,
            "row": row, "block": ctx.block,
            "attempt": index, "order": order, "display": os.environ.get("DISPLAY"),
            "started_utc": utc(), "calls": [], "checks": {}, **(extra or {}),
        }

    def states(self):
        return {tag: app.read() for tag, app in self.ctx.apps.items()}

    def call(self, actor, tool, args, expect, step, label=None, keep_tree=False):
        """expect: 'change:<TAG>' (poll for that fixture to change) or 'none'."""
        pre = self.states()
        sent, result = self.ctx.topo.call(actor, tool, args, label=label)
        if expect.startswith("change:"):
            tag = expect.split(":", 1)[1]
            deadline = time.monotonic() + LAND_S
            while time.monotonic() < deadline and self.ctx.apps[tag].read() == pre[tag]:
                time.sleep(0.02)
            time.sleep(0.2)  # catch any second (unexpected) write
        else:
            time.sleep(SETTLE_S)
        post = self.states()
        self.rec["calls"].append({
            "step": step, "actor": actor, "tool": tool,
            "args": {k: v for k, v in sent.items()}, "expect": expect,
            "is_error": is_error(result), "refusal_code": refusal_code(result),
            "response": compact(result, keep_tree=keep_tree), "pre": pre, "post": post,
            "utc": utc(),
        })
        return result

    def gws(self, actor, target, step, label=None, keep_tree=False):
        app = self.ctx.apps[target]
        result = self.call(actor, "get_window_state",
                           {"pid": app.pid, "window_id": app.window_id}, "none", step, label=label,
                           keep_tree=keep_tree)
        chk = element(result, CHECKBOX)
        sc = result.get("structuredContent") or {}
        return {
            "snapshot_id": sc.get("snapshot_id"), "capture_id": sc.get("capture_id"),
            "token": chk and chk.get("element_token"),
            "index": chk and chk.get("element_index"),
            "frame": chk and chk.get("screenshot_frame"),
            "result": result,
        }

    def click_token(self, actor, target_tag, token, expect, step, pid=None, label=None):
        pid = pid if pid is not None else self.ctx.apps[target_tag].pid
        return self.call(actor, "click", {"pid": pid, "element_token": token}, expect, step,
                         label=label)

    def click_capture(self, actor, target_tag, obs, capture_id, expect, step, label=None):
        app = self.ctx.apps[target_tag]
        frame = obs["frame"]
        # The check indicator: 10 px into the check box row, vertically centred.
        x, y = frame["x"] + 10, frame["y"] + frame["h"] / 2
        return self.call(actor, "click", {"pid": app.pid, "window_id": app.window_id, "x": x,
                                          "y": y, "capture_id": capture_id}, expect, step,
                         label=label)

    def done(self):
        self.rec["ended_utc"] = utc()
        self.ctx.emit(self.rec)


class Ctx:
    def __init__(self, topo, block, out):
        self.topo = topo
        self.block = block
        self.out = out
        self.apps = {"A": App("A"), "B": App("B")}

    def emit(self, record):
        line = scrub(json.dumps(record, sort_keys=True))
        self.out.write(line + "\n")
        self.out.flush()

    def window_of(self, tag):
        app = self.apps[tag]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            _, result = self.topo.call(tag, "list_windows", {"pid": app.pid})
            windows = (result.get("structuredContent") or {}).get("windows") or []
            if windows:
                app.window_id = windows[0]["window_id"]
                return
            time.sleep(0.2)
        raise RuntimeError(f"no window for {tag}")


# ── rows ─────────────────────────────────────────────────────────────────────
FORGED_TOKENS = ["garbage", "s00000001", "sffffffff:2", "{live}:999", "s0000000g:2"]
FORGED_CAPTURES = ["garbage", "capture_", "capture_" + "0" * 32 + "_0000000000000000",
                   "{seq+256}", "{ns-flip}"]


def forge_token(kind_index, live_snapshot):
    value = FORGED_TOKENS[kind_index % len(FORGED_TOKENS)]
    return value.replace("{live}", live_snapshot or "s00000001")


def forge_capture(kind_index, live_capture):
    value = FORGED_CAPTURES[kind_index % len(FORGED_CAPTURES)]
    if value == "{seq+256}":
        ns, seq = live_capture.rsplit("_", 1)
        return f"{ns}_{int(seq, 16) + 256:016x}"
    if value == "{ns-flip}":
        prefix, ns, seq = live_capture.split("_")
        flipped = ("1" if ns[0] != "1" else "2") + ns[1:]
        return f"{prefix}_{flipped}_{seq}"
    return value


def observe_pair(att, order, label_a=None):
    """Initial observations in AB or BA order. Returns obs dict per tag."""
    obs = {}
    for tag in (order[0], order[1]):
        obs[tag] = att.gws(tag, tag, f"observe-{tag}", label=label_a if tag == "A" else None)
    return obs


def row_P(ctx, index, order, forge=None):
    att = Attempt(ctx, "P", index, order)
    obs = observe_pair(att, order)
    for tag in order:
        att.click_token(tag, tag, obs[tag]["token"], f"change:{tag}", f"own-token-{tag}")
    att.done()


def row_I1(ctx, index, order, forge=None):
    att = Attempt(ctx, "I1", index, order, {"forged": forge is not None})
    obs = observe_pair(att, order)
    capture = obs["A"]["capture_id"]
    if forge is not None:
        capture = forge_capture(forge, obs["A"]["capture_id"])
        att.rec["forged_value"] = capture
    att.click_capture("B", "A", obs["A"], capture, "none", "B-uses-A-capture")
    # Discriminating tail: A's capture is still live for A after B's refused attempt.
    att.click_capture("A", "A", obs["A"], obs["A"]["capture_id"], "change:A", "A-uses-own-capture")
    att.done()


def row_I2(ctx, index, order, forge=None):
    att = Attempt(ctx, "I2", index, order, {"forged": forge is not None})
    obs = observe_pair(att, order)
    token = obs["A"]["token"]
    if forge is not None:
        token = forge_token(forge, obs["A"]["snapshot_id"])
        att.rec["forged_value"] = token
    att.click_token("B", "B", token, "none", "B-uses-A-token-on-B-pid")
    att.click_token("B", "A", token, "none", "B-uses-A-token-on-A-pid")
    # Tail: A's own token on A (verifies the token was live; restores state parity).
    att.click_token("A", "A", obs["A"]["token"], "change:A", "A-uses-own-token")
    att.done()


def row_I2d(ctx, index, order, forge=None):
    """Diagnostic: B never receives A's token; it derives one from a refusal envelope."""
    att = Attempt(ctx, "I2d", index, order)
    obs = observe_pair(att, order)
    probe = att.click_token("B", "A", "sffffffff:%d" % obs["B"]["index"], "none",
                            "B-stale-probe-on-A-pid")
    current = (probe.get("structuredContent") or {}).get("current_snapshots") or []
    match = [c for c in current if c.get("window_id") == ctx.apps["A"].window_id]
    derived = f"{match[0]['snapshot_id']}:{obs['B']['index']}" if match else None
    # FIX-02: record the disclosure, and when the refusal discloses no handle, B still mints
    # `<A's handle>:<B's own index>` from a handle obtained out of band (the harness supplies A's
    # snapshot handle), so the minted token is always presented.
    att.rec["disclosed_handles"] = [c.get("snapshot_id") for c in current]
    att.rec["disclosed_A_handle"] = obs["A"]["snapshot_id"] in att.rec["disclosed_handles"]
    att.rec["derived_source"] = "disclosure" if derived else "harness"
    if not derived:
        derived = f"{obs['A']['snapshot_id']}:{obs['B']['index']}"
    att.rec["derived_token"] = derived
    att.rec["derived_equals_A_token"] = derived == obs["A"]["token"]
    if derived:
        att.click_token("B", "A", derived, "none", "B-uses-derived-token-on-A-pid")
    att.click_token("A", "A", obs["A"]["token"], "change:A", "A-uses-own-token")
    att.done()


def row_I3(ctx, index, order, forge=None):
    att = Attempt(ctx, "I3", index, order, {"forged": forge is not None})
    obs = observe_pair(att, order)
    replaced = att.gws("A", "A", "A-replaces-snapshot")
    token_b = obs["B"]["token"]
    expect = "change:B"
    if forge is not None:
        token_b = forge_token(forge, obs["B"]["snapshot_id"])
        att.rec["forged_value"] = token_b
        expect = "none"
    att.click_token("B", "B", token_b, expect, "B-uses-own-pre-replacement-token")
    # In-session discriminating negative: A's own superseded token is refused.
    att.click_token("A", "A", obs["A"]["token"], "none", "A-uses-own-superseded-token")
    att.rec["A_new_token"] = replaced["token"]
    att.done()


def row_I3s(ctx, index, order, forge=None):
    """Diagnostic: both sessions observe the SAME window (A's)."""
    att = Attempt(ctx, "I3s", index, order)
    first, second = order[0], order[1]
    o1 = att.gws(first, "A", f"{first}-observes-A-window")
    o2 = att.gws(second, "A", f"{second}-observes-A-window")
    att.click_token(first, "A", o1["token"], "none", f"{first}-uses-token-after-{second}-observed")
    att.click_token(second, "A", o2["token"], "change:A", f"{second}-uses-own-latest-token")
    att.done()


def row_I4(ctx, index, order, forge=None):
    att = Attempt(ctx, "I4", index, order, {"forged": forge is not None})
    label_a = None
    if ctx.topo.kind == "T1":
        label_a = f"own36-A-{ctx.block}-i4-{index}"
    else:
        ctx.topo.reconnect("A")  # fresh implicit session for A
    obs = observe_pair(att, order, label_a=label_a)
    att.call("A", "end_session", {}, "none", "A-ends-session", label=label_a)
    att.click_token("B", "B", obs["B"]["token"], "change:B", "B-own-token-after-A-ended")
    token = obs["A"]["token"]
    if forge is not None:
        token = forge_token(forge, obs["A"]["snapshot_id"])
        att.rec["forged_value"] = token
    att.click_token("B", "A", token, "none", "B-uses-ended-A-token")
    att.click_token("A", "A", obs["A"]["token"], "none", "A-uses-own-token-after-end",
                    label=label_a)
    att.done()


def row_I5(ctx, index, order, forge=None):
    att = Attempt(ctx, "I5", index, order, {"forged": forge is not None})
    label_a = f"own36-A-{ctx.block}-i5-{index}"
    att.rec["label_restart"] = True
    obs = observe_pair(att, order, label_a=label_a)
    if order == "AB":
        att.click_token("B", "B", obs["B"]["token"], "change:B", "B-own-token-before-A-restart")
    att.call("A", "end_session", {}, "none", "A-ends-session", label=label_a)
    att.call("A", "start_session", {}, "none", "A-restarts-same-label", label=label_a)
    new = att.gws("A", "A", "A-observes-after-restart", label=label_a)
    old_token = obs["A"]["token"]
    if forge is not None:
        old_token = forge_token(forge, new["snapshot_id"])
        att.rec["forged_value"] = old_token
    att.click_token("A", "A", old_token, "none", "A-uses-old-generation-token", label=label_a)
    att.click_capture("A", "A", obs["A"], obs["A"]["capture_id"], "none",
                      "A-uses-old-generation-capture", label=label_a)
    att.click_token("A", "A", new["token"], "change:A", "A-uses-new-generation-token",
                    label=label_a)
    if order == "BA":
        att.click_token("B", "B", obs["B"]["token"], "change:B", "B-own-token-after-A-restart")
    att.done()


def row_N(ctx, index, order, forge=None):
    """In-session discriminating negative: token from a destroyed + recreated window."""
    att = Attempt(ctx, "N", index, order)
    before = att.gws("A", "A", "A-observes")
    old_pid, old_window = ctx.apps["A"].pid, ctx.apps["A"].window_id
    ctx.apps["A"].stop()
    ctx.apps["A"].launch()
    ctx.window_of("A")
    att.rec["recreated"] = {"old_pid": old_pid, "old_window": old_window,
                            "new_pid": ctx.apps["A"].pid, "new_window": ctx.apps["A"].window_id}
    att.gws("A", "A", "A-observes-recreated")
    att.click_token("A", "A", before["token"], "none", "A-uses-stale-token-on-recreated-pid")
    att.click_token("A", "A", before["token"], "none", "A-uses-stale-token-on-dead-pid",
                    pid=old_pid)
    att.done()


ROWS = {"P": row_P, "I1": row_I1, "I2": row_I2, "I2d": row_I2d, "I3": row_I3, "I3s": row_I3s,
        "I4": row_I4, "I5": row_I5, "N": row_N}


def setup_markers(ctx):
    """Give each window a unique saved note (the I6 content markers), verified on the oracle."""
    markers = {}
    for tag in "AB":
        marker = f"{'ALPHA' if tag == 'A' else 'BRAVO'}{random.randrange(16**8):08x}"
        att = Attempt(ctx, "setup", 0, "AB", {"marker_tag": tag, "marker": marker})
        obs = att.gws(tag, tag, "observe")
        note = element(obs["result"], NOTE)
        save = element(obs["result"], SAVE)
        att.call(tag, "set_value", {"pid": ctx.apps[tag].pid, "element_token": note["element_token"],
                                    "value": marker}, "none", "set-note")
        att.call(tag, "click", {"pid": ctx.apps[tag].pid, "element_token": save["element_token"]},
                 f"change:{tag}", "save-note")
        att.gws(tag, tag, "observe-with-marker", keep_tree=True)
        att.rec["marker_saved"] = (ctx.apps[tag].read() or {}).get("note_saved") == marker
        att.done()
        markers[tag] = marker
    return markers


# ── T3 rows (separate processes) ─────────────────────────────────────────────
def t3_block(args, out):
    apps = {"A": App("A"), "B": App("B")}
    for app in apps.values():
        app.launch()
    emit = lambda r: (out.write(scrub(json.dumps(r, sort_keys=True)) + "\n"), out.flush())

    def proc():
        client = McpClient([DRV, "mcp"], os.path.join(WORK, f"mcp-{time.monotonic_ns()}.stderr"),
                           env=driver_env())
        client.initialize()
        return client

    def window(client, app):
        for _ in range(75):
            r = client.call("list_windows", {"pid": app.pid})
            w = (r.get("structuredContent") or {}).get("windows") or []
            if w:
                return w[0]["window_id"]
            time.sleep(0.2)
        raise RuntimeError("no window")

    def gws(client, app, wid, label):
        r = client.call("get_window_state", {"pid": app.pid, "window_id": wid, "session": label})
        chk = element(r, CHECKBOX)
        sc = r.get("structuredContent") or {}
        return {"snapshot_id": sc.get("snapshot_id"), "capture_id": sc.get("capture_id"),
                "token": chk["element_token"], "frame": chk["screenshot_frame"]}, r

    def call(client, actor, tool, a, expect, step, rec):
        pre = {t: x.read() for t, x in apps.items()}
        result = client.call(tool, a)
        if expect.startswith("change:"):
            tag = expect.split(":")[1]
            deadline = time.monotonic() + LAND_S
            while time.monotonic() < deadline and apps[tag].read() == pre[tag]:
                time.sleep(0.02)
            time.sleep(0.2)
        else:
            time.sleep(SETTLE_S)
        rec["calls"].append({"step": step, "actor": actor, "tool": tool, "args": a,
                             "expect": expect, "is_error": is_error(result),
                             "refusal_code": refusal_code(result), "response": compact(result),
                             "pre": pre, "post": {t: x.read() for t, x in apps.items()},
                             "utc": utc()})
        return result

    for index in args.attempt_list:
        order = "AB" if index % 2 == 0 else "BA"
        rec = {"kind": "attempt", "topology": "T3", "row": args.row, "block": args.block,
               "attempt": index, "order": order, "display": os.environ.get("DISPLAY"),
               "started_utc": utc(), "calls": [], "checks": {}}
        if args.row == "X1":
            # Two concurrent Driver processes, each observing only its own window first.
            ca, cb = proc(), proc()
            wa, wb = window(ca, apps["A"]), window(cb, apps["B"])
            seq = [("A", ca, wa), ("B", cb, wb)] if order == "AB" else [("B", cb, wb), ("A", ca, wa)]
            toks = {}
            for tag, client, wid in seq:
                o, r = gws(client, apps[tag], wid, f"own36-{tag}")
                toks[tag] = o
                rec["calls"].append({"step": f"observe-{tag}", "actor": tag,
                                     "tool": "get_window_state", "response": compact(r),
                                     "utc": utc()})
            rec["tokens"] = {t: toks[t]["token"] for t in toks}
            rec["captures"] = {t: toks[t]["capture_id"] for t in toks}
            ca.close()
            cb.close()
        elif args.row == "I5p":
            # Driver process generation 1 observes; it exits; generation 2 observes and is
            # handed generation 1's token and capture. Arm 'same' keeps the observation order
            # (A first), arm 'swapped' observes B first in generation 2.
            arm = "same"  # FIX-02: every I5p attempt keeps the observation order
            rec["arm"] = arm
            g1 = proc()
            wa, wb = window(g1, apps["A"]), window(g1, apps["B"])
            o1a, r1 = gws(g1, apps["A"], wa, "own36-A")
            rec["calls"].append({"step": "gen1-observe-A", "actor": "A", "tool": "get_window_state",
                                 "response": compact(r1), "utc": utc()})
            g1.close()
            g2 = proc()
            if arm == "swapped":
                _, rb = gws(g2, apps["B"], wb, "own36-B")
                rec["calls"].append({"step": "gen2-observe-B", "actor": "B",
                                     "tool": "get_window_state", "response": compact(rb),
                                     "utc": utc()})
            o2a, r2 = gws(g2, apps["A"], wa, "own36-A")
            rec["calls"].append({"step": "gen2-observe-A", "actor": "A", "tool": "get_window_state",
                                 "response": compact(r2), "utc": utc()})
            rec["gen1_token"], rec["gen2_token"] = o1a["token"], o2a["token"]
            rec["gen1_capture"], rec["gen2_capture"] = o1a["capture_id"], o2a["capture_id"]
            call(g2, "A", "click", {"pid": apps["A"].pid, "element_token": o1a["token"],
                                    "session": "own36-A"}, "none", "gen2-uses-gen1-token", rec)
            f = o1a["frame"]
            call(g2, "A", "click", {"pid": apps["A"].pid, "window_id": wa, "x": f["x"] + 10,
                                    "y": f["y"] + f["h"] / 2, "capture_id": o1a["capture_id"],
                                    "session": "own36-A"}, "none", "gen2-uses-gen1-capture", rec)
            g2.close()
        elif args.row == "I5pt":
            # FIX-02: the tree differs between Driver generations. Generation 1 observes A (default
            # tree) and exits; A is relaunched with CUA_GTK3_TASK_DENSITY=12 (distractor controls
            # precede the task controls, so element indices shift); generation 2 observes the
            # relaunched A first (same order) and is handed generation 1's token for it.
            if getattr(apps["A"], "density", None):
                apps["A"].stop()
                apps["A"].launch()
                apps["A"].density = None
            g1 = proc()
            wa = window(g1, apps["A"])
            o1a, r1 = gws(g1, apps["A"], wa, "own36-A")
            rec["calls"].append({"step": "gen1-observe-A", "actor": "A", "tool": "get_window_state",
                                 "response": compact(r1), "utc": utc()})
            g1.close()
            old_pid = apps["A"].pid
            apps["A"].stop()
            apps["A"].launch(extra_env={"CUA_GTK3_TASK_DENSITY": "12"})
            apps["A"].density = 12
            rec["relaunched"] = {"old_pid": old_pid, "new_pid": apps["A"].pid, "density": 12}
            g2 = proc()
            wa2 = window(g2, apps["A"])
            o2a, r2 = gws(g2, apps["A"], wa2, "own36-A")
            rec["calls"].append({"step": "gen2-observe-A", "actor": "A", "tool": "get_window_state",
                                 "response": compact(r2), "utc": utc()})
            rec["gen1_token"], rec["gen2_token"] = o1a["token"], o2a["token"]
            gen1_index = int(o1a["token"].rsplit(":", 1)[1])
            at_index = [e for e in (r2.get("structuredContent") or {}).get("elements", [])
                        if e.get("element_index") == gen1_index]
            rec["gen2_element_at_gen1_index"] = (
                {"label": at_index[0].get("label"), "role": at_index[0].get("role")} if at_index else None)
            call(g2, "A", "click", {"pid": apps["A"].pid, "element_token": o1a["token"],
                                    "session": "own36-A"}, "none", "gen2-uses-gen1-token", rec)
            g2.close()
        rec["ended_utc"] = utc()
        emit(rec)
    for app in apps.values():
        app.stop()
    return len(args.attempt_list)


def parse_attempts(spec):
    lo, _, hi = spec.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topology", required=True, choices=["T1", "T2", "T3"])
    parser.add_argument("--row", required=True)
    parser.add_argument("--block", required=True)
    parser.add_argument("--attempts", required=True)
    parser.add_argument("--forged", action="store_true",
                        help="attempt k presents forged value family[k] instead of the real one")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    args.attempt_list = parse_attempts(args.attempts)
    assert len(args.attempt_list) <= 10, "at most 10 attempts per lock acquisition"
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(DRV, "rb") as stream:
        sha = hashlib.sha256(stream.read()).hexdigest()
    version = subprocess.run([DRV, "--version"], capture_output=True, text=True,
                             env=driver_env()).stdout.strip()
    with open(args.out, "a", encoding="utf-8") as out:
        header = {"kind": "block", "topology": args.topology, "row": args.row,
                  "block": args.block, "attempts": args.attempt_list, "forged": args.forged,
                  "display": os.environ.get("DISPLAY"), "driver_sha256": sha,
                  "driver_version": version, "started_utc": utc(),
                  "telemetry_env": {"DO_NOT_TRACK": "1", "CUA_DRIVER_RS_TELEMETRY_ENABLED": "0"}}
        out.write(json.dumps(header, sort_keys=True) + "\n")
        out.flush()
        if args.topology == "T3":
            n = t3_block(args, out)
        else:
            topo = Topology(args.topology, args.block)
            ctx = Ctx(topo, args.block, out)
            try:
                for app in ctx.apps.values():
                    app.launch()
                topo.start()
                for tag in "AB":
                    ctx.window_of(tag)
                setup_markers(ctx)
                fn = ROWS[args.row]
                for index in args.attempt_list:
                    order = "AB" if index % 2 == 0 else "BA"
                    fn(ctx, index, order, forge=index if args.forged else None)
                n = len(args.attempt_list)
            finally:
                topo.close()
                for app in ctx.apps.values():
                    app.stop()
        out.write(json.dumps({"kind": "block_end", "block": args.block, "attempts_run": n,
                              "ended_utc": utc()}) + "\n")


if __name__ == "__main__":
    main()
