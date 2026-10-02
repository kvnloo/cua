#!/usr/bin/env python3
"""grade.py <runs-root> <out.json> [--server-log <ollama serve.log>] [--tz-offset-hours -5]

Independent oracle for the MULTISEAT packet. Inputs are target-owned or compositor-owned receipts only:
fixture journals (written by the app), final fixture state, per-session sway trees/seats, seatprobe logs,
round timing, the 1 Hz resource samples, the lane-private Hermes transcript digest (for stale-ref / refusal
counts, never for success) and the observer spool (API-call counts / prompt sizes). The model's own final text
is never used to decide success. Every agent run that was launched is in a denominator.

Layout expected under <runs-root>:
  main/<round-id>/{round.json, resources.jsonl, <AID>/...}        seq / conc rounds (Hermes agents)
  lookalike/<round-id>/...                                         2-agent look-alike Hermes rounds
  crosswire/<rep>/{A,B}/...                                        deliberate cross-session attempts
  seat-lookalike/<rep>/ , seat-driver/<rep>/                       single-compositor 2-seat controls
"""
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import statistics as st
import sys

ROOT, OUT = sys.argv[1], sys.argv[2]
SERVER_LOG = sys.argv[sys.argv.index("--server-log") + 1] if "--server-log" in sys.argv else None
TZ = float(sys.argv[sys.argv.index("--tz-offset-hours") + 1]) if "--tz-offset-hours" in sys.argv else -5.0
STALE = re.compile(r"\b(stale|superseded)\b", re.I)


def jl(path):
    try:
        return [json.loads(x) for x in open(path) if x.strip()]
    except OSError:
        return []


def jload(path, default=None):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return default


def num(path):
    try:
        return float(open(path).read().strip())
    except (OSError, ValueError):
        return None


def walk(n):
    yield n
    for k in ("nodes", "floating_nodes"):
        for c in n.get(k, []):
            yield from walk(c)


def views(tree):
    return [n for n in walk(tree or {}) if n.get("pid") and n.get("type") in ("con", "floating_con")]


def all_tokens():
    toks = {}
    for rj in glob.glob(f"{ROOT}/*/*/round.json"):
        for a in (jload(rj, {}) or {}).get("agents", []):
            toks[a["note"]] = (rj, a["aid"])
    return toks


def transcript(db):
    out = {"tool_calls": 0, "results": 0, "stale_results": 0, "refused_results": 0, "element_index_refusals": 0,
           "approval_blocks": 0, "actions": {}}
    if not os.path.exists(db):
        out["missing"] = True
        return out
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for role, content, tool_calls in con.execute("SELECT role, content, tool_calls FROM messages ORDER BY rowid"):
        if role == "assistant" and tool_calls:
            try:
                for tc in json.loads(tool_calls):
                    out["tool_calls"] += 1
                    try:
                        act = json.loads((tc.get("function") or {}).get("arguments") or "{}").get("action", "?")
                    except ValueError:
                        act = "?"
                    out["actions"][act] = out["actions"].get(act, 0) + 1
            except ValueError:
                pass
        elif role == "tool":
            text = content if isinstance(content, str) else json.dumps(content)
            out["results"] += 1
            out["stale_results"] += bool(STALE.search(text or ""))
            out["refused_results"] += ('"refusal"' in (text or "")) or ('"status": "refused"' in (text or ""))
            out["element_index_refusals"] += "unknown argument element_index" in (text or "")
            out["approval_blocks"] += "requires approval" in (text or "")
    return out


def observer(path):
    ev = jl(path)
    post = [e for e in ev if e.get("event") == "post_api_request"]
    err = [e for e in ev if e.get("event") == "api_request_error"]
    pts = [((e.get("usage") or {}).get("prompt_tokens")) for e in post]
    pts = [p for p in pts if isinstance(p, (int, float))]
    return {"rows": len(ev), "api_ok": len(post), "api_error": len(err), "max_prompt_tokens": max(pts) if pts else None,
            "api_seconds": round(sum((e.get("fields") or {}).get("api_duration") or 0 for e in post), 3),
            "spans": [((e.get("fields") or {}).get("started_at"), (e.get("fields") or {}).get("ended_at")) for e in post]}


