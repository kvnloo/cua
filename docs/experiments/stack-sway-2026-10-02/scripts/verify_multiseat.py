#!/usr/bin/env python3
"""verify_multiseat.py <outdir> [summary-out]: grade a multiseat-proof.sh run from its raw receipts only.

Oracles: the two seatprobe event logs (the compositor labels every event with its wl_seat),
swaymsg get_seats snapshots (per-seat focus + attached devices) and get_tree (window ids/rects).
Writes <outdir>/summary.json and exits 0 only if every check passes.
"""
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
marks = [l.split() for l in (out / "phases.txt").read_text().splitlines() if l.strip()]
bounds = {name: (float(t), float(marks[i + 1][1]) if i + 1 < len(marks) else 1e18) for i, (name, t) in enumerate(marks)}


def load(p):
    return [json.loads(l) for l in (out / p).read_text().splitlines() if l.strip()]


probe = {"L": load("probe-L.jsonl"), "R": load("probe-R.jsonl")}


def walk(n):
    yield n
    for k in ("nodes", "floating_nodes"):
        for c in n.get(k, []):
            yield from walk(c)


tree = json.loads((out / "tree.json").read_text())
views = {n["name"]: n for n in walk(tree) if n.get("app_id") == "cua-seatprobe"}
origin = {k: (v["rect"]["x"] + v["window_rect"]["x"], v["rect"]["y"] + v["window_rect"]["y"]) for k, v in views.items()}
ids = {k: v["id"] for k, v in views.items()}
env = dict(kv.split("=") for kv in (out / "ids.env").read_text().split())
LC = (int(env["LCX"]), int(env["LCY"]))
RC = (int(env["RCX"]), int(env["RCY"]))


def ev(win, phase, seat=None, kinds=None):
    lo, hi = bounds[phase]
    return [e for e in probe[win] if lo <= e["t"] < hi and "seat" in e
            and (seat is None or e["seat"] == seat) and (kinds is None or e["ev"] in kinds)]


PTR = {"pointer_enter", "pointer_motion", "pointer_button"}


def typed(win, phase, seat):
    return "".join(e["utf8"] for e in ev(win, phase, seat, {"key"}) if e["state"] == 1)


def pos_ok(win, phase, seat, absxy):
    want = (absxy[0] - origin[win][0], absxy[1] - origin[win][1])
    got = [(e["x"], e["y"]) for e in ev(win, phase, seat, {"pointer_enter", "pointer_motion"})]
    return any(abs(x - want[0]) <= 1.5 and abs(y - want[1]) <= 1.5 for x, y in got), want, got


def seats(fname):
    return {s["name"]: s for s in json.loads((out / fname).read_text())}


def devs(s):
    return sorted((d["type"], d["identifier"]) for d in s["devices"])



def cross_ok(win, phase, wrong_seat, other_target_abs, prev_abs=None):
    """A wrong-seat event in `win` is only legitimate as that seat's own resting cursor (the probe
    binds wl_pointer while the seat's cursor still sits where it was): an enter/motion before the
    seat's own move, never a click, never at the other seat's target, and at prev_abs when known."""
    evs = ev(win, phase, wrong_seat, PTR)
    o = origin[win]
    bad = []
    for e in evs:
        if e["ev"] == "pointer_button":
            bad.append(e); continue
        ax, ay = e["x"] + o[0], e["y"] + o[1]
        if abs(ax - other_target_abs[0]) <= 1.5 and abs(ay - other_target_abs[1]) <= 1.5:
            bad.append(e); continue
        if prev_abs is not None and not (abs(ax - prev_abs[0]) <= 1.5 and abs(ay - prev_abs[1]) <= 1.5):
            bad.append(e)
    return not bad, {"wrong_seat_events": [(e["ev"], e.get("x"), e.get("y")) for e in evs], "violations": len(bad)}


checks = []


def check(name, ok, detail):
    checks.append({"check": name, "pass": bool(ok), "detail": detail})


sA = seats("seats-A-devices-held.json")
check("A.get_seats focus seat0=L seat1=R", sA["seat0"]["focus"] == ids["L"] and sA["seat1"]["focus"] == ids["R"],
      {"seat0_focus": sA["seat0"]["focus"], "seat1_focus": sA["seat1"]["focus"], "L": ids["L"], "R": ids["R"]})
check("A.each seat holds exactly its own virtual pointer",
      devs(sA["seat0"]) == [("pointer", "0:0:wlr_virtual_pointer_v1")] and devs(sA["seat1"]) == [("pointer", "0:0:wlr_virtual_pointer_v1")],
      {"seat0": devs(sA["seat0"]), "seat1": devs(sA["seat1"])})
