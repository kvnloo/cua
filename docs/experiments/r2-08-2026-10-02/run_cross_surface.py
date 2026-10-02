"""R2-08 cross-surface equivalence trial runner (measurement only).

Runs INSIDE the isolated X11 session (cua-x11-session.sh via run_in_session.sh)
with the jev-use virtualenv and cwd = the jev-use directory. It reuses the
jev-use runner pieces unchanged (``Driver``, ``wait_for_window``,
``select_tab_id``, ``task_candidates_for_step``, ``FixtureFormTask``,
``choose_mock_for_task``, ``validate_choice``) and the experiment-owned fixture
variants in ``variants.py``. Every Driver call is an ordinary public MCP tool
call on the unmodified main binary with default safety settings.

Per trial: fresh fixture server (port 0), fresh ``cua-driver mcp`` process and
fresh isolated_new Chrome; G_off toggles ``set_agent_cursor_enabled
{enabled:false}`` right after initialize; then browser_prepare, window, bind,
navigate and a wait for the browser's own GET / receipt in the fixture journal
(the same initial page load in every arm), then an initial /state read. All of
that is before T.

T starts at the first observation send (GUI) or the first eligibility read
send (API), and ends at the return of the first /state read that shows the
trial's value. After the final action returns, /state is polled every 2 ms up
to a 2000 ms bound. Nothing is ever retried or replayed: a transport error
leaves the outcome to the oracle.

usage (inside the session):
  run_cross_surface.py --driver <bin> --out <dir> --phase base --rounds 20
  run_cross_surface.py --driver <bin> --out <dir> --phase neg --variant n1 --chunk 0
  run_cross_surface.py --driver <bin> --out <dir> --phase n2ctl
  run_cross_surface.py --driver <bin> --out <dir> --phase pilot
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PKT = Path(__file__).resolve().parent
JEV = Path.cwd()
sys.path[:0] = [str(PKT), str(JEV), str(JEV / "python")]

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from core import validate_choice  # noqa: E402
from driver_env import driver_environment  # noqa: E402
from jev_adapter import choose_mock_for_task  # noqa: E402
from run import Driver, select_tab_id, supports_capture_bound_click, task_candidates_for_step, wait_for_window  # noqa: E402
from tasks import FixtureFormTask  # noqa: E402
from variants import DOCUMENTED_CONTRACT, FORM_URLENCODED, VariantServer, eligibility, sha16  # noqa: E402

ARMS = ("G_on", "G_off", "API")
_HOST = socket.gethostname()
_ABS = re.compile(r"/(?:home|mnt|tmp|root|run|var|opt|usr)/[^\s\"']*")
POLL_S = 0.002
BOUND_MS = 2000.0
SETTLE_S = 0.3


def now() -> int:
    return time.monotonic_ns()


def loadavg() -> str:
    try:
        return Path("/proc/loadavg").read_text().strip()
    except OSError:
        return "unavailable"


def make_value(kind: str) -> str:
    if kind == "valid":
        return "r2-08-" + secrets.token_hex(6)
    return "r2-08-INVALID-" + secrets.token_hex(3)


# ------------------------------------------------------------------- plans
def plan_for(args: argparse.Namespace) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    if args.phase == "base":
        for r in range(args.round_offset, args.round_offset + args.rounds):
            k = r % 3
            order = list(ARMS[k:] + ARMS[:k])
            for pos, arm in enumerate(order):
                plan.append({"id": f"b{r:02d}-{pos}-{arm}", "phase": "base", "round": r, "pos": pos,
                             "variant": "base", "arm": arm, "value_kind": "valid"})
    elif args.phase == "neg":
        kind = "invalid" if args.variant == "n2" else "valid"
        first = ("G_off", "API") if args.chunk == 0 else ("API", "G_off")
        for i in range(10):
            arm = first[i % 2]
            plan.append({"id": f"{args.variant}c{args.chunk}-{i:02d}-{arm}", "phase": "neg", "chunk": args.chunk,
                         "pos": i, "variant": args.variant, "arm": arm, "value_kind": kind})
    elif args.phase == "n2ctl":
        for i in range(3):
            plan.append({"id": f"n2ctl-{i:02d}-G_off", "phase": "n2ctl", "pos": i, "variant": "n2",
                         "arm": "G_off", "value_kind": "valid"})
    elif args.phase == "pilot":
        for i, (variant, arm, kind) in enumerate([
            ("base", "G_on", "valid"), ("base", "G_off", "valid"), ("base", "API", "valid"),
            ("n1", "G_off", "valid"), ("n1", "API", "valid"), ("n2", "G_off", "invalid"),
            ("n2", "API", "invalid"), ("n3", "G_off", "valid"), ("n3", "API", "valid"),
            ("n2", "G_off", "valid"),
        ]):
            plan.append({"id": f"pilot-{i:02d}-{variant}-{arm}", "phase": "pilot", "pos": i,
                         "variant": variant, "arm": arm, "value_kind": kind})
    else:
        raise SystemExit(f"unknown phase {args.phase}")
    return plan


# ---------------------------------------------------------------- recorder
class Recorder:
    def __init__(self, value: str) -> None:
        self.events: list[dict[str, Any]] = []
        self.value = value

    def redact(self, obj: Any) -> Any:
        if isinstance(obj, str):
            obj = obj.replace(self.value, "<value>")
            if _HOST:
                obj = obj.replace(_HOST, "<host>")
            return _ABS.sub("<abs-path>", obj)
        if isinstance(obj, dict):
            return {k: self.redact(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.redact(v) for v in obj]
        return obj

    def add(self, name: str, **fields: Any) -> None:
        self.events.append({"event": name, "t_mono_ns": now(), **self.redact(fields)})


def compact(result: dict[str, Any]) -> dict[str, Any]:
    """Top-level scalar fields of a Driver result (no snapshot bodies)."""
    out: dict[str, Any] = {}
    for k, v in result.items():
        if isinstance(v, (str, bool, int, float)) or v is None:
            out[k] = v if not isinstance(v, str) else v[:200]
    return out


async def timed_call(rec: Recorder, driver: Driver, label: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    rec.add("call_send", label=label, tool=tool)
    try:
        result = await driver.call(tool, args)
    except Exception as error:  # retained, never retried
        rec.add("call_return", label=label, tool=tool, ok=False, error=type(error).__name__,
                code=getattr(error, "code", None), message=str(error)[:300])
        raise
    rec.add("call_return", label=label, tool=tool, ok=True, result=compact(result))
    return result


def http_state(url: str) -> dict[str, Any]:
    with urlopen(url + "state", timeout=2) as response:
        return json.loads(response.read())


def poll_oracle(rec: Recorder, url: str, value: str, label: str) -> None:
    """Poll /state every 2 ms until it shows ``value`` or the bound expires."""
    polls: list[list[Any]] = []
    t_start = now()
    confirmed = None
    final_tag = None
    while True:
        ts = now()
        try:
            submitted = http_state(url).get("submitted")
            tag = "value" if submitted == value else ("none" if submitted is None else "other")
            other = None if tag != "other" else sha16(submitted)
        except Exception as error:  # noqa: BLE001
            tag, other = "error:" + type(error).__name__, None
        tr = now()
        polls.append([ts, tr, tag] + ([other] if other else []))
        final_tag = tag
        if tag == "value":
            confirmed = tr
            break
        if (tr - t_start) / 1e6 >= BOUND_MS:
            break
        time.sleep(POLL_S)
    rec.add("oracle_polls", label=label, polls=polls, confirmed_ns=confirmed, final_tag=final_tag,
            bound_ms=BOUND_MS, poll_s=POLL_S)


def browser_loaded(server: VariantServer) -> bool:
    return any(e["kind"] == "render" and e.get("user_agent_is_browser") for e in server.state.entries())


# ------------------------------------------------------------------ arms
async def gui_task(rec: Recorder, driver: Driver, task: FixtureFormTask, ctx: dict[str, Any], result: dict[str, Any]) -> None:
    target_id, tab_id = ctx["target_id"], ctx["tab_id"]

    async def step(n: int, expect_tool: str) -> Any:
        snap = await timed_call(rec, driver, f"snapshot{n}", "get_browser_state",
                                {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
        rec.add("decide_start", step=n)
        candidates, sources, visual = await task_candidates_for_step(
            driver, task, snap, ctx["pid"], ctx["window_id"], ctx["available"], ctx["capture_bound"],
            visual_mode="auto")
        choice, _, _ = choose_mock_for_task(task, sources, candidates, [])
        cand = validate_choice(choice, candidates, current_capture_id=None)
        rec.add("decided", step=n, candidate=cand.id, tool=cand.tool,
                input_route=(cand.arguments or {}).get("input_route"),
                replace=(cand.arguments or {}).get("replace"), visual=visual.get("status"),
                candidate_ids=[c.id for c in candidates])
        if cand.tool != expect_tool:
            raise RuntimeError(f"forced_path_violation step {n}: {cand.id}/{cand.tool}")
        return cand

    rec.add("task_start", arm=result["arm"])
    cand1 = await step(1, "browser_type")
    await timed_call(rec, driver, "type", cand1.tool, cand1.arguments)
    cand2 = await step(2, "browser_click")
    if cand2.arguments.get("input_route") != "dom_event":
        raise RuntimeError("forced_path_violation: click route is not dom_event")
    result["forced_path_ok"] = True
    try:
        await timed_call(rec, driver, "click", cand2.tool, cand2.arguments)
    finally:
        poll_oracle(rec, ctx["url"], task.token, "verify")


def api_task(rec: Recorder, url: str, value: str, result: dict[str, Any]) -> None:
    rec.add("task_start", arm="API")
    rec.add("eligibility_send")
    with urlopen(url, timeout=2) as response:  # the target's own page, not captured traffic
        page = response.read().decode()
    rec.add("eligibility_return", bytes=len(page))
    check = eligibility(page, value)
    rec.add("eligibility_checked", check=check)
    result["eligibility"] = check
    # The request is built from the documented contract only. In negative
    # variants it is sent even if a stricter check would object: the arm
    # measures whether the base-task route transfers unchanged.
    c = DOCUMENTED_CONTRACT
    body = urlencode({c["field"]: value}).encode()
    req = Request(url.rstrip("/") + c["action"], method=c["method"].upper(), data=body,
                  headers={"Content-Type": FORM_URLENCODED})
    rec.add("post_send", fields=[c["field"]])
    status: int | None = None
    error = None
    try:
        with urlopen(req, timeout=2) as response:
            status = response.status
            response.read()
    except HTTPError as http_error:  # a refusal is an answer, not a transport failure
        status = http_error.code
    except (URLError, OSError) as transport:  # outcome unknown: never resend
        error = type(transport).__name__
    rec.add("post_return", status=status, error=error)
    result["forced_path_ok"] = True
    poll_oracle(rec, url, value, "verify")


# ------------------------------------------------------------------ trial
async def run_trial(spec: dict[str, Any], args: argparse.Namespace, out: Path) -> dict[str, Any]:
    value = make_value(spec["value_kind"])
    rec = Recorder(value)
    server = VariantServer(("127.0.0.1", 0), spec["variant"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    label = f"r2-08-{uuid.uuid4().hex[:8]}"
    result: dict[str, Any] = {**spec, "value_sha16": sha16(value), "value_len": len(value),
                              "loadavg_before": loadavg(), "outcome": "unknown", "forced_path_ok": None,
                              "error": None}
    t0 = now()
    prepared_pid = None
    try:
        params = StdioServerParameters(command=args.driver, args=["mcp"], env=driver_environment())
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                result["server_info"] = {"name": init.serverInfo.name, "version": init.serverInfo.version}
                tools = (await session.list_tools()).tools
                driver = Driver(session, label)
                if spec["arm"] == "G_off":
                    await timed_call(rec, driver, "arm_toggle", "set_agent_cursor_enabled", {"enabled": False})
                prepared = await timed_call(rec, driver, "prepare", "browser_prepare",
                                            {"allow_launch": True, "profile": {"mode": "isolated_new"}})
                prepared_pid = int(prepared["prepared_pid"])
                window = await wait_for_window(driver, prepared_pid)
                bound = await timed_call(rec, driver, "bind", "get_browser_state",
                                         {"pid": prepared_pid, "window_id": window["window_id"]})
                ctx = {"target_id": bound["target_id"], "tab_id": select_tab_id(bound["tabs"]),
                       "pid": prepared_pid, "window_id": int(window["window_id"]), "url": url,
                       "available": {t.name for t in tools}, "capture_bound": supports_capture_bound_click(tools)}
                await timed_call(rec, driver, "navigate", "browser_navigate",
                                 {"target_id": ctx["target_id"], "tab_id": ctx["tab_id"], "url": url})
                deadline = time.monotonic() + 5
                while not browser_loaded(server) and time.monotonic() < deadline:
                    await asyncio.sleep(0.01)
                rec.add("page_loaded", ok=browser_loaded(server))
                rec.add("initial_state", state=http_state(url))
                if spec["arm"] == "API":
                    api_task(rec, url, value, result)
                else:
                    task = FixtureFormTask(value, url, 4)
                    await gui_task(rec, driver, task, ctx, result)
                await asyncio.sleep(SETTLE_S)  # trailing beacons only; outside T
                rec.add("final_state", state=http_state(url))
                rec.add("driver_closing")
    except Exception as error:  # keep every failure in the denominator
        result["error"] = f"{type(error).__name__}: {str(error)[:300]}"
        try:
            rec.add("final_state_after_error", state=http_state(url))
        except Exception:  # noqa: BLE001
            pass
    result["trial_wall_ms"] = (now() - t0) / 1e6
    result["journal"] = rec.redact(server.state.entries())
    server.shutdown()
    server.server_close()
    result["loadavg_after"] = loadavg()
    result["browser_pid_alive_after"] = pid_alive(prepared_pid)
    path = out / "trials" / f"{spec['id']}.jsonl"
    with path.open("w") as fh:
        for ev in rec.events:
            fh.write(json.dumps(ev, sort_keys=True) + "\n")
        fh.write(json.dumps({"event": "summary", **rec.redact(result)}, sort_keys=True) + "\n")
    polls = next((e for e in rec.events if e["event"] == "oracle_polls"), {})
    print(json.dumps({"trial": spec["id"], "final": polls.get("final_tag"), "error": result["error"],
                      "load": result["loadavg_before"].split()[0]}), flush=True)
    return result


def pid_alive(pid: int | None) -> bool | None:
    if not pid:
        return None
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        time.sleep(0.1)
    return True


async def amain(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=False)
    plan = plan_for(args)
    manifest: dict[str, Any] = {"phase": args.phase, "variant": args.variant, "chunk": args.chunk,
                                "plan": [p["id"] for p in plan], "loadavg_start": loadavg(),
                                "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        for spec in plan:
            try:
                await asyncio.wait_for(run_trial(spec, args, out), timeout=120)
            except Exception as error:  # noqa: BLE001
                (out / "trials" / f"{spec['id']}.harness-error.jsonl").write_text(
                    json.dumps({"event": "summary", **spec, "outcome": "harness_error",
                                "error": f"{type(error).__name__}: {str(error)[:300]}"}) + "\n")
    finally:
        manifest["loadavg_end"] = loadavg()
        manifest["ended_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (out / "run-manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--phase", required=True, choices=["base", "neg", "n2ctl", "pilot"])
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--round-offset", type=int, default=0)
    p.add_argument("--variant", choices=["n1", "n2", "n3"])
    p.add_argument("--chunk", type=int, choices=[0, 1], default=0)
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ) or not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if args.phase == "neg" and not args.variant:
        raise SystemExit("--variant is required for --phase neg")
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
