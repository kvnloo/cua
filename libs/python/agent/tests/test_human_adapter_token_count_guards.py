"""Tests: human adapter token counting tolerates non-string responses.

The human UI returns its raw "response" verbatim (see _wait_for_completion),
so a UI serving structured payloads hands back a dict/list/None. streaming()
called len(response_text.split()) on it -> AttributeError, killing the
streaming generator. Worse, astreaming() treated the whole
_async_generate_response dict as the response text, so its .split() crashed
on EVERY call. streaming() now counts via _token_count_estimate (None -> 0,
non-string -> str() word count); astreaming() extracts "response" from the
dict like the sync path.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

PATH = (
    Path(__file__).resolve().parents[1]
    / "cua_agent"
    / "adapters"
    / "human_adapter.py"
)


def _load_module():
    litellm = types.ModuleType("litellm")
    llms = types.ModuleType("litellm.llms")
    custom_llm = types.ModuleType("litellm.llms.custom_llm")
    tutils = types.ModuleType("litellm.types.utils")

    class CustomLLM:
        def __init__(self, *a, **k):
            pass

    class GenericStreamingChunk(dict):
        pass

    class ModelResponse:
        pass

    custom_llm.CustomLLM = CustomLLM
    tutils.GenericStreamingChunk = GenericStreamingChunk
    tutils.ModelResponse = ModelResponse
    litellm.acompletion = lambda *a, **k: None
    litellm.completion = lambda *a, **k: None
    sys.modules["litellm"] = litellm
    sys.modules["litellm.llms"] = llms
    sys.modules["litellm.llms.custom_llm"] = custom_llm
    sys.modules["litellm.types.utils"] = tutils

    spec = importlib.util.spec_from_file_location("human_adapter_ut", PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()


def _adapter(response_data):
    a = _mod.HumanAdapter.__new__(_mod.HumanAdapter)
    a.base_url = "http://localhost:1"
    a.timeout = 1.0
    a._generate_response = lambda messages, model: response_data

    async def _async_generate_response(messages, model):
        return response_data

    a._async_generate_response = _async_generate_response
    return a


class TestTokenCountEstimate:
    def test_plain_string(self):
        assert _mod._token_count_estimate("hello world") == 2

    def test_none_is_zero(self):
        assert _mod._token_count_estimate(None) == 0

    def test_dict_coerced(self):
        assert _mod._token_count_estimate({"a": 1}) == len(str({"a": 1}).split())

    def test_list_coerced(self):
        assert _mod._token_count_estimate(["x", "y"]) == len(str(["x", "y"]).split())

    def test_empty_string(self):
        assert _mod._token_count_estimate("") == 0


class TestStreaming:
    def _chunks(self, adapter):
        return list(adapter.streaming(messages=[], model="human"))

    def test_dict_response_counts_and_survives(self):
        a = _adapter({"response": {"structured": True}})
        (chunk,) = self._chunks(a)
        assert chunk["usage"]["completion_tokens"] == len(str({"structured": True}).split())
        assert chunk["usage"]["total_tokens"] == chunk["usage"]["completion_tokens"]

    def test_none_response_counts_zero(self):
        a = _adapter({"response": None})
        (chunk,) = self._chunks(a)
        assert chunk["usage"]["completion_tokens"] == 0

    def test_string_response_unchanged(self):
        a = _adapter({"response": "hello world"})
        (chunk,) = self._chunks(a)
        assert chunk["text"] == "hello world"
        assert chunk["usage"]["completion_tokens"] == 2


class TestAStreaming:
    def _chunks(self, adapter):
        async def run():
            return [c async for c in adapter.astreaming(messages=[], model="human")]

        return asyncio.run(run())

    def test_extracts_response_text(self):
        a = _adapter({"response": "hello world"})
        (chunk,) = self._chunks(a)
        assert chunk["text"] == "hello world"
        assert chunk["usage"]["completion_tokens"] == 2

    def test_dict_response_text_tolerated(self):
        a = _adapter({"response": {"structured": True}})
        (chunk,) = self._chunks(a)
        assert chunk["usage"]["completion_tokens"] == len(str({"structured": True}).split())
