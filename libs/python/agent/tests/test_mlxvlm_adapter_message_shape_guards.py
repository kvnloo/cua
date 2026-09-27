"""Message-shape guards in the MLX VLM adapter's message conversion.

MLXVLMAdapter._convert_messages read ``message["role"]`` and
``item.get("type")`` unguarded, and assumed ``item["image_url"]`` was a
dict-of-str. Malformed shapes that survive earlier run-loop stages as raw
provider output raised TypeError/AttributeError/KeyError out of the
litellm custom-LLM completion path; those exceptions are not retryable,
so each killed the whole run. (The existing mlxvlm-image-url-errors
branch covers data-URL *value* parsing only, not these shapes.)

Non-dict messages are now skipped; a missing role defaults to "user"
(matching the HuggingFaceLocalAdapter convention in the same family);
non-dict content items and non-dict/non-string image_url values are
skipped. Well-formed conversion is unchanged.

Self-contained: litellm/mlx_vlm are stubbed (absent in some CI); PIL is
real but never touched — shape tests use text content or fail before
image loading. Runs under pytest or plain ``python3 <file>``.
"""

import os
import sys
import types
import unittest

# Stub litellm and mlx_vlm so the adapter imports without them.
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
    os.path.dirname(__file__), "..", "cua_agent", "adapters", "mlxvlm_adapter.py"
)
_spec = importlib.util.spec_from_file_location("mlxvlm_adapter", _ADAPTER_PATH)
mlxvlm_adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mlxvlm_adapter)


class ConvertMessagesShapeGuards(unittest.TestCase):
    def setUp(self):
        self.adapter = mlxvlm_adapter.MLXVLMAdapter.__new__(mlxvlm_adapter.MLXVLMAdapter)

    def test_non_dict_message_skipped(self):
        processed, images, _, _ = self.adapter._convert_messages(
            ["hello", {"role": "user", "content": "hi"}]
        )
        self.assertEqual(processed, [{"role": "user", "content": "hi"}])
        self.assertEqual(images, [])

    def test_missing_role_defaults_to_user(self):
        processed, images, _, _ = self.adapter._convert_messages([{"content": "hi"}])
        self.assertEqual(processed, [{"role": "user", "content": "hi"}])
        self.assertEqual(images, [])

    def test_non_dict_content_item_skipped(self):
        processed, images, _, _ = self.adapter._convert_messages(
            [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "a"}, "oops", {"type": "text", "text": "b"}],
                }
            ]
        )
        self.assertEqual(
            processed[0]["content"],
            [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
        )
        self.assertEqual(images, [])

    def test_non_dict_image_url_skipped(self):
        processed, images, _, _ = self.adapter._convert_messages(
            [{"role": "user", "content": [{"type": "image_url", "image_url": 42}]}]
        )
        self.assertEqual(processed[0]["content"], [])
        self.assertEqual(images, [])

    def test_non_string_url_skipped(self):
        processed, images, _, _ = self.adapter._convert_messages(
            [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": 42}}]}]
        )
        self.assertEqual(processed[0]["content"], [])
        self.assertEqual(images, [])

    def test_well_formed_text_content_preserved(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": [{"type": "text", "text": "hello"}]},
        ]
        processed, images, _, _ = self.adapter._convert_messages(messages)
        self.assertEqual(processed[0], {"role": "system", "content": "sys"})
        self.assertEqual(
            processed[1]["content"], [{"type": "text", "text": "hello"}]
        )
        self.assertEqual(images, [])


if __name__ == "__main__":
    unittest.main()
