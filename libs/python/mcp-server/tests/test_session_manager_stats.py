"""Regression tests for SessionManager.get_session_stats (muse).

Red-on-base: the sync implementation called
``asyncio.run_coroutine_threadsafe(coro, loop).result()`` where ``loop`` is the
*currently running* loop (the MCP ``get_session_stats`` tool is async, so a
loop is always running). Blocking ``.result()`` on the loop's own thread
deadlocks: the scheduled coroutine can never run, so the tool hangs forever.
"""

import asyncio
import importlib.util
import inspect
import threading
from pathlib import Path

_SESSION_MANAGER_PATH = (
    Path(__file__).resolve().parent.parent / "mcp_server" / "session_manager.py"
)


def _load_session_manager():
    spec = importlib.util.spec_from_file_location(
        "mcp_session_manager_under_test", _SESSION_MANAGER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _call_from_running_loop(manager):
    """Call get_session_stats the way the async MCP tool does: on a running loop."""
    outcome = {}

    def runner():
        async def main():
            stats = manager.get_session_stats()
            if inspect.isawaitable(stats):
                stats = await stats
            outcome["stats"] = stats

        try:
            asyncio.run(main())
            outcome["done"] = True
        except Exception as exc:  # noqa: BLE001 - surfaced via outcome
            outcome["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout=5)
    return outcome


def test_get_session_stats_returns_from_running_loop():
    """get_session_stats must return when called with a running event loop."""
    module = _load_session_manager()
    manager = module.SessionManager()
    outcome = _call_from_running_loop(manager)
    assert outcome.get("done"), (
        "get_session_stats() hung when called with a running event loop "
        "(deadlock via run_coroutine_threadsafe(...).result() on the running loop)"
    )
    stats = outcome["stats"]
    assert stats["total_sessions"] == 0
    assert stats["max_concurrent"] == 10
    assert stats["sessions"] == {}


def test_get_session_stats_reflects_sessions():
    """Stats must reflect registered sessions without needing a Computer."""
    module = _load_session_manager()
    manager = module.SessionManager()

    async def seed():
        async with manager._session_lock:
            manager._sessions["s1"] = module.SessionInfo(
                session_id="s1",
                computer=object(),
                created_at=0.0,
                last_activity=0.0,
            )

    asyncio.run(seed())
    outcome = _call_from_running_loop(manager)
    assert outcome.get("done"), "get_session_stats() hung with a session registered"
    stats = outcome["stats"]
    assert stats["total_sessions"] == 1
    assert stats["sessions"]["s1"]["active_tasks"] == 0
