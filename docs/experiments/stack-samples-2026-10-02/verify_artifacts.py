#!/usr/bin/env python3
"""Independent re-check of the stack-samples-2026-10-02 packet (stdlib only, no models, no network).

  python3 verify_artifacts.py            -> RESULT PASS | RESULT FAIL (exit 1)

Recomputes from committed data instead of trusting summaries:
  1  PREREG workload hash == workload/tasks.jsonl; oracle implementation hash == harness/workload.py
  2  dataset MANIFEST file hashes and content hash
  3  every task appears once in runs.jsonl; RUN tasks form a prefix of the preregistered order
     (no outcome-based skipping); NOT_RUN only for the deadline
  4  oracle verdicts re-derived from the committed run outputs == raw/collect/verdicts.jsonl == runs.jsonl
  5  api examples + join audit rebuilt from dataset/events.jsonl with the vendored #386 joiner
  6  turn examples: state recomputed from the turn's own observer rows, label == (oracle verdict is False)
  7  every scored file matches its examples one-to-one; evaluate_shadow re-run reproduces raw/eval/*
  8  analysis re-run (seeded) reproduces raw/analysis/*.json
  9  quiet-lane ledger has an rc=0 entry for every latency-bearing scoring label, all after collection ended
 10  per-run isolation receipts ok; no local path markers or secret-looking strings in the packet
 SAMPLESFIX (errata E2-E6):
 11  CUA attribution re-derived from the committed private-home agent.log/errors.log of every CUA run:
     0 completed tool calls, every error at tool_call, 0 computer_use dispatches, 0 approval lines,
     agent.log tool lines == observer pre/post_tool_call per run, GUI state unchanged, -t computer_use;
     the tally file reproduces; the README's BLOCKED section no longer lists CUA input tasks
 12  every GENERATED table in README.md is byte-identical to harness/make_tables.py output, and
     summary.json is byte-identical to a fresh harness/make_summary.py run
 13  MANIFEST counts recomputed from dataset/, MANIFEST identities == provenance identities, README and
     summary cite the MANIFEST content hash
 14  the lab unit-test log is committed and shows 25 passed / 2 skipped and 13 passed
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAIL: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def close(a, b, tol: float = 1e-9) -> bool:
    """Structural equality with float tolerance (Python 3.12+ sums floats with compensation, so the
    scorer venv's 3.11 and a newer verifier differ in the last bits)."""
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) <= tol * max(1.0, abs(a), abs(b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    return a == b


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    prereg = json.loads((HERE / "PREREG.json").read_text())
    tasks = jl(HERE / "workload" / "tasks.jsonl")
    check(sha(HERE / "workload" / "tasks.jsonl") == prereg["workload"]["tasks_sha256"], "1 workload hash matches PREREG")
    check(sha(HERE / "harness" / "workload.py") == prereg["oracle"]["implementation"].split("sha256 ")[1].rstrip(")"),
          "1 oracle implementation hash matches PREREG")

    ds = HERE / "dataset"
    manifest = json.loads((ds / "MANIFEST.json").read_text())
    check(all(sha(ds / n) == h for n, h in manifest["files"].items()), "2 MANIFEST file hashes")
    check(hashlib.sha256(json.dumps(manifest["files"], sort_keys=True).encode()).hexdigest() == manifest["content_sha256"],
          "2 MANIFEST content hash")
    check(manifest["workload"]["tasks_sha256"] == prereg["workload"]["tasks_sha256"], "2 MANIFEST workload hash == PREREG")

    runs = jl(ds / "runs.jsonl")
    check([r["task_id"] for r in runs] == [t["task_id"] for t in tasks], "3 runs.jsonl covers every task once, in order")
    status = [r["status"] for r in runs]
    n_run = status.count("RUN")
    check(status == ["RUN"] * n_run + ["NOT_RUN"] * (len(status) - n_run), "3 RUN tasks are a prefix of the preregistered order")
    check(all(r.get("reason") == "deadline" for r in runs if r["status"] != "RUN"), "3 NOT_RUN only for the deadline")

    wl = load("workload", HERE / "harness" / "workload.py")
    task_by_id = {t["task_id"]: t for t in tasks}
    verdicts = {v["task_id"]: v for v in jl(HERE / "raw" / "collect" / "verdicts.jsonl")}
    mismatch = []
    with tempfile.TemporaryDirectory() as tmp:
        for r in runs:
            if r["status"] != "RUN":
                continue
            src = HERE / "raw" / "runs" / r["run_id"]
            run = Path(tmp) / r["run_id"]
            (run / "meta").mkdir(parents=True)
            (run / "meta" / "stdout").write_text((src / "stdout").read_text() if (src / "stdout").exists() else "")
            if (src / "cwd").exists():
                import shutil
                shutil.copytree(src / "cwd", run / "cwd")
            if (src / "gui-state").exists():
                import shutil
                shutil.copytree(src / "gui-state", run / "meta" / "gui-state")
            got = wl.oracle(task_by_id[r["task_id"]], run)["verified_success"]
            if not (got == verdicts[r["task_id"]].get("verified_success") == r.get("verified_success")):
                mismatch.append(r["task_id"])
    check(not mismatch, f"4 oracle verdicts re-derived from committed outputs ({n_run} runs; mismatches {mismatch[:5]})")

    vendor = HERE / "harness" / "vendor"
    saf = load("shadow_api_failure_v", vendor / "shadow_api_failure.py")
    events = jl(ds / "events.jsonl")
    api = jl(HERE / "raw" / "examples" / "api-examples.jsonl")
    check(saf.joined_examples(events) == api, "5 api examples rebuilt from frozen events")
    check(saf.join_audit(events) == json.loads((HERE / "raw" / "examples" / "api-audit.json").read_text()), "5 api join audit rebuilt")

    bte = load("build_turn_examples_v", HERE / "harness" / "build_turn_examples.py")
    turn = jl(HERE / "raw" / "examples" / "turn-examples.jsonl")
    by_sid: dict = {}
    for e in events:
        by_sid.setdefault((e.get("identity") or {}).get("session_id"), []).append(e)
    run_by_task = {r["task_id"]: r for r in runs}
    bad = []
    for ex in turn:
        r = run_by_task[ex["identity"]["work_item_id"]]
        state, _ = bte.turn_state(by_sid.get(r.get("session_id"), []) if r.get("session_id") else [])
        label = None if r.get("verified_success") is None else (r["verified_success"] is False)
        if state != ex["request"]["state"] or label != ex["verified_outcome"]:
            bad.append(r["task_id"])
    check(len(turn) == n_run and not bad, f"6 turn examples: state + label recomputed ({len(turn)} examples; bad {bad[:5]})")
    forbidden = {"prompt", "family", "oracle", "task_id", "work_item_id", "verified_success", "reply"}
    check(not any(forbidden & set(ex["request"]["state"]) for ex in turn), "6 turn request state carries no prompt/family/oracle/task field")

    evs = load("evaluate_shadow_v", vendor / "evaluate_shadow.py")
    for lane, qid, exs in (("api", "api.attempt_will_fail", api), ("turn", "verification_needed", turn)):
        keys = [json.dumps(e["request"], sort_keys=True) for e in exs]
        for f in sorted((HERE / "raw" / "scored" / lane).glob("scored-*.jsonl")):
            rows = jl(f)
            check([json.dumps(r["request"], sort_keys=True) for r in rows] == keys, f"7 {lane}/{f.name} one-to-one with examples ({len(rows)})")
            want = json.loads((HERE / "raw" / "eval" / lane / f"eval-{f.stem.removeprefix('scored-')}.json").read_text())
            check(close(evs.evaluate(rows, question_id=qid), want), f"7 {lane}/{f.name} evaluate_shadow reproduces (floats to 1e-9)")

    with tempfile.TemporaryDirectory() as tmp:
        fake_wt = Path(tmp) / "wt" / "lab" / "z0_hermes_observer"
        fake_wt.mkdir(parents=True)
        (fake_wt / "evaluate_shadow.py").write_text((vendor / "evaluate_shadow.py").read_text())
        for lane, qid in (("api", "api.attempt_will_fail"), ("turn", "verification_needed")):
            out = Path(tmp) / f"{lane}.json"
            subprocess.run([sys.executable, str(HERE / "harness" / "analyze.py"), str(Path(tmp) / "wt"), qid,
                            str(HERE / "raw" / "examples" / f"{lane}-examples.jsonl"), str(HERE / "raw" / "scored" / lane),
                            str(ds / "runs.jsonl"), str(out)], check=True, capture_output=True)
            check(json.loads(out.read_text()) == json.loads((HERE / "raw" / "analysis" / f"{lane}-analysis.json").read_text()),
                  f"8 {lane} analysis reproduces")

    ledger = jl(HERE / "raw" / "quiet-lane-ledger.samples.jsonl")
    summary = json.loads((HERE / "summary.json").read_text())
    labels = summary.get("timed_labels", [])
    last_end = max(r["ended_at"] for r in runs if r["status"] == "RUN")
    ok = all(any(l["label"] == lab and l["rc"] == 0 and l["acquired"] > last_end for l in ledger) for lab in labels)
    check(bool(labels) and ok, f"9 ledger rc=0 for all {len(labels)} timed labels, after collection ended {last_end}")

    iso = [r for r in runs if r["status"] == "RUN"]
    head = manifest["identities"]["hermes"]["commit"]
    check(head.startswith(prereg["identities"]["hermes"]["commit"][:10])
          and all(r["worktree_head"] == head and r["worktree_clean"] for r in iso),
          f"10 every run executed hermes {head[:12]} with a clean worktree (PREREG short prefix; erratum E1 in provenance.json)")
    check(all(r["isolation"]["ok"] for r in iso), "10 mask receipts ok for every run (live home, real home, host runtime dir empty; GUI runs see only their private X socket)")
    changed = [(r["task_id"], c) for r in iso for c in r["isolation"]["live_home_changed_entries"]]
    declared = all(c["entry"] == "auth.json" and not c["size_changed"] for _, c in changed)
    check(declared, f"10 live-home file stats unchanged except declared mtime-only auth.json refreshes by the live Hermes "
                    f"({len(changed)} of {len(iso)} runs; see README)")
    env_checks = json.loads((HERE / "raw" / "env_checks.json").read_text())
    check(all(not v["live_path_or_secret_var_hits"] and v["hermes_home_in_run_dir"] for v in env_checks.values()), "10 env.inside: no live paths/secret vars; HERMES_HOME private")
    # Generic absolute-path pattern (run-relative "$RUN/home/..." is fine); extra private markers such as a
    # host name can be supplied locally via STACK_PRIVATE_MARKERS="a:b" without committing them.
    abs_path = re.compile(r"(?<![\w$}.~-])/(mnt|home|workspace|run/user|srv|opt)/[A-Za-z0-9]")
    markers = [m for m in os.environ.get("STACK_PRIVATE_MARKERS", "").split(":") if m]
    secret = re.compile(r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
    hits = []
    for p in HERE.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        text = p.read_text(errors="replace")
        if abs_path.search(text) or secret.search(text) or any(m in text for m in markers):
            hits.append(str(p.relative_to(HERE)))
    check(not hits, f"10 no absolute local paths / private markers ({len(markers)}) / secret-looking strings ({hits[:5]})")

    # 11 CUA attribution (erratum E2)
    cbt = load("cua_bridge_tally_v", HERE / "harness" / "cua_bridge_tally.py")
    tally = cbt.tally(HERE)
    check(tally == json.loads((HERE / "raw" / "analysis" / "cua-bridge-tally.json").read_text()),
          "11 cua-bridge-tally.json reproduces from committed logs, events, runs and tasks")
    cua_runs = [r for r in iso if r["kind"] == "cua"]
    tr, tt = tally["runs"], tally["totals"]
    check(len(tr) == len(cua_runs) == 12 and all((HERE / "raw" / "runs" / r["run_id"] / "agent.log").exists() for r in cua_runs),
          f"11 private-home agent.log committed for every CUA run ({len(tr)})")
    check(tt["tool_calls_completed"] == 0 and tt["tool_calls_failed"] == 0 and tt["tool_names_called"] == ["tool_call"]
          and tt["computer_use_dispatches"] == 0 and tt["runs_with_driver_or_computer_use_logger"] == 0,
          f"11 CUA: 0 completed tool calls, all {tt['tool_errors']} errors at tool_call {tt['tool_error_classes']}, 0 computer_use dispatches")
    check(tt["approval_lines"] == 0, "11 CUA: 0 approval / fail-close lines in agent.log, errors.log and replies")
    check(all(x["tool_errors"] == x["observer_pre_tool_call"] == x["observer_post_tool_call"] == x["tool_error_lines_errors_log"]
              and x["api_calls_agent_log"] == x["api_attempts_observer"] for x in tr),
          "11 CUA: agent.log tool lines == errors.log == observer pre/post_tool_call, and API calls == observer attempts, per run")
    check(tt["runs_gui_state_unchanged"] == tt["runs_argv_toolset_computer_use"] == len(tr),
          "11 CUA: GUI state unchanged and argv '-t computer_use' in every run")
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    blocked = readme.split("- **BLOCKED:**", 1)[1].split("\n## ", 1)[0] if "- **BLOCKED:**" in readme else ""
    check(bool(blocked) and "CUA" not in blocked, "11 README BLOCKED section does not list CUA input tasks (approval attribution withdrawn)")

    # 12 generated tables and summary
    mt = load("make_tables_v", HERE / "harness" / "make_tables.py")
    bad_blocks = mt.check(HERE)
    n_blocks = len(re.findall(r"<!-- BEGIN GENERATED ", readme))
    check(not bad_blocks and n_blocks == len(mt.blocks(HERE)), f"12 README tables byte-identical to make_tables.py ({n_blocks} blocks; mismatched {bad_blocks})")
    with tempfile.TemporaryDirectory() as tmp:
        import shutil
        cp = Path(tmp) / "p"
        shutil.copytree(HERE, cp, ignore=shutil.ignore_patterns("__pycache__", "summary.json"))
        subprocess.run([sys.executable, str(cp / "harness" / "make_summary.py"), str(cp)], check=True, capture_output=True)
        check((cp / "summary.json").read_bytes() == (HERE / "summary.json").read_bytes(), "12 summary.json byte-identical to a fresh make_summary.py run")

    # 13 manifest
    events_lines = sum(1 for l in (ds / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())
    want_counts = {"tasks": len(runs), "run": n_run, "not_run": len(runs) - n_run, "observer_rows": events_lines}
    check(manifest["counts"] == want_counts, f"13 MANIFEST counts recomputed {want_counts}")
    check(sorted(manifest["files"]) == sorted(p.name for p in ds.iterdir() if p.name != "MANIFEST.json"),
          "13 MANIFEST lists every dataset file")
    prov = json.loads((HERE / "provenance.json").read_text())
    check(manifest["identities"] == prov["identities"], "13 MANIFEST identities == provenance identities")
    check(summary["dataset_content_sha256"] == manifest["content_sha256"] and manifest["content_sha256"][:8] in readme,
          f"13 summary and README cite MANIFEST content hash {manifest['content_sha256'][:12]}")

    # 14 unit log
    ulog = HERE / "raw" / "unit" / "unit-lab-5d01f608.log"
    utext = ulog.read_text() if ulog.exists() else ""
    check(head in utext and "25 passed, 2 skipped" in utext and "13 passed" in utext,
          "14 unit log committed: hermes head, 25 passed / 2 skipped, 13 passed with z0int")

    print("RESULT", "PASS" if not FAIL else "FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
