#!/usr/bin/env python3
"""Per-attempt isolation table for trycua/cua#4317 runs (MCP trace + server-side journal witness).

usage: analyze_isolation.py RUN_ROOT [--json OUT.json] [--md OUT.md]
RUN_ROOT contains run01/ run02/ ... each with summary.json, witness.json, mcp-trace.jsonl.

For every tools/call it derives the calling Cua session, the session that owns the target/ref
(from the get_browser_state call that first returned that target / minted that ref), the Driver's
response (structured refusal code or accepted), and the two fixture journals immediately before the
request and after the response. A "cross-use attempt" is any browser call whose target belongs to a
different session, plus any call made in a session after that session was ended.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TARGET_TOOLS = {"browser_type", "browser_click", "browser_navigate", "get_browser_state"}


def load_calls(trace: Path):
    rows = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
    start = next(r for r in rows if r.get("dir") == "proxy" and r.get("event") == "start")
    calls, pending = [], {}
    for r in rows:
        if r.get("dir") == "c2s" and r["msg"].get("method") == "tools/call":
            p = r["msg"]["params"]
            args = dict(p.get("arguments", {}))
            pending[r["msg"]["id"]] = {"name": p["name"], "session": args.pop("session", None), "args": args, "t_req": r["t_ns"]}
        elif r.get("dir") == "s2c" and "id" in r["msg"] and r["msg"]["id"] in pending:
            c = pending.pop(r["msg"]["id"])
            c["t_resp"] = r["t_ns"]
            c["result"] = r["msg"].get("result") or {}
            calls.append(c)
    return calls, start["mono_ns0"]


def refusal_of(result: dict):
    """Return (kind, code) for a Driver result; kind is 'refused' or 'accepted'."""
    sc = result.get("structuredContent") if isinstance(result.get("structuredContent"), dict) else {}
    if sc.get("effect") == "refused" and isinstance(sc.get("error"), dict):
        return "refused", sc["error"].get("code")
    if sc.get("status") == "refused" and isinstance(sc.get("refusal"), dict):
        return "refused", sc["refusal"].get("code")
    if result.get("isError"):
        return "refused", sc.get("code") or (sc.get("refusal") or {}).get("code") or "error"
    return "accepted", None


def analyze_run(run: Path):
    calls, mono0 = load_calls(run / "mcp-trace.jsonl")
    witness = json.loads((run / "witness.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    journal = witness["journal"]

    def counts(abs_ns: int):
        return {name: sum(1 for e in journal if e["fixture"] == name and e["op"] == "submit" and e["mono_ns"] <= abs_ns) for name in "AB"}

    label = {}
    target_owner, tab_owner, ref_owner, ended = {}, {}, {}, set()
    retired: set[str] = set()   # targets whose owning session was ended; retired for good
    lifecycle = ("end_session", "start_session")
    rows = []
    for idx, c in enumerate(calls):
        s = c["session"]
        sc = c["result"].get("structuredContent") if isinstance(c["result"].get("structuredContent"), dict) else {}
        if s not in label:
            label[s] = "A" if s and s.endswith("-a") else "B" if s and s.endswith("-b") else s
        name, args = c["name"], c["args"]
        if name == "get_browser_state" and "pid" in args and sc.get("target_id"):
            target_owner[sc["target_id"]] = label[s]
            for tab in sc.get("tabs", []):
                tab_owner[tab["tab_id"]] = label[s]
        if name == "get_browser_state" and args.get("snapshot_format") == "semantic_v2":
            for ref in sc.get("refs", []) or []:
                if ref.get("ref"):
                    ref_owner[(args["target_id"], ref["ref"])] = (label[s], idx)
        kind, code = refusal_of(c["result"])
        owner = target_owner.get(args.get("target_id"))
        cross = owner is not None and owner != label[s]
        after_end = label[s] in ended and name not in lifecycle
        stale_after_restart = (args.get("target_id") in retired and label[s] not in ended and name not in lifecycle)
        if name == "end_session":
            ended.add(label[s])
            retired |= {t for t, o in target_owner.items() if o == label[s]}
        if name == "start_session":
            ended.discard(label[s])
        t_req_abs, t_resp_abs = mono0 + c["t_req"], mono0 + c["t_resp"]
        if cross or after_end or stale_after_restart or (name in ("browser_type", "browser_click") and kind == "refused"):
            ref = args.get("ref")
            minted = ref_owner.get((args.get("target_id"), ref))
            rows.append({
                "seq": idx + 1, "tool": name, "calling_session": label[s], "call_session_label": s,
                "target_owner": owner, "ref": ref, "ref_minted_by": minted[0] if minted else None,
                "kind": "cross_session" if cross else "ended_session" if after_end else "retired_after_same_label_restart" if stale_after_restart else "other_refusal",
                "driver_result": kind, "refusal_code": code,
                "dispatch_reached_target": kind == "accepted",
                "journal_submissions_before": counts(t_req_abs), "journal_submissions_after": counts(t_resp_abs),
            })
    positives = []
    for idx, c in enumerate(calls):
        s, name = c["session"], c["name"]
        owner = target_owner.get(c["args"].get("target_id"))
        if name in ("browser_type", "browser_click") and owner == label.get(s) and refusal_of(c["result"])[0] == "accepted":
            positives.append({"seq": idx + 1, "tool": name, "session": label[s], "ref": c["args"].get("ref")})
    return {
        "run": run.name,
        "script_complete": summary.get("complete"),
        "summary": {k: summary.get(k) for k in ("cross_pre_mutation", "cross_fresh_completion", "session_end")},
        "journals_match_expected": witness["journals_match_expected"],
        "observed_journals": witness["observed"],
        "cross_session_mutations": witness["cross_session_mutations"],
        "foreign_value_landed": witness["foreign_value_landed"],
        "attempts": rows,
        "own_session_actions_accepted": positives,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--md", type=Path)
    args = parser.parse_args()
    runs = [analyze_run(p) for p in sorted(args.root.glob("run*")) if (p / "witness.json").exists()]
    verdict = {
        "runs": len(runs),
        "runs_complete": sum(bool(r["script_complete"]) for r in runs),
        "runs_with_expected_journals": sum(bool(r["journals_match_expected"]) for r in runs),
        "cross_session_mutations_total": sum(len(r["cross_session_mutations"]) for r in runs),
        "foreign_values_landed_total": sum(bool(r["foreign_value_landed"]) for r in runs),
        "attempts_total": sum(len(r["attempts"]) for r in runs),
        "attempts_accepted_by_driver": sum(a["dispatch_reached_target"] for r in runs for a in r["attempts"]),
        "attempt_refusal_codes": sorted({(a["kind"], a["tool"], a["calling_session"], a["target_owner"], a["refusal_code"]) for r in runs for a in r["attempts"]}),
    }
    out = {"verdict": verdict, "runs": runs}
    if args.json:
        args.json.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    lines = ["# #4317 isolation: per-attempt results\n", "```json", json.dumps(verdict, indent=1, default=list), "```\n",
             "| run | seq | kind | tool | calling session | target owner | ref (minted by) | driver result | code | journals A/B submissions before -> after |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        for a in r["attempts"]:
            b, f = a["journal_submissions_before"], a["journal_submissions_after"]
            lines.append(f"| {r['run']} | {a['seq']} | {a['kind']} | {a['tool']} | {a['calling_session']} | {a['target_owner']} | "
                         f"{a['ref']} ({a['ref_minted_by']}) | {a['driver_result']} | {a['refusal_code']} | "
                         f"A {b['A']}->{f['A']}, B {b['B']}->{f['B']} |")
    md = "\n".join(lines) + "\n"
    if args.md:
        args.md.write_text(md)
    print(md)
    return 0 if verdict["cross_session_mutations_total"] == 0 and verdict["attempts_accepted_by_driver"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
