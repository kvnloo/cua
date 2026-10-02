"""Freeze the collected SAMPLES dataset.

  python freeze.py <tasks.jsonl> <collect_dir> <runs_dir> <dataset_dir> <identities.json>

Writes dataset/events.jsonl (each RUN task's observer spool, rows unchanged, concatenated in index
order), dataset/runs.jsonl (index + oracle verdict + per-run receipt facts), dataset/MANIFEST.json
(sha256 of every frozen file, schema versions, workload description, identities). No outcome-based
selection: every task in tasks.jsonl appears in runs.jsonl as RUN or NOT_RUN.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SPOOL = Path("home/.hermes/plugin-data/z0-hermes-observer/events.jsonl")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _kv(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v.strip()
    return out


def main() -> None:
    tasks_path, collect, runs_dir, out, ident_path = map(Path, sys.argv[1:6])
    tasks = read_jsonl(tasks_path)
    index = {r["task_id"]: r for r in read_jsonl(collect / "index.jsonl")}
    verdicts = {r["task_id"]: r for r in read_jsonl(collect / "verdicts.jsonl")}
    out.mkdir(parents=True, exist_ok=True)
    runs, n_rows = [], 0
    with (out / "events.jsonl").open("w", encoding="utf-8") as events:
        for task in tasks:
            tid = task["task_id"]
            idx = index.get(tid, {"task_id": tid, "status": "NOT_RUN", "reason": "absent_from_index"})
            row = {"task_id": tid, "order": task["order"], "kind": task["kind"], "family": task["family"],
                   "status": idx.get("status", "NOT_RUN")}
            if row["status"] == "RUN":
                rd = runs_dir / idx["run_id"]
                spool = rd / SPOOL
                lines = spool.read_text(encoding="utf-8").splitlines() if spool.exists() else []
                for line in lines:
                    if line.strip():
                        events.write(line.rstrip("\n") + "\n")
                        n_rows += 1
                mask = _kv(rd / "meta" / "mask.inside")
                before = (rd / "meta" / "live-home-stat.before").read_text() if (rd / "meta" / "live-home-stat.before").exists() else None
                after = (rd / "meta" / "live-home-stat.after").read_text() if (rd / "meta" / "live-home-stat.after").exists() else None
                t0 = datetime.fromisoformat(idx["started_at"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(idx["ended_at"].replace("Z", "+00:00"))
                x11 = mask.get("x11_entries", "").split()
                verdict = verdicts.get(tid, {})
                row.update({
                    "run_id": idx["run_id"], "session_id": idx.get("session_id") or None,
                    "exit_code": idx.get("exit_code"), "timed_out": idx.get("exit_code") in (124, 137),
                    "started_at": idx["started_at"], "ended_at": idx["ended_at"],
                    "wall_s": round((t1 - t0).total_seconds(), 3),
                    "verified_success": verdict.get("verified_success"),
                    "oracle_type": verdict.get("oracle_type"), "oracle_error": bool(verdict.get("oracle_error")),
                    "observer_rows": sum(1 for l in lines if l.strip()),
                    "observer_spool_sha256": sha(spool) if spool.exists() else None,
                    "worktree_head": (rd / "meta" / "worktree-head").read_text().strip() if (rd / "meta" / "worktree-head").exists() else None,
                    "worktree_clean": (rd / "meta" / "worktree-status").exists() and not (rd / "meta" / "worktree-status").read_text().strip(),
                    "isolation": {
                        "live_hermes_home_entries": mask.get("live_hermes_home_entries"),
                        "real_home_entries": mask.get("real_home_entries"),
                        "run_user_entries": mask.get("run_user_entries"),
                        "x11_entries": x11,
                        "ok": mask.get("live_hermes_home_entries") == "0" and mask.get("real_home_entries") == "0"
                              and mask.get("run_user_entries") == "0"
                              and (x11 == [] if task["kind"] == "file" else len(x11) == 1),
                        # Line 1 is the live home directory itself, whose mtime the concurrently running live
                        # Hermes moves; the file entries (state.db, -wal, config.yaml, .env, auth.json, logs)
                        # must be identical. Contents are never read (stat metadata only).
                        "live_home_stat_unchanged": before is not None and after is not None
                                                    and before.splitlines()[1:] == after.splitlines()[1:],
                        "live_home_dir_mtime_moved": before is not None and after is not None
                                                     and before.splitlines()[:1] != after.splitlines()[:1],
                        "live_home_changed_entries": [
                            {"entry": b.split("|")[0].rsplit("/", 1)[-1], "size_changed": b.split("|")[-1] != a.split("|")[-1]}
                            for b, a in zip((before or "").splitlines()[1:], (after or "").splitlines()[1:]) if b != a],
                    },
                })
            else:
                row["reason"] = idx.get("reason")
            runs.append(row)
    with (out / "runs.jsonl").open("w", encoding="utf-8") as stream:
        for row in runs:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    identities = json.loads(ident_path.read_text())
    manifest = {
        "schema": "stack.samples.dataset_manifest.v1",
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workload": {"tasks_sha256": sha(tasks_path), "n_tasks": len(tasks),
                     "description": "see PREREG.json workload; one isolated one-shot Hermes turn per task"},
        "schemas": {"events": "z0int.hermes_observer_event.v1", "runs": "stack.samples.run.v1",
                    "oracle": "stack.samples.oracle_verdict.v1"},
        "counts": {"tasks": len(runs), "run": sum(r["status"] == "RUN" for r in runs),
                   "not_run": sum(r["status"] != "RUN" for r in runs), "observer_rows": n_rows},
        "files": {name: sha(out / name) for name in ("events.jsonl", "runs.jsonl")},
        "identities": identities,
    }
    manifest["content_sha256"] = hashlib.sha256(json.dumps(manifest["files"], sort_keys=True).encode()).hexdigest()
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"] | {"content_sha256": manifest["content_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
