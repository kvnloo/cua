#!/usr/bin/env python3
"""Recompute every OWN-75 result from raw/ and check the evidence rules (stdlib only).

usage: python3 verify_artifacts.py            (from anywhere; run it under bin/hostless)

Checks, each printed PASS/FAIL:
  unit       test counts, skips and exit codes per arm from raw/unit; head-only test identities are
             exactly the PR's 2 Python + 2 TypeScript parity tests; nothing fails at head
  mutation   raw/mutation/mutations.jsonl rows agree with their logs; none rows pass; M1..M8 detected
  real       analyze.py recomputed from raw/real equals own-75-summary.json; 160 trials, 40 per cell,
             10 AB + 10 BA pairs per cell, oracle verified, one primary digest per cell, field checks
  guard      network guard armed in every trial, 0 refusals in trials, self-test pass in every block
  comparator the normalization discriminates (a non-timing edit changes the digest, a timing edit
             does not)
  ledger     every block has one shared acquisition with <= 10 trials and every trial lies inside it
  prereg     PREREG.json was committed before the first REAL trial and before the reported unit run,
             and is unchanged since that commit
  privacy    no absolute local path, host name or credential-like string in the packet files or in
             any commit of the branch since the PR head
"""

from __future__ import annotations

import copy
import gzip
import json
import re
import socket
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402

PR_HEAD = "8391cf80275d2a5e7288f9d7c6b0a3e5f7822939"
M0 = "2ca90d33857fdb4813ecc8d12c2058be7d4ebcc4"
NEW_PY = {"test_form_task_reports_common_fields_without_a_visual_parse",
          "test_visual_fallback_reports_parse_only_visual_time_and_both_observations"}
NEW_TS = {"form task reports common fields without a visual parse",
          "visual fallback reports parse-only visual time and both observations"}
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")


def ts(value: str) -> datetime:
    value = value.rstrip("Z")
    if "." in value:
        head, frac = value.split(".")
        value = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(value)


def verify_unit() -> dict:
    unit = HERE / "raw/unit"
    out = {}
    py_ids, ts_ids = {}, {}
    for arm in ("head", "m0"):
        rc = json.loads((unit / f"{arm}-rc.json").read_text())
        py = (unit / f"{arm}-python-unittest.log").read_text()
        tsl = (unit / f"{arm}-ts-test.log").read_text()
        ran = int(re.search(r"^Ran (\d+) tests", py, re.M).group(1))
        ok = re.search(r"^OK(?: \(skipped=(\d+)\))?$", py, re.M)
        skipped = [m.group(1) for m in re.finditer(r"^(test_\S+) \(.*\) \.\.\. skipped", py, re.M)]
        failed_py = re.findall(r"^(test_\S+) \(.*\) \.\.\. (?:FAIL|ERROR)$", py, re.M)
        counts = {k: int(re.search(rf"^# {k} (\d+)$", tsl, re.M).group(1)) for k in ("tests", "pass", "fail", "skipped")}
        py_ids[arm] = set(re.findall(r"^(test_\S+) \(", py, re.M))
        ts_ids[arm] = set(re.sub(r"^(?:not )?ok \d+ - ", "", line) for line in tsl.splitlines()
                          if re.match(r"^(?:not )?ok \d+ - ", line))
        out[arm] = {"python_ran": ran, "python_ok": bool(ok), "python_skipped": skipped,
                    "python_failed": failed_py, "ts": counts,
                    "rc": {k: v for k, v in rc.items() if k not in ("arm", "head", "jev_use_tree", "jev_use_dirty")},
                    "jev_use_tree": rc["jev_use_tree"], "jev_use_dirty": rc["jev_use_dirty"]}
        check(f"unit[{arm}] all commands rc 0", all(v == 0 for v in out[arm]["rc"].values()), json.dumps(out[arm]["rc"]))
        check(f"unit[{arm}] python OK", bool(ok) and not failed_py, f"ran {ran}, skipped {skipped}")
        check(f"unit[{arm}] ts 0 fail", counts["fail"] == 0 and counts["pass"] == counts["tests"], json.dumps(counts))
    check("unit head-only python tests == PR parity tests", py_ids["head"] - py_ids["m0"] == NEW_PY
          and not (py_ids["m0"] - py_ids["head"]), str(sorted(py_ids["head"] - py_ids["m0"])))
    check("unit head-only ts tests == PR parity tests", ts_ids["head"] - ts_ids["m0"] == NEW_TS
          and not (ts_ids["m0"] - ts_ids["head"]), str(sorted(ts_ids["head"] - ts_ids["m0"])))
    check("unit tested trees", out["head"]["jev_use_tree"] == "f3ba27c40253d00cd235ca001bdae72357300f6c"
          and out["m0"]["jev_use_tree"] == "635a4f588c6817ccb6cb6f5b7baacddbfc42f786"
          and out["head"]["jev_use_dirty"] == "0" and out["m0"]["jev_use_dirty"] == "0")
    return out


