#!/usr/bin/env python3
"""CUA vs opencli head-to-head, one shard (kvnloo/cua#161, rerun after the invalid 2026-10-26 run).

Four cells per tool: {warm, cold} x {read, write}. Blocks are ABBA or BAAB (A = CUA Driver,
B = opencli), balanced inside every shard. Read blocks run first; write blocks run only when
the read phase in the same shard had zero unauthorized effects (synthetic, reversible writes
on the loopback fixture only). One attempt = independent reset, one timed tool invocation,
independent /state + /audit oracle. No retry, no fallback, no model calls.

  warm  CUA: one persistent `cua-driver mcp` session and one driver-launched isolated Chromium,
             prepared before the timed attempts; each attempt navigates and reads/acts.
        opencli: one persistent Chromium with a CDP port; each attempt runs the `opencli` CLI
             (opencli's normal CDP route; one node process per call).
  cold  CUA: timer starts before `cua-driver mcp` spawns; includes initialize, browser_prepare
             (Chromium launch), window bind, navigate and read/act.
        opencli: timer starts before Chromium spawns; includes CDP readiness and the CLI call.
  Browser/driver teardown is outside the timer for both tools.

Writes: CUA types into the semantic ref and clicks Submit (dom_event), then polls the page until
it shows the submitted status. opencli's adapter does the same with page.evaluate + 100 ms poll.
Credit: opencli is jackwener/opencli (Apache-2.0). Pomerado (MIT, Pomerado AI, Inc.) is NOT run here.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from urllib.request import urlopen
import uuid

HERE = Path(__file__).resolve().parent
PREV = HERE.parent / "pomerado-cua-2026-10-25"
sys.path.insert(0, str(PREV))
from arm_common import Oracle, judge, sha256_text  # noqa: E402
from mcp_stdio import McpStdioClient  # noqa: E402

SCHEMA = "cua.h2h.attempt.v1"
SEED = 20261027
SHARDS = 10
BLOCKS_PER_CELL_PER_SHARD = 4  # 2 ABBA + 2 BAAB per (mode, effect) per shard
TOOL = {"A": "cua", "B": "opencli"}
FIELD_NAME, SUBMIT_NAME = "verification value", "Submit"


def build_plan(seed: int = SEED, shards: int = SHARDS, per: int = BLOCKS_PER_CELL_PER_SHARD) -> list:
    """Deterministic, balanced block plan for all shards."""
    plan = []
    for shard in range(shards):
        rng = random.Random(f"{seed}:{shard}")
        phases = []
        for effect in ("read", "write"):
            blocks = []
            for mode in ("warm", "cold"):
                schemes = ["ABBA", "BAAB"] * (per // 2)
                rng.shuffle(schemes)
                blocks += [{"mode": mode, "effect": effect, "scheme": s} for s in schemes]
            rng.shuffle(blocks)
            phases += blocks
        for i, b in enumerate(phases):
            b["block_id"] = f"s{shard}-b{i:02d}-{b['effect'][0]}{b['mode'][0]}"
            b["shard"] = shard
        plan.append(phases)
    return plan


class ToolError(Exception):
    pass


def wait_gone(pid: int, timeout: float = 8.0) -> None:
    for _ in range(int(timeout / 0.1)):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        time.sleep(0.1)


class Cua:
    """Minimal deterministic CUA Driver caller over MCP stdio (same tools jev-use uses)."""

    def __init__(self, binary: str):
        self.client = McpStdioClient([binary, "mcp"], env=dict(os.environ))
        self.label = f"h2h-{uuid.uuid4().hex[:8]}"
        self.client.initialize(30)
        self.pid = None
        self.target = self.tab = None
        self.calls = 0

    def call(self, name: str, args: dict, timeout: float = 30.0) -> dict:
        self.calls += 1
        result = self.client.request("tools/call", {"name": name,
                                                    "arguments": {**args, "session": self.label}},
                                     timeout)
        data = result.get("structuredContent")
        if result.get("isError") or not isinstance(data, dict) or data.get("status") == "refused" \
                or data.get("refusal"):
            raise ToolError(f"{name}: {json.dumps(result)[:300]}")
        return data

    def prepare(self) -> None:
        prepared = self.call("browser_prepare",
                             {"allow_launch": True, "profile": {"mode": "isolated_new"}}, 60)
        self.pid = int(prepared["prepared_pid"])
        window = None
        for _ in range(120):
            wins = self.call("list_windows", {"pid": self.pid}).get("windows", [])
            visible = [w for w in wins if w.get("is_on_screen")]
            if visible:
                window = max(visible, key=lambda w: w["bounds"]["width"] * w["bounds"]["height"])
                break
            time.sleep(0.1)
        if window is None:
            raise ToolError("isolated browser window did not become ready")
        bound = self.call("get_browser_state", {"pid": self.pid, "window_id": window["window_id"]})
        self.target = bound["target_id"]
        tabs = bound["tabs"]
        self.tab = str(next((t for t in tabs if t.get("active")), tabs[0])["tab_id"])

    def _tab(self) -> dict:
        return {"target_id": self.target, "tab_id": self.tab}

    def snapshot(self) -> dict:
        return self.call("get_browser_state", {**self._tab(), "snapshot_format": "semantic_v2"})

    def read(self, base: str) -> dict:
        self.call("browser_navigate", {**self._tab(), "url": base + "/"})
        return self.snapshot()

    def write(self, base: str, value: str) -> dict:
        self.call("browser_navigate", {**self._tab(), "url": base + "/"})
        snap = self.snapshot()
        refs = snap.get("refs") or []
        field = [r for r in refs if r.get("role") == "textbox" and r.get("name") == FIELD_NAME]
        button = [r for r in refs if r.get("role") == "button" and r.get("name") == SUBMIT_NAME]
        if len(field) != 1 or len(button) != 1:
            raise ToolError(f"target not unique: field={len(field)} button={len(button)}")
        self.call("browser_type", {**self._tab(), "ref": field[0]["ref"], "text": value,
                                   "replace": True})
        # One submission. Anything after this click is confirmation only; never replayed.
        self.call("browser_click", {**self._tab(), "ref": button[0]["ref"],
                                    "input_route": "dom_event"})
        want = "status=submitted:" + value
        for _ in range(50):
            try:
                snap = self.snapshot()
                if want in json.dumps(snap):
                    return snap
            except ToolError:
                pass  # navigation in flight
            time.sleep(0.1)
        raise ToolError("submitted status not observed on page within 5 s")

    def close(self) -> None:
        pid = self.pid
        try:
            self.client.close()
        except Exception:
            pass
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            wait_gone(pid)


class Chrome:
    """A plain Chromium with a CDP port for opencli (same binary family the driver launches)."""

    def __init__(self, binary: str):
        self.profile = tempfile.mkdtemp(prefix="h2h-chrome-")
        self.proc = subprocess.Popen(
            [binary, f"--user-data-dir={self.profile}", "--remote-debugging-port=0",
             "--remote-debugging-address=127.0.0.1", "--no-first-run",
             "--no-default-browser-check", "--disable-features=Translate", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        port_file = Path(self.profile) / "DevToolsActivePort"
        deadline = time.monotonic() + 30
        self.endpoint = None
        while time.monotonic() < deadline:
            if port_file.exists():
                first = port_file.read_text().split("\n", 1)[0].strip()
                if first.isdigit():
                    endpoint = f"http://127.0.0.1:{first}"
                    try:
                        with urlopen(endpoint + "/json/version", timeout=2) as r:  # noqa: S310
                            if r.status == 200:
                                self.endpoint = endpoint
                                break
                    except OSError:
                        pass
            time.sleep(0.05)
        if not self.endpoint:
            raise ToolError("chromium CDP endpoint not ready within 30 s")

    def close(self) -> None:
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait()
        shutil.rmtree(self.profile, ignore_errors=True)


def opencli_call(cmd: list, endpoint: str, effect: str, base: str, value: str | None,
                 timeout: float) -> dict:
    if effect == "read":
        argv = [*cmd, "jev", "read-status", "--origin", base, "-f", "json"]
    else:
        argv = [*cmd, "jev", "submit-value", "--value", value, "--origin", base,
                "--confirm-write", "yes", "-f", "json"]
    env = {**os.environ, "OPENCLI_CDP_ENDPOINT": endpoint}
    env.pop("OPENCLI_DAEMON_PORT", None)
    done = subprocess.run(argv, env=env, capture_output=True, timeout=timeout, check=False)
    if done.returncode != 0:
        raise ToolError(f"opencli exit {done.returncode}: {done.stderr.decode(errors='replace')[-200:]}")
    out = json.loads(done.stdout)
    if effect == "write" and ("status=submitted:" + value) not in json.dumps(out):
        raise ToolError("submitted status not observed on page")
    return out


class Shard:
    def __init__(self, a):
        self.a = a
        self.base = "http://127.0.0.1:8766"
        self.oracle = Oracle(self.base)
        self.cua_warm = None
        self.chrome_warm = None
        self.opencli = [a.opencli]
        self.pins = json.loads(Path(a.pins).read_text())

    def emit(self, kind: str, obj: dict) -> None:
        print(f"{kind} " + json.dumps(obj, sort_keys=True), flush=True)

    def warm_up(self) -> None:
        self.cua_warm = Cua(self.a.driver)
        self.cua_warm.prepare()
        self.chrome_warm = Chrome(self.a.chrome)
        exe = {}
        for name, pid in (("cua_browser_exe", self.cua_warm.pid),
                          ("opencli_browser_exe", self.chrome_warm.proc.pid)):
            try:
                exe[name] = os.readlink(f"/proc/{pid}/exe")
            except OSError as error:
                exe[name] = f"unreadable: {type(error).__name__}"
        # Process-start baselines (not attempts): explains the CLI-per-call share of opencli warm time.
        for name, argv in (("opencli_version_ms", [*self.opencli, "--version"]),
                           ("cua_driver_version_ms", [self.a.driver, "--version"])):
            samples = []
            for _ in range(5):
                t0 = time.perf_counter()
                subprocess.run(argv, capture_output=True, check=False, timeout=30)
                samples.append(round((time.perf_counter() - t0) * 1000.0, 1))
            exe[name] = samples
        self.emit("H2HMETA", exe)

    def invoke(self, tool: str, mode: str, effect: str, value: str | None):
        """Returns (ok, output, detail, teardown, extra) with teardown run after the timer."""
        if tool == "cua":
            if mode == "warm":
                c = self.cua_warm
                before = c.calls
                out = c.read(self.base) if effect == "read" else c.write(self.base, value)
                return out, None, {"tool_calls": c.calls - before}
            c = None
            try:
                c = Cua(self.a.driver)
                c.prepare()
                out = c.read(self.base) if effect == "read" else c.write(self.base, value)
                return out, c.close, {"tool_calls": c.calls}
            except Exception:
                if c is not None:
                    c.close()
                raise
        if mode == "warm":
            out = opencli_call(self.opencli, self.chrome_warm.endpoint, effect, self.base, value, 60)
            return out, None, {"tool_calls": 1}
        ch = Chrome(self.a.chrome)
        try:
            out = opencli_call(self.opencli, ch.endpoint, effect, self.base, value, 60)
        except Exception:
            ch.close()
            raise
        return out, ch.close, {"tool_calls": 1}

    def attempt(self, block: dict, pos: int, arm: str, warmup: bool = False) -> dict:
        tool, mode, effect = TOOL[arm], block["mode"], block["effect"]
        value = f"h2h-{block['block_id']}-{pos}-{uuid.uuid4().hex[:6]}" if effect == "write" else None
        reset_ok, before, audit0 = self.oracle.reset_verified()
        rec = {"schema": SCHEMA, "shard": block["shard"], "block_id": block["block_id"],
               "scheme": block["scheme"], "position": pos, "arm": arm, "tool": tool, "mode": mode,
               "effect": effect, "warmup": warmup, **self.pins}
        if not reset_ok:
            rec.update(oracle_outcome="not_run", detail="reset not verified")
            return rec
        teardown, detail, extra, out, ok = None, "", {}, None, True
        t0 = time.perf_counter()
        try:
            out, teardown, extra = self.invoke(tool, mode, effect, value)
        except Exception as error:  # one attempt, no retry
            ok, detail = False, f"{type(error).__name__}: {str(error)[:240]}"
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        try:
            state, audit1 = self.oracle.state(), self.oracle.audit()
            after = int(audit1.get("commit_count", -1))
        except Exception as error:
            state, audit1, after = {"submitted": "<oracle-unreachable>"}, {}, before
            ok, detail = False, f"oracle unreachable: {type(error).__name__}"
        if teardown:
            t1 = time.perf_counter()
            try:
                teardown()
            except Exception:
                pass
            rec["teardown_ms"] = round((time.perf_counter() - t1) * 1000.0, 1)
        verdict = judge(SimpleNamespace(effect_kind=effect, value=value),
                        SimpleNamespace(ok=ok, output=out), state, before, after,
                        "status=waiting")
        rec.update(elapsed_ms=round(elapsed_ms, 2), audit_before=before, audit_after=after,
                   route=("blocked" if not ok else
                          ("cua-driver-mcp" if tool == "cua" else "opencli-adapter-cdp")),
                   output_sha256=sha256_text(json.dumps(out, sort_keys=True)) if ok else None,
                   oracle_evidence="state+audit:" + sha256_text(json.dumps(
                       {"before": audit0, "after": audit1, "state": state}, sort_keys=True)),
                   model_calls=0, fallback_count=0, retries=0, detail=detail, **extra, **verdict)
        return rec

    def run(self) -> int:
        started = time.monotonic()
        plan = build_plan()[self.a.shard]
        if self.a.max_blocks < len(plan):  # smoke: first block of each cell, never a result
            seen, smoke = set(), []
            for b in plan:
                if (b["mode"], b["effect"]) not in seen:
                    seen.add((b["mode"], b["effect"]))
                    smoke.append({**b, "block_id": "smoke-" + b["block_id"]})
            plan = smoke[:self.a.max_blocks]
        self.emit("H2HPLAN", {"shard": self.a.shard, "blocks": plan})
        fixture = subprocess.Popen([sys.executable, str(PREV / "audit_fixture.py"), "--port", "8766"],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                try:
                    with urlopen(self.base + "/state", timeout=1):  # noqa: S310
                        break
                except OSError:
                    time.sleep(0.05)
            self.warm_up()
            # Excluded warm-up: one attempt per tool per mode before any timed block.
            for mode in ("warm", "cold"):
                for arm in ("A", "B"):
                    wb = {"mode": mode, "effect": "read", "scheme": "-", "shard": self.a.shard,
                          "block_id": f"s{self.a.shard}-warmup-{mode}"}
                    self.emit("H2HJSON", self.attempt(wb, 0, arm, warmup=True))
            read_bad = 0
            for block in plan:
                if block["effect"] == "write" and read_bad:
                    self.emit("H2HSKIP", {"block_id": block["block_id"],
                                          "reason": "write gate closed: read phase had unauthorized/unknown effects"})
                    continue
                if time.monotonic() - started > self.a.deadline_s:
                    self.emit("H2HSKIP", {"block_id": block["block_id"], "reason": "shard deadline"})
                    continue
                for pos, arm in enumerate(block["scheme"], start=1):
                    rec = self.attempt(block, pos, arm)
                    if block["effect"] == "read" and (rec.get("unauthorized_effect")
                                                      or rec.get("oracle_outcome") == "unknown"):
                        read_bad += 1
                    self.emit("H2HJSON", rec)
        finally:
            for closer in (self.cua_warm, self.chrome_warm):
                if closer is not None:
                    try:
                        closer.close()
                    except Exception:
                        pass
            fixture.terminate()
            fixture.wait(timeout=5)
        self.emit("H2HDONE", {"shard": self.a.shard,
                              "seconds": round(time.monotonic() - started, 1)})
        return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--shard", type=int)
    p.add_argument("--driver", help="absolute path of the pinned cua-driver binary")
    p.add_argument("--chrome", default="/opt/google/chrome/google-chrome")
    p.add_argument("--opencli", help="absolute path of the pinned opencli executable")
    p.add_argument("--pins", help="JSON file with the pins recorded in every receipt")
    p.add_argument("--deadline-s", type=float, default=380.0)
    p.add_argument("--max-blocks", type=int, default=99, help="smoke runs only; partial shards are not results")
    p.add_argument("--print-plan", action="store_true")
    a = p.parse_args(argv)
    if a.print_plan:
        print(json.dumps({"seed": SEED, "shards": SHARDS,
                          "blocks_per_cell_per_shard": BLOCKS_PER_CELL_PER_SHARD,
                          "plan": build_plan()}, indent=1, sort_keys=True))
        return 0
    if None in (a.shard, a.driver, a.opencli, a.pins):
        p.error("--shard, --driver, --opencli and --pins are required")
    return Shard(a).run()


if __name__ == "__main__":
    raise SystemExit(main())
