#!/usr/bin/env python3
"""FIX-05 independent verifier. Recomputes every counted number from raw/ without importing analyze.py and
checks it against summary.json / dispositions.json, plus provenance, locks, PREREG order, units, the blob
manifest of the copied harness, and privacy.

usage: python3 verify_artifacts.py [--git <repo>]
  --git <repo>  also checks the commits (replay patch-ids, F7, PREREG before the first counted block) and
                scans every lane commit's diff for privacy. Private names (host name, user names) are read
                from the file named by CUA_PRIVACY_NAMES_FILE (one per line), never from this packet.
Exit code 0 iff every check passes.
"""

import argparse
import difflib
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
PACKET_REL = "docs/experiments/fix-05-native-index-residue-2026-10-03"
KEYS = ("agreed", "counter", "size", "note_saved", "note_text", "scroll_value", "focus", "focus_log")
TOOL_KEY = {"click": "agreed", "scroll": "scroll_value", "set_value": "note_text", "hotkey": "focus_log",
            "type_text": "note_text"}
ARM_SHA = {}
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def jl(path):
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def w(state, key):
    state = state or {}
    return state if key == "w" else ((state.get("windows") or {}).get(key) or {})


def diff_keys(pre, post):
    return [k for k in KEYS if pre.get(k) != post.get(k)]


def tool_calls(rec):
    return [c for c in rec["calls"] if c["tool"] not in ("get_window_state", "list_windows")]


def sc(call):
    return (call.get("response") or {}).get("structuredContent") or {}


def code_of(call):
    s = sc(call)
    return (s.get("refusal") or {}).get("code") if isinstance(s.get("refusal"), dict) else s.get("code")


def regrade():
    out = {}
    for path in sorted(glob.glob(os.path.join(RAW, "native", "*", "*", "b*.jsonl"))):
        arm, row = path.split(os.sep)[-3], path.split(os.sep)[-2]
        cell = out.setdefault(row, {}).setdefault(arm, {"n": 0, "cross": 0, "tail": 0, "closed": 0,
                                                        "a_err": 0, "refused_effect": 0, "unverifiable_a": 0,
                                                        "success_shaped_cross": 0, "tool": {}, "shas": set(),
                                                        "versions": set(), "blocks": 0})
        for rec in jl(path):
            if rec.get("kind") == "block":
                cell["shas"].add(rec["driver_sha256"])
                cell["versions"].add(rec["driver_version"])
                cell["blocks"] += 1
                continue
            if rec.get("kind") != "attempt":
                continue
            cell["n"] += 1
            calls = tool_calls(rec)
            if row in ("NC", "NS"):
                for c in calls:
                    pre, post = c["pre"]["P"], c["post"]["P"]
                    own = "w" if row == "NS" else ("w1" if c["actor"] == "A" else "w2")
                    other = None if row == "NS" else ("w2" if own == "w1" else "w1")
                    t = cell["tool"].setdefault(f'{c["tool"]}:{own}', {"n": 0, "own": 0, "other": 0})
                    t["n"] += 1
                    t["own"] += TOOL_KEY[c["tool"]] in diff_keys(w(pre, own), w(post, own))
                    if other:
                        t["other"] += bool(diff_keys(w(pre, other), w(post, other)))
                continue
            a, tail = calls[0], calls[-1]
            cross = bool(diff_keys(w(a["pre"]["P"], "w2"), w(a["post"]["P"], "w2")))
            cell["cross"] += cross
            cell["closed"] += bool(rec.get("w1_closed_confirmed"))
            cell["tail"] += TOOL_KEY[tail["tool"]] in diff_keys(w(tail["pre"]["P"], "w2"), w(tail["post"]["P"], "w2"))
            err = bool(a.get("is_error"))
            cell["a_err"] += err
            eff = sc(a).get("effect")
            cell["refused_effect"] += err and code_of(a) == "stale_element_token" and eff == "refused"
            cell["unverifiable_a"] += eff == "unverifiable"
            cell["success_shaped_cross"] += cross and not err
    return out


