"""Oracle self-test: for every frozen task, a synthetic ideal run must PASS, an empty run must FAIL
(or be UNKNOWN for GUI tasks whose state file is missing), and a wrong answer must FAIL.
  python oracle_selftest.py <tasks.jsonl> <scratch_dir>
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workload  # noqa: E402


def _run(scratch: Path, name: str, reply: str = "", files: dict | None = None, state: dict | None = None) -> Path:
    run = scratch / name
    shutil.rmtree(run, ignore_errors=True)
    (run / "meta").mkdir(parents=True)
    (run / "cwd").mkdir()
    (run / "meta" / "stdout").write_text(reply + "\n\nsession_id: x\n", encoding="utf-8")
    for rel, content in (files or {}).items():
        (run / "cwd" / rel).write_text(content, encoding="utf-8")
    if state is not None:
        (run / "meta" / "gui-state").mkdir()
        (run / "meta" / "gui-state" / "state.after.json").write_text(json.dumps(state), encoding="utf-8")
    return run


def ideal(task: dict) -> dict:
    spec = task["oracle"]
    base_state = {"counter": 0, "agreed": False}
    kind = spec["type"]
    if kind in ("reply_contains", "reply_one_of"):
        return {"reply": str(spec["value"])}
    if kind == "reply_number":
        return {"reply": str(spec["value"])}
    if kind == "file_equals":
        return {"files": {spec["path"]: spec["value"] + "\n"}}
    if kind == "gui_state":
        return {"state": {**base_state, **spec["state"]}}
    if kind == "gui_reply_and_state":
        return {"reply": spec["reply"], "state": {**base_state, **spec["state"]}}
    if kind == "gui_yes_no":
        return {"reply": spec["value"].capitalize() + ".", "state": base_state}
    raise ValueError(kind)


def wrong(task: dict) -> dict:
    spec = task["oracle"]
    kind = spec["type"]
    if kind == "reply_one_of":
        return {"reply": f"{spec['value']} or {spec['others'][0]}"}
    if kind == "reply_number":
        return {"reply": str(int(spec["value"]) + 1)}
    if kind == "file_equals":
        return {"files": {spec["path"]: spec["value"] + " extra\n"}}
    if kind in ("gui_state", "gui_reply_and_state"):
        return {"reply": "counter=1", "state": {"counter": 1, "agreed": False}}
    if kind == "gui_yes_no":
        return {"reply": "yes and no", "state": {}}
    return {"reply": "I could not find it."}


def main() -> None:
    tasks = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
    scratch = Path(sys.argv[2])
    failures = []
    for task in tasks:
        good = workload.oracle(task, _run(scratch, "ideal", **ideal(task)))["verified_success"]
        empty = workload.oracle(task, _run(scratch, "empty"))["verified_success"]
        bad = workload.oracle(task, _run(scratch, "wrong", **wrong(task)))["verified_success"]
        empty_ok = (empty is None) if task["kind"] == "cua" and task["oracle"]["type"] != "gui_yes_no" else (empty is False)
        if not (good is True and empty_ok and bad is False):
            failures.append({"task_id": task["task_id"], "ideal": good, "empty": empty, "wrong": bad})
    print(json.dumps({"tasks": len(tasks), "failures": failures, "result": "PASS" if not failures else "FAIL"}, sort_keys=True))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
