"""Re-derive what happened in every CUA run from committed receipts (SAMPLESFIX, erratum E2). Stdlib only.

  python cua_bridge_tally.py <packet_dir>            -> prints the tally JSON
  python cua_bridge_tally.py <packet_dir> <out.json> -> also writes it

Inputs per CUA run (all committed): raw/runs/<run>/{agent.log, errors.log, stdout, argv, gui-state/},
dataset/runs.jsonl, dataset/events.jsonl, workload/tasks.jsonl. Tool lines come from Hermes's own
agent.tool_executor logger, which writes "tool <name> completed" for a dispatched call and
"Tool <name> returned error (...): <error>" for a refused one. The three tool_call error strings seen
here are raised by tools/tool_search_validation.py before any tool is dispatched.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LOG_LINE = re.compile(r"^\d{4}-\d\d-\d\d [\d:,]+ [A-Z]+ (?:\[[^\]]+\] )?(?P<logger>[A-Za-z0-9_.]+): (?P<msg>.*)$")
OK = re.compile(r"^tool (?P<tool>\S+) completed")
FAILED = re.compile(r"^tool (?P<tool>\S+) failed")
ERR = re.compile(r"^Tool (?P<tool>\S+) returned error \([^)]*\): (?P<err>.*)$")
API_CALL = re.compile(r"^API call #\d+:")
APPROVAL = re.compile(r"approv|fail.?clos", re.I)
CLASSES = (("missing_calls_array", "tool_call requires 'calls'"),
           ("unknown_tool_name", "is not a known tool name"),
           ("bridge_self_invoke", "it is itself a bridge tool"))


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def classify(err: str) -> str:
    return next((name for name, needle in CLASSES if needle in err), "other")


def tally(packet: Path) -> dict:
    tasks = {t["task_id"]: t for t in jl(packet / "workload" / "tasks.jsonl")}
    events = jl(packet / "dataset" / "events.jsonl")
    by_sid: dict[str, list[dict]] = {}
    for e in events:
        by_sid.setdefault((e.get("identity") or {}).get("session_id"), []).append(e)
    rows = []
    for r in jl(packet / "dataset" / "runs.jsonl"):
        if r["status"] != "RUN" or r["kind"] != "cua":
            continue
        d = packet / "raw" / "runs" / r["run_id"]
        agent = d.joinpath("agent.log").read_text(encoding="utf-8").splitlines()
        errors = d.joinpath("errors.log").read_text(encoding="utf-8").splitlines()
        stdout = d.joinpath("stdout").read_text(encoding="utf-8") if d.joinpath("stdout").exists() else ""
        argv = d.joinpath("argv").read_text(encoding="utf-8").replace("\0", "\n").split("\n")
        loggers, ok, failed, errs, api_calls = set(), [], [], [], 0
        for line in agent:
            m = LOG_LINE.match(line)
            if not m:
                continue
            loggers.add(m["logger"])
            msg = m["msg"]
            if m["logger"] == "agent.tool_executor":
                if (o := OK.match(msg)):
                    ok.append(o["tool"])
                elif (f := FAILED.match(msg)):
                    failed.append(f["tool"])
                elif (e := ERR.match(msg)):
                    errs.append((e["tool"], classify(e["err"])))
            elif m["logger"] == "agent.conversation_loop" and API_CALL.match(msg):
                api_calls += 1
        err_lines_errors_log = sum(1 for l in errors if (m := LOG_LINE.match(l)) and m["logger"] == "agent.tool_executor"
                                   and ERR.match(m["msg"]))
        ev = by_sid.get(r.get("session_id"), [])
        end = [e for e in ev if e.get("event") == "on_session_end"]
        gs = d / "gui-state"
        before = json.loads((gs / "state.before.json").read_text()) if (gs / "state.before.json").exists() else None
        after = json.loads((gs / "state.after.json").read_text()) if (gs / "state.after.json").exists() else None
        classes: dict[str, int] = {}
        for _, c in errs:
            classes[c] = classes.get(c, 0) + 1
        rows.append({
            "run_id": r["run_id"], "task_id": r["task_id"], "family": r["family"],
            "oracle": tasks[r["task_id"]]["oracle"], "verified_success": r["verified_success"], "exit_code": r["exit_code"],
            "turn_exit_reason": (end[-1].get("fields") or {}).get("turn_exit_reason") if end else None,
            "argv_toolset_computer_use": any(a == "-t" and b == "computer_use" for a, b in zip(argv, argv[1:])),
            "api_calls_agent_log": api_calls,
            "api_attempts_observer": sum(e.get("event") == "post_api_request" for e in ev),
            "tool_calls_completed": len(ok), "tool_calls_failed": len(failed), "tool_errors": len(errs),
            "tool_error_lines_errors_log": err_lines_errors_log,
            "tool_names_called": sorted({t for t in ok + failed + [t for t, _ in errs]}),
            "tool_error_classes": dict(sorted(classes.items())),
            "observer_pre_tool_call": sum(e.get("event") == "pre_tool_call" for e in ev),
            "observer_post_tool_call": sum(e.get("event") == "post_tool_call" for e in ev),
            "computer_use_dispatches": sum(t == "computer_use" for t in ok + failed + [t for t, _ in errs]),
            "driver_or_computer_use_loggers": sorted(l for l in loggers if "computer_use" in l or "cua" in l or "driver" in l),
            "approval_lines": sum(bool(APPROVAL.search(l)) for l in agent + errors) + len(APPROVAL.findall(stdout)),
            "gui_state_unchanged": before is not None and before == after,
            "reply": stdout.strip()[:120],
        })
    tot = lambda k: sum(x[k] for x in rows)  # noqa: E731
    classes_total: dict[str, int] = {}
    for x in rows:
        for c, n in x["tool_error_classes"].items():
            classes_total[c] = classes_total.get(c, 0) + n
    return {
        "schema": "stack.samples.cua_bridge_tally.v1",
        "n_cua_runs": len(rows),
        "totals": {
            "api_calls_agent_log": tot("api_calls_agent_log"), "api_attempts_observer": tot("api_attempts_observer"),
            "tool_calls_completed": tot("tool_calls_completed"), "tool_calls_failed": tot("tool_calls_failed"),
            "tool_errors": tot("tool_errors"), "tool_error_lines_errors_log": tot("tool_error_lines_errors_log"),
            "tool_error_classes": dict(sorted(classes_total.items())),
            "tool_names_called": sorted({t for x in rows for t in x["tool_names_called"]}),
            "observer_pre_tool_call": tot("observer_pre_tool_call"), "observer_post_tool_call": tot("observer_post_tool_call"),
            "computer_use_dispatches": tot("computer_use_dispatches"),
            "runs_with_driver_or_computer_use_logger": sum(bool(x["driver_or_computer_use_loggers"]) for x in rows),
            "approval_lines": tot("approval_lines"),
            "runs_gui_state_unchanged": sum(x["gui_state_unchanged"] for x in rows),
            "runs_argv_toolset_computer_use": sum(x["argv_toolset_computer_use"] for x in rows),
            "oracle_pass": sum(x["verified_success"] is True for x in rows),
        },
        "runs": rows,
    }


def main() -> None:
    out = tally(Path(sys.argv[1]))
    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text)
    print(json.dumps(out["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
