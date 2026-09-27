"""Shape guards in the Azure ML adapter's request preparation and streaming.

AzureMLAdapter._prepare_request iterates caller-supplied messages with
unguarded ``message.copy()`` / ``tool_call.copy()`` / ``function.copy()``
subscripts. Malformed shapes — which survive earlier run-loop stages as raw
provider output (see c69) — raised AttributeError/TypeError out of the
litellm custom-LLM completion path; those exceptions are not retryable, so
each killed the whole run. model=None raised AttributeError on .replace.

The streaming generators only caught json.JSONDecodeError: a malformed
provider chunk (empty/non-list choices, non-dict choices[0], null delta,
non-dict chunk) raised AttributeError/IndexError mid-generator.

Malformed entries are now skipped (prepare) or degrade to empty
deltas (streaming); well-formed behavior unchanged.

Self-contained: litellm is stubbed (absent in some CI); httpx is real but
never hit — the adapter's clients are replaced with fakes. Runs under
pytest or plain ``python3 <file>``.
"""

import io
import json
import os
import sys
import types
import unittest

# Stub litellm and httpx so the adapter imports without them.
_httpx = types.ModuleType("httpx")
_httpx.Client = type("Client", (), {})
_httpx.AsyncClient = type("AsyncClient", (), {})
sys.modules["httpx"] = _httpx

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
    os.path.dirname(__file__), "..", "cua_agent", "adapters", "azure_ml_adapter.py"
)
_spec = importlib.util.spec_from_file_location("azure_ml_adapter", _ADAPTER_PATH)
azure_ml_adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(azure_ml_adapter)

BASE = dict(api_base="https://example.inference.ml.azure.com", api_key="k", model="azure_ml/Fara-7B")


class _FakeStream:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self._lines)


class _FakeClient:
    def __init__(self, lines):
        self._lines = lines

    def stream(self, *a, **k):
        return _FakeStream(self._lines)


def _sse_chunk(payload):
    return "data: " + json.dumps(payload)


class PrepareRequestShapeGuards(unittest.TestCase):
    def setUp(self):
        self.adapter = azure_ml_adapter.AzureMLAdapter.__new__(azure_ml_adapter.AzureMLAdapter)
        self.adapter._client = None
        self.adapter._async_client = None

    def test_non_dict_message_skipped(self):
        url, headers, data = self.adapter._prepare_request(
            messages=["hello", {"role": "user", "content": "hi"}], **BASE
        )
        self.assertEqual(data["messages"], [{"role": "user", "content": "hi"}])

    def test_non_dict_tool_call_skipped(self):
        messages = [
            {
                "role": "assistant",
                "tool_calls": ["oops", {"function": {"arguments": '{"a":1}'}}],
            }
        ]
        url, headers, data = self.adapter._prepare_request(messages=messages, **BASE)
        self.assertEqual(len(data["messages"][0]["tool_calls"]), 1)
        # string arguments still double-encoded
        self.assertEqual(
            data["messages"][0]["tool_calls"][0]["function"]["arguments"], '"{\\"a\\":1}"'
        )

    def test_non_dict_function_skipped(self):
        messages = [{"role": "assistant", "tool_calls": [{"function": "not-a-dict"}]}]
        url, headers, data = self.adapter._prepare_request(messages=messages, **BASE)
        self.assertEqual(data["messages"][0]["tool_calls"], [])

    def test_non_string_arguments_left_alone(self):
        messages = [{"role": "assistant", "tool_calls": [{"function": {"arguments": {"a": 1}}}]}]
        url, headers, data = self.adapter._prepare_request(messages=messages, **BASE)
        self.assertEqual(data["messages"][0]["tool_calls"][0]["function"]["arguments"], {"a": 1})

    def test_model_none(self):
        base = dict(BASE)
        base["model"] = None
        url, headers, data = self.adapter._prepare_request(messages=[], **base)
        self.assertEqual(data["model"], "")

    def test_well_formed_double_encoding_preserved(self):
        messages = [
            {
                "role": "assistant",
                "content": "ok",
                "tool_calls": [{"id": "1", "function": {"name": "f", "arguments": '{"a":1}'}}],
            }
        ]
        url, headers, data = self.adapter._prepare_request(messages=messages, **BASE)
        msg = data["messages"][0]
        self.assertEqual(msg["content"], "ok")  # original message not mutated
        self.assertEqual(msg["tool_calls"][0]["function"]["arguments"], '"{\\"a\\":1}"')
        self.assertEqual(data["model"], "Fara-7B")


class StreamingShapeGuards(unittest.TestCase):
    def _adapter_with_lines(self, lines):
        adapter = azure_ml_adapter.AzureMLAdapter.__new__(azure_ml_adapter.AzureMLAdapter)
        adapter._client = _FakeClient(lines)
        adapter._async_client = None
        return adapter

    def test_non_dict_choice_degrades_gracefully(self):
        lines = [_sse_chunk({"choices": ["oops"]}), "data: [DONE]"]
        chunks = list(self._adapter_with_lines(lines).streaming(**BASE))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "")

    def test_empty_choices_degrades_gracefully(self):
        lines = [_sse_chunk({"choices": []}), "data: [DONE]"]
        chunks = list(self._adapter_with_lines(lines).streaming(**BASE))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "")

    def test_null_delta_degrades_gracefully(self):
        lines = [_sse_chunk({"choices": [{"delta": None, "finish_reason": None}]}), "data: [DONE]"]
        chunks = list(self._adapter_with_lines(lines).streaming(**BASE))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "")

    def test_non_dict_chunk_degrades_gracefully(self):
        lines = [_sse_chunk(["oops"]), "data: [DONE]"]
        chunks = list(self._adapter_with_lines(lines).streaming(**BASE))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "")

    def test_well_formed_chunk_streams(self):
        lines = [
            _sse_chunk({"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]}),
            _sse_chunk({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
            "data: [DONE]",
        ]
        chunks = list(self._adapter_with_lines(lines).streaming(**BASE))
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["text"], "hi")
        self.assertFalse(chunks[0]["is_finished"])
        self.assertTrue(chunks[1]["is_finished"])


if __name__ == "__main__":
    unittest.main()
