#!/usr/bin/env python3
"""RECERT-FIX a3 independent verifier (stdlib only; does not import analyze.py).

Checks, from the committed packet alone:
  1. PREREG.json was committed before the first counted record (with --git <repo>).
  2. Every counted block header / validity / session-env names its arm's Driver sha256 and a version.
  3. Every counted native/W2 block has a shared quiet-lane lock receipt; <= 10 attempts per native/W2
     acquisition (OWN-09R/OWN-16W take one acquisition per invocation/session: README Deviation 17).
  4. FIX-02 native, Part B, F3/F4 gates recomputed from the raw calls with the PREREG classification.
  5. OWN-09R gates from the raw harness verdicts; OWN-16W dispositions from own16w/own-16w-summary.json.
  6. Unit red/green from the unit logs.
  7. recert-summary.json equals a fresh analyze.py run (subprocess) and dispositions.json agrees.
  8a. Session evidence: no empty raw file (outside EMPTY_OK), a non-empty session log per receipt, xdpyinfo probes.
  8. Cited files are tracked (template helper) and no packet file holds an absolute local path.
usage: python3 verify_artifacts.py [--git <repo>]
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" ({detail})" if detail and not ok else ""))


def jl(path):
    return [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]


PROV = json.load(open(os.path.join(HERE, "provenance.json")))
BIN = PROV["binaries"]
# Empty files that are evidence as they are: the superseded first unit run (Deviation 2) was stopped by
# exact PID (the rustup fix) before these two commands wrote any output (see its unit-runs.txt: no "unit end").
EMPTY_OK = {
    "raw/unit/superseded-rustup/own16w/green-selector-F.log": "superseded run stopped before the command wrote output",
    "raw/unit/superseded-rustup/own09r/build-tests-P.log": "superseded run stopped before the command wrote output",
}
# Sessions whose private Xvfb died before the first attempt (Deviation 7).
PROBE_FAILED = ["a3-N-F-T2-I2-02", "a3-N-U-T2-I2-02", "a3-N-U-T1-I2d-05", "a3-W-F-W2c-25"]
ARM_SHA = {"U":BIN["fix02r3-u-513e45fee"]["sha256"], "F": BIN["fix02r3-f-df4f1edf5"]["sha256"]}


# ── classification (independent re-implementation of PREREG refusal_classification) ──
def fail_resp(c):
    s = (c.get("response") or {}).get("structuredContent") or {}
    return c.get("is_error") or "rpc_error" in (c.get("response") or {}) or isinstance(s.get("refusal"), dict) \
        or s.get("effect") == "refused" or bool(c.get("refusal_code"))


def moved(c, key=None):
    a, b = c.get("pre") or {}, c.get("post") or {}
    return a != b if key is None else a.get(key) != b.get(key)


def ref(c):
    return bool(fail_resp(c)) and not moved(c)


def ver(c, key):
    return not fail_resp(c) and moved(c, key)


def by(rec):
    return {c["step"]: c for c in rec["calls"]}


def native_records(arm):
    hdr, att = [], []
    for p in glob.glob(os.path.join(RAW, "fix02", "native", arm, "*", "*", "b*.jsonl")):
        for r in jl(p):
            (hdr if r.get("kind") == "block" else att if r.get("kind") == "attempt" else []).append(r)
    return hdr, att


def w2_records(arm):
    hdr, att = [], []
    for p in glob.glob(os.path.join(RAW, "fix02", "w2", arm, "W2*", "b*.jsonl")):
        for r in jl(p):
            (hdr if r.get("kind") == "block" else att if r.get("kind") == "attempt" else []).append(r)
    return hdr, att


def wchg(c, w):
    a = dict((((c.get("pre") or {}).get("P") or {}).get("windows") or {}).get(w) or {})
    b = dict((((c.get("post") or {}).get("P") or {}).get("windows") or {}).get(w) or {})
    a.pop("open", None), b.pop("open", None)
    return a != b


def main(argv):
    repo = argv[argv.index("--git") + 1] if "--git" in argv else None
    prereg_utc = PROV["prereg"]["committed_utc"]
    first = []

    # 2/4: native
    nat = {}
    for arm in ("U", "F"):
        hdr, att = native_records(arm)
        nat[arm] = att
        first += [h["started_utc"] for h in hdr]
        check(f"native {arm}: every block header names the {arm} binary",
              hdr and all(h["driver_sha256"] == ARM_SHA[arm] and h["driver_version"] for h in hdr),
              f"{len(hdr)} headers")
    F = nat["F"]
    U = nat["U"]

    def rows(att, row, forged=False):
        return [r for r in att if r["row"] == row and bool(r.get("forged")) == forged]

    i2 = rows(F, "I2")
    check("F1 I2: F' refuses both B calls and A's tail verifies 40/40",
          len(i2) == 40 and all(ref(by(r)["B-uses-A-token-on-B-pid"]) and ref(by(r)["B-uses-A-token-on-A-pid"])
                                and ver(by(r)["A-uses-own-token"], "A") for r in i2), f"n={len(i2)}")
    ui2 = rows(U, "I2")
    check("F1 I2: U' lands on pid_A (discriminating, >= 1)",
          sum(moved(by(r)["B-uses-A-token-on-A-pid"], "A") for r in ui2) >= 1,
          f"{sum(moved(by(r)['B-uses-A-token-on-A-pid'], 'A') for r in ui2)}/{len(ui2)}")
    i2d = rows(F, "I2d")
    check("F1 I2d: derived token refused, 0 disclosures, A tail verified 40/40",
          len(i2d) == 40 and all(ref(by(r)["B-uses-derived-token-on-A-pid"]) and not r.get("disclosed_A_handle")
                                 and ver(by(r)["A-uses-own-token"], "A") for r in i2d), f"n={len(i2d)}")
    ui2d = rows(U, "I2d")
    check("F1 I2d: U' derived token lands (discriminating, >= 1)",
          sum(moved(by(r)["B-uses-derived-token-on-A-pid"], "A") for r in ui2d) >= 1)
    for row, n in (("I5p", 20), ("I5ps", 20)):
        rr = rows(F, row)
        check(f"F2 {row}: gen1 token and capture refused, strings differ {n}/{n}",
              len(rr) == n and all(ref(by(r)["gen2-uses-gen1-token"]) and ref(by(r)["gen2-uses-gen1-capture"])
                                   and r["gen1_token"] != r["gen2_token"] for r in rr), f"n={len(rr)}")
    rr = rows(F, "I5pt")
    check("F2 I5pt: gen1 token refused 10/10", len(rr) == 10 and all(ref(by(r)["gen2-uses-gen1-token"]) for r in rr))
    up = rows(U, "I5p")
    check("F2 I5p: U' 'same' accepts the gen1 token (discriminating, >= 1)",
          sum(moved(by(r)["gen2-uses-gen1-token"]) for r in up) >= 1)
    rr = rows(F, "P")
    check("P: own tokens verified 20/20 on F'",
          len(rr) == 20 and all(all(ver(c, c["actor"]) for c in r["calls"] if c["step"].startswith("own-token-")) for r in rr))
    for row in ("I2", "I1"):
        rr = rows(F, row, True)
        bsteps = ("B-uses-A-token-on-B-pid", "B-uses-A-token-on-A-pid") if row == "I2" else ("B-uses-A-capture",)
        tail = "A-uses-own-token" if row == "I2" else "A-uses-own-capture"
        check(f"forged {row}: every forged value refused and A tail verified 10/10 on F'",
              len(rr) == 10 and all(all(ref(by(r)[s]) for s in bsteps) and ver(by(r)[tail], "A") for r in rr),
              f"n={len(rr)}")

    # Part B
    w = {}
    for arm in ("U", "F"):
        hdr, att = w2_records(arm)
        w[arm] = att
        first += [h["started_utc"] for h in hdr]
        check(f"W2 {arm}: every block header names the {arm} binary",
              hdr and all(h["driver_sha256"] == ARM_SHA[arm] for h in hdr))
    WF = w["F"]

    def wr(row):
        return [r for r in WF if r["row"] == row]

    a = wr("W2a")
    check("W2a: B's use of A's w1 token refused 20/20 on F', both own-token positives verified",
          len(a) == 20 and all(ref(by(r)["B-uses-A-w1-token"]) and ver(by(r)["A-uses-own-w1-token"], "P")
                               and wchg(by(r)["A-uses-own-w1-token"], "w1") and ver(by(r)["B-uses-own-w2-token"], "P")
                               and wchg(by(r)["B-uses-own-w2-token"], "w2") for r in a), f"n={len(a)}")
    b = wr("W2b")
    check("W2b: w1 token verifies after observing w2, w2 token verifies, 20/20 on F'",
          len(b) == 20 and all(ver(by(r)["A-uses-w1-token-after-observing-w2"], "P")
                               and wchg(by(r)["A-uses-w1-token-after-observing-w2"], "w1")
                               and ver(by(r)["A-uses-w2-token"], "P") and wchg(by(r)["A-uses-w2-token"], "w2") for r in b))
    c = wr("W2c")
    check("W2c: w1 capture in w2 refused (0 mutations), w2 capture verified, 20/20 on F'",
          len(c) == 20 and all(ref(by(r)["A-clicks-in-w2-with-w1-capture"])
                               and ver(by(r)["A-clicks-in-w2-with-w2-capture"], "P")
                               and wchg(by(r)["A-clicks-in-w2-with-w2-capture"], "w2") for r in c))
    d = wr("W2d")
    check("W2d: closed w1 token refused, w2 token verified, 20/20 on F'",
          len(d) == 20 and all(r.get("w1_closed_confirmed") and ref(by(r)["A-uses-closed-w1-token"])
                               and ver(by(r)["A-uses-w2-token-after-w1-closed"], "P")
                               and wchg(by(r)["A-uses-w2-token-after-w1-closed"], "w2") for r in d))

    # browser
    cells = {"U": [], "F": []}
    for vd in glob.glob(os.path.join(RAW, "fix02", "browser", "*", "validity.json")):
        v = json.load(open(vd))
        arm = v["arm"]
        check(f"browser {os.path.basename(os.path.dirname(vd))}: validity ok and {arm} binary",
              v["ok"] and v["driver"]["sha256"] == ARM_SHA[arm])
        first.append(v["started_utc"])
        cells[arm] += jl(os.path.join(os.path.dirname(vd), "cells.jsonl"))
    for rt, phase in (("py", "f3"), ("ts", "f3ts")):
        tu = [x for x in cells["F"] if x["phase"] == phase and x["code"] == "trust_unknown"]
        st = [x for x in cells["F"] if x["phase"] == phase and x["code"] == "stale"]
        check(f"F3 {rt}: post-dispatch unknown 0 re-dispatches, unknown, applied 1, 10/10",
              len(tu) == 10 and all(x["injected"] and x["redispatches_after_refusal"] == 0 and x["outcome"] == "unknown"
                                    and x["journal_applied"] == 1 for x in tu), f"n={len(tu)}")
        check(f"F3 {rt}: pre-dispatch refusal 1 re-dispatch, verified, applied 1, 10/10",
              len(st) == 10 and all(x["injected"] and x["redispatches_after_refusal"] == 1 and x["outcome"] == "verified"
                                    and x["journal_applied"] == 1 and x["state_matches_token"] for x in st))
    f4 = [x for x in cells["F"] if x["phase"] == "f4"]
    check("F4: old ref refused, 0 old-node events, rebind verified 20/20",
          len(f4) == 20 and all(x["old_ref_result"] == "refused" and x["old_node_events"] == 0 and x["rebind_verified"]
                                for x in f4))
    blind = sum(x["redispatches_after_refusal"] for x in cells["F"] if x.get("code") == "trust_unknown")
    check("F3: 0 blind re-dispatches on F'", blind == 0, str(blind))

    # OWN-09R
    def o9(arm, variant):
        recs = []
        for p in glob.glob(os.path.join(RAW, "own09r", "**", arm, variant + ".jsonl"), recursive=True):
            recs += jl(p)
        return recs

    def allv(arm, variant, verdict, n):
        r = o9(arm, variant)
        return len(r) == n and all(x["verdict"] == verdict for x in r)

    check("OWN-09R P' R1D PASS 40/40", allv("P", "R1D__flag_before_admission", "PASS", 40))
    check("OWN-09R P' R6 PASS 80/80", allv("P", "R6__shutdown_after_cancel", "PASS", 40)
          and allv("P", "R6__end_session_after_cancel", "PASS", 40))
    check("OWN-09R P' R2 PASS 40/40", allv("P", "R2__cancel_after_admission", "PASS", 40))
    check("OWN-09R P' R4/R4C PASS 40/40 each", all(allv("P", v, "PASS", 40) for v in (
        "R4__after_completion", "R4__after_inflight_cancel", "R4C__after_completion_retained_token",
        "R4C__after_inflight_cancel_retained_token")))
    check("OWN-09R P' R7 PASS 40/40", allv("P", "R7__ack_lost_guarded_retry", "PASS", 40))
    check("OWN-09R P' R5 PASS 40/40", allv("P", "R5__foreign_session_and_transport", "PASS", 40))
    check("OWN-09R M reproduces R1D FAIL 40/40", allv("M", "R1D__flag_before_admission", "FAIL", 40))
    check("OWN-09R M reproduces R2 40/40, R6 80/80, R7 40/40 FAIL",
          allv("M", "R2__cancel_after_admission", "FAIL", 40) and allv("M", "R6__shutdown_after_cancel", "FAIL", 40)
          and allv("M", "R6__end_session_after_cancel", "FAIL", 40) and allv("M", "R7__ack_lost_guarded_retry", "FAIL", 40))
    errs = sum(1 for p in glob.glob(os.path.join(RAW, "own09r", "**", "*.jsonl"), recursive=True)
               if "receipts" not in p and "ledger" not in p for x in jl(p) if x.get("error"))
    check("OWN-09R: 0 harness errors", errs == 0, str(errs))

    # OWN-16W
    s16 = json.load(open(os.path.join(RAW, "own16w", "own-16w-summary.json")))
    x11 = s16["modes"]["X11"]
    # PREREG X11 gates (the wave-3 analyzer's mode rule also needs U'''s positive control; Deviation 8).
    check("OWN-16W X11: F'' refuses both string rows, F'' positive control passes, U'' silently accepts",
          x11["rows"]["F"]["both"]["class"] == "positive_control_pass"
          and all(x11["rows"]["F"][r]["class"] == "refused_invalid_arguments" for r in ("string_false", "string_true"))
          and all(x11["rows"]["U"][r]["class"] == "silently_accepted_default" for r in ("string_false", "string_true")))
    for r in ("string_false", "string_true"):
        pf = x11["rows"]["F"][r]["pooled"]
        check(f"OWN-16W X11 F'' {r}: 42 calls", pf.get("n") == 42, str(pf.get("n")))
    sw = s16["modes"].get("SW")
    want = {"both": "positive_control_pass", "screenshot_only": "honored_complete",
            "accessibility_only": "honored_complete", "neither": "rejected_explicit",
            "unknown_field": "rejected_explicit", "legacy_omitted": "default_honored",
            "string_false": "refused_invalid_arguments", "string_true": "refused_invalid_arguments"}
    got = {k: v["class"] for k, v in (sw or {}).get("rows", {}).get("F", {}).items()}
    check("OWN-16W S-W: every F'' row meets its wave-3 gate (F''-only recert; U'' not run on S-W)",
          bool(sw) and got == want and len(sw["truth"]["F"]) == 2
          and all(s["usability"].get("oracle_verified") is True for s in sw["truth"]["F"])
          and all(v["pooled"]["n"] == 42 for v in sw["rows"]["F"].values()), json.dumps(got))

    # 1: PREREG before first record
    check("PREREG committed before the first counted record",
          first and prereg_utc < min(first), f"prereg {prereg_utc} first {min(first) if first else None}")
    if repo:
        ct = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%cI", PROV["prereg"]["commit"]],
                            capture_output=True, text=True).stdout.strip()
        check("PREREG commit exists in git with the recorded time", bool(ct), ct)

    # 3: locks
    led = []
    for p in glob.glob(os.path.join(RAW, "**", "lock-ledger.jsonl"), recursive=True):
        led += jl(p)
    labels = {x["label"] for x in led if x.get("mode") == "shared" and x.get("lane") == "RECERT-FIX-a3"}
    blocks = set()
    for arm in ("U", "F"):
        for p in glob.glob(os.path.join(RAW, "fix02", "native", arm, "*", "*", "b*.jsonl")):
            parts = p.split(os.sep)
            row, topo, blk = parts[-2], parts[-3], os.path.basename(p)[1:-6]
            blocks.add(f"a3-N-{arm}-{topo}-{row}-{blk}")
        for p in glob.glob(os.path.join(RAW, "fix02", "w2", arm, "W2*", "b*.jsonl")):
            blocks.add(f"a3-W-{arm}-{p.split(os.sep)[-2]}-{os.path.basename(p)[1:-6]}")
    missing = sorted(b for b in blocks if b not in labels)
    check("every counted native/W2 block has a shared-lock receipt", not missing, ", ".join(missing[:5]))
    att_counts = [len([r for r in jl(p) if r.get("kind") == "attempt"])
                  for p in glob.glob(os.path.join(RAW, "fix02", "*", "*", "**", "b*.jsonl"), recursive=True)]
    check("<= 10 attempts per native/W2 lock acquisition", att_counts and max(att_counts) <= 10)

    # 6: unit
    U_ = os.path.join(RAW, "unit")

    def txt(p):
        return open(os.path.join(U_, p), encoding="utf-8", errors="replace").read()

    def res(p):
        t = txt(p)
        m = re.findall(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed", t)
        return sum(int(x[1]) for x in m), sum(int(x[2]) for x in m), t

    p_, f_, _ = res("fix02/F-core.log")
    check("FIX-02 F' cua-driver-core lib+tests 0 failed", p_ > 0 and f_ == 0, f"{p_}/{f_}")
    p_, f_, _ = res("fix02/F-platform-linux-lib.log")
    check("FIX-02 F' platform-linux lib 0 failed", p_ > 0 and f_ == 0, f"{p_}/{f_}")
    _, f_, t = res("fix02/red-core.log")
    red = set(re.findall(r"^test (\S+) \.\.\. FAILED", t, re.M))
    check("FIX-02 red tree fails exactly the new F1/F2/F4 tests", f_ == len(red) and red == set(PROV["unit"]["fix02_red_expected"]),
          ", ".join(sorted(red)))
    _, f_, t = res("own16w/red-selector-U.log")
    check("OWN-16W selector red on U''", f_ >= 1)
    p_, f_, _ = res("own16w/green-selector-F.log")
    check("OWN-16W selector green on F''", p_ >= 1 and f_ == 0)
    check("OWN-09R c1 red: merge does not compile the slice A fixture", "E0599" in txt("own09r/c1-red-sdk-lib-no-run.log"))
    for g in ("c1-green-slice-a", "c2-green-unit", "c3-green-unit"):
        p_, f_, _ = res(f"own09r/{g}.log")
        check(f"OWN-09R {g} passes", p_ >= 1 and f_ == 0, f"{p_}/{f_}")
    for r_ in ("c2-red-unit", "c3-red-unit"):
        _, f_, _ = res(f"own09r/{r_}.log")
        check(f"OWN-09R {r_} fails", f_ >= 1)
    check("OWN-09R c4: converter red (unconverted sites) / green (0)",
          not re.search(r"converted_now=0\b", txt("own09r/c4-red-convert-check.log"))
          and re.search(r"converted_now=0\b", txt("own09r/c4-green-convert-check.log")))
    for s in ("cua-driver-sdk", "cua-driver"):
        p_, f_, _ = res(f"own09r/head-{s}.log")
        check(f"OWN-09R head {s} 0 failed", p_ > 0 and f_ == 0, f"{p_}/{f_}")
    # Head cua-driver-core: rule committed in 34b55dfac before the re-run existed (Deviation 6).
    p1, f1, t1 = res("own09r/head-cua-driver-core.log")
    p2, f2, _ = res("own09r/head-cua-driver-core-rerun.log")
    failing = set(re.findall(r"^test (\S+) \.\.\. FAILED", t1, re.M))
    iso_ok = True
    for t in failing:
        short = t.split("::")[-1]
        logs = glob.glob(os.path.join(U_, "own09r", "history-isolation", f"P-{short}-[0-9][0-9].log"))
        passes = sum(bool(re.search(r"test result: ok\. 1 passed; 0 failed", open(l, errors="replace").read())) for l in logs)
        iso_ok = iso_ok and len(logs) == 20 and passes == 20
    check("OWN-09R head cua-driver-core: first run 0 failed, or re-run 0 failed + 20/20 isolation on P'",
          (p1 > 0 and f1 == 0) or (p2 > 0 and f2 == 0 and failing and iso_ok),
          f"first {p1}/{f1}, rerun {p2}/{f2}, failing {sorted(failing)}")

    # 7: summary consistency
    out = subprocess.run([sys.executable, os.path.join(HERE, "analyze.py"), "--check"], capture_output=True, text=True)
    check("recert-summary.json equals a fresh analyze.py run", out.returncode == 0, out.stdout.strip())

    # 8a: session evidence. No file under raw/ may be empty unless listed in EMPTY_OK with its reason. Every
    # native/W2/browser lock receipt needs a non-empty session log beside its ledger; native/W2 sessions
    # must show the xdpyinfo probe passing, and a failed probe is allowed only for a pre-attempt death
    # (receipt rc != 0) that was re-run once as <label>R with a passing probe (Deviation 7).
    empty = sorted(os.path.relpath(p, HERE) for p in glob.glob(os.path.join(RAW, "**", "*"), recursive=True)
                   if os.path.isfile(p) and os.path.getsize(p) == 0)
    check("no empty raw file outside EMPTY_OK", set(empty) == set(EMPTY_OK), ", ".join(sorted(set(empty) ^ set(EMPTY_OK))[:5]))
    missing, noprobe, failed_probe, bad_retry = [], [], [], []
    for led in [os.path.join(RAW, "fix02", "lock-ledger.jsonl")] + glob.glob(os.path.join(RAW, "shakedown", "*", "lock-ledger.jsonl")):
        recs = {r["label"]: r for r in jl(led)}
        for label, r in recs.items():
            if not re.match(r"a3-[NWB]-", label):
                continue
            log = os.path.join(os.path.dirname(led), f"session-{label}.log")
            if not (os.path.isfile(log) and os.path.getsize(log) > 0):
                missing.append(os.path.relpath(log, HERE))
                continue
            if label.startswith("a3-B-"):
                continue
            t = open(log, errors="replace").read()
            if "[a3-probe] xdpyinfo ok" in t:
                continue
            if "[a3-probe] xdpyinfo FAILED" not in t:
                noprobe.append(label)
                continue
            failed_probe.append(label)
            rr = recs.get(label + "R")
            rlog = os.path.join(os.path.dirname(led), f"session-{label}R.log")
            if r.get("rc") == 0 or not rr or not os.path.isfile(rlog) or "[a3-probe] xdpyinfo ok" not in open(rlog, errors="replace").read():
                bad_retry.append(label)
    check("every native/W2/browser receipt has a non-empty session log", not missing, ", ".join(missing[:5]))
    check("every native/W2 session log records the xdpyinfo probe", not noprobe, ", ".join(noprobe[:5]))
    check("failed probes are exactly the 4 pre-attempt deaths of Deviation 7, each re-run once with a passing probe",
          sorted(failed_probe) == sorted(PROBE_FAILED) and not bad_retry, f"{sorted(failed_probe)} bad={bad_retry}")
    src = jl(os.path.join(RAW, "fix02", "session-log-sources.jsonl"))
    src_ok = [os.path.isfile(os.path.join(HERE, e["path"])) and __import__("hashlib").sha256(
        open(os.path.join(HERE, e["path"]), "rb").read()).hexdigest() == e["sha256_sanitized"] for e in src]
    check("session-log-sources.jsonl: 69 inner session logs, sanitized sha256 match", len(src) == 69 and all(src_ok),
          f"n={len(src)}, mismatched={src_ok.count(False)}")

    # 8: cited files + privacy
    sys.path.insert(0, HERE)
    try:
        import verify_helper
        findings = verify_helper.check_cited(__import__("pathlib").Path(HERE), "files")
        check("cited files tracked", not findings, str(findings[:3]))
    except Exception as error:  # noqa: BLE001
        check("cited files tracked (helper ran)", False, repr(error))
    pat = re.compile(r"(?<![\w<>.-])/(?:home|mnt|root|Users|media|run/user)/[\w.-]+")
    bad = []
    for p in glob.glob(os.path.join(HERE, "**", "*"), recursive=True):
        if os.path.isdir(p) or p.endswith((".pyc", ".gz")):
            continue
        if pat.search(open(p, encoding="utf-8", errors="replace").read()):
            bad.append(os.path.relpath(p, HERE))
    check("privacy: no absolute local paths in packet files", not bad, ", ".join(bad[:5]))

    failed = [r for r in RESULTS if not r[1]]
    print(f"{len(RESULTS)} checks, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
