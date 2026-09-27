"""Shape guards in the Yutori adapter's parameter building.

YutoriAdapter._normalize_model called ``model.startswith`` unguarded, so
model=None raised AttributeError out of the litellm custom-LLM
completion path (non-retryable -> run-kill). _build_params crashed on
non-dict ``extra_headers`` (dict.update with a non-mapping) and non-dict
``optional_params`` (.items() on a non-dict). (The existing
yutori-malformed-model-output branch covers model-*output* conversion,
not these kwargs shapes.)

Malformed entries are now normalized (model=None -> ''), and non-dict
extra_headers/optional_params are ignored instead of crashing;
well-formed behavior is unchanged.

Self-contained: litellm is stubbed (absent in some CI); the inner
litellm.completion call is never reached — _build_params is tested
directly. Runs under pytest or plain ``python3 <file>``.
"""

import os
import sys
import types
import unittest

# Stub litellm so the adapter imports without it.
litellm = types.ModuleType("litellm")
litellm.acompletion = lambda *a, **k: None
litellm.completion = lambda *a, **k: None
_litellm_llms = types.ModuleType("litellm.llms")
_litellm_custom = types.ModuleType("litellm.llms.custom_llm")
_litellm_custom.CustomLLM = type("CustomLLM", (), {"__init__": lambda self, **k: None})
_litellm_types = types.ModuleType("litellm.types")
_litellm_types_utils = types.ModuleType("litellm.types.utils")
_litellm_types_utils.GenericStreamingChunk = dict
_litellm_types_utils.ModelResponse = dict
for _name, _mod in {
    "litellm": litellm,
    "litellm.llms": _litellm_llms,
    "litellm.llms.custom_llm": _litellm_custom,
    "litellm.types": _litellm_types,
    "litellm.types.utils": _litellm_types_utils,
}.items():
    sys.modules[_name] = _mod

import importlib.util  # noqa: E402

_ADAPTER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "cua_agent", "adapters", "yutori_adapter.py"
)
_spec = importlib.util.spec_from_file_location("yutori_adapter", _ADAPTER_PATH)
yutori_adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(yutori_adapter)

BASE = dict(model="yutori/n1", api_key="k", messages=[{"role": "user", "content": "hi"}])


class BuildParamsShapeGuards(unittest.TestCase):
    def setUp(self):
        self.adapter = yutori_adapter.YutoriAdapter.__new__(yutori_adapter.YutoriAdapter)
        self.adapter.base_url = "https://api.yutori.com/v1"
        self.adapter.api_key = "env-key"

    def test_model_none(self):
        params = self.adapter._build_params(dict(BASE, model=None))
        self.assertEqual(params["model"], "openai/")

    def test_non_dict_extra_headers_ignored(self):
        params = self.adapter._build_params(dict(BASE, extra_headers="oops"))
        self.assertIn("Authorization", params["extra_headers"])
        self.assertEqual(len(params["extra_headers"]), 1)

    def test_non_dict_optional_params_ignored(self):
        params = self.adapter._build_params(dict(BASE, optional_params=["oops"]))
        self.assertEqual(params["model"], "openai/n1")

    def test_well_formed_preserved(self):
        params = self.adapter._build_params(
            dict(
                BASE,
                extra_headers={"X-Custom": "1"},
                optional_params={"temperature": 0.5, "api_key": "evil"},
                temperature=0.7,
            )
        )
        self.assertEqual(params["model"], "openai/n1")
        self.assertEqual(params["extra_headers"]["X-Custom"], "1")
        self.assertTrue(params["extra_headers"]["Authorization"].startswith("Bearer "))
        # protected optional_params keys stay filtered; others forwarded
        self.assertEqual(params["temperature"], 0.5)  # optional_params applied last (pre-existing)
        self.assertEqual(params["api_key"], "k")  # "evil" from optional_params filtered


if __name__ == "__main__":
    unittest.main()
