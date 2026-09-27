"""Tests: HuggingFaceLocalAdapter._convert_messages tolerates malformed messages.

_convert_messages converted OpenAI-format messages to HuggingFace format with
unguarded subscripts. Four malformed shapes crashed it out of the litellm
custom-LLM completion path, and the exceptions (KeyError, AttributeError,
TypeError) are not retryable, so each killed the whole run:

- a message missing "role" -> KeyError
- a non-dict message entry -> TypeError (string indices)
- a non-dict content item -> AttributeError (.get on str)
- a non-dict image_url value -> AttributeError (.get on str)
- messages=None -> TypeError (not iterable)

Malformed entries are now skipped (messages/content items), a missing role
defaults to "user" (matching InternVLModel.generate in the same adapter
family), and a non-dict image_url yields an empty url instead of crashing.

The real huggingfacelocal_adapter module is loaded (not copied); only litellm
(not installed here) and the torch-dependent .models sibling are stubbed.
"""

import importlib.util
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
ADAPTER_DIR = os.path.join(_HERE, "..", "cua_agent", "adapters")


def _load_adapter():
    # Stub litellm (not installed in this environment)
    litellm = types.ModuleType("litellm")
    litellm.acompletion = lambda *a, **k: (_ for _ in ()).throw(NotImplementedError())
    litellm.completion = lambda *a, **k: (_ for _ in ()).throw(NotImplementedError())

    class CustomLLM:
        def __init__(self, *a, **k):
            pass

    custom_llm = types.ModuleType("litellm.llms.custom_llm")
    custom_llm.CustomLLM = CustomLLM
    llms_pkg = types.ModuleType("litellm.llms")
    llms_pkg.__path__ = []
    types_utils = types.ModuleType("litellm.types.utils")
    types_utils.GenericStreamingChunk = dict
    types_utils.ModelResponse = dict
    types_pkg = types.ModuleType("litellm.types")
    types_pkg.__path__ = []
    sys.modules["litellm"] = litellm
    sys.modules["litellm.llms"] = llms_pkg
    sys.modules["litellm.llms.custom_llm"] = custom_llm
    sys.modules["litellm.types"] = types_pkg
    sys.modules["litellm.types.utils"] = types_utils

    # Stub the torch-dependent .models sibling; conversion needs no model
    models_stub = types.ModuleType("c69_hf_models")
    models_stub.load_model = lambda *a, **k: None

    pkg = types.ModuleType("c69_hf_pkg")
    pkg.__path__ = [ADAPTER_DIR]
    sys.modules["c69_hf_pkg"] = pkg
    sys.modules["c69_hf_pkg.models"] = models_stub

    spec = importlib.util.spec_from_file_location(
        "c69_hf_pkg.huggingfacelocal_adapter",
        os.path.join(ADAPTER_DIR, "huggingfacelocal_adapter.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["c69_hf_pkg.huggingfacelocal_adapter"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_adapter()
_adapter = _mod.HuggingFaceLocalAdapter.__new__(_mod.HuggingFaceLocalAdapter)


class TestMalformedMessages:
    def test_missing_role_defaults_to_user(self):
        out = _adapter._convert_messages([{"content": "hello"}])
        assert out == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]

    def test_non_dict_message_skipped(self):
        out = _adapter._convert_messages(
            [
                "oops",
                {"role": "user", "content": "kept"},
                None,
            ]
        )
        assert out == [{"role": "user", "content": [{"type": "text", "text": "kept"}]}]

    def test_non_dict_content_item_skipped(self):
        out = _adapter._convert_messages(
            [{"role": "user", "content": ["oops", {"type": "text", "text": "hi"}]}]
        )
        assert out == [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]}
        ]

    def test_non_dict_image_url_yields_empty_url(self):
        out = _adapter._convert_messages(
            [{"role": "user", "content": [{"type": "image_url", "image_url": "not-a-dict"}]}]
        )
        assert out == [{"role": "user", "content": [{"type": "image", "image": ""}]}]

    def test_none_messages_returns_empty(self):
        assert _adapter._convert_messages(None) == []


class TestWellFormedUnchanged:
    def test_string_content(self):
        out = _adapter._convert_messages([{"role": "user", "content": "hello"}])
        assert out == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]

    def test_text_and_image_url_parts(self):
        out = _adapter._convert_messages(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "look"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,AAA"},
                        },
                    ],
                }
            ]
        )
        assert out == [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {"type": "image", "image": "data:image/png;base64,AAA"},
                ],
            }
        ]

    def test_unknown_part_type_ignored(self):
        out = _adapter._convert_messages(
            [{"role": "assistant", "content": [{"type": "mystery", "x": 1}]}]
        )
        assert out == [{"role": "assistant", "content": []}]