def verify_mutation() -> dict:
    rows = [json.loads(line) for line in (HERE / "raw/mutation/mutations.jsonl").read_text().splitlines()]
    detected = {}
    for row in rows:
        log = (HERE / f"raw/mutation/{row['id']}.log").read_text()
        if row["language"] == "python":
            log_failed = bool(re.search(r"^FAILED", log, re.M))
            log_ok = bool(re.search(r"^OK", log, re.M))
        else:
            fail = int(re.search(r"^# fail (\d+)$", log, re.M).group(1))
            log_failed, log_ok = fail > 0, fail == 0
        consistent = row["applied"] and (log_failed if row["rc"] != 0 else log_ok)
        check(f"mutation {row['id']} log consistent", consistent, f"rc {row['rc']}")
        detected[row["id"]] = row["rc"] != 0
    for lang in ("py", "ts"):
        check(f"mutation none-{lang} passes (positive control)", detected.get(f"none-{lang}") is False)
        for m in ("M1-decision-boundary", "M2-drop-act_ms"):
            check(f"mutation GATE {m}-{lang} detected", detected.get(f"{m}-{lang}") is True)
    others = {k: v for k, v in detected.items() if not k.startswith(("none", "M1", "M2"))}
    check("mutation M3..M8 detected (reported)", all(others.values()), json.dumps(others, sort_keys=True))
    return {"rows": len(rows), "detected": detected}


def verify_real() -> dict:
    real = HERE / "raw/real"
    fresh = analyze.analyze(real)
    stored = json.loads((HERE / "own-75-summary.json").read_text())["real_analysis"]
    check("real analysis recomputes to the stored summary", fresh == stored)
    records = [json.loads(line) for line in (real / "trials.jsonl").read_text().splitlines()]
    plan = [t for p in sorted((real / "plan").glob("block-*.json")) for t in json.loads(p.read_text())]
    check("real trials == plan (ids, order)", [r["trial_id"] for r in records] == [t["trial_id"] for t in plan],
          f"{len(records)} trials")
    pairs = defaultdict(list)
    for t in plan:
        pairs[(t["runner"], t["task"])].append(t["pair_order"])
    for cell, orders in sorted(pairs.items()):
        c = Counter(orders)
        check(f"real {cell} 10 AB + 10 BA pairs", c == Counter({"AB": 20, "BA": 20}), json.dumps(c))
    for cell, c in sorted(fresh["cells"].items()):
        check(f"real GATE {cell} n 20+20, oracle 40/40", c["n_head"] == 20 and c["n_m0"] == 20
              and c["verified_head"] == 20 and c["verified_m0"] == 20)
        check(f"real GATE {cell} one primary digest (20/20 head, 20/20 m0)", c["primary_identical_all"]
              and c["head_matching_reference"] == 20 and c["m0_matching_reference"] == 20,
              f"distinct {c['distinct_primary_digests']}")
        check(f"real {cell} head carries all PR fields on every step", c["head_trials_with_all_pr_fields"] == 20)
        check(f"real {cell} head carries decide_ms, act_ms, observation.observe_ms", c["head_trials_with_all_legacy_fields"] == 20)
        check(f"real {cell} m0 carries the same legacy fields and no PR field", c["legacy_fields_m0"] == c["legacy_fields_head"]
              and c["pr_fields_on_steps_m0"] == [])
        check(f"real {cell} visual_observe_scope == parse_only", c["visual_observe_scope_values_head"] == ["parse_only"])
    aliases_ok, parse_ok = True, True
    for r in records:
        if r["arm"] != "head":
            continue
        events = analyze.load_jsonl_gz(real / "trials" / r["trial_id"] / "events.jsonl.gz")
        for e in events:
            if e.get("event") != "step":
                continue
            aliases_ok &= e["provider_decision_ms"] == e["decide_ms"] and e["action_ms"] == e["act_ms"]
            if "parse_ms" in e.get("visual", {}):
                parse_ok &= e["visual"]["parse_ms"] == e["visual_observe_ms"]
            parse_ok &= e["visual"].get("status") != "skipped" or e["visual_observe_ms"] == 0
    check("real head alias equalities on every step", aliases_ok)
    check("real head visual_observe_ms is 0 when no parse ran / == parse_ms", parse_ok)
    return fresh


