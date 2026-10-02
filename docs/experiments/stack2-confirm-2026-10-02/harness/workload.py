"""Fresh frozen workload + independent fixture oracle for the stack v2 CONFIRM lane (kvnloo/hermes-agent#319).

  python workload.py generate <out_dir> [seed]                  -> tasks.jsonl (seeded, shuffled) + fixtures/<task_id>/
  python workload.py oracle <tasks.jsonl> <run_dir> <task_id>   -> one verdict JSON on stdout

Derived from the SAMPLES workload (stack-samples-2026-10-02/harness/workload.py): the same 10 file-tool
families with a NEW seed (fresh instances), and CUA families on the fixed integration (token addressing,
tool search off): GTK3 TaskWindow tasks plus the jev-use browser form in Chrome.

The oracle reads only what the task produced: the final reply (meta/stdout), files in the run's cwd, or the
fixture-owned state captured by the harness after Hermes exited (fixture/state.after.json). It never reads
observer rows, Hermes logs or any backend output, so no observer or scorer can credit its own success.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import string
import sys
from pathlib import Path

SEED = 20261012          # SAMPLES used 20261002; a new seed gives fresh instances
REPS_PER_FILE_FAMILY = 10
FILE_TURNS = 6
CUA_TURNS = 12
GUI_TITLE = "CuaTestHarness GTK3 Tasks"
# Mirrors DISTRACTOR_BUTTONS / DENSITY_COUNTS in libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py.
DISTRACTOR_BUTTONS = (
    "New folder", "Refresh", "Undo", "Redo", "Zoom in", "Zoom out", "Save draft",
    "Increase font size", "Copy link", "Duplicate", "Rename", "Print preview", "Export PDF",
    "Import", "Bold", "Italic", "Underline", "Align left", "Align center", "Align right",
    "Insert table", "Insert image", "Spell check", "Word count", "Show sidebar", "Help",
)
DENSITY_BUTTONS = {12: 8, 24: 26}
WORDS = ("amber", "basalt", "cobalt", "delta", "ember", "fjord", "garnet", "harbor", "indigo", "juniper",
         "kestrel", "lagoon", "mesa", "nectar", "onyx", "prairie", "quartz", "raven", "sierra", "tundra")
NAMES = ("Ada Lovelace", "Grace Hopper", "Alan Turing", "Edsger Dijkstra", "Barbara Liskov",
         "Donald Knuth", "Frances Allen", "Ken Thompson", "Margaret Hamilton", "John Backus")
CLEAN_GTK = {"counter": 0, "agreed": False, "size": "none", "note_saved": None}

GTK_INTRO = (f"A GTK window titled '{GUI_TITLE}' is open on this desktop; its app name for computer_use is "
             "'Main.py'. Use the computer_use tool and never pass pid or window_id: start with action='capture', "
             "mode='ax', app='Main.py', then act on elements by their index from that capture.")
BROWSER_INTRO = ("A Chrome window is open on this desktop; its app name for computer_use is 'Google-chrome'. It shows "
                 "a web form with a text field labeled 'verification value' and a Submit button. Chrome only accepts "
                 "input with delivery_mode='foreground'. Use the computer_use tool and never pass pid or window_id: "
                 "start with action='capture', mode='ax', app='Google-chrome', then act on elements by their index "
                 "from that capture.")


def _code(rng: random.Random) -> str:
    return f"{''.join(rng.choices(string.ascii_uppercase, k=2))}-{rng.randint(1000, 9999)}-{''.join(rng.choices(string.ascii_uppercase, k=2))}"


def _file_tasks(rng: random.Random) -> list[dict]:
    """Verbatim SAMPLES families and prompts; only the seed differs."""
    tasks = []
    for _ in range(REPS_PER_FILE_FAMILY):
        code = _code(rng)
        tasks.append(dict(family="read_code", files={"notes/code.txt": f"Project notes\naccess code: {code}\nend\n"},
                          prompt="Read the file notes/code.txt and reply with only the access code it contains.",
                          oracle={"type": "reply_contains", "value": code}))
        owner = rng.choice(NAMES)
        data = {"id": rng.randint(100, 999), "owner": owner, "tags": rng.sample(WORDS, 3)}
        tasks.append(dict(family="json_field", files={"data.json": json.dumps(data, indent=2) + "\n"},
                          prompt="Read data.json and reply with only the value of its owner field.",
                          oracle={"type": "reply_contains", "value": owner}))
        words = rng.sample(WORDS, 4)
        target = rng.randrange(4)
        files = {f"docs/{name}.md": f"# {name}\nThis page is about {w}.\n"
                 for name, w in zip(("alpha", "bravo", "charlie", "delta"), words)}
        tasks.append(dict(family="find_file", files=files,
                          prompt=f"Which file in the docs directory mentions the word '{words[target]}'? Reply with only the file name.",
                          oracle={"type": "reply_one_of", "value": f"{('alpha', 'bravo', 'charlie', 'delta')[target]}.md",
                                  "others": [f"{n}.md" for j, n in enumerate(("alpha", "bravo", "charlie", "delta")) if j != target]}))
        token = f"{rng.choice(WORDS)}-{rng.randint(10, 99)}-{rng.choice(WORDS)}"
        tasks.append(dict(family="write_token", files={},
                          prompt=f"Create a file named answer.txt whose entire content is exactly: {token}",
                          oracle={"type": "file_equals", "path": "answer.txt", "value": token}))
        port = rng.randint(2000, 9999)
        cfg = f"[server]\nhost = 127.0.0.1\nport = 8080\nworkers = {rng.randint(2, 8)}\n"
        tasks.append(dict(family="edit_config", files={"config.ini": cfg},
                          prompt=f"In config.ini change the port value from 8080 to {port}. Do not change anything else.",
                          oracle={"type": "file_equals", "path": "config.ini", "value": cfg.replace("port = 8080", f"port = {port}")}))
        nums = [rng.randint(1, 60) for _ in range(5)]
        tasks.append(dict(family="sum_numbers", files={"numbers.txt": "\n".join(map(str, nums)) + "\n"},
                          prompt="numbers.txt contains one integer per line. Reply with only the sum of those integers.",
                          oracle={"type": "reply_number", "value": sum(nums)}))
        lines = []
        for _ in range(rng.randint(8, 12)):
            level = rng.choice(("INFO", "INFO", "WARN", "ERROR"))
            lines.append(f"2026-10-02 {level} {rng.choice(WORDS)} step {rng.randint(1, 99)}")
        tasks.append(dict(family="count_errors", files={"log.txt": "\n".join(lines) + "\n"},
                          prompt="How many lines of log.txt contain the word ERROR? Reply with only the number.",
                          oracle={"type": "reply_number", "value": sum("ERROR" in line for line in lines)}))
        phrase = f"{rng.choice(WORDS)} {rng.choice(WORDS)} {rng.randint(1, 99)}"
        tasks.append(dict(family="uppercase_copy", files={"name.txt": phrase + "\n"},
                          prompt="Write the contents of name.txt converted to upper case into a new file named upper.txt.",
                          oracle={"type": "file_equals", "path": "upper.txt", "value": phrase.upper()}))
        items = rng.sample(WORDS, 10)
        k = rng.randint(1, 10)
        tasks.append(dict(family="line_n", files={"list.txt": "\n".join(items) + "\n"},
                          prompt=f"Reply with only the word on line {k} of list.txt.",
                          oracle={"type": "reply_one_of", "value": items[k - 1], "others": [w for w in items if w != items[k - 1]]}))
        a, b = rng.randint(12, 99), rng.randint(12, 99)
        tasks.append(dict(family="no_tool_math", files={},
                          prompt=f"What is {a} multiplied by {b}? Reply with only the number.",
                          oracle={"type": "reply_number", "value": a * b}))
    for t in tasks:
        t.update(kind="file", app="none", density="none", toolset="file", max_turns=FILE_TURNS)
    return tasks


def _token(i: int) -> str:
    return f"cnf{i:02d}-" + hashlib.sha256(f"stack2-confirm-2026-10-02/{i}".encode()).hexdigest()[:6]


def _cua_tasks(rng: random.Random) -> list[dict]:
    tasks = []
    for density in ("none", "none", "none", "none", "12", "12", "24", "24"):
        tasks.append(dict(family="cua_agree", app="gtk3", density=density,
                          prompt=f"{GTK_INTRO} Task: check the checkbox labeled 'I agree' and change nothing else. "
                                 "When finished, reply with the single word DONE.",
                          oracle={"type": "gtk_state", "state": {"agreed": True}}))
    for _ in range(8):
        n = rng.randint(2, 4)
        tasks.append(dict(family="cua_increment", app="gtk3", density="none",
                          prompt=f"{GTK_INTRO} Task: click the 'Increment' button exactly {n} times and change nothing "
                                 "else. When finished, reply with the single word DONE.",
                          oracle={"type": "gtk_state", "state": {"counter": n}}))
    for size in ("Small", "Medium", "Large", "Small", "Medium", "Large"):
        tasks.append(dict(family="cua_size", app="gtk3", density="none",
                          prompt=f"{GTK_INTRO} Task: select the '{size}' option and change nothing else. When "
                                 "finished, reply with the single word DONE.",
                          oracle={"type": "gtk_state", "state": {"size": size.lower()}}))
    for _ in range(6):
        word = f"{rng.choice(WORDS)}{rng.randint(10, 99)}"
        tasks.append(dict(family="cua_note", app="gtk3", density="none",
                          prompt=f"{GTK_INTRO} Task: enter the text {word} into the text field named 'Note', then "
                                 "click the 'Save note' button. Change nothing else. When finished, reply with the "
                                 "single word DONE.",
                          oracle={"type": "gtk_state", "state": {"note_saved": word}}))
    for density, label in ((12, rng.choice(DISTRACTOR_BUTTONS[:8])), (12, rng.choice(DISTRACTOR_BUTTONS[8:])),
                           (24, rng.choice(DISTRACTOR_BUTTONS[8:])), (24, rng.choice(DISTRACTOR_BUTTONS[:8])),
                           (12, rng.choice(DISTRACTOR_BUTTONS[12:])), (24, rng.choice(DISTRACTOR_BUTTONS[16:]))):
        present = label in DISTRACTOR_BUTTONS[:DENSITY_BUTTONS[density]]
        tasks.append(dict(family="cua_button_present", app="gtk3", density=str(density),
                          prompt=f"{GTK_INTRO} Task: find out whether that window has a button labeled '{label}'. "
                                 "Do not click anything. Reply with only yes or no.",
                          oracle={"type": "gui_yes_no", "value": "yes" if present else "no"}))
    for i in range(8):
        token = _token(i)
        tasks.append(dict(family="browser_submit", app="browser", density="none",
                          prompt=f"{BROWSER_INTRO} Task: enter the exact value {token} into the 'verification value' "
                                 "field and submit the form. When finished, reply with the single word DONE.",
                          oracle={"type": "browser_submitted", "value": token}))
    for t in tasks:
        t.update(kind="cua", toolset="computer_use", max_turns=CUA_TURNS, files={})
    return tasks


def generate(out_dir: Path, seed: int = SEED) -> None:
    rng = random.Random(seed)
    tasks = _file_tasks(rng) + _cua_tasks(rng)
    random.Random(seed + 1).shuffle(tasks)  # execution order fixed before any outcome exists
    out_dir.mkdir(parents=True, exist_ok=True)
    counters: dict[str, int] = {}
    with (out_dir / "tasks.jsonl").open("w", encoding="utf-8") as stream:
        for order, task in enumerate(tasks):
            counters[task["family"]] = counters.get(task["family"], 0) + 1
            task_id = f"c{order:03d}-{task['family']}-{counters[task['family']]:02d}"
            fixture = out_dir / "fixtures" / task_id
            fixture.mkdir(parents=True, exist_ok=True)
            for rel, content in task["files"].items():
                (fixture / rel).parent.mkdir(parents=True, exist_ok=True)
                (fixture / rel).write_text(content, encoding="utf-8")
            row = {"task_id": task_id, "order": order, **{k: v for k, v in task.items() if k != "files"},
                   "fixture_files": sorted(task["files"])}
            stream.write(json.dumps(row, sort_keys=True) + "\n")


def _reply(run_dir: Path) -> str:
    try:
        text = (run_dir / "meta" / "stdout").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    return "\n".join(line for line in text.splitlines() if not line.startswith("session_id:")).strip()


def _norm(text: str) -> str:
    return re.sub(r"[`*\"'“”‘’]", "", text).strip()


def _state(run_dir: Path) -> dict | None:
    try:
        return json.loads((run_dir / "fixture" / "state.after.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def oracle(task: dict, run_dir: Path) -> dict:
    spec = task["oracle"]
    kind = spec["type"]
    reply = _norm(_reply(run_dir))
    detail: dict = {}
    verdict: bool | None
    if kind == "reply_contains":
        verdict = spec["value"] in reply
    elif kind == "reply_one_of":
        low = reply.lower()
        verdict = spec["value"].lower() in low and not any(o.lower() in low for o in spec["others"])
    elif kind == "reply_number":
        numbers = [int(x) for x in re.findall(r"-?\d+", reply.replace(",", ""))]
        verdict = spec["value"] in numbers and len(set(numbers)) == 1
    elif kind == "file_equals":
        path = run_dir / "cwd" / spec["path"]
        verdict = path.is_file() and path.read_text(encoding="utf-8", errors="replace").strip() == spec["value"].strip()
    elif kind == "gtk_state":
        state = _state(run_dir)
        if state is None:
            verdict = None  # oracle input missing: unknown, never a guessed pass/fail
        else:
            want = dict(CLEAN_GTK, **spec["state"])
            collateral = {k: state.get(k) for k in want if state.get(k) != want[k] and k not in spec["state"]}
            if state.get("distractor_actions"):
                collateral["distractor_actions"] = state["distractor_actions"]
            target = all(state.get(k) == v for k, v in spec["state"].items())
            verdict = target and not collateral
            detail = {"target": target, "collateral": collateral}
    elif kind == "gui_yes_no":
        words = set(re.findall(r"[a-z]+", reply.lower()))
        verdict = spec["value"] in words and ({"yes", "no"} - {spec["value"]}).isdisjoint(words)
    elif kind == "browser_submitted":
        state = _state(run_dir)
        if state is None:
            verdict = None
        else:
            verdict = state.get("submitted") == spec["value"]
            detail = {"submitted_present": state.get("submitted") is not None}
    else:
        raise ValueError(f"unknown oracle type {kind}")
    return {"schema": "stack2.confirm.oracle_verdict.v1", "task_id": task["task_id"], "oracle_type": kind,
            "verified_success": verdict, "reply_chars": len(reply), "detail": detail}


def main() -> None:
    if sys.argv[1] == "generate":
        generate(Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else SEED)  # seed override: pilots only
    elif sys.argv[1] == "oracle":
        tasks = {json.loads(l)["task_id"]: json.loads(l) for l in Path(sys.argv[2]).read_text().splitlines() if l.strip()}
        print(json.dumps(oracle(tasks[sys.argv[4]], Path(sys.argv[3])), sort_keys=True))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
