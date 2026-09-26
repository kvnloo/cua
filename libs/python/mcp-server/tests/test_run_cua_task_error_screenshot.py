"""run_cua_task error path must screenshot the resolved session (muse).

Red-on-base: the error handler checked ``if session_id:`` — the *requested*
id. With the default ``session_id=None`` (auto-created session, the common
case) it was always False, so the failure screenshot was never taken even
though the session existed. The fix captures the resolved id on session open.
"""

import asyncio
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock

PKG_DIR = Path(__file__).resolve().parent.parent / "mcp_server"


def _load_server_module():
    """Load mcp_server/server.py with its heavy deps stubbed out."""
    captured = {}

    class FakeFastMCP:
        def __init__(self, name=None):
            pass

        def tool(self, **kwargs):
            def deco(fn):
                captured[fn.__name__] = fn
                return fn

            return deco

    def make_module(name, **attrs):
        mod = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[name] = mod
        return mod

    # stub mcp.server.fastmcp (+ Context/Image)
    make_module("mcp")
    make_module("mcp.server")
    fastmcp = make_module(
        "mcp.server.fastmcp", Context=MagicMock, FastMCP=FakeFastMCP
    )
    make_module("mcp.server.fastmcp.utilities")
    make_module(
        "mcp.server.fastmcp.utilities.types",
        Image=type("Image", (), {"__init__": lambda self, format=None, data=b"": setattr(self, "data", data)}),
    )
    sys.modules["mcp"].server = sys.modules["mcp.server"]
    sys.modules["mcp.server"].fastmcp = fastmcp

    # stub computer / cua_agent
    make_module("computer", Computer=MagicMock)

    # anyio is only used by main(); stub it so the module imports
    make_module("anyio", run=MagicMock())

    class BoomAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, messages):
            raise RuntimeError("agent exploded")
            yield  # pragma: no cover - makes this an async generator

    make_module("cua_agent", ComputerAgent=BoomAgent)

    # load mcp_server/server.py as fakepkg.server so its relative import works
    pkg = types.ModuleType("fakepkg")
    pkg.__path__ = [str(PKG_DIR)]
    sys.modules["fakepkg"] = pkg
    import importlib

    module = importlib.import_module("fakepkg.server")
    return module, captured


class FakeSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.computer = MagicMock()

    async def _shot(self):
        return b"real-screenshot"

    def __post_init__(self):
        pass


class FakeSessionManager:
    def __init__(self):
        self.opened_with = []

    @asynccontextmanager
    async def get_session(self, session_id=None):
        if session_id is None:
            session_id = "auto-generated-123"
        self.opened_with.append(session_id)
        session = FakeSession(session_id)
        session.computer.interface.screenshot = FakeSession._shot.__get__(
            session, FakeSession
        )
        yield session

    async def register_task(self, session_id, task_id):
        pass

    async def unregister_task(self, session_id, task_id):
        pass


def test_error_path_screenshots_resolved_session():
    module, captured = _load_server_module()
    fake_manager = FakeSessionManager()
    module.get_session_manager = lambda: fake_manager

    ctx = MagicMock()
    run_cua_task = captured["run_cua_task"]

    message, image = asyncio.run(run_cua_task(ctx, "do the thing", None))

    assert "agent exploded" in message
    # error path must have re-opened the AUTO-CREATED session for a screenshot
    # (the fake resolves None -> "auto-generated-123" exactly like the real
    # manager's uuid generation; on base the error path never re-opened at all)
    assert fake_manager.opened_with == ["auto-generated-123", "auto-generated-123"], (
        f"error path did not screenshot the resolved session: {fake_manager.opened_with}"
    )
    assert image.data == b"real-screenshot", (
        "error path returned the placeholder instead of the session screenshot"
    )