def grade_agent(d, aid, token, tokens):
    j = jl(f"{d}/journal.jsonl")
    states = [e for e in j if e.get("kind") == "state"]
    notes = [e.get("text") or "" for e in j if e.get("kind") == "note_text"]
    final = jload(f"{d}/final-state.json", {}) or {}
    foreign = sorted({t for t in tokens if t != token and any(t in (x or "") for x in notes + [s.get("note_saved") or "" for s in states])})
    saves = 0
    for a, b in zip(states, states[1:]):
        if (a["counter"], a["agreed"], a["size"]) == (b["counter"], b["agreed"], b["size"]):
            saves += 1
    other_controls = any((s["counter"], s["agreed"], s["size"]) != (0, False, "none") for s in states)
    tb, ta = jload(f"{d}/tree-before.json"), jload(f"{d}/tree-after.json")
    sess = dict(x.split("=", 1) for x in open(f"{d}/session.txt").read().split() if "=" in x) if os.path.exists(f"{d}/session.txt") else {}
    fpid = int(sess.get("fixture_pid", "-1") or -1)
    va = views(ta)
    focus = [e for e in j if e.get("kind") == "focus"]
    unpaired_out = 0
    for i, e in enumerate(focus):
        if not e["focused"] and not any(f["focused"] and 0 <= f["t"] - e["t"] <= 1.0 for f in focus[i + 1:]):
            unpaired_out += 1
    focused_after = next((n.get("pid") for n in walk(ta or {}) if n.get("focused") and n.get("pid")), None)
    tx = transcript(f"{d}/hermes/home/.hermes/state.db")
    obs = observer(f"{d}/hermes/home/.hermes/plugin-data/z0-hermes-observer/events.jsonl")
    t0, t1 = num(f"{d}/agent_start_epoch"), num(f"{d}/agent_end_epoch")
    success = (final.get("note_saved") == token) and not foreign and not other_controls
    return {
        "aid": aid, "token": token, "launched": True,
        "session_display": sess.get("display"), "fixture_pid": fpid, "agent_rc": num(f"{d}/agent_rc"),
        "hermes_exit": num(f"{d}/hermes/meta/exit_code"),
        "success": bool(success), "note_saved": final.get("note_saved"), "final_state_present": bool(final),
        "foreign_tokens_in_journal": foreign, "other_controls_changed": other_controls,
        "save_presses": saves, "duplicate_effect": saves > 1,
        "views_after": len(va), "foreign_views_after": [n.get("pid") for n in va if n.get("pid") != fpid],
        "focused_after_is_fixture": focused_after == fpid, "focus_out_events": sum(1 for e in focus if not e["focused"]),
        "unpaired_focus_out": unpaired_out,
        "stale_ref_results": tx["stale_results"], "refused_results": tx["refused_results"],
        "element_index_refusals": tx["element_index_refusals"], "approval_blocks": tx["approval_blocks"],
        "tool_calls": tx["tool_calls"], "actions": tx["actions"], "transcript_missing": tx.get("missing", False),
        "api_ok": obs["api_ok"], "api_error": obs["api_error"], "max_prompt_tokens": obs["max_prompt_tokens"],
        "observer_rows": obs["rows"], "api_seconds": obs["api_seconds"], "_spans": obs["spans"],
        "agent_wall_s": round(t1 - t0, 3) if t0 and t1 else None, "t0": t0, "t1": t1,
    }


def server_requests(t0, t1):
    if not SERVER_LOG or not os.path.exists(SERVER_LOG):
        return None
    n = 0
    pat = re.compile(r'^\[GIN\] (\d{4}/\d{2}/\d{2} - \d{2}:\d{2}:\d{2}) \| \d+ \|\s+([\d.]+)(µs|ms|s|m[\d.]*s)? .*POST\s+"/v1/chat/completions"')
    for line in open(SERVER_LOG, errors="replace"):
        m = pat.search(line)
        if not m:
            continue
        end = dt.datetime.strptime(m.group(1), "%Y/%m/%d - %H:%M:%S").replace(
            tzinfo=dt.timezone(dt.timedelta(hours=TZ))).timestamp()
        if t0 - 1 <= end <= t1 + 1:
            n += 1
    return n


