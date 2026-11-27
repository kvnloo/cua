"""Offline validator for the frozen three-arm CUA/Pomerado/opencli task packet.

No installed dependencies, model calls, browser launches, or benchmark attempts.
Run: python -m unittest docs/experiments/h2h-cua-pomerado-opencli/test_task_spec.py -v
"""
from __future__ import annotations

import copy
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = HERE / "tasks.json"
DOCUMENT = HERE / "TASK-SPEC.md"
FIXTURE_PATH = ROOT / "libs/cua-driver/examples/jev-use/fixture_server.py"

EXPECTED_FIXTURE_COMMIT = "6e74bfadd82790312f0ab46ae7ed48027f8aca56"
EXPECTED_FIXTURE_BLOB = "055500f713ba2c33d8544096f4084ebb108757ce"
REQUIRED_FIELDS = {
    "id", "fixture_mode", "start_path", "navigation_paths",
    "instruction", "oracle", "max_steps", "timeout_s",
}
SCHEDULE = (
    ("A", "B", "C", "C", "B", "A"),
    ("B", "C", "A", "A", "C", "B"),
    ("C", "A", "B", "B", "A", "C"),
    ("A", "C", "B", "B", "C", "A"),
    ("B", "A", "C", "C", "A", "B"),
)


def _strings(value: object):
    """Walk all strings, including JSON object keys, to reject off-origin URLs."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _approved_path(value: object) -> bool:
    """Only routes that the pinned main-branch fixture actually serves."""
    return isinstance(value, str) and value in {"/", "/state"}


def validate_manifest(manifest: object, document: str) -> None:
    """Raise ValueError on any malformed or non-frozen task packet."""
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    if set(manifest) != {
        "schema", "status", "fixture_commit", "fixture_path",
        "fixture_blob_sha", "tasks",
    }:
        raise ValueError("unexpected/missing top-level manifest fields")
    if manifest["schema"] != "cua.h2h.tasks.v1":
        raise ValueError("unknown task schema")
    if manifest["status"] != "PREREGISTERED_NOT_RUN":
        raise ValueError("task plan must not claim an execution")
    if manifest["fixture_commit"] != EXPECTED_FIXTURE_COMMIT:
        raise ValueError("fixture source commit differs from preregistered pin")
    if manifest["fixture_path"] != "libs/cua-driver/examples/jev-use/fixture_server.py":
        raise ValueError("fixture file path changed")
    if manifest["fixture_blob_sha"] != EXPECTED_FIXTURE_BLOB:
        raise ValueError("fixture blob identity changed")
    tasks = manifest["tasks"]
    if not isinstance(tasks, list) or not 8 <= len(tasks) <= 12:
        raise ValueError("task count must be between 8 and 12")
    if len(tasks) != 10:
        raise ValueError("frozen N=10 task count changed")
    seen: set[str] = set()
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict) or set(task) != REQUIRED_FIELDS:
            raise ValueError("missing or unexpected task fields")
        task_id = task["id"]
        if not isinstance(task_id, str) or not re.fullmatch(r"H2H-T[0-9]{2}", task_id):
            raise ValueError("invalid task id")
        if task_id in seen:
            raise ValueError("duplicate task id")
        if task_id != f"H2H-T{index:02d}":
            raise ValueError("task ids must remain in preregistered order")
        seen.add(task_id)
        if f"`{task_id}`" not in document:
            raise ValueError(f"{task_id} absent from TASK-SPEC.md")
        if task["fixture_mode"] not in {"default", "visual_submit"}:
            raise ValueError(f"{task_id} unknown fixture mode")
        if (task["fixture_mode"] == "visual_submit") != (task_id == "H2H-T10"):
            raise ValueError("visual-submit variant has changed")
        if not _approved_path(task["start_path"]):
            raise ValueError(f"{task_id} invalid/off-origin start path")
        hops = task["navigation_paths"]
        if (
            not isinstance(hops, list)
            or not 1 <= len(hops) <= 3
            or not all(_approved_path(path) for path in hops)
            or hops[0] != task["start_path"]
        ):
            raise ValueError(f"{task_id} invalid/off-origin navigation")
        if task_id == "H2H-T09":
            if hops != ["/", "/state"]:
                raise ValueError("T09 must visit the two preregistered routes")
        elif hops != ["/"]:
            raise ValueError(f"{task_id} gained an unregistered page")
        if not isinstance(task["instruction"], str) or not task["instruction"].strip():
            raise ValueError(f"{task_id} needs a nonempty task instruction")
        if not isinstance(task["oracle"], dict) or not task["oracle"]:
            raise ValueError(f"{task_id} needs an exact nonempty JSON-object oracle")
        try:
            json.dumps(task["oracle"], allow_nan=False)
        except (ValueError, TypeError) as error:
            raise ValueError(f"{task_id} oracle is not finite JSON") from error
        for limit in ("max_steps", "timeout_s"):
            value = task[limit]
            maximum = 20 if limit == "max_steps" else 120
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{task_id} invalid {limit}")
        if task["timeout_s"] != 45:
            raise ValueError(f"{task_id} changed its frozen timeout")
        for value in _strings(task):
            # We require relative paths even for the synthetic origin:
            # no URL from any host may be smuggled into an instruction or oracle.
            if re.search(r"(?i)(?:[a-z][a-z0-9+.-]*://|www\.)", value):
                raise ValueError(f"{task_id} contains an absolute/external URL")
    if len(seen) != len(tasks):
        raise ValueError("task ids not unique")


class FixtureHTML(HTMLParser):
    """Extract only the semantic values this tiny pinned HTML fixture provides."""

    def __init__(self) -> None:
        super().__init__()
        self.text: dict[str, list[str]] = {
            "title": [], "h1": [], "p": [], "output": [],
            "button": [], "presentation": [],
        }
        self.active: str | None = None
        self.form: dict[str, str | None] = {}
        self.inputs: list[dict[str, str | None]] = []
        self.buttons: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        properties = dict(attrs)
        if tag == "form":
            self.form = properties
        elif tag == "input":
            self.inputs.append(properties)
        elif tag == "button":
            self.buttons.append(properties)
            self.active = "button"
        elif tag == "div" and properties.get("role") == "presentation":
            self.active = "presentation"
        elif tag in {"title", "h1", "p", "output"}:
            self.active = tag

    def handle_data(self, data: str) -> None:
        if self.active in self.text:
            self.text[self.active].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self.active or (tag == "div" and self.active == "presentation"):
            self.active = None

    def value(self, kind: str) -> str:
        return "".join(self.text[kind]).strip()


def _fixture_module():
    spec = importlib.util.spec_from_file_location("cua_h2h_readonly_fixture", FIXTURE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("fixture source cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TaskSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.doc = DOCUMENT.read_text(encoding="utf-8")

    def test_manifest_and_markdown(self) -> None:
        validate_manifest(self.data, self.doc)

    def test_blob_matches_exact_fixture_source(self) -> None:
        raw = FIXTURE_PATH.read_bytes()
        header = f"blob {len(raw)}\0".encode("ascii")
        self.assertEqual(hashlib.sha1(header + raw).hexdigest(), EXPECTED_FIXTURE_BLOB)

    def test_actual_fixture_oracles(self) -> None:
        module = _fixture_module()
        basic = FixtureHTML()
        basic.feed(module.PAGE.decode("utf-8"))
        visual = FixtureHTML()
        visual.feed(module.VISUAL_PAGE.decode("utf-8"))
        self.assertEqual(module.FixtureState().snapshot(), {"submitted": None})
        self.assertEqual(len(basic.inputs), 1)
        self.assertEqual(len(basic.buttons), 1)
        self.assertEqual(len(visual.buttons), 0)
        expected = {
            "H2H-T01": {"title": basic.value("title")},
            "H2H-T02": {"heading": basic.value("h1")},
            "H2H-T03": {"instruction": basic.value("p")},
            "H2H-T04": {
                "textbox_accessible_name": basic.inputs[0]["aria-label"],
                "required": "required" in basic.inputs[0],
            },
            "H2H-T05": {
                "button_label": basic.value("button"),
                "button_type": basic.buttons[0]["type"],
            },
            "H2H-T06": {
                "form_method": basic.form["method"], "form_action": basic.form["action"],
            },
            "H2H-T07": {"status": basic.value("output").split("=", 1)[1]},
            "H2H-T08": {
                "textbox_count": len(basic.inputs),
                "submit_button_count": len(basic.buttons),
            },
            "H2H-T09": {
                "heading": basic.value("h1"),
                **module.FixtureState().snapshot(),
            },
            "H2H-T10": {
                "presentational_submit_text": visual.value("presentation"),
                "submit_button_count": len(visual.buttons),
            },
        }
        for task in self.data["tasks"]:
            with self.subTest(task=task["id"]):
                self.assertEqual(task["oracle"], expected[task["id"]])

    def test_document_exact_schedule_and_source_pins(self) -> None:
        for pin in (
            EXPECTED_FIXTURE_COMMIT,
            EXPECTED_FIXTURE_BLOB,
            "ff888c6159c9fae3b9c47938f77bcf104373d426",
            "1d8a016862b6b1c8e43c770a75514d487efb8bc5",
            "916705f34456ea54200fb79d0a28fd1cbc0727f6",
            "adapter_file_sha256", "mint_model_ids", "driver_binary_sha256",
            "NOT_RUN", "INVALID",
        ):
            with self.subTest(pin=pin):
                self.assertIn(pin, self.doc)
        for i, order in enumerate(SCHEDULE):
            with self.subTest(pattern=i):
                self.assertIn(f"| P{i} | `{' '.join(order)}` |", self.doc)
                self.assertEqual({arm: order.count(arm) for arm in "ABC"},
                                 {"A": 2, "B": 2, "C": 2})
                for left in "ABC":
                    for right in "ABC":
                        if left != right:
                            self.assertEqual(
                                sum(order[a] == left and order[b] == right
                                    for a in range(6) for b in range(a + 1, 6)),
                                sum(order[a] == right and order[b] == left
                                    for a in range(6) for b in range(a + 1, 6)),
                            )
        for i, task in enumerate(self.data["tasks"]):
            sequence = " → ".join(f"P{(i + j) % 5}" for j in range(5))
            self.assertIn(f"| `{task['id']}` | {sequence} |", self.doc)
            counts = [sum(SCHEDULE[(i + j) % 5].count(arm) for j in range(5))
                      for arm in "ABC"]
            self.assertEqual(counts, [10, 10, 10])

    def test_duplicate_id_refused(self) -> None:
        changed = copy.deepcopy(self.data)
        changed["tasks"][1]["id"] = changed["tasks"][0]["id"]
        with self.assertRaises(ValueError):
            validate_manifest(changed, self.doc)

    def test_missing_required_fields_refused(self) -> None:
        for missing in ("oracle", "max_steps", "timeout_s", "start_path"):
            with self.subTest(missing=missing):
                changed = copy.deepcopy(self.data)
                del changed["tasks"][0][missing]
                with self.assertRaises(ValueError):
                    validate_manifest(changed, self.doc)

    def test_unapproved_paths_and_external_urls_refused(self) -> None:
        for field, replacement in (
            ("start_path", "https://external.invalid/"),
            ("start_path", "//external.invalid/"),
            ("start_path", "/../state"),
            ("start_path", "/state?next=other"),
            ("navigation_paths", ["/", "http://external.invalid/"]),
            ("instruction", "Visit https://external.invalid/ instead."),
        ):
            with self.subTest(field=field, value=replacement):
                changed = copy.deepcopy(self.data)
                changed["tasks"][0][field] = replacement
                with self.assertRaises(ValueError):
                    validate_manifest(changed, self.doc)

    def test_missing_markdown_coverage_refused(self) -> None:
        with self.assertRaises(ValueError):
            validate_manifest(self.data, self.doc.replace("`H2H-T03`", "REMOVED"))

    def test_invalid_limits_and_oracles_refused(self) -> None:
        for field, replacement in (
            ("timeout_s", 0),
            ("timeout_s", True),
            ("max_steps", -1),
            ("max_steps", 1.5),
            ("oracle", {}),
            ("oracle", {"bad": float("nan")}),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.data)
                changed["tasks"][0][field] = replacement
                with self.assertRaises(ValueError):
                    validate_manifest(changed, self.doc)

    def test_no_result_receipts_or_fake_execution_claims(self) -> None:
        self.assertEqual(self.data["status"], "PREREGISTERED_NOT_RUN")
        for task in self.data["tasks"]:
            self.assertNotIn("result", task)
            self.assertNotIn("elapsed_ms", task)
            self.assertNotIn("passed", task)


if __name__ == "__main__":
    unittest.main()