okL, wantL, gotL = pos_ok("L", "A", "seat0", LC)
okR, wantR, gotR = pos_ok("R", "A", "seat1", RC)
check("A.seat0 cursor lands in L at its own position", okL, {"want_surface_xy": wantL, "got": gotL})
check("A.seat1 cursor lands in R at its own position", okR, {"want_surface_xy": wantR, "got": gotR})
check("A.seat0 click delivered to L, seat1 click to R",
      any(e["state"] == 1 for e in ev("L", "A", "seat0", {"pointer_button"})) and any(e["state"] == 1 for e in ev("R", "A", "seat1", {"pointer_button"})), {})
okx1, dx1 = cross_ok("L", "A", "seat1", LC)
okx2, dx2 = cross_ok("R", "A", "seat0", RC)
check("A.no cross-seat clicks; wrong-seat events only at that seat's own resting cursor", okx1 and okx2,
      {"L_from_seat1": dx1, "R_from_seat0": dx2})

sB = seats("seats-B-keyboards-held.json")
check("B.each seat holds exactly its own virtual keyboard",
      devs(sB["seat0"]) == [("keyboard", "0:0:wlr_virtual_keyboard_v1")] and devs(sB["seat1"]) == [("keyboard", "0:0:wlr_virtual_keyboard_v1")],
      {"seat0": devs(sB["seat0"]), "seat1": devs(sB["seat1"])})
check("B.seat0 typed 'left' into L only", typed("L", "B", "seat0") == "left" and typed("R", "B", "seat0") == "",
      {"L": typed("L", "B", "seat0"), "R": typed("R", "B", "seat0")})
check("B.seat1 typed 'right' into R only", typed("R", "B", "seat1") == "right" and typed("L", "B", "seat1") == "",
      {"R": typed("R", "B", "seat1"), "L": typed("L", "B", "seat1")})

okC, wantC, gotC = pos_ok("L", "C", "seat0", (100, 100))
check("C.seat0 moved alone to (100,100) in L", okC, {"want_surface_xy": wantC, "got": gotC})
check("C.no seat1 pointer events anywhere and none in R",
      not ev("L", "C", "seat1", PTR) and not ev("R", "C", None, PTR),
      {"L_seat1": len(ev("L", "C", "seat1", PTR)), "R_any": len(ev("R", "C", None, PTR))})

sD = seats("seats-D-swapped.json")
check("D.get_seats focus swapped: seat0=R seat1=L", sD["seat0"]["focus"] == ids["R"] and sD["seat1"]["focus"] == ids["L"],
      {"seat0_focus": sD["seat0"]["focus"], "seat1_focus": sD["seat1"]["focus"]})
okD0, w0, g0 = pos_ok("R", "D", "seat0", (1100, 200))
okD1, w1, g1 = pos_ok("L", "D", "seat1", (320, 600))
check("D.seat0 cursor in R, seat1 cursor in L at their own positions", okD0 and okD1,
      {"seat0": {"want": w0, "got": g0}, "seat1": {"want": w1, "got": g1}})
oky1, dy1 = cross_ok("L", "D", "seat0", (320, 600), prev_abs=(100, 100))
oky2, dy2 = cross_ok("R", "D", "seat1", (1100, 200), prev_abs=RC)
check("D.no cross-seat clicks; wrong-seat events only at that seat's previous position", oky1 and oky2,
      {"L_from_seat0": dy1, "R_from_seat1": dy2})

check("E.seat0 typed 'zero' into R only", typed("R", "E", "seat0") == "zero" and typed("L", "E", "seat0") == "",
      {"R": typed("R", "E", "seat0"), "L": typed("L", "E", "seat0")})
check("E.seat1 typed 'one' into L only", typed("L", "E", "seat1") == "one" and typed("R", "E", "seat1") == "",
      {"L": typed("L", "E", "seat1"), "R": typed("R", "E", "seat1")})

version = json.loads((out / "sway-version.json").read_text())["human_readable"]
summary = {
    "schema": "cua.stack.sway.multiseat.v1",
    "evidence_class": "REAL",
    "sway_version": version,
    "window_ids": ids,
    "checks": checks,
    "passed": sum(c["pass"] for c in checks),
    "total": len(checks),
    "result": "PASS" if all(c["pass"] for c in checks) else "FAIL",
}
Path(sys.argv[2] if len(sys.argv) > 2 else out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
print(json.dumps({k: summary[k] for k in ("result", "passed", "total")}))
for c in checks:
    print(("PASS " if c["pass"] else "FAIL ") + c["check"])
sys.exit(0 if summary["result"] == "PASS" else 1)
