"""Red/green test: uitars predict_step history scan must not crash on malformed entries.

The inline history scan in UITARSConfig.predict_step had two defects:

1. The computer_call_output check (`message.get("type")`) sat OUTSIDE the
   `isinstance(message, dict)` guard -- a non-dict entry in history raised
   AttributeError and killed predict_step before any model call.
2. image_url values were taken without a type check -- a dict-shaped
   `image_url["url"]` flowed into process_image_for_uitars, which crashed
   with AttributeError on `.startswith` before the model call.

The scan is now the module-level `_scan_uitars_step_messages` with both
guards; malformed entries are skipped (a missing screenshot falls back to
the computer_handler screenshot path, unchanged behavior).

Self-contained: the fixed helper is AST-extracted from the real file (the
loop needs litellm etc. to import). The base version is extracted from the
actual base file text via `git show HEAD:...` so the red check runs the
real base code, not a replica.
"""

import ast
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LOOPS_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "loops"
UITARS = LOOPS_DIR / "uitars.py"


def _exec_fn(path, name, extra_ns=None):
    tree = ast.parse(Path(path).read_text())
    node = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == name
    )
    ns = {
        "List": List,
        "Dict": Dict,
        "Any": Any,
        "Optional": Optional,
        "Tuple": Tuple,
    }
    ns.update(extra_ns or {})
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    return ns[name]


def _base_scan_fn():
    """Wrap the BASE predict_step scan loop (from HEAD text) as a callable."""
    base_src = subprocess.run(
        ["git", "show", f"HEAD:{UITARS.relative_to(Path.cwd())}"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent.parent,
        check=True,
    ).stdout
    tree = ast.parse(base_src)
    predict_step = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "predict_step"
    )
    loop = next(
        n
        for n in ast.walk(predict_step)
        if isinstance(n, ast.For)
        and isinstance(n.target, ast.Name)
        and n.target.id == "message"
    )
    body_src = ast.get_source_segment(base_src, loop)
    assert body_src, "base scan loop not found"
    fn_src = textwrap.dedent(
        """\
        def _base_scan(messages):
            instruction = ""
            image_data = None
            if isinstance(messages, str):
                messages = [{"role": "user", "content": messages}]
        """
    ) + textwrap.indent(body_src, "    ") + '\n    return instruction, image_data\n'
    ns = {"List": List, "Dict": Dict, "Any": Any, "Optional": Optional}
    exec(compile(fn_src, "<base_scan>", "exec"), ns)
    return ns["_base_scan"]


SCAN = _exec_fn(UITARS, "_scan_uitars_step_messages")
BASE_SCAN = _base_scan_fn()


def _user_msg(url):
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "click the button"},
            {"type": "image_url", "image_url": {"url": url}},
        ],
    }


def test_helper_found():
    assert callable(SCAN) and callable(BASE_SCAN)


def test_well_formed_control():
    msgs = [_user_msg("data:image/png;base64,AAA")]
    assert SCAN(msgs) == ("click the button", "data:image/png;base64,AAA")
    assert BASE_SCAN(msgs) == ("click the button", "data:image/png;base64,AAA")


def test_computer_call_output_control():
    msgs = [
        {
            "type": "computer_call_output",
            "output": {
                "type": "input_image",
                "image_url": "data:image/png;base64,BBB",
            },
        }
    ]
    assert SCAN(msgs)[1] == "data:image/png;base64,BBB"
    assert BASE_SCAN(msgs)[1] == "data:image/png;base64,BBB"


def test_non_dict_message_skipped():
    # A non-dict entry is scanned before the instruction+image break fires.
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "click it"}]},
        "junk string entry",
        {
            "type": "computer_call_output",
            "output": {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
        },
    ]
    try:
        base_result = BASE_SCAN(msgs)
    except AttributeError:
        base_result = "ATTRIBUTE_ERROR"
    assert base_result == "ATTRIBUTE_ERROR", "base must crash on non-dict message"
    assert SCAN(msgs) == ("click it", "data:image/png;base64,AAA")


def test_non_string_image_url_rejected():
    # A dict-shaped image_url["url"] crashed process_image_for_uitars on base
    # (.startswith on a dict); the scan must never hand a non-str through.
    msgs = [_user_msg({"not": "a string"})]
    instruction, image_data = SCAN(msgs)
    assert instruction == "click the button"
    assert image_data is None or isinstance(image_data, str)

    base_instruction, base_image = BASE_SCAN(msgs)
    assert base_instruction == "click the button"
    assert not isinstance(base_image, str), "base leaks a non-str image_data"


def test_non_string_computer_output_url_rejected():
    msgs = [
        {
            "type": "computer_call_output",
            "output": {"type": "input_image", "image_url": ["not", "a", "str"]},
        }
    ]
    _, image_data = SCAN(msgs)
    assert image_data is None or isinstance(image_data, str)
    _, base_image = BASE_SCAN(msgs)
    assert not isinstance(base_image, str), "base leaks a non-str image_data"


def test_string_message_input():
    assert SCAN("do the thing") == ("do the thing", None)
    assert BASE_SCAN("do the thing") == ("do the thing", None)
