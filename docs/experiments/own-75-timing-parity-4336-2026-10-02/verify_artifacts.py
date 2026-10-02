#!/usr/bin/env python3
"""Recompute every OWN-75 result from raw/ and check the evidence rules (stdlib only).

usage: python3 verify_artifacts.py            (from anywhere inside the worktree; run it under bin/hostless)

Checks, each printed PASS/FAIL:
  unit        test counts, skips and exit codes per arm from raw/unit; the head-only test identities
              are exactly the PR's 2 Python + 2 TypeScript parity tests; nothing fails at either arm
  mutation    raw/mutation rows agree with their logs; both none rows pass; M1/M2 detected in both
              languages (PREREG gate); all 16 M1..M8 rows detected (amendment-1 gate)
  real        analyze.py recomputed from raw/real equals own-75-summary.json; 160 trials in plan order,
              40 per cell, 10 AB + 10 BA pairs per cell, oracle 40/40 per cell, one primary digest per
              cell (20/20 head, 20/20 m0); S2 field checks on every step
  guard       network guard armed in every trial, 0 refusals in trials, self-test pass in every block
  comparator  the normalization discriminates (a non-timing edit changes the digest, a timing edit
              does not)
  ledger      every block: one acquired/released pair in raw/real/lock-ledger.jsonl (exclusive, <= 10
              trials, rc 0) nested inside its quiet-timed receipt (raw/real/quiet-lane-ledger-excerpt),
              and every trial of the block inside the pair
  session     every block saw Driver telemetry disabled, private DISPLAY + AT-SPI bus, no Wayland,
              Hyprland or provider key
  provenance  Driver sha256 equal at start and end and to the pinned value; one Driver version in every
              block; PR head equal at start and end
  prereg      PREREG.json committed once (cd1878872) and unchanged; PREREG-AMENDMENT-1.json committed once,
              unchanged, before the reported unit run, the mutation run and the first REAL trial; the
              branch is the PR head plus packet-only commits
  privacy     no absolute local path, host name or credential-like string in the packet files or in any
              commit of the branch since the PR head
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
import summarize  # noqa: E402

PR_HEAD = "8391cf80275d2a5e7288f9d7c6b0a3e5f7822939"
M0 = "2ca90d33857fdb4813ecc8d12c2058be7d4ebcc4"
PREREG_COMMIT = "cd18788725090377d64347235cb31ce628d9d796"
DRIVER_SHA256 = "8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3"
REL = "docs/experiments/own-75-timing-parity-4336-2026-10-02"
NEW_PY = {"test_form_task_reports_common_fields_without_a_visual_parse",
          "test_visual_fallback_reports_parse_only_visual_time_and_both_observations"}
NEW_TS = {"form task reports common fields without a visual parse",
          "visual fallback reports parse-only visual time and both observations"}
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")


def ts(value: str) -> datetime:
    value = value.rstrip("Z")
    if "." in value:
        head, frac = value.split(".")
        value = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(value)


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify_unit() -> None:
    unit = HERE / "raw/unit"
    py_ids, ts_ids, trees = {}, {}, {}
    for arm in ("head", "m0"):
        rc = json.loads((unit / f"{arm}-rc.json").read_text())
        py = (unit / f"{arm}-python-unittest.log").read_text()
        tsl = (unit / f"{arm}-ts-test.log").read_text()
        ran = int(re.search(r"^Ran (\d+) tests", py, re.M).group(1))
        ok = re.search(r"^OK(?: \(skipped=(\d+)\))?$", py, re.M)
        skipped = re.findall(r"^(test_\S+) \(.*\) \.\.\. skipped '([^']*)'", py, re.M)
        failed_py = re.findall(r"^(test_\S+) \(.*\) \.\.\. (?:FAIL|ERROR)$", py, re.M)
        counts = {k: int(re.search(rf"^# {k} (\d+)$", tsl, re.M).group(1)) for k in ("tests", "pass", "fail", "skipped")}
        py_ids[arm] = set(re.findall(r"^(test_\S+) \(", py, re.M))
        ts_ids[arm] = set(re.sub(r"^(?:not )?ok \d+ - ", "", line) for line in tsl.splitlines()
                          if re.match(r"^(?:not )?ok \d+ - ", line))
        codes = {k: v for k, v in rc.items() if k not in ("arm", "head", "jev_use_tree", "jev_use_dirty")}
        trees[arm] = (rc["jev_use_tree"], rc["jev_use_dirty"])
        check(f"unit[{arm}] all 7 commands rc 0", len(codes) == 7 and all(v == 0 for v in codes.values()),
              json.dumps(codes, sort_keys=True))
        check(f"unit[{arm}] python OK", bool(ok) and not failed_py, f"ran {ran}, skipped {skipped}")
        check(f"unit[{arm}] ts 0 fail", counts["fail"] == 0 and counts["pass"] == counts["tests"], json.dumps(counts))
    check("unit head-only python tests == PR parity tests", py_ids["head"] - py_ids["m0"] == NEW_PY
          and not (py_ids["m0"] - py_ids["head"]), str(sorted(py_ids["head"] - py_ids["m0"])))
    check("unit head-only ts tests == PR parity tests", ts_ids["head"] - ts_ids["m0"] == NEW_TS
          and not (ts_ids["m0"] - ts_ids["head"]), str(sorted(ts_ids["head"] - ts_ids["m0"])))
    check("unit tested jev-use trees (clean)", trees["head"] == ("f3ba27c40253d00cd235ca001bdae72357300f6c", "0")
          and trees["m0"] == ("635a4f588c6817ccb6cb6f5b7baacddbfc42f786", "0"), json.dumps(trees))


def verify_mutation() -> None:
    rows = jsonl(HERE / "raw/mutation/mutations.jsonl")
    detected = {}
    for row in rows:
        log = (HERE / f"raw/mutation/{row['id']}.log").read_text()
        if row["language"] == "python":
            log_failed = bool(re.search(r"^FAILED", log, re.M))
            log_ok = bool(re.search(r"^OK", log, re.M))
            # a dropped field surfaces as KeyError where the parity test indexes it (M2, M4)
            assertion = (("AssertionError" in log or "KeyError" in log)
                         and not re.search(r"SyntaxError|ImportError|ModuleNotFoundError|NameError", log))
        else:
            fail = int(re.search(r"^# fail (\d+)$", log, re.M).group(1))
            log_failed, log_ok = fail > 0, fail == 0
            assertion = "ERR_ASSERTION" in log or "AssertionError" in log
        consistent = row["applied"] and (log_failed if row["rc"] != 0 else log_ok)
        check(f"mutation {row['id']} applied once, log consistent"
              + (", failure is a test assertion (not a load error)" if row["rc"] != 0 else ""),
              consistent and (assertion if row["rc"] != 0 else True), f"rc {row['rc']}")
        detected[row["id"]] = row["rc"] != 0
    check("mutation 18 rows (2 none + 16 mutants)", len(rows) == 18 and len(detected) == 18)
    for lang in ("py", "ts"):
        check(f"mutation none-{lang} passes (positive control)", detected.get(f"none-{lang}") is False)
        for m in ("M1-decision-boundary", "M2-drop-act_ms"):
            check(f"mutation PREREG GATE {m}-{lang} detected", detected.get(f"{m}-{lang}") is True)
    mutants = {k: v for k, v in detected.items() if not k.startswith("none")}
    check("mutation AMENDMENT GATE all 16 mutants detected", len(mutants) == 16 and all(mutants.values()),
          f"{sum(mutants.values())}/16")


def verify_real() -> dict:
    real = HERE / "raw/real"
    fresh = analyze.analyze(real)
    stored = json.loads((HERE / "own-75-summary.json").read_text())
    check("real analysis recomputes to the stored summary", fresh == stored["real_analysis"])
    contract = summarize.field_contract(real)
    check("real field contract recomputes to the stored summary", contract == stored["field_contract"])
    records = jsonl(real / "trials.jsonl")
    plan = [t for p in sorted((real / "plan").glob("block-*.json")) for t in json.loads(p.read_text())]
    check("real trials == plan (ids, order), 160 trials, 16 blocks",
          [r["trial_id"] for r in records] == [t["trial_id"] for t in plan] and len(plan) == 160
          and len(list((real / "plan").glob("block-*.json"))) == 16, f"{len(records)} trials")
    check("real 0 harness errors, runner rc 0 everywhere",
          not any(r.get("harness_error") for r in records) and all(r.get("runner_rc") == 0 for r in records))
    pairs = defaultdict(list)
    for t in plan:
        pairs[(t["runner"], t["task"])].append(t["pair_order"])
    for cell, orders in sorted(pairs.items()):
        c = Counter(orders)
        check(f"real {cell} 10 AB + 10 BA pairs", c == Counter({"AB": 20, "BA": 20}), json.dumps(c))
    check("real 4 cells", len(fresh["cells"]) == 4)
    for cell, c in sorted(fresh["cells"].items()):
        check(f"real GATE {cell} n 20+20, oracle 40/40", c["n_head"] == 20 and c["n_m0"] == 20
              and c["verified_head"] == 20 and c["verified_m0"] == 20)
        check(f"real GATE {cell} one primary digest (20/20 head, 20/20 m0)", c["primary_identical_all"]
              and c["head_matching_reference"] == 20 and c["m0_matching_reference"] == 20,
              f"distinct {c['distinct_primary_digests']}")
        check(f"real {cell} head carries all PR fields on every trial", c["head_trials_with_all_pr_fields"] == 20)
        check(f"real {cell} head carries decide_ms, act_ms, observation.observe_ms", c["head_trials_with_all_legacy_fields"] == 20)
        check(f"real {cell} m0 carries the same legacy fields and no PR field (discriminating)",
              c["legacy_fields_m0"] == c["legacy_fields_head"] and c["pr_fields_on_steps_m0"] == [])
        check(f"real {cell} visual_observe_scope == parse_only", c["visual_observe_scope_values_head"] == ["parse_only"])
    h, m = contract["head"], contract["m0"]
    check("real S2 every head step: 7 common fields + scope parse_only + aliases + legacy fields",
          h["steps"] > 0 and h["all_common"] == h["scope_parse_only"] == h["alias_provider"] == h["alias_action"]
          == h["legacy_all"] == h["steps"], json.dumps({k: v for k, v in h.items() if k != "visual_status"}))
    check("real S2 parse_ms == visual_observe_ms whenever parse_ms is present",
          h["parse_ms_present"] == h["parse_ms_equal_visual"], f"{h['parse_ms_present']} steps with parse_ms")
    check("real S2 every m0 step: legacy fields, no common field or scope",
          m["steps"] > 0 and m["legacy_all"] == m["steps"] and m["any_common_or_scope"] == 0, json.dumps(m))
    check("real S2 step counts equal between arms", h["steps"] == m["steps"], f"{h['steps']} vs {m['steps']}")
    return fresh


def verify_guard(fresh: dict) -> None:
    check("guard armed in every trial", fresh["netguard_armed_trials"] == fresh["trials"] == 160)
    check("guard 0 refusals in trials (no non-loopback connect attempted by a runner)", fresh["netguard_refused_total"] == 0)
    metas = sorted((HERE / "raw/real/blocks").glob("*/meta.json"))
    check("guard 16 block metas", len(metas) == 16)
    for meta_path in metas:
        meta = json.loads(meta_path.read_text())
        check(f"guard self-test {meta['block']} refused 2/2, no Wayland, no provider key",
              meta["guard_self_test"]["pass"] is True and meta["typesafe_key_present"] is False
              and meta["wayland_display_set"] is False and meta["display_set"] is True
              and meta["at_spi_bus_set"] is True and meta["failures"] == 0, meta["driver_version"])


def verify_comparator() -> None:
    real = HERE / "raw/real"
    record = jsonl(real / "trials.jsonl")[0]
    primary, _, _ = analyze.build_traces(real / "trials" / record["trial_id"], record)
    base = analyze.digest(primary)
    step = next(i for i, e in enumerate(primary["events"]) if e.get("event") == "step")
    changed = copy.deepcopy(primary)
    changed["events"][step]["candidate"] = changed["events"][step]["candidate"] + "-x"
    check("comparator: a changed candidate changes the digest", analyze.digest(changed) != base)
    changed = copy.deepcopy(primary)
    call = next(r for r in changed["requests"] if r.get("tool") not in (None, "get_window_state", "list_windows"))
    call["arguments"]["delivery_mode"] = "foreground-x"
    check("comparator: a changed action argument changes the digest", analyze.digest(changed) != base)
    changed = copy.deepcopy(primary)
    changed["oracle_state"] = {**changed["oracle_state"], "seq": -1}
    check("comparator: a changed oracle state changes the digest", analyze.digest(changed) != base)
    events = analyze.load_jsonl_gz(real / "trials" / record["trial_id"] / "events.jsonl.gz")
    start = next(e for e in events if e.get("event") == "start")
    norm = analyze.Normalizer(start["pid"], start["window_id"])
    timed = copy.deepcopy(events)
    for e in timed:
        if e.get("event") == "step":
            e["decision_ms"] = 123456.0
            e["total_step_ms"] = 7.0
            e["act_ms"] = 1.0
            e.pop("visual_observe_scope", None)
    check("comparator: changed/removed timing fields leave the digest unchanged", norm(timed) == norm(events))


def verify_ledger() -> None:
    real = HERE / "raw/real"
    ledger = jsonl(real / "lock-ledger.jsonl")
    excerpt = {e["label"]: e for e in jsonl(real / "quiet-lane-ledger-excerpt.jsonl")}
    records = jsonl(real / "trials.jsonl")
    by_block = defaultdict(list)
    for entry in ledger:
        by_block[entry["block"]].append(entry)
    ok, nested = True, True
    for block, entries in sorted(by_block.items()):
        events = [e["event"] for e in entries]
        ok &= events == ["acquired", "released"] and all(e["mode"] == "exclusive" and e["trials"] <= 10 for e in entries)
        ok &= entries[1].get("rc") == 0
        lo, hi = ts(entries[0]["utc"]), ts(entries[1]["utc"])
        receipt = excerpt.get(f"own75r-{block}")
        nested &= receipt is not None and receipt["rc"] == 0 and ts(receipt["acquired"]) <= lo and hi <= ts(receipt["released"])
        for r in records:
            if r["block"] == block:
                ok &= lo <= ts(r["start_utc"]) and ts(r["end_utc"]) <= hi
    check("ledger: one exclusive acquired/released pair per block, <= 10 trials, rc 0, every trial inside",
          ok and len(by_block) == 16, f"{len(by_block)} blocks")
    check("ledger: every pair nested inside its quiet-timed receipt (shared quiet-lane ledger)",
          nested and len(excerpt) == 16, f"{len(excerpt)} receipts")
    spans = sorted((ts(e["acquired"]), ts(e["released"])) for e in excerpt.values())
    longest = max((b - a).total_seconds() for a, b in spans)
    check("ledger: every lock chunk <= 15 minutes", longest <= 900, f"longest {longest:.0f} s")


def verify_session() -> None:
    envs = sorted((HERE / "raw/real/session-env").glob("*.json"))
    good = 0
    for path in envs:
        e = json.loads(path.read_text())
        good += (e["CUA_DRIVER_RS_TELEMETRY_ENABLED"] == "0" and e["DO_NOT_TRACK"] == "1" and e["CUA_SESSION_ATSPI"] == "1"
                 and e["DISPLAY_set"] is True and e["AT_SPI_BUS_ADDRESS_set"] is True and e["WAYLAND_DISPLAY_set"] is False
                 and e["HYPRLAND_INSTANCE_SIGNATURE_set"] is False and e["TYPESAFE_API_KEY_set"] is False)
    check("session: 16/16 blocks with telemetry off, private DISPLAY + AT-SPI, no Wayland/Hyprland/provider key",
          len(envs) == 16 and good == 16, f"{good}/{len(envs)}")


def verify_provenance() -> None:
    prov = HERE / "raw/provenance"
    hashes = [(prov / f"driver-sha256-{w}.txt").read_text().split()[0] for w in ("start", "end")]
    check("provenance: Driver sha256 start == end == pinned", hashes == [DRIVER_SHA256, DRIVER_SHA256], hashes[1][:16])
    versions = {json.loads(p.read_text())["driver_version"] for p in (HERE / "raw/real/blocks").glob("*/meta.json")}
    check("provenance: one Driver version in every block", len(versions) == 1, str(sorted(versions)))
    heads = [json.loads((prov / f"pr-head-{w}.json").read_text())["headRefOid"] for w in ("start", "end")]
    check("provenance: trycua/cua PR 4336 head start == end == tested", heads == [PR_HEAD, PR_HEAD])
    doc = json.loads((HERE / "provenance.json").read_text())
    check("provenance.json names the tested SHAs and binary", doc["pr_head"] == PR_HEAD and doc["m0"] == M0
          and doc["driver"]["sha256"] == DRIVER_SHA256 and doc["prereg_commit"] == PREREG_COMMIT)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout


def commit_utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(timezone.utc).replace(tzinfo=None)


def verify_prereg() -> None:
    rel = f"{REL}/PREREG.json"
    commits = [c for c in git("log", "--format=%H %cI", "--", rel).splitlines() if c.strip()]
    check("prereg: PREREG.json committed once (cd1878872) and unchanged since", len(commits) == 1
          and commits[0].split()[0] == PREREG_COMMIT and git("diff", PREREG_COMMIT, "--", rel) == ""
          and git("status", "--porcelain", "--", rel) == "")
    rel_a = f"{REL}/PREREG-AMENDMENT-1.json"
    acommits = [c for c in git("log", "--format=%H %cI", "--", rel_a).splitlines() if c.strip()]
    asha, atime = acommits[-1].split()
    check("prereg: PREREG-AMENDMENT-1.json committed once and unchanged since", len(acommits) == 1
          and git("diff", asha, "--", rel_a) == "" and git("status", "--porcelain", "--", rel_a) == "", asha[:12])
    amended = commit_utc(atime)
    records = jsonl(HERE / "raw/real/trials.jsonl")
    first_trial = min(ts(r["start_utc"]) for r in records)
    unit_start = ts((HERE / "raw/unit/run-utc.txt").read_text().split()[0])
    mut_start = ts((HERE / "raw/mutation/run-utc.txt").read_text().split()[0])
    check("prereg: amendment committed before the unit run, the mutation run and the first REAL trial",
          amended < unit_start and amended < mut_start and amended < first_trial,
          f"amendment {amended.isoformat()}Z, unit {unit_start.isoformat()}Z, mutation {mut_start.isoformat()}Z, "
          f"first trial {first_trial.isoformat()}Z")
    written = json.loads((HERE / "PREREG-AMENDMENT-1.json").read_text())["written_utc"]
    check("prereg: amendment written_utc not later than its commit",
          datetime.fromisoformat(written.rstrip("Z")) <= amended, f"{written} vs {amended.isoformat()}Z")
    changed = git("diff", "--name-only", PR_HEAD, "HEAD").split()
    check("prereg: branch = PR head + packet-only commits",
          git("merge-base", "--is-ancestor", PR_HEAD, "HEAD") == "" and changed != []
          and all(p.startswith(f"{REL}/") for p in changed), f"{len(changed)} packet files")


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
    verify_session()
    verify_provenance()
    verify_prereg()
    verify_privacy()
    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    for name in failed:
        print("FAILED:", name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