def check_summary(re_):
    with open(os.path.join(HERE, "summary.json"), encoding="utf-8") as stream:
        summ = json.load(stream)
    rows = summ["rows"]
    for row, arms in re_.items():
        for arm, c in arms.items():
            s = rows.get(row, {}).get(arm)
            check(f"summary has {row}/{arm}", s is not None)
            if s is None:
                continue
            check(f"{row}/{arm} n", s["n"] == c["n"], f'{s["n"]} vs {c["n"]}')
            check(f"{row}/{arm} sha256 single and equal to its arm",
                  len(c["shas"]) == 1 and next(iter(c["shas"])) == ARM_SHA.get(arm), str(c["shas"]))
            check(f"{row}/{arm} version recorded", len(c["versions"]) == 1 and next(iter(c["versions"])).startswith("cua-driver "))
            if row in ("NC", "NS"):
                for key, t in c["tool"].items():
                    st = s["per_tool"].get(key, {})
                    check(f"{row}/{arm} {key} own", st.get("own_effect") == t["own"] and st.get("n") == t["n"],
                          f'{st.get("own_effect")}/{st.get("n")} vs {t["own"]}/{t["n"]}')
                    check(f"{row}/{arm} {key} other", st.get("other_changed", 0) == t["other"])
            else:
                for k_s, k_c in (("cross_window", "cross"), ("tail_ok", "tail"), ("w1_closed", "closed"),
                                 ("a_is_error", "a_err")):
                    check(f"{row}/{arm} {k_s}", s[k_s] == c[k_c], f"{s[k_s]} vs {c[k_c]}")
    return summ


def check_dispositions(re_):
    with open(os.path.join(HERE, "dispositions.json"), encoding="utf-8") as stream:
        disp = json.load(stream)
    g = lambda row, arm, k: re_.get(row, {}).get(arm, {}).get(k)
    exp = {
        "CT_recert_pass": g("CT", "F6m", "cross") == 0 and (g("CT", "F5m", "cross") or 0) >= 18,
        "R-CF_discriminating": (g("RCF", "F5m", "cross") or 0) >= 18,
    }
    for row in ("RSC", "RSV", "RPA", "RCF"):
        exp[f"HOLE_{row}"] = (g(row, "F6m", "cross") or 0) >= 1
    f7_rows_zero = all(g(r, "F7m", "cross") == 0 and g(r, "F7m", "n") == 20 for r in ("RSC", "RSV", "RPA", "RCF"))
    nc = re_.get("NC", {}).get("F7m", {}).get("tool", {})
    ns = re_.get("NS", {}).get("F7m", {}).get("tool", {})
    nc_ok = len(nc) == 8 and all(t["own"] == t["n"] == 20 and t["other"] == 0 for t in nc.values())
    ns_ok = len(ns) == 4 and all(t["own"] == t["n"] == 20 for t in ns.values())
    refused_ok = all(g(r, "F7m", "refused_effect") == 20 for r in ("RSC", "RSV", "RCF"))
    exp["F7_REAL_gates"] = f7_rows_zero and nc_ok and ns_ok and refused_ok
    for k, v in exp.items():
        check(f"disposition {k}", disp["gates"].get(k) == v, f'{disp["gates"].get(k)} vs {v}')


def check_plan_and_locks():
    plan = [l.split() for l in open(os.path.join(HERE, "plans", "1-all.txt"), encoding="utf-8")
            if l.strip() and not l.startswith("#")]
    ledger = jl(os.path.join(RAW, "lock-ledger.jsonl"))
    labels = {}
    for line in ledger:
        labels.setdefault(line["label"], []).append(line)
    check("plan has 30 counted blocks", len(plan) == 30, str(len(plan)))
    for f in plan:
        if f[0] == "CT":
            arm, row, block = f[1], "CT", f[2]
        else:
            arm, row, block = f[1], f[2], f[3]
        path = os.path.join(RAW, "native", arm, row, f"b{block}.jsonl")
        retry = os.path.join(RAW, "native", arm, row, f"b{block}R.jsonl")
        ok = os.path.exists(path) or os.path.exists(retry)
        check(f"block {row}/{arm}/{block} raw present", ok)
        label = f"fix05-{row}-{arm}-{block}" if row != "CT" else f"fix05-CT-{arm}-{block}"
        hits = labels.get(label, []) + labels.get(label + "R", [])
        check(f"block {label} lock receipt", bool(hits) and all(h["mode"] == "shared" and h["held_s"] <= 310 for h in hits),
              json.dumps(hits)[:200])
    times = sorted((datetime.fromisoformat(l["acquired"].replace("Z", "+00:00")),
                    datetime.fromisoformat(l["released"].replace("Z", "+00:00"))) for l in ledger)
    gaps = [(times[i + 1][0] - times[i][1]).total_seconds() for i in range(len(times) - 1)]
    check(">= 30 s between acquisitions", all(g >= 29.5 for g in gaps), f"min gap {min(gaps) if gaps else None}")
    return min(t[0] for t in times) if times else None


