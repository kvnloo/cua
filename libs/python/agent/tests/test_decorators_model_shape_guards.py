"""Shape guards for non-string model names in agent-loop registration.

ComputerAgent(model=None) reached find_agent_config(None), which crashed
in _strip_cua_prefix with AttributeError (None.split) and in
AgentConfigInfo.matches_model with TypeError (re.match on a non-string
subject) — before the intended ValueError("No agent config found for
model: ...") could fire. No existing muse/* branch touches decorators.py
or the matches_model path in types.py, so these shapes were uncovered.

Non-string models now degrade through the intended lookup-miss path:
_strip_cua_prefix passes them through, find_agent_config returns None,
and matches_model returns False. Well-formed routing is unchanged.

Self-contained: litellm and pydantic are stubbed; runs under pytest or
plain ``python3 <file>``.
"""

import os
import re
import sys
import types
import unittest

# Stub litellm (types.py imports names from it).
litellm = types.ModuleType("litellm")
litellm.ResponseInputParam = object
litellm.ResponsesAPIResponse = object
litellm.ToolParam = object
sys.modules["litellm"] = litellm

# Stub pydantic.BaseModel with a minimal kwarg/defaults implementation.
pydantic = types.ModuleType("pydantic")


class BaseModel:
    def __init__(self, **kwargs):
        annotations = {}
        for klass in reversed(type(self).__mro__):
            annotations.update(getattr(klass, "__annotations__", {}))
        for name in annotations:
            if name in kwargs:
                setattr(self, name, kwargs.pop(name))
            elif hasattr(type(self), name):
                setattr(self, name, getattr(type(self), name))
        for k, v in kwargs.items():
            setattr(self, k, v)


pydantic.BaseModel = BaseModel
sys.modules["pydantic"] = pydantic

# Stub the cua_agent package so decorators.py loads with relative imports.
_pkg = types.ModuleType("cua_agent")
_pkg.__path__ = []
sys.modules["cua_agent"] = _pkg

import importlib.util  # noqa: E402


def _load(mod_name, rel_path):
    path = os.path.join(os.path.dirname(__file__), "..", "cua_agent", rel_path)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


types_mod = _load("cua_agent.types", "types.py")
decorators = _load("cua_agent.decorators", "decorators.py")


class StripCuaPrefixGuards(unittest.TestCase):
    def test_model_none(self):
        self.assertIsNone(decorators._strip_cua_prefix(None))

    def test_model_non_string(self):
        self.assertEqual(decorators._strip_cua_prefix(123), 123)

    def test_well_formed_preserved(self):
        self.assertEqual(
            decorators._strip_cua_prefix("cua/google/gemini-3-flash-preview"),
            "gemini-3-flash-preview",
        )
        self.assertEqual(
            decorators._strip_cua_prefix("gemini-3-flash-preview"),
            "gemini-3-flash-preview",
        )
        self.assertEqual(decorators._strip_cua_prefix("cua/x"), "cua/x")


class FindAgentConfigGuards(unittest.TestCase):
    def test_model_none_returns_none(self):
        self.assertIsNone(decorators.find_agent_config(None))

    def test_model_non_string_returns_none(self):
        self.assertIsNone(decorators.find_agent_config(123))
        self.assertIsNone(decorators.find_agent_config(["openai/gpt"]))

    def test_unknown_string_still_none(self):
        self.assertIsNone(decorators.find_agent_config("no-such-model-xyz"))

    def test_registered_model_still_resolves(self):
        @decorators.register_agent(models=r"test-guard-model")
        class _Cfg:
            async def predict_step(self, *a, **k):
                return {}

            async def predict_click(self, *a, **k):
                return None

            def get_capabilities(self):
                return ["step"]

        try:
            found = decorators.find_agent_config("test-guard-model-v1")
            self.assertIsNotNone(found)
            self.assertEqual(found.models_regex, r"test-guard-model")
        finally:
            decorators._agent_configs[:] = [
                c for c in decorators._agent_configs if c.models_regex != r"test-guard-model"
            ]


class MatchesModelGuards(unittest.TestCase):
    def setUp(self):
        self.info = types_mod.AgentConfigInfo(
            agent_class=object, models_regex=r"openai/.*"
        )

    def test_model_none(self):
        self.assertFalse(self.info.matches_model(None))

    def test_model_non_string(self):
        self.assertFalse(self.info.matches_model(123))

    def test_well_formed_preserved(self):
        self.assertTrue(self.info.matches_model("openai/gpt-4o"))
        self.assertFalse(self.info.matches_model("anthropic/claude"))


if __name__ == "__main__":
    unittest.main()