def verify_guard(fresh: dict) -> None:
    check("guard armed in every trial", fresh["netguard_armed_trials"] == fresh["trials"])
    check("guard 0 refusals in trials (no non-loopback connect attempted)", fresh["netguard_refused_total"] == 0)
    for meta_path in sorted((HERE / "raw/real/blocks").glob("*/meta.json")):
        meta = json.loads(meta_path.read_text())
        check(f"guard self-test {meta['block']} refused 2/2", meta["guard_self_test"]["pass"] is True
              and meta["typesafe_key_present"] is False and meta["wayland_display_set"] is False,
              meta["driver_version"])


def verify_comparator() -> None:
    real = HERE / "raw/real"
    record = json.loads((real / "trials.jsonl").read_text().splitlines()[0])
    primary, _, _ = analyze.build_traces(real / "trials" / record["trial_id"], record)
    base = analyze.digest(primary)
    step = next(i for i, e in enumerate(primary["events"]) if e.get("event") == "step")
    changed = copy.deepcopy(primary)
    changed["events"][step]["candidate"] = changed["events"][step]["candidate"] + "-x"
    check("comparator: a changed candidate changes the digest", analyze.digest(changed) != base)
    changed = copy.deepcopy(primary)
    call = next(r for r in changed["requests"] if r.get("tool") == "click")
    call["arguments"]["delivery_mode"] = "foreground"
    check("comparator: a changed request argument changes the digest", analyze.digest(changed) != base)
    events = analyze.load_jsonl_gz(real / "trials" / record["trial_id"] / "events.jsonl.gz")
    start = next(e for e in events if e.get("event") == "start")
    norm = analyze.Normalizer(start["pid"], start["window_id"])
    timed = copy.deepcopy(events)
    for e in timed:
        if e.get("event") == "step":
            e["decision_ms"] = 123456.0
            e["total_step_ms"] = 7.0
            e["act_ms"] = 1.0
    check("comparator: changed timing values leave the digest unchanged", norm(timed) == norm(events))


def verify_ledger() -> None:
    ledger = [json.loads(line) for line in (HERE / "raw/real/lock-ledger.jsonl").read_text().splitlines()]
    records = [json.loads(line) for line in (HERE / "raw/real/trials.jsonl").read_text().splitlines()]
    by_block = defaultdict(list)
    for entry in ledger:
        by_block[entry["block"]].append(entry)
    ok = True
    for block, entries in by_block.items():
        events = [e["event"] for e in entries]
        ok &= events == ["acquired", "released"] and all(e["mode"] == "shared" and e["trials"] <= 10 for e in entries)
        lo, hi = ts(entries[0]["utc"]), ts(entries[1]["utc"])
        for r in records:
            if r["block"] == block:
                ok &= lo <= ts(r["start_utc"]) and ts(r["end_utc"]) <= hi
    check("ledger: one shared acquisition per block, <= 10 trials, every trial inside its acquisition",
          ok and len(by_block) == 16, f"{len(by_block)} blocks")


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout


