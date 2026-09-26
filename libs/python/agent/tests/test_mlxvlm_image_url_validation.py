"""Image-URL input validation in the MLX VLM adapter.

_mconvert_messages is fed model-generated image_url values. Two malformed
shapes previously surfaced as misleading errors:

1. A data: URL without a comma raised bare ``IndexError: list index out of
   range`` (``image_url.split(",")[1]``) — it should name the malformed
   data-URL shape.
2. A remote http(s) URL fell through to ``Image.open`` on the URL as a
   local path, surfacing ``FileNotFoundError`` — the local adapter does
   not fetch remote images, so it should say so.

Both now raise ValueError with an actionable message. Valid data: URLs
and valid local file paths keep working unchanged.

Self-contained: litellm/mlx_vlm are stubbed (absent in some CI), PIL is
real. Runs under pytest or plain ``python3 <file>``.
"""

import base64
import io
import os
import sys
import tempfile
import types
import unittest

# Stub litellm (optional dep in some environments) so the adapter imports.
litellm = types.ModuleType("litellm")
litellm.acompletion = lambda *a, **k: None
litellm.completion = lambda *a, **k: None
litellm_llms = types.ModuleType("litellm.llms")
litellm_custom = types.ModuleType("litellm.llms.custom_llm")
litellm_custom.CustomLLM = type("CustomLLM", (), {"__init__": lambda self, **k: None})
litellm_types = types.ModuleType("litellm.types")
litellm_types_utils = types.ModuleType("litellm.types.utils")
litellm_types_utils.GenericStreamingChunk = dict
litellm_types_utils.ModelResponse = dict
for _name, _mod in {
    "litellm": litellm,
    "litellm.llms": litellm_llms,
    "litellm.llms.custom_llm": litellm_custom,
    "litellm.types": litellm_types,
    "litellm.types.utils": litellm_types_utils,
}.items():
    sys.modules[_name] = _mod

# Load the adapter module by file path (the cua_agent package __init__ pulls
# litellm submodules that are not stubbed here).
import importlib.util  # noqa: E402

_ADAPTER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "cua_agent", "adapters", "mlxvlm_adapter.py"
)
_spec = importlib.util.spec_from_file_location("mlxvlm_adapter", _ADAPTER_PATH)
mlxvlm_adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mlxvlm_adapter)
from PIL import Image  # noqa: E402


def _adapter():
    return mlxvlm_adapter.MLXVLMAdapter.__new__(mlxvlm_adapter.MLXVLMAdapter)


def _messages(url):
    return [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]}]


def _tiny_data_url():
    img = Image.new("RGB", (56, 56), (1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class TestMlxVlmImageUrlValidation(unittest.TestCase):
    def test_malformed_data_url_names_shape(self):
        with self.assertRaises(ValueError) as ctx:
            _adapter()._convert_messages(_messages("data:image/png;base64"))
        self.assertIn("Malformed data image URL", str(ctx.exception))

    def test_remote_url_rejected_with_reason(self):
        with self.assertRaises(ValueError) as ctx:
            _adapter()._convert_messages(_messages("https://example.com/x.png"))
        self.assertIn("Remote image URLs are not supported", str(ctx.exception))

    def test_valid_data_url_unchanged(self):
        _, images, _, _ = _adapter()._convert_messages(_messages(_tiny_data_url()))
        self.assertEqual(len(images), 1)

    def test_valid_file_path_unchanged(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            Image.new("RGB", (56, 56), (4, 5, 6)).save(path, format="PNG")
            _, images, _, _ = _adapter()._convert_messages(_messages(path))
            self.assertEqual(len(images), 1)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
