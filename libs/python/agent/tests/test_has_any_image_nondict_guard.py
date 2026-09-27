"""Red/green test: image-scan helpers must skip non-dict messages.

Five nested _has_any_image closures (generic_vlm, opencua, qwen35, yutori,
fara/config) and yutori's module-level _convert_images_to_n1_format all
called msg.get("content") on every message -- a malformed (non-dict) entry in
history raised AttributeError and killed predict_step before any model call.

_convert_images_to_n1_format additionally called .get("url") on a truthy
non-dict image_url value and wrote back through part["image_url"]["url"]
unguarded; both are now dict-guarded.

Self-contained: extracts the real functions by AST and exec's them in
isolation (the loops need litellm etc. to import).
"""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional

LOOPS_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "loops"


def _find(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


def _exec_fn(path, name, extra_ns=None):
    tree = ast.parse(Path(path).read_text())
    node = _find(tree, name)
    ns = {"List": List, "Dict": Dict, "Any": Any, "Optional": Optional}
    ns.update(extra_ns or {})
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    return ns[name]


HAS_ANY_IMAGE = {
    name: _exec_fn(LOOPS_DIR / p, "_has_any_image")
    for name, p in {
        "generic_vlm": "generic_vlm.py",
        "opencua": "opencua.py",
        "qwen35": "qwen35.py",
        "yutori": "yutori.py",
        "fara": "fara/config.py",
    }.items()
}

CONVERT = _exec_fn(
    LOOPS_DIR / "yutori.py",
    "_convert_images_to_n1_format",
    extra_ns={"_prepare_image_for_n1": lambda b64: "WEBPBYTES"},
)


def test_helpers_found():
    assert len(HAS_ANY_IMAGE) == 5


def test_has_any_image_skips_non_dict():
    for name, fn in HAS_ANY_IMAGE.items():
        assert fn([42, "x", None, ["l"], {"role": "user", "content": "hi"}]) is False, name


def test_has_any_image_detects_images():
    for name, fn in HAS_ANY_IMAGE.items():
        assert (
            fn(
                [
                    42,
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": "data:..."}}
                        ],
                    },
                ]
            )
            is True
        ), name


def test_convert_skips_non_dict_messages():
    msgs = [42, None, {"role": "user", "content": "hi"}]
    out = CONVERT(msgs)
    assert out == msgs


def test_convert_tolerates_string_image_url():
    """A truthy non-dict image_url must not raise; nothing rewritten."""
    part = {"type": "image_url", "image_url": "data:image/png;base64,xx"}
    msgs = [{"role": "user", "content": [part]}]
    out = CONVERT(msgs)
    assert out[0]["content"][0]["image_url"] == "data:image/png;base64,xx"


def test_convert_rewrites_data_url_images():
    part = {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}
    out = CONVERT([{"role": "user", "content": [part]}])
    assert out[0]["content"][0]["image_url"]["url"] == "data:image/webp;base64,WEBPBYTES"


if __name__ == "__main__":
    test_helpers_found()
    test_has_any_image_skips_non_dict()
    test_has_any_image_detects_images()
    test_convert_skips_non_dict_messages()
    test_convert_tolerates_string_image_url()
    test_convert_rewrites_data_url_images()
    print("PASS all 6")
