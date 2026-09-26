"""Regression tests: skill-name path traversal in the serve-mcp skills tools.

`skills_read` and `skills_delete` take a model-controlled skill name and join it
onto ``~/.cua/skills``. Before the fix, names like ``../../victim`` escaped the
skills directory, so ``skills_delete`` could delete arbitrary directories.
"""

import asyncio
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

MCP_MODULE_PATH = Path(
    os.environ.get(
        "CUA_MCP_UNDER_TEST",
        Path(__file__).resolve().parents[2] / "cua_cli" / "commands" / "mcp.py",
    )
)


def _ensure_fastmcp_stub():
    """Provide a minimal mcp.server.fastmcp stub when the real package is absent.

    The skills-tool registration only needs the ``Context`` annotation at
    function-definition time; the stub keeps these tests runnable without the
    optional ``cua-cli[mcp]`` extra.
    """
    try:
        import mcp.server.fastmcp  # noqa: F401
        return
    except ImportError:
        pass
    fake_fastmcp = types.ModuleType("mcp.server.fastmcp")
    fake_fastmcp.Context = object
    fake_server = types.ModuleType("mcp.server")
    fake_mcp = types.ModuleType("mcp")
    fake_server.fastmcp = fake_fastmcp
    fake_mcp.server = fake_server
    sys.modules.setdefault("mcp", fake_mcp)
    sys.modules.setdefault("mcp.server", fake_server)
    sys.modules.setdefault("mcp.server.fastmcp", fake_fastmcp)


def _load_mcp_module():
    _ensure_fastmcp_stub()
    spec = importlib.util.spec_from_file_location("cua_mcp_cmd_under_test", MCP_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mcp_module():
    return _load_mcp_module()


class FakeServer:
    """Minimal stand-in for FastMCP: collects registered tool functions."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def skills_env(mcp_module, tmp_path, monkeypatch):
    """Fake $HOME with a skills dir, one legit skill, and an outside victim dir."""
    fake_home = tmp_path / "home"
    skills_dir = fake_home / ".cua" / "skills"
    (skills_dir / "legit").mkdir(parents=True)
    (skills_dir / "legit" / "SKILL.md").write_text("# Legit\n")
    victim = fake_home / "victim"
    victim.mkdir()
    (victim / "important.txt").write_text("do not delete")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    server = FakeServer()
    asyncio.run(
        mcp_module._register_skills_tools(
            server, {mcp_module.Permission.SKILLS_READ, mcp_module.Permission.SKILLS_DELETE}
        )
    )
    return server.tools, skills_dir, victim


class TestResolveSkillDir:
    def test_rejects_parent_traversal(self, mcp_module, tmp_path):
        base = tmp_path / "skills"
        assert mcp_module._resolve_skill_dir(base, "..") is None
        assert mcp_module._resolve_skill_dir(base, "../../etc") is None
        assert mcp_module._resolve_skill_dir(base, "a/../../etc") is None

    def test_rejects_absolute_path(self, mcp_module, tmp_path):
        base = tmp_path / "skills"
        assert mcp_module._resolve_skill_dir(base, "/etc") is None

    def test_rejects_empty_name(self, mcp_module, tmp_path):
        base = tmp_path / "skills"
        assert mcp_module._resolve_skill_dir(base, "") is None

    def test_accepts_plain_and_nested_names(self, mcp_module, tmp_path):
        base = tmp_path / "skills"
        resolved = mcp_module._resolve_skill_dir(base, "my-skill")
        assert resolved == (base / "my-skill").resolve()
        resolved = mcp_module._resolve_skill_dir(base, "a/../my-skill")
        assert resolved == (base / "my-skill").resolve()


class TestSkillsDeleteTraversal:
    def test_traversal_delete_is_blocked(self, skills_env):
        tools, skills_dir, victim = skills_env
        out = json.loads(asyncio.run(tools["skills_delete"](ctx=None, name="../../victim")))
        assert "error" in out
        assert victim.exists(), "directory outside the skills dir must not be deleted"
        assert (victim / "important.txt").exists()

    def test_legit_delete_still_works(self, skills_env):
        tools, skills_dir, victim = skills_env
        out = json.loads(asyncio.run(tools["skills_delete"](ctx=None, name="legit")))
        assert out.get("success") is True
        assert not (skills_dir / "legit").exists()


class TestSkillsReadTraversal:
    def test_traversal_read_is_blocked(self, skills_env):
        tools, skills_dir, victim = skills_env
        out = json.loads(asyncio.run(tools["skills_read"](ctx=None, name="../../victim")))
        assert "error" in out

    def test_legit_read_still_works(self, skills_env):
        tools, skills_dir, victim = skills_env
        out = json.loads(asyncio.run(tools["skills_read"](ctx=None, name="legit")))
        assert out["name"] == "legit"
        assert "Legit" in out["content"]
