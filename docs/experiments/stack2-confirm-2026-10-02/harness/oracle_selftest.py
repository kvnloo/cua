"""Oracle self-test (before any measured run): for every task, a synthetic ideal run passes, an empty run fails
(or is unknown when a fixture state file is missing), and a wrong answer fails.

  python oracle_selftest.py <tasks.jsonl> <fixtures_dir> <scratch_dir>
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workload  # noqa: E402


def make_run(root: Path, name: str, reply: str = "", files: dict | None = None, state: dict | None = None) -> Path:
    rd = root / name
    shutil.rmtree(rd, ignore_errors=True)
    (rd / "meta").mkdir(parents=True)
    (rd / "cwd").mkdir()
    (rd / "fixture").mkdir()
    (rd / "meta" / "stdout").write_text(f"{reply}\n\nsession_id: 20261002_000000_abcdef\n")
    for rel, content in (files or {}).items():
        (rd / "cwd" / rel).parent.mkdir(parents=True, exist_ok=True)
        (rd / "cwd" / rel).write_text(content)
    if state is not None:
        (rd / "fixture" / "state.after.json").write_text(json.dumps(state))
    return rd


def ideal_and_wrong(task: dict, fixture: Path):
    spec = task["oracle"]
    kind = spec["type"]
    base_files = {str(p.relative_to(fixture)): p.read_text() for p in fixture.rglob("*") if p.is_file()}
    if kind in ("reply_contains", "reply_one_of"):
        wrong = spec.get("others", ["zz-wrong"])[0] if kind == "reply_one_of" else "ZZ-0000-ZZ"
        return dict(reply=spec["value"], files=base_files), dict(reply=wrong, files=base_files)
    if kind == "reply_number":
        return dict(reply=str(spec["value"])), dict(reply=str(spec["value"] + 1))
    if kind == "file_equals":
        good = dict(base_files, **{spec["path"]: spec["value"] + "\n"})
        bad = dict(base_files, **{spec["path"]: spec["value"] + "x\n"})
        return dict(reply="Done.", files=good), dict(reply="Done.", files=bad)
    if kind == "gtk_state":
        good = dict(workload.CLEAN_GTK, **spec["state"], seq=3)
        bad = dict(good, counter=good["counter"] + 7) if "counter" not in spec["state"] else dict(good, counter=99)
        return dict(reply="DONE", state=good), dict(reply="DONE", state=bad)
    if kind == "gui_yes_no":
        other = "no" if spec["value"] == "yes" else "yes"
        return dict(reply=spec["value"].capitalize()), dict(reply=other.capitalize())
    if kind == "browser_submitted":
        return dict(reply="DONE", state={"submitted": spec["value"]}), dict(reply="DONE", state={"submitted": spec["value"] + "0"})
    raise ValueError(kind)


def main() -> None:
    tasks_path, fixtures, scratch = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    tasks = [json.loads(l) for l in tasks_path.read_text().splitlines() if l.strip()]
    failures, counts = [], {"ideal_pass": 0, "empty_fail_or_unknown": 0, "wrong_fail": 0}
    for task in tasks:
        good, bad = ideal_and_wrong(task, fixtures / task["task_id"])
        v_good = workload.oracle(task, make_run(scratch, "ideal", **good))["verified_success"]
        v_empty = workload.oracle(task, make_run(scratch, "empty"))["verified_success"]
        v_bad = workload.oracle(task, make_run(scratch, "wrong", **bad))["verified_success"]
        counts["ideal_pass"] += v_good is True
        counts["empty_fail_or_unknown"] += v_empty in (False, None)
        counts["wrong_fail"] += v_bad is False
        if v_good is not True or v_empty not in (False, None) or v_bad is not False:
            failures.append({"task_id": task["task_id"], "ideal": v_good, "empty": v_empty, "wrong": v_bad})
    result = {"n_tasks": len(tasks), **counts, "failures": failures,
              "result": "PASS" if not failures else "FAIL"}
    print(json.dumps(result, indent=1, sort_keys=True))
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