def verify_prereg() -> None:
    rel = "docs/experiments/own-75-timing-parity-4336-2026-10-02/PREREG.json"
    commits = [c for c in git("log", "--format=%H %cI", "--", rel).splitlines() if c.strip()]
    first_sha, first_time = commits[-1].split()
    check("prereg: PREREG.json committed once and unchanged since", len(commits) == 1
          and git("diff", first_sha, "--", rel) == "" and git("status", "--porcelain", "--", rel) == "")
    prereg_utc = datetime.fromisoformat(first_time).astimezone(timezone.utc).replace(tzinfo=None)
    records = [json.loads(line) for line in (HERE / "raw/real/trials.jsonl").read_text().splitlines()]
    first_trial = min(ts(r["start_utc"]) for r in records)
    unit_start = ts((HERE / "raw/unit/run-utc.txt").read_text().split()[0])
    check("prereg: committed before the first REAL trial and before the reported unit run",
          prereg_utc < first_trial and prereg_utc < unit_start,
          f"prereg {prereg_utc.isoformat()}Z, unit {unit_start.isoformat()}Z, first trial {first_trial.isoformat()}Z")
    changed = git("diff", "--name-only", PR_HEAD, "HEAD").split()
    check("prereg: branch = PR head + packet-only commits",
          git("merge-base", "--is-ancestor", PR_HEAD, "HEAD") == "" and changed != []
          and all(p.startswith("docs/experiments/own-75-timing-parity-4336-2026-10-02/") for p in changed),
          f"{len(changed)} packet files")


PRIVACY_PATTERNS = [
    re.compile(r"/home/[A-Za-z0-9_.-]+"), re.compile(r"/mnt/[A-Za-z0-9_.-]+"), re.compile(r"/tmp/[A-Za-z0-9_.-]+"),
    re.compile(r"/Users/[A-Za-z0-9_.-]+"), re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|authorization|bearer)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}"),
]


def privacy_hits(text: str, host: str) -> list[str]:
    hits = [m.group(0) for p in PRIVACY_PATTERNS for m in p.finditer(text)]
    if host and len(host) > 2 and re.search(rf"\b{re.escape(host)}\b", text):
        hits.append("<hostname>")
    return hits


def verify_privacy() -> None:
    host = socket.gethostname()
    hits: dict[str, list[str]] = {}
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix == ".gz":
            text = gzip.open(path, "rt", encoding="utf-8", errors="replace").read()
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
        if path.name == "verify_artifacts.py":
            text = "\n".join(line for line in text.splitlines() if "re.compile(" not in line)
        found = privacy_hits(text, host)
        if found:
            hits[str(path.relative_to(HERE))] = sorted(set(found))[:5]
    check("privacy: packet files", not hits, json.dumps(hits)[:600])
    commit_hits = {}
    for sha in git("rev-list", f"{PR_HEAD}..HEAD").split():
        patch = git("show", "--format=%an %ae%n%B", sha)
        patch = "\n".join(line for line in patch.splitlines() if "re.compile(" not in line)
        for path in git("diff-tree", "--no-commit-id", "--name-only", "-r", sha).split():
            if path.endswith(".gz"):
                blob = subprocess.run(["git", "-C", str(HERE), "show", f"{sha}:{path}"], capture_output=True)
                if blob.returncode == 0:
                    patch += "\n" + gzip.decompress(blob.stdout).decode("utf-8", "replace")
        found = privacy_hits(patch, host)
        if found:
            commit_hits[sha[:12]] = sorted(set(found))[:5]
    check("privacy: every commit since the PR head (diffs, messages, gz blobs)", not commit_hits, json.dumps(commit_hits))


def main() -> int:
    verify_unit()
    verify_mutation()
    fresh = verify_real()
    verify_guard(fresh)
    verify_comparator()
    verify_ledger()
    verify_prereg()
    verify_privacy()
    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    for name in failed:
        print("FAILED:", name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