def resources(path):
    rows = [r for r in jl(path) if r.get("kind") == "tick"]
    meta = next((r for r in jl(path) if r.get("kind") == "meta"), {})
    if len(rows) < 2:
        return {"ticks": len(rows)}
    hz = meta.get("clk_tck", 100)
    span = rows[-1]["t"] - rows[0]["t"]
    def cpu_pct(key):
        vals = [r.get(key, {}).get("ticks") for r in rows if r.get(key)]
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            return None
        inc = sum(max(0, b - a) for a, b in zip(vals, vals[1:]))
        return round(100.0 * inc / hz / span, 1)
    gpu = [r["gpu"] for r in rows if "mem_used_mib" in r.get("gpu", {})]
    sess_peak = {}
    for r in rows:
        for k, v in r.get("sessions", {}).items():
            sess_peak[k] = max(sess_peak.get(k, 0), v["rss_kb"])
    return {
        "ticks": len(rows), "span_s": round(span, 1),
        "round_tree_cpu_pct_mean": cpu_pct("round_tree"),
        "round_tree_rss_mib_peak": round(max(r["round_tree"]["rss_kb"] for r in rows) / 1024, 1),
        "per_session_rss_mib_peak": sorted(round(v / 1024, 1) for v in sess_peak.values()),
        "ollama_cpu_pct_mean": cpu_pct("ollama"),
        "ollama_rss_mib_peak": round(max((r.get("ollama") or {}).get("rss_kb", 0) for r in rows) / 1024, 1),
        "gpu_mem_used_mib_peak": max((g["mem_used_mib"] for g in gpu), default=None),
        "gpu_mem_used_mib_mean": round(st.mean(g["mem_used_mib"] for g in gpu), 1) if gpu else None,
        "gpu_util_pct_mean": round(st.mean(g["util_pct"] for g in gpu), 1) if gpu else None,
        "gpu_apps_seen": sorted({a[0] for g in gpu for a in g.get("apps", [])}),
        "loadavg_first": rows[0].get("loadavg"), "loadavg_max1": max(float(r["loadavg"][0]) for r in rows),
    }


def grade_rounds(kind, tokens):
    out = []
    for rj in sorted(glob.glob(f"{ROOT}/{kind}/*/round.json")):
        rd = os.path.dirname(rj)
        r = jload(rj)
        agents = [grade_agent(f"{rd}/{a['aid']}", a["aid"], a["note"], tokens) for a in r["agents"]]
        mine = sum(a["api_ok"] + a["api_error"] for a in agents)
        total = server_requests(r["t0"], r["t1"])
        spans = sorted(s for a in agents for s in a.pop("_spans") if s[0] and s[1])
        overlap = 0.0
        for i, (s0, e0) in enumerate(spans):  # model-call overlap seconds between this round's own agents
            for s1, e1 in spans[i + 1:]:
                overlap += max(0.0, min(e0, e1) - max(s0, s1))
        out.append({
            "round": os.path.basename(rd), "arm": r["arm"], "n_agents": len(agents), "makespan_s": r["makespan_s"],
            "successes": sum(a["success"] for a in agents),
            "success_per_min": round(60 * sum(a["success"] for a in agents) / r["makespan_s"], 3),
            "episodes_per_min": round(60 * len(agents) / r["makespan_s"], 3),
            "sum_agent_wall_s": round(sum(a["agent_wall_s"] or 0 for a in agents), 1),
            "model_requests_mine": mine, "model_requests_server_total": total,
            "model_requests_foreign": (total - mine) if total is not None else None,
            "own_model_call_overlap_s": round(overlap, 2),
            "session_displays": [a["session_display"] for a in agents],
            "resources": resources(f"{rd}/resources.jsonl"), "agents": agents,
        })
    return out


def cross_landing(rounds):
    """Count every journal (agent) holding a token that belongs to another agent of the same or any round."""
    hits = []
    for r in rounds:
        for a in r["agents"]:
            for t in a["foreign_tokens_in_journal"]:
                hits.append({"round": r["round"], "victim": a["aid"], "token": t})
    return hits


