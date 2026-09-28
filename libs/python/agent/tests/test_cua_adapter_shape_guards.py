"""Shape guards in the CUA inference adapter.

CUAAdapter._normalize_model called ``model.startswith`` unguarded, so an
explicit model=None (litellm forwards kwargs verbatim) raised
AttributeError out of the custom-LLM completion path (non-retryable ->
run-kill). _resolve_route did ``"anthropic/" in model`` -> TypeError on
None. completion/acompletion/streaming/astreaming crashed on non-dict
extra_headers (dict.update with a non-mapping), non-dict optional_params
(.items() on a non-dict), and non-dict "headers" (** unpack of a
non-dict). No existing muse/* branch touches cua_adapter.py, so these
shapes were uncovered.

Malformed values are now normalized (model=None -> "", non-dict
extra_headers/optional_params/headers ignored); well-formed behavior is
unchanged.

Self-contained: litellm and cua_core.http are stubbed; the inner
litellm.completion/acompletion calls are captured, never executed. Runs
under pytest or plain ``python3 <file>``.
"""

import os
import sys
import types
import unittest

# Stub litellm so the adapter imports without it.
litellm = types.ModuleType("litellm")
_calls = {}


def _recorder(name):
    def _fn(*a, **k):
        _calls[name] = (a, k)
        return {"ok": name}

    return _fn


async def _acompletion_recorder(*a, **k):
    _calls["acompletion"] = (a, k)
    return {"ok": "acompletion"}


litellm.acompletion = _acompletion_recorder
litellm.completion = _recorder("completion")
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

# Stub cua_core.http.cua_version_headers.
_cua_core = types.ModuleType("cua_core")
_cua_core_http = types.ModuleType("cua_core.http")
_cua_core_http.cua_version_headers = lambda: {"X-CUA-Test": "1"}
_cua_core.http = _cua_core_http
sys.modules["cua_core"] = _cua_core
sys.modules["cua_core.http"] = _cua_core_http

import asyncio  # noqa: E402
import importlib.util  # noqa: E402

_ADAPTER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "cua_agent", "adapters", "cua_adapter.py"
)
_spec = importlib.util.spec_from_file_location("cua_adapter", _ADAPTER_PATH)
cua_adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cua_adapter)


def _make_adapter():
    adapter = cua_adapter.CUAAdapter.__new__(cua_adapter.CUAAdapter)
    adapter.base_url = "https://inference.cua.ai/v1"
    adapter.api_key = "env-key"
    return adapter


BASE = dict(model="cua/n1", api_key="k", messages=[{"role": "user", "content": "hi"}])


class NormalizeModelGuards(unittest.TestCase):
    def setUp(self):
        self.adapter = _make_adapter()

    def test_model_none(self):
        self.assertEqual(self.adapter._normalize_model(None), "")

    def test_model_non_string(self):
        self.assertEqual(self.adapter._normalize_model(["cua/n1"]), "")

    def test_prefix_stripping_preserved(self):
        self.assertEqual(self.adapter._normalize_model("cua/n1"), "n1")
        self.assertEqual(self.adapter._normalize_model("anthropic/x"), "x")
        self.assertEqual(self.adapter._normalize_model("gemini/y"), "y")
        self.assertEqual(self.adapter._normalize_model("plain"), "plain")


class ResolveRouteGuards(unittest.TestCase):
    def setUp(self):
        self.adapter = _make_adapter()

    def test_model_none(self):
        model, base = self.adapter._resolve_route(None, "https://x/v1")
        self.assertEqual(model, "openai/")
        self.assertEqual(base, "https://x/v1")

    def test_anthropic_route_preserved(self):
        model, base = self.adapter._resolve_route("anthropic/a", "https://x/v1")
        self.assertEqual(model, "anthropic/a")
        self.assertEqual(base, "https://x")

    def test_gemini_route_preserved(self):
        model, base = self.adapter._resolve_route("gemini/g", "https://x/v1")
        self.assertEqual(model, "gemini/g")
        self.assertEqual(base, "https://x/v1/gemini")


class CompletionShapeGuards(unittest.TestCase):
    def setUp(self):
        self.adapter = _make_adapter()

    def _params(self, **kw):
        _calls.clear()
        self.adapter.completion(**dict(BASE, **kw))
        return _calls["completion"][1]

    def test_model_none(self):
        params = self._params(model=None)
        self.assertEqual(params["model"], "openai/")

    def test_non_dict_extra_headers_ignored(self):
        params = self._params(extra_headers="oops")
        self.assertEqual(set(params["extra_headers"]), {"Authorization"})

    def test_non_dict_optional_params_ignored(self):
        params = self._params(optional_params=["oops"])
        self.assertEqual(params["model"], "openai/n1")

    def test_non_dict_headers_dropped(self):
        params = self._params(headers="oops")
        self.assertIsInstance(params["headers"], dict)
        self.assertIn("X-CUA-Test", params["headers"])

    def test_well_formed_preserved(self):
        params = self._params(
            extra_headers={"X-Custom": "1"},
            optional_params={"temperature": 0.5, "api_key": "evil"},
            headers={"X-Caller": "2"},
        )
        self.assertEqual(params["extra_headers"]["X-Custom"], "1")
        self.assertIn("Authorization", params["extra_headers"])
        self.assertEqual(params["temperature"], 0.5)
        self.assertEqual(params["api_key"], "k")  # optional_params "evil" filtered
        self.assertEqual(params["headers"]["X-Caller"], "2")
        self.assertIn("X-CUA-Test", params["headers"])


class AcompletionShapeGuards(unittest.TestCase):
    def setUp(self):
        self.adapter = _make_adapter()

    def test_model_none_and_malformed_kwargs(self):
        _calls.clear()
        asyncio.run(
            self.adapter.acompletion(
                **dict(BASE, model=None, extra_headers=42, optional_params="x")
            )
        )
        params = _calls["acompletion"][1]
        self.assertEqual(params["model"], "openai/")
        self.assertEqual(set(params["extra_headers"]), {"Authorization"})


class StreamingShapeGuards(unittest.TestCase):
    def setUp(self):
        self.adapter = _make_adapter()

    def test_streaming_malformed_model_and_headers(self):
        _calls.clear()
        chunks = list(self.adapter.streaming(**dict(BASE, model=None, headers=["x"])))
        params = _calls["completion"][1]
        self.assertEqual(params["model"], "openai/")
        self.assertTrue(params["stream"])
        self.assertIsInstance(params["headers"], dict)
        self.assertIn("X-CUA-Test", params["headers"])
        # Stubbed completion returns a dict; iteration yields its keys.
        self.assertEqual(chunks, ["ok"])

    def test_astreaming_malformed_extra_headers(self):
        _calls.clear()

        async def _agen():
            yield {"ok": "acompletion"}

        async def _fake_acomp(*a, **k):
            _calls["acompletion"] = (a, k)
            return _agen()

        old_acomp = cua_adapter.acompletion
        cua_adapter.acompletion = _fake_acomp
        try:  # noqa: E402

            async def _drain():
                out = []
                async for c in self.adapter.astreaming(
                    **dict(BASE, extra_headers=None, optional_params=7)
                ):
                    out.append(c)
                return out

            out = asyncio.run(_drain())
        finally:
            cua_adapter.acompletion = old_acomp
        params = _calls["acompletion"][1]
        self.assertEqual(set(params["extra_headers"]), {"Authorization"})
        self.assertTrue(params["stream"])
        self.assertEqual(out, [{"ok": "acompletion"}])


if __name__ == "__main__":
    unittest.main()