def check_manifest():
    lines = [l.split() for l in open(os.path.join(HERE, "harness", "COPIED_MANIFEST.txt"), encoding="utf-8")
             if l.strip() and not l.startswith("#")]
    check("manifest lists 8 copies", len(lines) == 8)
    for parts in lines:
        blob, sha, dst = parts[0], parts[1], parts[4]
        path = os.path.join(HERE, dst)
        data = open(path, "rb").read()
        gblob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        check(f"copy blob-identical {os.path.basename(dst)}", gblob == blob and hashlib.sha256(data).hexdigest() == sha)
    base = os.path.join(HERE, "harness", "copied", "fix-04-unknown-delivery-effect-2026-10-03", "harness",
                        "gtk3_main_two_windows.py")
    mine = os.path.join(HERE, "harness", "gtk3_main_two_windows.py")
    d = "".join(difflib.unified_diff(open(base).readlines(), open(mine).readlines(),
                                     "copied/fix-04-unknown-delivery-effect-2026-10-03/harness/gtk3_main_two_windows.py",
                                     "gtk3_main_two_windows.py"))
    recorded = open(os.path.join(HERE, "harness", "gtk3_main_two_windows.fix05.diff")).read()
    body = lambda text: [l for l in text.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    # Hunk alignment of blank lines differs between diff tools: compare the added/removed lines as multisets.
    check("fixture diff matches the copies", sorted(body(d)) == sorted(body(recorded)))
    sums = {}
    for path in glob.glob(os.path.join(RAW, "native", "*", "*", "b*.jsonl")):
        for rec in jl(path):
            if rec.get("kind") == "block":
                sums.setdefault(path.split(os.sep)[-2] == "CT", set()).add(rec["fixture_sha256"])
    fx4 = hashlib.sha256(open(base, "rb").read()).hexdigest()
    fx5 = hashlib.sha256(open(mine, "rb").read()).hexdigest()
    check("CT blocks ran the FIX-04 fixture", sums.get(True) == {fx4}, str(sums.get(True)))
    check("FIX-05 rows ran the packet fixture", sums.get(False) == {fx5}, str(sums.get(False)))


def check_units():
    u = os.path.join(RAW, "unit")
    red1 = open(os.path.join(u, "red", "red1-platform-linux.log"), encoding="utf-8").read()
    check("red-1: set_value test FAILED on F6m+tests",
          "window_scoped_set_value_without_its_snapshot_is_stale_not_resolved_pid_wide ... FAILED" in red1)
    check("red-1: pin passes on F6m", "observed_action_without_its_object_is_stale_and_never_re_walks ... ok" in red1)
    red2 = open(os.path.join(u, "red", "red2-platform-linux.log"), encoding="utf-8").read()
    check("red-2: scroll test does not compile on F6m (no window parameter)", "error[E0061]" in red2)
    for arm in ("green-F7m", "green-F6m"):
        for step in ("core-lib-tests", "platform-linux-lib"):
            log = open(os.path.join(u, arm, f"{step}.log"), encoding="utf-8").read()
            fails = re.findall(r"test result: (\w+)\. (\d+) passed; (\d+) failed", log)
            check(f"{arm} {step} green", fails and all(r == "ok" and f == "0" for r, _, f in fails), str(fails[-3:]))
        steps = open(os.path.join(u, arm, "jev-use", "steps.txt"), encoding="utf-8").read()
        for name in ("python-unittest-discover", "ts-npm-test", "ts-typecheck", "verify_choice_cli ",
                     "verify_decision_cli-mock", "verify_choice_cli-v2", "verify_decision_cli-native"):
            check(f"{arm} jev-use {name.strip()} rc 0", re.search(re.escape(name) + r"\s+rc=0", steps) is not None)
    f7 = open(os.path.join(u, "green-F7m", "platform-linux-lib.log"), encoding="utf-8").read()
    for test in ("window_scoped_set_value_without_its_snapshot_is_stale_not_resolved_pid_wide",
                 "window_scoped_scroll_without_its_snapshot_is_stale_not_resolved_pid_wide",
                 "observed_action_without_its_object_is_stale_and_never_re_walks",
                 "a_gone_element_is_refused_before_dispatch"):
        check(f"green F7m {test}", re.search(re.escape(test) + r" \.\.\. ok", f7) is not None)


def check_privacy_packet(names):
    pats = [re.compile(r"/home/[a-z]"), re.compile(r"/mnt/[a-z]"), re.compile(r"/Users/[A-Za-z]"),
            re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"), re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
            re.compile(r"(?i)typesafe_api_key\s*=\s*\S{8,}")]
    pats += [re.compile(r"\b" + re.escape(n) + r"\b") for n in names]
    bad = []
    for root, _, files in os.walk(HERE):
        for f in files:
            path = os.path.join(root, f)
            if f == "verify_artifacts.py":
                continue
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if any(p.search(text) for p in pats):
                bad.append(os.path.relpath(path, HERE))
    check("packet privacy (paths, host name, secrets)", not bad, ", ".join(bad[:5]))
    return pats


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def check_git(repo, pats, first_lock):
    prov = json.load(open(os.path.join(HERE, "provenance.json"), encoding="utf-8"))
    for line in open(os.path.join(RAW, "replay.txt"), encoding="utf-8"):
        m = re.match(r"(\w+) -> (\w+) patchid_orig=(\w+) patchid_new=(\w+) equal=yes", line)
        check(f"replay line parses: {line[:20]}", m is not None)
        if not m:
            continue
        for sha, pid in ((m.group(1), m.group(3)), (m.group(2), m.group(4))):
            show = subprocess.run(["git", "-C", repo, "show", sha], capture_output=True, check=True).stdout
            got = subprocess.run(["git", "patch-id", "--stable"], input=show, capture_output=True,
                                 check=True).stdout.decode().split()[0]
            check(f"patch-id {sha}", got == pid)
    base = prov["shas"]["upstream_base"]
    head = prov["shas"]["packet_head_at_verification"] if "packet_head_at_verification" in prov["shas"] else "HEAD"
    commits = git(repo, "rev-list", f"{base}..{head}").split()
    check("lane commits found (14 replayed + F7 + PREREG + packet)", len(commits) >= 16, str(len(commits)))
    for c in commits:
        text = git(repo, "show", "--format=%an <%ae>%n%cn <%ce>%n%B", c)
        hit = [p.pattern for p in pats if p.search(text)]
        check(f"privacy commit {c[:9]}", not hit, str(hit))
    for k in ("F5m", "F6m", "F7m", "prereg"):
        check(f"commit {k} exists", git(repo, "cat-file", "-t", prov["shas"][k]).strip() == "commit")
    t = git(repo, "show", "-s", "--format=%cI", prov["shas"]["prereg"]).strip()
    pre = datetime.fromisoformat(t)
    check("PREREG committed before the first counted lock acquisition", first_lock and pre < first_lock,
          f"{pre} vs {first_lock}")
    files = git(repo, "show", "--name-only", "--format=", prov["shas"]["F7"]).split()
    check("F7 touches only platform-linux sources", all(f.startswith("libs/cua-driver/rust/crates/platform-linux/src/")
                                                         for f in files), str(files))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--git")
    args = parser.parse_args()
    prov = json.load(open(os.path.join(HERE, "provenance.json"), encoding="utf-8"))
    for arm in ("F5m", "F6m", "F7m"):
        ARM_SHA[arm] = prov["binaries"][arm]["sha256"]
    names = []
    if os.environ.get("CUA_PRIVACY_NAMES_FILE"):
        names = [l.strip() for l in open(os.environ["CUA_PRIVACY_NAMES_FILE"]) if l.strip()]
    re_ = regrade()
    check_summary(re_)
    check_dispositions(re_)
    first_lock = check_plan_and_locks()
    check_manifest()
    check_units()
    pats = check_privacy_packet(names)
    if args.git:
        check_git(args.git, pats, first_lock)
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"FAIL {name} {detail}")
    print(f"{len(RESULTS)} checks, {len(failed)} failed")
    print("RESULT", "PASS" if not failed else "FAIL")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
