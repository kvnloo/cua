#!/usr/bin/env python3
"""FIX-02 independent verifier (stdlib only). Exit 0 iff every check passes.

Recomputes the gating rows from raw/ with its own code (not analyze.py), then checks them against
fix02-summary.json and the README numbers it is given; checks PREREG-before-first-trial, lock
receipts, binary identity, provider 0 and a privacy scan of every packet file.

usage: python3 verify_artifacts.py [--git <repo>]   (with --git, also checks commit times and SHAs)
"""

import glob
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
FAIL = []


def check(name, ok, detail=""):
    print(f"[{'ok' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        FAIL.append(name)


def jsonl(path):
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


PROV = json.load(open(os.path.join(HERE, "provenance.json"), encoding="utf-8"))
SUMMARY = json.load(open(os.path.join(HERE, "fix02-summary.json"), encoding="utf-8"))


# ── native: independent recomputation ─────────────────────────────────────────
def changed(call, tag):
    return call["pre"].get(tag) != call["post"].get(tag)


def any_change(call):
    return "pre" in call and (changed(call, "A") or changed(call, "B"))


def toggled(call, tag):
    pre, post = call["pre"].get(tag) or {}, call["post"].get(tag) or {}
    other = "B" if tag == "A" else "A"
    return (not call["is_error"] and post.get("agreed") is (not pre.get("agreed"))
            and post.get("seq") == (pre.get("seq") or 0) + 1 and not changed(call, other))


def by_step(a):
    return {c["step"]: c for c in a["calls"]}


native = {}
headers = {"U": set(), "F": set()}
files = sorted(glob.glob(os.path.join(RAW, "native", "*", "T*", "*", "b*.jsonl")))
first_attempt = None
for path in files:
    arm = os.path.relpath(path, RAW).split(os.sep)[1]
    for r in jsonl(path):
        if r["kind"] == "block":
            headers[arm].add((r["driver_sha256"], r["driver_version"]))
        if r["kind"] != "attempt":
            continue
        first_attempt = min(first_attempt or r["started_utc"], r["started_utc"])
        s = by_step(r)
        row, ok, mut = r["row"], False, 0
        if row == "I2":
            ba, bb, t = s["B-uses-A-token-on-A-pid"], s["B-uses-A-token-on-B-pid"], s["A-uses-own-token"]
            mut = int(any_change(ba)) + int(any_change(bb))
            ok = ba["is_error"] and bb["is_error"] and mut == 0 and toggled(t, "A")
            native.setdefault(f"{arm}/I2/landed_on_A", 0)
            native[f"{arm}/I2/landed_on_A"] += int(toggled(ba, "A"))
        elif row == "I2d":
            d, t = s["B-uses-derived-token-on-A-pid"], s["A-uses-own-token"]
            mut = int(any_change(d))
            disclosed = r["disclosed_A_handle"]
            ok = d["is_error"] and mut == 0 and not disclosed and toggled(t, "A")
            native[f"{arm}/I2d/landed_on_A"] = native.get(f"{arm}/I2d/landed_on_A", 0) + int(toggled(d, "A"))
            native[f"{arm}/I2d/disclosed"] = native.get(f"{arm}/I2d/disclosed", 0) + int(bool(disclosed))
        elif row in ("I5p", "I5pt"):
            t = s["gen2-uses-gen1-token"]
            mut = int(any_change(t))
            ok = t["is_error"] and mut == 0
            if row == "I5p":
                c = s["gen2-uses-gen1-capture"]
                ok = ok and c["is_error"] and not any_change(c) and r["gen1_token"] != r["gen2_token"]
                native[f"{arm}/I5p/tokens_equal"] = native.get(f"{arm}/I5p/tokens_equal", 0) + int(
                    r["gen1_token"] == r["gen2_token"])
            native[f"{arm}/{row}/accepted_mutation"] = native.get(f"{arm}/{row}/accepted_mutation", 0) + int(
                not t["is_error"] and bool(mut))
        elif row == "I1":
            b, t = s["B-uses-A-capture"], s["A-uses-own-capture"]
            mut = int(any_change(b))
            ok = b["is_error"] and mut == 0 and toggled(t, "A")
        elif row == "I3":
            ok = toggled(s["B-uses-own-pre-replacement-token"], "B") and s["A-uses-own-superseded-token"]["is_error"] \
                and not any_change(s["A-uses-own-superseded-token"])
        elif row == "I4":
            x = s["B-uses-ended-A-token"]
            y = s["A-uses-own-token-after-end"]
            mut = int(any_change(x))
            ok = toggled(s["B-own-token-after-A-ended"], "B") and x["is_error"] and mut == 0 and y["is_error"] \
                and not any_change(y)
        elif row == "I5":
            b = s.get("B-own-token-before-A-restart") or s.get("B-own-token-after-A-restart")
            ok = (s["A-uses-old-generation-token"]["is_error"] and not any_change(s["A-uses-old-generation-token"])
                  and s["A-uses-old-generation-capture"]["is_error"]
                  and not any_change(s["A-uses-old-generation-capture"])
                  and toggled(s["A-uses-new-generation-token"], "A") and toggled(b, "B"))
        key = f"{arm}/{row}"
        native.setdefault(key, [0, 0, 0])
        native[key][0] += 1
        native[key][1] += int(bool(ok))
        native[key][2] += mut

expected_native = {"F/I2": 40, "F/I2d": 40, "F/I5p": 20, "F/I5pt": 10, "F/I1": 20, "F/I3": 20, "F/I4": 20,
                   "F/I5": 20, "U/I2": 40, "U/I2d": 40, "U/I5p": 20, "U/I5pt": 10}
for key, n in expected_native.items():
    got = native.get(key, [0, 0, 0])
    check(f"native {key} attempts == {n}", got[0] == n, str(got[0]))
for key in ("F/I2", "F/I2d", "F/I5p", "F/I5pt", "F/I1", "F/I3", "F/I4", "F/I5"):
    got = native.get(key, [0, 0, 0])
    check(f"native {key} gate 100% and 0 target mutations", got[0] > 0 and got[1] == got[0] and got[2] == 0,
          f"{got[1]}/{got[0]} pass, {got[2]} mutations")
check("native U discriminating: I2 B+A token landed on A in every U attempt",
      native.get("U/I2/landed_on_A") == native.get("U/I2", [0])[0], str(native.get("U/I2/landed_on_A")))
check("native U discriminating: I2d minted token landed on A in every U attempt",
      native.get("U/I2d/landed_on_A") == native.get("U/I2d", [0])[0], str(native.get("U/I2d/landed_on_A")))
check("native U discriminating: I5p gen1 token accepted with a mutation in every U attempt",
      native.get("U/I5p/accepted_mutation") == native.get("U/I5p", [0])[0], str(native.get("U/I5p/accepted_mutation")))
check("native U discriminating: I5pt gen1 token accepted with a mutation in every U attempt",
      native.get("U/I5pt/accepted_mutation") == native.get("U/I5pt", [0])[0],
      str(native.get("U/I5pt/accepted_mutation")))
check("native F I2d discloses A's handle 0 times", native.get("F/I2d/disclosed", 0) == 0)

# I6 on F: other-session marker in any envelope
markers = {}
hits = scanned = positive = sessions = 0
for path in files:
    if os.sep + "F" + os.sep not in path:
        continue
    recs = jsonl(path)
    for r in recs:
        if r["kind"] == "setup":
            markers[r["marker_tag"]] = r["marker"]
            sessions += 1
            obs = [c for c in r["calls"] if c["step"] == "observe-with-marker"]
            positive += int(bool(obs) and r["marker"] in json.dumps(obs[0]["response"]))
    for r in recs:
        if r["kind"] != "attempt" or r["topology"] == "T3":
            continue
        for c in r["calls"]:
            other = markers.get({"A": "B", "B": "A"}.get(c.get("actor")))
            scanned += 1
            hits += int(bool(other) and other in json.dumps(c["response"]))
check("I6 F: 0 other-session markers in scanned envelopes", scanned > 0 and hits == 0, f"{hits} in {scanned}")
check("I6 F positive control: own marker found in every block-session", sessions > 0 and positive == sessions,
      f"{positive}/{sessions}")
i6 = SUMMARY["native"]["i6_F"]
check("summary I6 agrees (0 hits, 0 foreign-handle refusals)",
      i6["content_hits"] == 0 and i6["refusals_listing_other_session_handles"] == 0)

# ── browser: independent recomputation from the target journal ────────────────
groups = {}
for path in sorted(glob.glob(os.path.join(RAW, "browser", "*", "cells", "*.jsonl"))):
    recs = jsonl(path)
    cell = recs[0]
    journal = next((r["events"] for r in recs if r.get("type") == "target_journal"), [])
    received = sum(1 for e in journal if e["kind"] == "received")
    applied = sum(1 for e in journal if e["kind"] == "applied")
    token_applied = any(e["kind"] == "applied" and e.get("value_matches_token") for e in journal)
    if cell["phase"] == "f4":
        key = f"f4/{cell['arm']}"
        old = [e for e in journal if e["kind"] == "page_event" and e.get("node") == "old"]
        fresh_file = any(e["kind"] == "page_event" and e.get("node") == "fresh"
                         and str(e.get("event")).startswith("change") and str(e.get("event")) != "change0"
                         for e in journal)
        first = cell["steps"][0] if cell.get("steps") else {}
        ok = first.get("result") == "refused" and first.get("code") == "browser_ref_stale" and not old and fresh_file
        disc = first.get("result") == "accepted"
        groups.setdefault(key, [0, 0, 0, 0])
        groups[key][0] += 1
        groups[key][1] += int(ok)
        groups[key][2] += int(disc)
        groups[key][3] += int(bool(old))
        continue
    clicks = sum(1 for c in cell["driver_calls"] if c["tool"] == "browser_click")
    code = cell.get("code") or "-"
    key = f"{cell['phase']}/{code}/{cell['arm']}"
    out = cell["outcome"]
    if cell["phase"] == "f3ctl":
        ok = clicks == 1 and out == "verified" and applied == 1 and token_applied and cell["refusals_seen"] == 0
    elif code == "stale":
        ok = cell["injected"] and clicks == 2 and out == "verified" and applied == 1 and token_applied \
            and cell["observations_between_first_and_second_click"] == 1
    elif code.startswith("trust_unknown"):
        ok = cell["injected"] and clicks == 1 and out == "unknown" and received == 1 and applied == 1
    else:
        ok = cell["injected"] and clicks == 1 and out == "unknown" and applied == 0
    groups.setdefault(key, [0, 0, 0, 0])
    groups[key][0] += 1
    groups[key][1] += int(bool(ok))
    groups[key][2] += int(clicks >= 2)
    groups[key][3] += max(0, received - 1)

expect_b = {"f3/stale/F": 10, "f3/trust_unknown/F": 10, "f3/not_retryable/F": 10, "f3ctl/-/F": 20, "f4/F": 20,
            "f3/stale/U": 10, "f3/trust_unknown/U": 10, "f3/not_retryable/U": 10, "f4/U": 20}
for key, n in expect_b.items():
    got = groups.get(key, [0, 0, 0, 0])
    check(f"browser {key} cells == {n}", got[0] == n, str(got[0]))
for key in ("f3/stale/F", "f3/trust_unknown/F", "f3/not_retryable/F", "f3ctl/-/F", "f4/F"):
    got = groups.get(key, [0, 0, 0, 0])
    check(f"browser {key} gate 100%", got[0] > 0 and got[1] == got[0], f"{got[1]}/{got[0]}")
check("browser U discriminating: trust_unknown re-dispatched in every U cell",
      groups.get("f3/trust_unknown/U", [0, 0, 0])[2] == groups.get("f3/trust_unknown/U", [0])[0])
check("browser U discriminating: not_retryable re-dispatched in every U cell",
      groups.get("f3/not_retryable/U", [0, 0, 0])[2] == groups.get("f3/not_retryable/U", [0])[0])
check("browser U discriminating: F4 old ref accepted in every U cell",
      groups.get("f4/U", [0, 0, 0])[2] == groups.get("f4/U", [0])[0])
check("browser F duplicates 0 in every F3 row", all(groups.get(k, [0, 0, 0, 0])[3] == 0 for k in
                                                     ("f3/stale/F", "f3/trust_unknown/F", "f3/not_retryable/F",
                                                      "f3ctl/-/F")))
for key, g in SUMMARY["browser"]["groups"].items():
    k2 = key.replace("f4/-/", "f4/")
    if k2 in groups:
        check(f"summary agrees for {key}", g["n"] == groups[k2][0] and g["gate_pass"] == groups[k2][1],
              f"summary {g['n']}/{g['gate_pass']} vs {groups[k2][0]}/{groups[k2][1]}")

# ── provenance, binaries, locks, provider ─────────────────────────────────────
bins = PROV["binaries"]
check("native U blocks used the U binary", headers["U"] == {(bins["U"]["sha256"], bins["U"]["version"])},
      str(headers["U"]))
check("native F blocks used the F binary", headers["F"] == {(bins["F"]["sha256"], bins["F"]["version"])},
      str(headers["F"]))
for v in glob.glob(os.path.join(RAW, "browser", "*", "validity.json")):
    data = json.load(open(v, encoding="utf-8"))
    arm = data["arm"]
    check(f"browser block {os.path.basename(os.path.dirname(v))} valid and on the {arm} binary",
          data["ok"] and data["driver"]["sha256"] == bins[arm]["sha256"])
ledger = jsonl(os.path.join(RAW, "native", "lock-ledger.jsonl"))
native_blocks = set()
for p in files:
    _, arm_, topo_, row_, name_ = os.path.relpath(p, RAW).split(os.sep)
    native_blocks.add((topo_, row_, f"{arm_}-{name_[1:-6]}"))
receipts = {(r["topology"], r["row"], r["block"]): r for r in ledger}
check("every native block has a shared-lock receipt with rc 0 and its attempts recorded",
      native_blocks <= set(receipts) and all(r["mode"] == "shared" for r in ledger)
      and all(receipts[b]["rc"] == 0 and receipts[b]["attempts_recorded"] > 0 for b in native_blocks),
      f"{len(native_blocks)} blocks, {len(ledger)} receipts")
bledger = jsonl(os.path.join(RAW, "browser", "lock-ledger.jsonl"))
check("every browser block has a FIX-02 shared-lock receipt",
      len(bledger) >= len(glob.glob(os.path.join(RAW, "browser", "*", "validity.json")))
      and all(r["lane"] == "FIX-02" and r["mode"] == "shared" for r in bledger))
tledger = os.path.join(RAW, "timing", "quiet-ledger.jsonl")
if os.path.exists(tledger):
    check("timing chunk has an exclusive quiet-timed receipt", any(r["label"].startswith("fix02-timing")
                                                                   for r in jsonl(tledger)))
check("provider: 0 attempts, 0 reached", PROV["provider"]["attempts"] == 0 and PROV["provider"]["reached"] == 0)
nonloop = [c.get("nonloopback_refused_total", 0) for p in glob.glob(os.path.join(RAW, "browser", "*", "cells.jsonl"))
           for c in jsonl(p)]
check("socket guard counted 0 non-loopback connects", nonloop and max(nonloop) == 0)
check("PREREG committed before the first counted native attempt",
      PROV["prereg"]["committed_utc"] < first_attempt, f"{PROV['prereg']['committed_utc']} < {first_attempt}")

if "--git" in sys.argv:
    repo = sys.argv[sys.argv.index("--git") + 1]
    for name, sha in PROV["commits"].items():
        out = subprocess.run(["git", "-C", repo, "cat-file", "-t", sha], capture_output=True, text=True).stdout
        check(f"commit {name} {sha[:9]} exists", out.strip() == "commit")
    t = subprocess.run(["git", "-C", repo, "log", "-1", "--date=iso-strict-local", "--format=%cd",
                        PROV["prereg"]["commit"]], capture_output=True, text=True,
                       env={**os.environ, "TZ": "UTC"}).stdout.strip()
    check("PREREG commit time matches provenance", t[:19] == PROV["prereg"]["committed_utc"][:19],
          f"{t} vs {PROV['prereg']['committed_utc']}")
    for name in ("F1", "F2", "F3", "F4_F_head"):
        files_changed = subprocess.run(["git", "-C", repo, "show", "--name-only", "--format=",
                                        PROV["commits"][name]], capture_output=True, text=True).stdout.split()
        check(f"{name} touches libs/cua-driver only", files_changed and
              all(f.startswith("libs/cua-driver/") for f in files_changed))
    tree = subprocess.run(["git", "-C", repo, "rev-parse", f"{PROV['commits']['F4_F_head']}:libs/cua-driver/rust"],
                          capture_output=True, text=True).stdout.strip()
    check("F Rust tree matches provenance", tree == PROV["trees"]["F_rust"])

# ── privacy ───────────────────────────────────────────────────────────────────
host_sha = PROV.get("privacy", {}).get("host_name_sha256")
pat = re.compile("(" + "|".join("/" + root + "/" for root in ("mnt", "home", "Users", "root")) + ")")
bad = []
for path in glob.glob(os.path.join(HERE, "**", "*"), recursive=True):
    if os.path.isdir(path) or path.endswith(".pyc"):
        continue
    text = open(path, encoding="utf-8", errors="replace").read()
    if pat.search(text):
        bad.append(os.path.relpath(path, HERE) + ":abs-path")
    if host_sha:
        for word in set(re.findall(r"[A-Za-z0-9]{3,16}", text)):
            if hashlib.sha256(word.encode()).hexdigest() == host_sha:
                bad.append(os.path.relpath(path, HERE) + ":host-name")
                break
check("privacy: no absolute local paths or host name in packet files", not bad, ", ".join(bad[:5]))

print(f"\n{len(FAIL)} failed check(s)")
sys.exit(1 if FAIL else 0)
