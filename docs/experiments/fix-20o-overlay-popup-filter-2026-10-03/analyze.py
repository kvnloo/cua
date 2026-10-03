#!/usr/bin/env python3
"""FIX-20O: recompute every row and gate from raw/ (stdlib only).

usage: analyze.py [--check]   (writes fix20o-summary.json and fix20o-trial-metrics.jsonl.gz next to it;
                               --check recomputes and compares with the committed summary instead)

Per-trial metrics are the ORIGINAL analyzers' definitions, imported from the blob-identical copies:
  orig/own-20p/analyze.py focus_metrics  (R1 replystall / replyonly / NORMAL nosteal)
  orig/own-20q/analyze.py focus_metrics  (R1m mfstall / mfonly, DLG dlgsteal / dlgdialog, normal nosteal)
Every trial is keyed by the driver_sha256 it recorded (provenance.json binaries), never by its role.
On top, each focus trial gets the fixture's own focus-log oracle (raw/.../focuslog/<trial>.jsonl,
written by the GTK3 fixture through harness/focuslog/sitecustomize.py):
  fx_stolen   the task window logged focus_out after T0
  fx_restored fx_stolen and the task window's last focus event after T0 is focus_in
  fx_quiet    no focus event of the task window after T0 (no-steal rows)
The PROBE rows use FRESH-07's probe records (guard summary text and xtree map states); the POPUP and
INTEGRITY rows use this packet's popup_harness.py records.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

PKT = Path(__file__).resolve().parent
RAW = PKT / "raw" / "rows"
TASK_TITLE = "CuaTestHarness GTK3 Tasks"
GUARD_TEXT = "A popup menu is open"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


P20 = load_module("own20p_analyze", PKT / "orig" / "own-20p" / "analyze.py")
Q20 = load_module("own20q_analyze", PKT / "orig" / "own-20q" / "analyze.py")


def gz_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(x) for x in stream if x.strip()]


def focus_log(block_dir: Path, trial_id: str) -> list[dict] | None:
    f = block_dir / "focuslog" / f"{trial_id}.jsonl"
    if not f.exists():
        return None
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def fixture_oracle(log: list[dict] | None, t0: int | None) -> dict[str, Any]:
    if log is None:
        return {"fx_log": False}
    hooked = any(e.get("event") == "hooked" and e.get("title") == TASK_TITLE for e in log)
    ev = [e for e in log if e.get("title") == TASK_TITLE and e.get("event") in ("focus_in", "focus_out")
          and t0 and e.get("mono_ns", 0) >= t0]
    stolen = any(e["event"] == "focus_out" for e in ev)
    return {"fx_log": True, "fx_hooked": hooked, "fx_events_after_T0": len(ev),
            "fx_stolen": stolen, "fx_restored": bool(stolen and ev and ev[-1]["event"] == "focus_in"),
            "fx_quiet": not ev, "fx_last": ev[-1]["event"] if ev else None}


def main() -> int:
    check = "--check" in sys.argv
    prov = json.loads((PKT / "provenance.json").read_text(encoding="utf-8"))
    by_sha = {v["sha256"]: k for k, v in prov["binaries"].items()}
    counted = prov["counted_blocks"]  # {pass: [label, ...]}
    metrics: list[dict] = []
    probe_runs: list[dict] = []
    popup: list[dict] = []
    tools: list[dict] = []
    attempts: list[dict] = []
    per_bin: dict[str, int] = {}
    for pass_name, labels in sorted(counted.items()):
        for label in labels:
            d = RAW / pass_name / label
            if (d / "probe.jsonl.gz").exists():
                rows = gz_rows(d / "probe.jsonl.gz")
                meta = next(r for r in rows if r.get("event") == "meta")
                for r in rows:
                    if r.get("event") == "run":
                        r["_label"], r["_pass"] = label, pass_name
                        r["_binary"] = by_sha.get(meta["binaries"][r["binary"]], "UNKNOWN")
                        probe_runs.append(r)
                attempts.append({"pass": pass_name, "label": label, "runs": sum(r.get("event") == "run" for r in rows)})
                continue
            rows = gz_rows(d / "trials.jsonl.gz")
            trials = [r for r in rows if r.get("event") == "trial"]
            attempts.append({"pass": pass_name, "label": label, "trials": len(trials)})
            for t in trials:
                t["_label"] = label
                name = by_sha.get(t.get("driver_sha256"), "UNKNOWN")
                per_bin[name] = per_bin.get(name, 0) + 1
                if t.get("kind") == "popup":
                    popup.append({**t, "_binary": name, "_pass": pass_name})
                    continue
                if t.get("kind") == "toolslist":
                    tools.append({**t, "_binary": name, "_pass": pass_name})
                    continue
                if t.get("kind") in P20.FOCUS_KINDS and pass_name.startswith("P"):
                    m = P20.focus_metrics(t)
                    family = "own20p"
                elif t.get("kind") in Q20.FOCUS_KINDS and pass_name.startswith("Q"):
                    m = Q20.focus_metrics(t)
                    family = "own20q"
                else:
                    continue
                m.update(fixture_oracle(focus_log(d / "raw" if (d / "raw").exists() else d, t["id"]), t.get("T0_m")))
                m["restore_pass"] = bool(m.get("pass")) if family == "own20p" else None
                m.update({"family": family, "run_pass": pass_name, "binary_name": name,
                          "driver_sha256": t.get("driver_sha256")})
                metrics.append(m)

    def sel(**kw) -> list[dict]:
        return [m for m in metrics if all(m.get(k) == v for k, v in kw.items())]

    S: dict[str, Any] = {"schema": "fix20o.summary.v1", "focus_trials": len(metrics), "probe_runs": len(probe_runs),
                         "popup_trials": len(popup), "toolslist_reads": len(tools), "attempts": attempts,
                         "trials_per_binary": dict(sorted(per_bin.items()))}

    # ---- OWN-20P R1 (replystall), per binary and task
    r1: dict[str, Any] = {}
    for b in ("G0m8", "G0m8F", "G0m8A", "U0m8F"):
        for task in ("checkbox", "text"):
            rows = sel(family="own20p", kind="replystall", binary_name=b, task=task)
            r1[f"{task}/{b}"] = {"n": len(rows), "valid": sum(r["valid"] for r in rows),
                                 "restored": sum(bool(r["restore_pass"]) for r in rows),
                                 "silent_miss": sum(r["silent_miss"] for r in rows),
                                 "fx_restored": sum(bool(r.get("fx_restored")) for r in rows),
                                 "fx_log": sum(bool(r.get("fx_log")) for r in rows),
                                 "restored_and_fx": sum(bool(r["restore_pass"] and r.get("fx_restored")) for r in rows),
                                 "receipts": _receipts(rows)}
        r1[b] = {k: sum(r1[f"{t}/{b}"][k] for t in ("checkbox", "text"))
                 for k in ("n", "valid", "restored", "silent_miss", "fx_restored", "restored_and_fx")}
    ctl = sel(family="own20p", kind="replyonly")
    r1["control_replyonly"] = {b: {"n": len(c), "valid": sum(r["valid"] for r in c),
                                   "false_restore": sum(r["false_restore"] for r in c),
                                   "fx_quiet": sum(bool(r.get("fx_quiet")) for r in c)}
                               for b in sorted({r["binary_name"] for r in ctl})
                               for c in [[r for r in ctl if r["binary_name"] == b]]}
    S["own20p_r1"] = r1
    nm = sel(family="own20p", kind="nosteal")
    S["own20p_normal"] = {b: {"n": len(c), "verified": sum(r["oracle_verified"] for r in c),
                              "failures": sum(1 for r in c if not r["oracle_verified"]),
                              "false_restore": sum(r["false_restore"] for r in c),
                              "fx_quiet": sum(bool(r.get("fx_quiet")) for r in c)}
                          for b in sorted({r["binary_name"] for r in nm})
                          for c in [[r for r in nm if r["binary_name"] == b]]}

    # ---- OWN-20Q R1m, DLG, dialog control, normal
    q: dict[str, Any] = {}
    for kind in ("mfstall", "mfonly", "dlgsteal", "dlgdialog", "nosteal"):
        rows_k = sel(family="own20q", kind=kind)
        for (pass_name, b) in sorted({(r["run_pass"], r["binary_name"]) for r in rows_k}):
            c = [r for r in rows_k if r["binary_name"] == b and r["run_pass"] == pass_name]
            q[f"{kind}/{pass_name}/{b}"] = {
                "n": len(c), "valid": sum(r["valid"] for r in c),
                "verified_restore": sum(r["verified_restore"] for r in c),
                "silent_miss": sum(r["silent_miss"] for r in c),
                "misclassified_same_app": sum(r["misclassified_same_app"] for r in c),
                "false_restore": sum(r["false_restore"] for r in c),
                "oracle_verified": sum(r["oracle_verified"] for r in c),
                "spurious_reconnects": sum(r["spurious_reconnects"] for r in c),
                "dialog_left_focused": sum(bool(r.get("dialog_left_focused")) for r in c),
                "fx_restored": sum(bool(r.get("fx_restored")) for r in c),
                "fx_quiet": sum(bool(r.get("fx_quiet")) for r in c),
                "verified_restore_and_fx": sum(bool(r["verified_restore"] and r.get("fx_restored")) for r in c),
                "receipts": _receipts(c)}
    S["own20q"] = q

    # ---- PROBE (plain background click; FRESH-07 probe)
    pr: dict[str, Any] = {}
    for b in sorted({r["_binary"] for r in probe_runs}):
        rr = [r for r in probe_runs if r["_binary"] == b]
        def txt(r: dict, k: str) -> bool:
            return GUARD_TEXT in " ".join((r.get(k) or {}).get("text") or [])
        def ov(snap: dict | None) -> list[str]:
            return [o["map_state"] for o in (snap or {}).get("overlays", [])]
        pr[b] = {"n": len(rr), "failures": sum(1 for r in rr if r.get("failure")),
                 "S2_click_verified": sum(bool((r.get("S2_on_oracle") or {}).get("verified")) for r in rr),
                 "S2_false_popup_text": sum(txt(r, "S2_on_click") for r in rr),
                 "S3_false_popup_text": sum(txt(r, "S3_off_click") for r in rr),
                 "S1_idle_overlay_unmapped": sum(ov(r.get("S1_idle")) == ["UNMAPPED"] for r in rr),
                 "S2_overlay_viewable_after_reply": sum("VIEWABLE" in ov(r.get("S2_on_after")) for r in rr),
                 "S2_overlay_viewable_settled": sum("VIEWABLE" in ov(r.get("S2_on_settled")) for r in rr),
                 "S2_overlay_shape_rects_after_reply": sorted({o.get("bounding_rects") for r in rr
                                                               for o in (r.get("S2_on_after") or {}).get("overlays", [])
                                                               if o.get("map_state") == "VIEWABLE"}),
                 "S2_overlay_input_rects_after_reply": sorted({o.get("input_rects") for r in rr
                                                               for o in (r.get("S2_on_after") or {}).get("overlays", [])}),
                 "poller_map_transitions_runs": sum(any("VIEWABLE" in str(x.get("overlays")) for x in
                                                        (r.get("poller") or {}).get("transitions", [])) for r in rr),
                 "focus_unchanged_S2": sum(((r.get("S2_on_pre") or {}).get("focus") ==
                                            (r.get("S2_on_settled") or {}).get("focus")) for r in rr)}
    S["probe"] = pr

    # ---- POPUP control
    pc: dict[str, Any] = {}
    for b in sorted({r["_binary"] for r in popup}):
        rr = [r for r in popup if r["_binary"] == b]
        def holds(r: dict) -> dict[str, bool]:
            text = " ".join((r.get("click") or {}).get("text") or [])
            final = ((r.get("focus_samples") or {}).get("changes") or [[0, 0, 0]])[-1]
            decoy, menu = r.get("decoy_window"), (r.get("state_final") or {}).get("menu_window")
            mapped = {w["window"] for w in (r.get("x_final") or {}).get("mapped_or", [])}
            return {"verified": bool(r.get("oracle_verified")),
                    "guard_reports_popup": GUARD_TEXT in text,
                    "not_on_decoy": bool(final and final[1] != decoy and final[2] != decoy),
                    "active_is_app": bool(final and final[2] == r.get("window_id")),
                    "menu_still_mapped": bool(menu and menu in mapped and (r.get("state_final") or {}).get("menu_open")),
                    "grab_held": bool((r.get("grab_probe") or {}).get("held_by_other")),
                    "no_restore_receipt": "focus_outcome=restored" not in text and "focus_outcome=not_restored" not in text}
        hs = [holds(r) for r in rr]
        keys = list(hs[0]) if hs else []
        pc[b] = {"n": len(rr), **{k: sum(h[k] for h in hs) for k in keys},
                 "control_holds": sum(all(h.values()) for h in hs),
                 "receipts": _popup_receipts(rr),
                 "menu_pid_removed": sum(bool((r.get("state_final") or {}).get("menu_pid_removed")) for r in rr)}
    S["popup"] = pc

    # ---- INTEGRITY tools/list
    S["toolslist"] = {b: sorted({r.get("tools_sha256") for r in tools if r["_binary"] == b}, key=str)
                      for b in sorted({r["_binary"] for r in tools})}
    S["toolslist_reads"] = {b: sum(1 for r in tools if r["_binary"] == b and r.get("tools_sha256")) for b in S["toolslist"]}

    # ---- E4
    e4 = {"false_restores_control_rows": (sum(v["false_restore"] for v in r1["control_replyonly"].values())
                                          + sum(v["false_restore"] for v in S["own20p_normal"].values())
                                          + sum(v["false_restore"] for k, v in q.items()
                                                if k.split("/")[0] in ("mfonly", "nosteal", "dlgdialog"))),
          "unverified_success": sum(bool(m.get("unverified_success")) for m in metrics),
          "stale_token_actions": sum(1 for m in metrics if "stale" in str(m.get("click_error") or "")),
          "silent_miss_outside_positive_controls": sum(m["silent_miss"] for m in metrics
                                                        if m["binary_name"] not in ("U0m8F", "M8", "G0m8", "GQ8", "GA8F"))}
    S["e4"] = e4

    # ---- gates (PREREG.json)
    g = {}
    g["G1"] = bool(r1["G0m8F"]["n"] == 40 and r1["G0m8F"]["restored"] == 40 and r1["G0m8F"]["silent_miss"] == 0
                   and r1["G0m8F"]["fx_restored"] == 40)
    dl = [v for k, v in q.items() if k.startswith("dlgsteal/") and k.endswith("/GQ8F")]
    g["G2"] = bool(dl and all(v["n"] == 20 and v["verified_restore"] == 20 and v["misclassified_same_app"] == 0
                              and v["fx_restored"] == 20 for v in dl))
    g["G3"] = bool(r1["checkbox/G0m8"]["n"] == 20 and r1["checkbox/G0m8"]["restored"] <= 2)
    g["G4"] = bool(r1["G0m8A"]["n"] == 40 and r1["G0m8A"]["restored"] >= 38)
    g["G5"] = bool(pc.get("G0m8F", {}).get("n") == 20 and pc["G0m8F"]["control_holds"] == 20)
    ga = q.get("dlgsteal/Q2/GA8F", {})
    g["G6"] = bool(r1["U0m8F"]["n"] == 40 and r1["U0m8F"]["silent_miss"] >= 36
                   and ga.get("n") == 20 and ga.get("misclassified_same_app", 0) >= 16)
    g["G7"] = bool(e4["false_restores_control_rows"] == 0 and e4["unverified_success"] == 0
                   and e4["stale_token_actions"] == 0)
    unit = json.loads((PKT / "unit-summary.json").read_text(encoding="utf-8"))
    g["G8"] = bool(unit.get("red_live_assertion_failed") and unit.get("green_live_passed")
                   and unit.get("green_suites_passed"))
    # secondary pre-registered rows (reported; KEEP rests on G1, G2, G5-G8)
    ctl_ok = all(v["false_restore"] == 0 and v["valid"] == v["n"] > 0 for v in r1["control_replyonly"].values())
    nrm = S["own20p_normal"].get("G08F", {})
    r1m = q.get("mfstall/Q1/G08F", {})
    dd = {b: q.get(f"dlgdialog/Q2/{b}", {}) for b in ("GA8F", "GQ8F")}
    qn = [v for k, v in q.items() if k.startswith("nosteal/Q2/")]
    g["S_replyonly"] = bool(ctl_ok and r1["control_replyonly"].get("G0m8F", {}).get("n") == 10)
    g["S_normal_G08F"] = bool(nrm.get("n") == 40 and nrm.get("verified") == 40 and nrm.get("false_restore") == 0)
    g["S_r1m_G08F"] = bool(r1m.get("n") == 40 and r1m.get("verified_restore") == 40)
    g["S_dlg_GQ8_fails"] = bool(q.get("dlgsteal/Q3/GQ8", {}).get("n") == 20
                                and q["dlgsteal/Q3/GQ8"]["verified_restore"] == 0)
    g["S_dialog_control"] = bool(all(v.get("n") == 10 and v.get("dialog_left_focused") == 10 for v in dd.values()))
    g["S_normal_GQ8F"] = bool(sum(v["n"] for v in qn) == 40 and sum(v["oracle_verified"] for v in qn) == 40
                              and sum(v["false_restore"] for v in qn) == 0 and sum(v["spurious_reconnects"] for v in qn) == 0)
    g["S_probe"] = bool(pr.get("M8", {}).get("n") == 20 and pr["M8"]["S2_false_popup_text"] == 20
                        and pr.get("M8F", {}).get("n") == 20 and pr["M8F"]["S2_false_popup_text"] == 0)
    g["S_integrity"] = bool(pr.get("M8F", {}).get("S2_overlay_viewable_after_reply") == 20
                            and len(S["toolslist"].get("M8", [])) == 1
                            and S["toolslist"].get("M8") == S["toolslist"].get("M8F"))
    g["S_popup_discriminates"] = bool(pc.get("G0m8T", {}).get("n") == 20 and pc["G0m8T"]["control_holds"] <= 4)
    S["gates"] = g
    S["keep"] = bool(g["G1"] and g["G2"] and all(g[k] for k in ("G5", "G6", "G7", "G8")))
    S["attribution"] = "KEEP" if (g["G3"] and g["G4"]) else "REVISE"
    S["disposition"] = ("KEEP" if S["keep"] else "REVISE/KILL (see gates)")

    out = PKT / "fix20o-summary.json"
    text = json.dumps(S, indent=1, sort_keys=True) + "\n"
    if check:
        same = out.read_text(encoding="utf-8") == text
        print("summary matches" if same else "SUMMARY DIFFERS")
        return 0 if same else 1
    out.write_text(text, encoding="utf-8")
    with gzip.open(PKT / "fix20o-trial-metrics.jsonl.gz", "wt", encoding="utf-8") as stream:
        for m in metrics:
            stream.write(json.dumps({k: v for k, v in m.items() if k != "xrecord"}, sort_keys=True, default=str) + "\n")
    print(json.dumps(S["gates"], indent=1), "keep", S["keep"], "attribution", S["attribution"])
    return 0


def _receipts(rows: list[dict]) -> dict[str, int]:
    keys = sorted({str(r.get("receipt_focus_outcome")) for r in rows})
    return {k: sum(1 for r in rows if str(r.get("receipt_focus_outcome")) == k) for k in keys}


def _popup_receipts(rows: list[dict]) -> dict[str, int]:
    import re
    out: dict[str, int] = {}
    for r in rows:
        found = re.search(r"focus_outcome=([a-z_]+)", " ".join((r.get("click") or {}).get("text") or []))
        k = found.group(1) if found else "None"
        out[k] = out.get(k, 0) + 1
    return out


if __name__ == "__main__":
    sys.exit(main())