def grade_crosswire():
    reps = []
    for d in sorted(glob.glob(f"{ROOT}/crosswire/*")):
        att = jl(f"{d}/A/attempts.jsonl")
        bj = open(f"{d}/B/journal.jsonl").read() if os.path.exists(f"{d}/B/journal.jsonl") else ""
        aj = open(f"{d}/A/journal.jsonl").read() if os.path.exists(f"{d}/A/journal.jsonl") else ""
        rows = []
        for a in att:
            rows.append({"id": a["id"], "rc": a["rc"], "landed_in_B": a["token"] in bj, "landed_in_A": a["token"] in aj,
                         "b_journal_grew": a["b_lines"][1] > a["b_lines"][0]})
        reps.append({"rep": os.path.basename(d), "attempts": rows})
    summary = {}
    for rep in reps:
        for r in rep["attempts"]:
            s = summary.setdefault(r["id"], {"n": 0, "landed_in_B": 0, "landed_in_A": 0, "b_journal_grew": 0})
            s["n"] += 1
            s["landed_in_B"] += r["landed_in_B"]
            s["landed_in_A"] += r["landed_in_A"]
            s["b_journal_grew"] += r["b_journal_grew"]
    return {"reps": reps, "summary": summary}


def probe_events(path):
    ev = jl(path)
    keys = {}
    btn = {}
    for e in ev:
        if e.get("ev") == "key" and e.get("state") == 1:
            keys[e["seat"]] = keys.get(e["seat"], "") + (e.get("utf8") or "")
        if e.get("ev") == "pointer_button" and e.get("state") == 1:
            btn[e["seat"]] = btn.get(e["seat"], 0) + 1
    return keys, btn


def grade_seat(kind):
    reps = []
    for d in sorted(glob.glob(f"{ROOT}/{kind}/*")):
        ids = dict(x.split("=") for x in open(f"{d}/ids.env").read().split()) if os.path.exists(f"{d}/ids.env") else {}
        lay = open(f"{d}/layout.txt").read() if os.path.exists(f"{d}/layout.txt") else ""
        m = re.search(r"L pid=(\d+).*R pid=(\d+)", lay)
        lpid, rpid = (m.group(1), m.group(2)) if m else (None, None)
        probe_for = {}
        for p in ("1", "2"):
            ev = jl(f"{d}/probe-{p}.jsonl")
            probe_for[p] = ev
        # map probe file -> L/R by the pid the launcher recorded (P1 is the left window after the swap fix)
        p1, p2 = ids.get("P1"), ids.get("P2")
        left = "1" if p1 == lpid else "2"
        right = "2" if left == "1" else "1"
        kl, bl = probe_events(f"{d}/probe-{left}.jsonl")
        kr, br = probe_events(f"{d}/probe-{right}.jsonl")
        tag = os.path.basename(d).lower()
        rep = {"rep": os.path.basename(d), "left_keys": kl, "right_keys": kr, "left_buttons": bl, "right_buttons": br}
        if kind == "seat-lookalike":
            exp = {"left": {"seat0": f"{tag}s0l", "seat1": f"{tag}s1l"}, "right": {"seat1": f"{tag}s1r", "seat0": f"{tag}s0r"}}
            ok = (kl.get("seat0") == exp["left"]["seat0"] and kl.get("seat1") == exp["left"]["seat1"]
                  and kr.get("seat1") == exp["right"]["seat1"] and kr.get("seat0") == exp["right"]["seat0"])
            rep["expected"] = exp
            rep["pass"] = ok
            rep["cross_seat_landings"] = sum(1 for side, kk in (("left", kl), ("right", kr)) for s, v in kk.items()
                                             if v != exp[side].get(s))
        else:
            seats = sorted(set(bl) | set(br))
            rep["seats_used_by_two_driver_agents"] = seats
            rep["per_agent_seat_binding"] = len(seats) >= 2 and set(bl) != set(br)
        reps.append(rep)
    return reps


tokens = all_tokens()
main = grade_rounds("main", tokens)
look = grade_rounds("lookalike", tokens)
res = {"schema": "cua.stack.multiseat.grade.v1", "main_rounds": main, "lookalike_rounds": look,
       "cross_landings_main": cross_landing(main), "cross_landings_lookalike": cross_landing(look),
       "crosswire": grade_crosswire(), "seat_lookalike": grade_seat("seat-lookalike"),
       "seat_driver": grade_seat("seat-driver")}
json.dump(res, open(OUT, "w"), indent=1, default=str)
print(json.dumps({"main_rounds": len(main), "lookalike_rounds": len(look),
                  "cross_landings": len(res["cross_landings_main"]) + len(res["cross_landings_lookalike"])}))
