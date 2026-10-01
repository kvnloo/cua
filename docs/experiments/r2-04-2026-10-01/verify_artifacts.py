#!/usr/bin/env python3
"""Recompute every R2-04 headline number from raw/ and check the packet against it.

Independent of analyze.py: it re-parses raw/<session>/trials.jsonl.gz with its
own small code, then checks r2-04-summary.json, README.md, provenance.json and
PREREG.json, and privacy-scans the packet. Exit 0 = consistent.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import socket
import statistics
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
ORDER = ["s1-M", "s2-P", "s3-P", "s4-M", "s5-P", "s6-M", "s7-M", "s8-P"]
KINDS = ("checkbox", "button", "text")
failures: list[str] = []


def check(cond: bool, what: str) -> None:
    if not cond:
        failures.append(what)


def close(a, b, tol=0.002) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def load(name: str) -> list[dict]:
    with gzip.open(R / "raw" / name / "trials.jsonl.gz", "rt", encoding="utf-8") as s:
        return [json.loads(x) for x in s if x.strip()]


summary = json.loads((R / "r2-04-summary.json").read_text())
prov = json.loads((R / "provenance.json").read_text())
readme = (R / "README.md").read_text()

# --- provenance / prereg ------------------------------------------------------
for key in ("tested_source_base", "instrumentation_commit", "prereg_commit"):
    check(bool(re.fullmatch(r"[0-9a-f]{40}", prov[key])), f"provenance {key} not a 40-hex SHA")
for arm in ("M", "P"):
    check(bool(re.fullmatch(r"[0-9a-f]{64}", prov["binaries"][arm]["sha256"])), f"binary {arm} sha256")
check(hashlib.sha256((R / "PREREG.json").read_bytes()).hexdigest() == prov["prereg_sha256"], "PREREG sha256 mismatch")
prereg = json.loads((R / "PREREG.json").read_text())
for fname, digest in prereg["files_frozen_with_this_prereg"].items():
    check(hashlib.sha256((R / fname).read_bytes()).hexdigest() == digest, f"{fname} changed after pre-registration")
head = (R / "source-head.txt").read_text().split()
check(head[0] == prov["tested_source_base"], "source-head.txt base")

# --- raw ----------------------------------------------------------------------
sessions = {n: load(n) for n in ORDER}
check(sorted(p.name for p in (R / "raw").glob("s*-*")) == sorted(ORDER), "session set/order")
measured, negatives, warm = [], [], []
for name, rows in sessions.items():
    arm = name.split("-")[1]
    meta = rows[0]
    check(meta.get("event") == "meta" and meta["arm"] == arm, f"{name} meta arm")
    check(meta["phase_trace"] == (arm == "P"), f"{name} phase trace flag")
    trials = [r for r in rows if r.get("event") == "trial"]
    for r in trials:
        r["_arm"], r["_session"] = arm, name
    measured += [r for r in trials if r["phase"] == "measured"]
    negatives += [r for r in trials if r["phase"] == "negative"]
    warm += [r for r in trials if r["phase"] == "warmup"]
    check(sum(1 for r in trials if r["phase"] == "measured") == 30, f"{name} 30 measured trials")
    check(sum(1 for r in trials if r["phase"] == "negative") == 4, f"{name} 4 negatives")
    check(all("loadavg" in r for r in trials), f"{name} loadavg per trial")

# denominators
for arm in ("M", "P"):
    for kind in KINDS:
        xs = [r for r in measured if r["_arm"] == arm and r["kind"] == kind]
        ver = sum(1 for r in xs if r["oracle_verified"])
        d = summary["denominators"][f"{arm}/{kind}"]
        check(len(xs) == 40 == d["attempted"], f"{arm}/{kind} attempted")
        check(ver == d["verified"], f"{arm}/{kind} verified {ver} vs {d['verified']}")
        check(sum(1 for r in xs if r["monitored"]) == 20, f"{arm}/{kind} 20 monitored")

# negatives
for arm in ("M", "P"):
    xs = [r for r in negatives if r["_arm"] == arm]
    passed = sum(1 for r in xs if r["refused_stale"] and r["no_mutation"]
                 and sum(1 for p in r["rpc"] if p["member"] == "DoAction") == 0)
    check(passed == summary["stale_negative"][arm]["passed"] == len(xs) == 16, f"stale negatives {arm}")


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


ok = [r for r in measured if r["oracle_verified"]]
headline: dict[str, float] = {}
for arm in ("M", "P"):
    for kind in KINDS:
        xs = [r for r in ok if r["_arm"] == arm and r["kind"] == kind]
        act = med([sum(a["wrapper_ms"] for a in r["actions"]) for r in xs])
        tree = med([r["tree"]["wrapper_ms"] for r in xs])
        outcome = med([(r["oracle"]["w1"] - r["w_start"]) / 1e6 for r in xs])
        cs = summary["caller_spans"][f"{arm}/{kind}"]
        check(close(act, cs["action_ms"]["median"]), f"{arm}/{kind} action median")
        check(close(tree, cs["tree_ms"]["median"]), f"{arm}/{kind} tree median")
        check(close(outcome, cs["outcome_ms"]["median"]), f"{arm}/{kind} outcome median")
        headline[f"{arm}/{kind}/action"] = act
        headline[f"{arm}/{kind}/tree"] = tree


# RPC counts and D (arm M monitored, own parse)
def drv(rpc):
    c = {}
    for p in rpc:
        if (p.get("interface") or "").startswith("org.a11y.atspi.") and p.get("dest") != "org.a11y.atspi.Registry":
            c[p["sender"]] = c.get(p["sender"], 0) + 1
    return max(c, key=c.get)


def busy(calls):
    iv = sorted((c["t_ns"], c["end_ns"]) for c in calls if c.get("end_ns"))
    tot, s0, e0 = 0, None, None
    for s, e in iv:
        if e0 is None or s > e0:
            if e0 is not None:
                tot += e0 - s0
            s0, e0 = s, e
        else:
            e0 = max(e0, e)
    return (tot + ((e0 - s0) if e0 is not None else 0)) / 1e6


for kind in KINDS:
    xs = [r for r in ok if r["_arm"] == "M" and r["kind"] == kind and r["monitored"]]
    tree_counts, act_counts, ds = [], [], []
    for r in xs:
        d = drv(r["rpc"])
        inw = lambda w: [p for p in r["rpc"] if p["sender"] == d and w["w0"] <= p["t_ns"] <= w["w1"]]
        t = inw(r["tree"])
        acts = [inw(a) for a in r["actions"]]
        tree_counts.append(len(t))
        act_counts.append(sum(len(a) for a in acts))
        disc = busy([p for p in t if p["member"] not in ("DoAction", "SetTextContents")]) + sum(
            busy([p for p in a if p["member"] not in ("DoAction", "SetTextContents")]) for a in acts)
        ds.append(disc / (r["tree"]["wrapper_ms"] + sum(a["wrapper_ms"] for a in r["actions"])))
    s = summary["rpc"][f"M/{kind}"]
    check(med(tree_counts) == s["tree_count"]["median"], f"M/{kind} tree rpc count")
    check(close(med(ds), s["D"]["median"], 0.01), f"M/{kind} D")
    headline[f"M/{kind}/tree_rpc"] = med(tree_counts)
    headline[f"M/{kind}/action_rpc"] = med(act_counts)
    headline[f"M/{kind}/D"] = med(ds)
check((max(headline[f"M/{k}/D"] for k in KINDS) >= 0.5) == summary["gate_bulk"]["fires"], "bulk gate")

# Driver spans from raw marks (arm P), final click of each trial


def span(r, call, a, b):
    first = {}
    for m in r["marks"]:
        if call["w0"] <= m["wall_ns"] <= call["w1"]:
            first.setdefault(f"{m['scope']}.{m['mark']}", m["wall_ns"])
    return (first[b] - first[a]) / 1e6 if a in first and b in first else None


PAIRS = {"reveal": ("click.placement_done", "click.reveal_done"),
         "post_sleep": ("atspi_action.do_action_replied", "atspi_action.post_sleep_done"),
         "guard_restore": ("atspi_action.post_sleep_done", "focus_guard.restored"),
         "do_action": ("atspi_action.metadata_done", "atspi_action.do_action_replied")}
for kind in KINDS:
    xs = [r for r in ok if r["_arm"] == "P" and r["kind"] == kind]
    idx = len(xs[0]["actions"]) - 1
    entry = summary["driver_spans_P"][kind]["actions"][idx]["median_ms"]
    for nm, (a, b) in PAIRS.items():
        v = med([span(r, r["actions"][idx], a, b) for r in xs])
        check(close(v, entry[nm], 0.005), f"P/{kind} {nm} {v} vs {entry[nm]}")
        headline[f"P/{kind}/{nm}"] = v
    if kind == "text":
        v = med([span(r, r["actions"][0], "set_value.element_resolved", "set_value.cursor_done") for r in xs])
        check(close(v, summary["driver_spans_P"]["text"]["actions"][0]["median_ms"]["cursor"], 0.005), "P/text cursor")
        headline["P/text/set_value_cursor"] = v

# Per-action RPC counts (arm M monitored), effect landing -> return, and tree size (own parse)
act_rpc_by_call: dict[str, list[float]] = {}
landed: list[float] = []
for kind in KINDS:
    xs = [r for r in ok if r["_arm"] == "M" and r["kind"] == kind and r["monitored"]]
    for i in range(len(xs[0]["actions"])):
        vals = []
        for r in xs:
            d = drv(r["rpc"])
            a = r["actions"][i]
            vals.append(sum(1 for p in r["rpc"] if p["sender"] == d and a["w0"] <= p["t_ns"] <= a["w1"]))
        act_rpc_by_call[f"{kind}/{i}"] = vals
    for r in xs:
        d = drv(r["rpc"])
        a = r["actions"][-1]
        ends = [p["end_ns"] for p in r["rpc"] if p["sender"] == d and a["w0"] <= p["t_ns"] <= a["w1"]
                and p["member"] in ("DoAction", "SetTextContents") and p.get("end_ns")]
        landed.append((a["w1"] - max(ends)) / 1e6)
click_rpc = {med(act_rpc_by_call[k]) for k in ("checkbox/0", "button/0", "text/1")}
check(len(click_rpc) == 1, f"click RPC count differs by target {click_rpc}")
click_rpc = click_rpc.pop()
set_value_rpc = med(act_rpc_by_call["text/0"])
landed_med = med(landed)
headline["M/landed_to_return"] = landed_med

all_m = [r for r in ok if r["_arm"] == "M"]
els = {r["tree"]["summary"]["element_count"] for r in ok} | {r["tree"]["summary"]["nodes_visited"] for r in ok}
check(len(els) == 1, f"tree size varies across trials {els}")
n_el = els.pop()
mon_m = [r for r in all_m if r["monitored"]]
objs = set()
per_el_bus = []
for r in mon_m:
    d = drv(r["rpc"])
    t = [p for p in r["rpc"] if p["sender"] == d and r["tree"]["w0"] <= p["t_ns"] <= r["tree"]["w1"]]
    objs.add(len({(p["dest"], p["path"]) for p in t if (p.get("interface") or "").startswith("org.a11y.atspi.")
                  and p["dest"] != "org.a11y.atspi.Registry"}))
    per_el_bus.append(busy([p for p in t if p["member"] not in ("DoAction", "SetTextContents")]) / n_el)
check(len(objs) == 1, f"app objects queried varies {objs}")
n_obj = objs.pop()
tree_rpc = headline["M/checkbox/tree_rpc"]
ts = summary["supplementary_tree_size"]["M"]
check(ts["element_count"]["median"] == n_el == ts["nodes_visited"]["median"], "summary tree size")
check(ts["app_objects_queried"]["median"] == n_obj, "summary app objects queried")
check(close(med(per_el_bus), ts["tree_discovery_bus_ms_per_element"]["median"], 0.01), "summary bus ms per element")
check(close(tree_rpc / n_el, ts["tree_rpc_per_element"]["median"], 0.01), "summary rpc per element")
check(f"({n_el:g}-element" in summary["dispositions"]["H_A_scope"], "H_A scope names the tree size")

# README must quote the recomputed numbers in context (table rows / phrases, not bare substrings)
f1 = lambda v: f"{v:.1f}"
H = headline
expect = {
    "tree row": "| Tree acquisition (`get_window_state` wrapper) | " + " | ".join(
        f"{f1(H[f'M/{k}/tree'])} / {f1(H[f'P/{k}/tree'])}" for k in KINDS) + " |",
    "action row": "| Action tool call(s) | " + " | ".join(
        f"{f1(H[f'M/{k}/action'])} / {f1(H[f'P/{k}/action'])}" for k in KINDS),
    "tree rpc": f"**Tree acquisition: {tree_rpc:g} RPCs",
    "click rpc": f"**Click (checkbox, button, Save note): {click_rpc:g} RPCs",
    "set_value rpc": f"**set_value: {set_value_rpc:g} RPCs",
    "gate D": "checkbox {:.3f}, button {:.3f}, text {:.3f}".format(*(H[f"M/{k}/D"] for k in KINDS)),
    "landed": f"**{landed_med:.0f} ms before the click returns**",
    "reveal row": "| **Agent-cursor reveal / keyboard-cursor positioning** | " + " | ".join(
        f"**{f1(v)}**" for v in (H["P/checkbox/reveal"], H["P/button/reveal"], H["P/text/reveal"],
                                 H["P/text/set_value_cursor"])) + " |",
    "sleep row": "| **Fixed post-`DoAction` sleep** (`perform_action_ref`, 50 ms) | " + " | ".join(
        f"**{f1(H[f'P/{k}/post_sleep'])}**" for k in KINDS) + " |",
    "restore row": "| **Focus-guard restore** (220 ms settle watch + checks) | " + " | ".join(
        f"**{f1(H[f'P/{k}/guard_restore'])}**" for k in KINDS) + " |",
    "tree size": f"**{n_el:g} elements** (`nodes_visited` = `element_count` = {n_el:g} in all",
    "objects": f"{n_obj:g} distinct app-side AT-SPI objects",
    "per element": f"about **{tree_rpc / n_el:.1f} RPCs and {med(per_el_bus):.2f} ms of bus time per emitted element**",
    "stale": f"{sum(summary['stale_negative'][a]['passed'] for a in ('M', 'P'))}/{len(negatives)} stale negatives refused",
}
for arm in ("M", "P"):
    for kind in KINDS:
        d = summary["denominators"][f"{arm}/{kind}"]
        expect[f"denominator {arm}/{kind}"] = f"| {arm} / {kind} | {d['attempted']} | {d['verified']} | 20 | REAL |"
for what, s in expect.items():
    check(s in readme, f"README lacks {what}: {s!r}")
check(summary["dispositions"]["H_A_bulk_cache"] in readme and summary["dispositions"]["H_B_localization"] in readme,
      "README dispositions")

# --- unit evidence must be present in the packet ------------------------------
unit = R / "raw" / "unit" / "in-session-tests.txt"
check(unit.is_file(), "raw/unit/in-session-tests.txt missing")
if unit.is_file():
    u = unit.read_text()
    for n in (77, 177):
        check(f"ok. {n} passed; 0 failed" in u, f"in-session unit log lacks {n} passed")
        check(f"{n} tests" in readme, f"README lacks unit count {n}")
    check(len(re.findall(r"^rc=0$", u, re.M)) == 2 and not re.search(r"^rc=[1-9]", u, re.M), "in-session unit log rc")
for name in ("host-shell-core-phase-trace", "host-shell-core-tool-phase",
             "host-shell-platform-linux-focus-atspi", "host-shell-platform-linux-tools"):
    check((R / "raw" / "unit" / f"{name}.txt").is_file(), f"raw/unit/{name}.txt missing")
check(not list((R / "raw").rglob("*.log")), "a .log file in raw/ would be dropped by .gitignore")

# --- privacy -------------------------------------------------------------------
host = socket.gethostname()
pat = re.compile(r"/home/|/mnt/|/tmp/|/root/")
for p in R.rglob("*"):
    if not p.is_file():
        continue
    data = gzip.decompress(p.read_bytes()).decode("utf-8", "replace") if p.suffix == ".gz" else p.read_text("utf-8", "replace")
    if p.name == "verify_artifacts.py":
        continue
    check(not pat.search(data), f"absolute path in {p.relative_to(R)}")
    check(not (host and host in data), f"host name in {p.relative_to(R)}")
    check(not re.search(r"(sk-[A-Za-z0-9]{20,}|api[_-]?key\s*[:=]\s*\S{12,})", data, re.I), f"secret-like token in {p.relative_to(R)}")

if failures:
    print("FAILED:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print(f"R2-04 packet consistent: {len(measured)} measured trials, {len(negatives)} negatives, {len(warm)} warm-up; "
      f"{len(headline)} headline numbers recomputed from raw/")
