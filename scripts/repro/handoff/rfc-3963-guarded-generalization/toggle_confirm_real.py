#!/usr/bin/env python3
"""Is trycua/cua#4316's guarded rule a fixture hack or a reusable two-action obligation?

Second guarded task shape on a REAL Driver/MCP/Chromium path: toggle -> confirm, against a LOCAL owned
disposable fixture (the upstream fixture has no toggle page and #4316's module is hard-wired to the form
fixture, so nothing upstream is modified). The recipe below is the SAME rule shape as guarded_completion.py:

  plan   : after the provider selects the first mutation, bind (session, logical completion target,
           prior ref) only if exactly one completion target exists and the task is exactly two actions;
  resolve: after the first mutation, re-prove from a FRESH snapshot - same session, first action's
           postcondition visible (switch is on), exactly one enabled completion target, fresh ref != prior
           ref - else fail closed to an ordinary provider decision.

Independent oracle = the fixture's own /state journal (toggle/confirm POST counts), never the Driver.

usage (inside the isolated X session): toggle_confirm_real.py --examples-dir DIR --out-dir DIR [--reps N] [--dump]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = """<!doctype html><meta charset=utf-8><title>Settings</title>
<h1>Settings</h1>
<label><input id=sw type=checkbox role=switch aria-label="Enable alerts"> Enable alerts</label>
<button id=confirm type=button disabled>Confirm</button>
<div id=extra></div>
<script>
const v = new URLSearchParams(location.search).get('variant') || 'normal';
const sw = document.getElementById('sw'), btn = document.getElementById('confirm'), extra = document.getElementById('extra');
if (v === 'dup') { const b = document.createElement('button'); b.textContent = 'Confirm'; b.disabled = true; extra.appendChild(b); b.onclick = () => fetch('/confirm', {method: 'POST'}); }
sw.addEventListener('change', async () => {
  const r = await fetch('/toggle', {method: 'POST', body: JSON.stringify({on: sw.checked})});
  const j = await r.json();
  if (!j.accepted) { sw.checked = false; return; }
  btn.disabled = false;
  if (v === 'rebind') btn.textContent = 'Confirm changes';
  if (v === 'dup_after') { const b = document.createElement('button'); b.textContent = 'Confirm'; b.onclick = () => fetch('/confirm', {method: 'POST'}); extra.appendChild(b); }
  if (v === 'dup') extra.querySelector('button').disabled = false;
});
btn.addEventListener('click', () => fetch('/confirm', {method: 'POST'}));
</script>"""


class Journal:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = {"toggled": False, "toggle_posts": 0, "confirmed": False, "confirm_posts": 0, "refuse_toggle": False}


JOURNAL = Journal()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, payload, code=200):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/state"):
            return self._json({k: v for k, v in JOURNAL.state.items() if k != "refuse_toggle"})
        if self.path.startswith("/reset"):
            JOURNAL.reset()
            JOURNAL.state["refuse_toggle"] = "refuse" in self.path
            return self._json({"ok": True})
        data = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        s = JOURNAL.state
        if self.path == "/toggle":
            s["toggle_posts"] += 1
            accepted = not s["refuse_toggle"]
            if accepted:
                s["toggled"] = json.loads(body or b"{}").get("on", False)
            return self._json({"accepted": accepted})
        if self.path == "/confirm":
            s["confirm_posts"] += 1
            if s["toggled"]:
                s["confirmed"] = True
            return self._json({"ok": True})
        self._json({}, 404)


def oracle(url_base: str) -> dict:
    return json.loads(urllib.request.urlopen(url_base + "/state", timeout=3).read())


# ---- the generic two-action obligation (same rule shape as guarded_completion.py) -------------------

@dataclass(frozen=True)
class Plan:
    session: str
    first_id: str
    completion_role: str
    completion_name: str
    prior_ref: str


def matching(snapshot: dict, role: str, name: str, *, actionable_only: bool = True) -> list:
    """Actionable refs live in snapshot["refs"]; disabled/inert nodes only in snapshot["content_refs"]."""
    pools = [snapshot.get("refs") or []] + ([] if actionable_only else [snapshot.get("content_refs") or []])
    return [r for pool in pools for r in pool
            if isinstance(r, dict) and r.get("role") == role and r.get("name") == name and r.get("ref")]


def plan_two_action(*, session, action_count, first_id, snapshot, completion_role, completion_name):
    if not session or action_count != 2:
        return None
    found = matching(snapshot, completion_role, completion_name, actionable_only=False)
    if len(found) != 1:
        return None
    return Plan(session, first_id, completion_role, completion_name, str(found[0]["ref"]))


def resolve_two_action(plan, *, session, snapshot, postcondition):
    if not session or session != plan.session or not postcondition(snapshot):
        return None
    # exactly one logical target anywhere in the fresh snapshot, and it must be actionable now
    if len(matching(snapshot, plan.completion_role, plan.completion_name, actionable_only=False)) != 1:
        return None
    found = matching(snapshot, plan.completion_role, plan.completion_name)
    if len(found) != 1:
        return None
    ref = str(found[0]["ref"])
    if ref == plan.prior_ref or (found[0].get("states") or {}).get("disabled"):
        return None
    return ref


def switch_is_on(snapshot: dict) -> bool:
    found = matching(snapshot, "switch", "Enable alerts")
    return len(found) == 1 and str((found[0].get("states") or {}).get("checked")).lower() == "true"


async def run(a) -> int:
    ex = a.examples_dir.resolve()
    sys.path[:0] = [str(ex / "python"), str(ex)]
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from driver_env import driver_environment
    from run import Driver, select_tab_id, wait_for_window

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    params = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=driver_environment())
    rows = []
    a.out_dir.mkdir(parents=True, exist_ok=True)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            d = Driver(s, "toggle-guarded")
            prepared = await d.call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int(prepared["prepared_pid"])
            window = await wait_for_window(d, pid)
            state = await d.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
            target, tab = str(state["target_id"]), select_tab_id(state["tabs"])

            async def snap():
                return await d.call("get_browser_state", {"target_id": target, "tab_id": tab, "snapshot_format": "semantic_v2"})

            async def click(ref):
                return await d.call("browser_click", {"target_id": target, "tab_id": tab, "ref": ref, "input_route": "dom_event"})

            async def trial(name, variant, *, guarded, action_count=2, refuse=False, inject_first_error=False, old_ref_probe=False):
                urllib.request.urlopen(f"{base}/reset{'?refuse=1' if refuse else ''}", timeout=3).read()
                await d.call("browser_navigate", {"target_id": target, "tab_id": tab, "url": f"{base}/?variant={variant}"})
                t0 = time.perf_counter()
                counts = {"provider_decisions": 0, "semantic_observations": 0, "driver_actions": 0}
                route = []
                s0 = await snap(); counts["semantic_observations"] += 1
                sw = matching(s0, "switch", "Enable alerts")
                if a.dump:
                    (a.out_dir / "snapshot-dump.json").write_text(json.dumps(s0, indent=1))
                    return {}
                assert len(sw) == 1, f"switch not found: {[ (r.get('role'), r.get('name')) for r in s0.get('refs', [])]}"
                counts["provider_decisions"] += 1; route.append("provider")      # provider selects the first mutation
                plan = plan_two_action(session="toggle-guarded", action_count=action_count, first_id="toggle-alerts",
                                       snapshot=s0, completion_role="button", completion_name="Confirm") if guarded else None
                first = await click(sw[0]["ref"]); counts["driver_actions"] += 1
                first_error = inject_first_error   # emulate "may have landed": result treated as unknown
                s1 = await snap(); counts["semantic_observations"] += 1
                ref = None
                if plan is not None and not first_error:
                    ref = resolve_two_action(plan, session="toggle-guarded", snapshot=s1, postcondition=switch_is_on)
                old_ref_result = None
                if old_ref_probe and plan is not None:
                    try:
                        r = await click(plan.prior_ref)
                        refused = isinstance(r, dict) and r.get("effect") == "refused"
                        old_ref_result = {"accepted": not refused,
                                          "refusal_code": (r.get("error") or {}).get("code") if refused else None}
                    except Exception as exc:
                        old_ref_result = {"accepted": False, "refusal": str(exc)[:200]}
                if ref is not None:
                    route.append("guarded-completion")
                else:
                    counts["provider_decisions"] += 1; route.append("provider")
                    cands = matching(s1, "button", "Confirm")   # chooser only sees actionable candidates
                    ref = str(cands[0]["ref"]) if len(cands) == 1 else None
                    # a provider never re-issues the toggle: the fresh state shows it already applied
                dispatched = None
                if ref is not None:
                    await click(ref); counts["driver_actions"] += 1; dispatched = ref
                deadline = time.perf_counter() + 2.0
                final = oracle(base)
                while time.perf_counter() < deadline and not (final["confirmed"] and final["toggled"]):
                    await asyncio.sleep(0.02); final = oracle(base)
                verified = bool(final["toggled"] and final["confirmed"] and final["toggle_posts"] == 1 and final["confirm_posts"] == 1)
                return {"trial": name, "variant": variant, "guarded_flag": guarded, "route": route, "counts": counts,
                        "verified_by_independent_oracle": verified, "oracle": final,
                        "ms_to_verified": round((time.perf_counter() - t0) * 1000, 1),
                        "prior_ref": plan.prior_ref if plan else None, "dispatched_completion_ref": dispatched,
                        "second_action_fresh_ref": bool(plan and dispatched and dispatched != plan.prior_ref) if plan else None,
                        "old_ref_probe": old_ref_result}

            if a.dump:
                await trial("dump", "normal", guarded=True)
                return 0
            # Positive: baseline vs guarded, interleaved
            for i in range(a.reps):
                for guarded in ((False, True) if i % 2 == 0 else (True, False)):
                    row = await trial(f"positive-{i}-{'guarded' if guarded else 'baseline'}", "normal", guarded=guarded)
                    rows.append(row)
            # Negative rows (guarded flag on; deletion must be refused, mutation must not be replayed)
            rows.append(await trial("neg-duplicate-target-at-plan", "dup", guarded=True))
            rows.append(await trial("neg-duplicate-target-after-toggle", "dup_after", guarded=True))
            rows.append(await trial("neg-rebound-target-renamed", "rebind", guarded=True))
            rows.append(await trial("neg-toggle-rejected-by-app", "normal", guarded=True, refuse=True))
            rows.append(await trial("neg-three-step-task-stays-chooser", "normal", guarded=True, action_count=3))
            rows.append(await trial("neg-may-have-landed-no-replay", "normal", guarded=True, inject_first_error=True))
            rows.append(await trial("ctl-old-ref-reuse-refuses", "normal", guarded=True, old_ref_probe=True))
    (a.out_dir / "trials.json").write_text(json.dumps(rows, indent=1) + "\n")
    pos = [r for r in rows if r["trial"].startswith("positive")]
    for arm in ("baseline", "guarded"):
        sel = [r for r in pos if r["trial"].endswith(arm)]
        print(arm, "n", len(sel), "verified", sum(r["verified_by_independent_oracle"] for r in sel),
              "provider decisions", sorted({r["counts"]["provider_decisions"] for r in sel}),
              "routes", sorted({tuple(r["route"]) for r in sel}),
              "ms_to_verified p50", statistics.median(r["ms_to_verified"] for r in sel))
    for r in rows:
        if not r["trial"].startswith("positive"):
            print(r["trial"], "route", r["route"], "provider_decisions", r["counts"]["provider_decisions"], "verified", r["verified_by_independent_oracle"],
                  "toggle_posts", r["oracle"]["toggle_posts"], "confirm_posts", r["oracle"]["confirm_posts"], "old_ref", r["old_ref_probe"])
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--examples-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--reps", type=int, default=10)
    p.add_argument("--dump", action="store_true")
    raise SystemExit(asyncio.run(run(p.parse_args())))
