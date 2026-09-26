"""Regression tests: sessions marked for shutdown must not leak as zombies.

Bug: SessionManager.cleanup_session() marks a session is_shutting_down=True when
it still has active tasks, intending to reclaim it once the tasks finish. But
unregister_task() never checked that flag, and the background cleanup loop
explicitly skips is_shutting_down sessions — so the session (and its pooled
computer) was never reclaimed.

These tests import session_manager directly (stdlib-only module) with a stubbed
pool so no native Computer/driver is required.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

# Load session_manager.py directly by file path: the package __init__ imports
# server.py (needs mcp/anyio, absent in this sandbox), but session_manager is
# stdlib-only and importable standalone.
_MOD_PATH = Path(__file__).resolve().parent.parent / "mcp_server" / "session_manager.py"
_spec = importlib.util.spec_from_file_location("session_manager", _MOD_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SessionManager = _mod.SessionManager


class _StubPool:
    """Minimal pool stub: hands out dummy computers, tracks releases."""

    def __init__(self):
        self.released = []

    async def acquire(self):
        return object()

    async def release(self, computer):
        self.released.append(computer)


def _make_manager() -> SessionManager:
    mgr = SessionManager()
    mgr._computer_pool = _StubPool()
    return mgr


async def _marked_session_lifecycle() -> SessionManager:
    mgr = _make_manager()
    async with mgr.get_session("s1"):
        await mgr.register_task("s1", "t1")
        await mgr.cleanup_session("s1")
        assert mgr._sessions["s1"].is_shutting_down, "session should be marked for shutdown"
        await mgr.unregister_task("s1", "t1")
    return mgr


def test_marked_session_reclaimed_after_last_task():
    """Marked-for-shutdown session is reclaimed when its last task unregisters."""
    mgr = asyncio.run(_marked_session_lifecycle())
    assert "s1" not in mgr._sessions, "zombie session leaked after tasks drained"
    assert len(mgr._computer_pool.released) == 1, "computer never returned to pool"


def test_unmarked_session_survives_task_drain():
    """Normal sessions are NOT destroyed when their tasks finish (idle reclamation only)."""
    async def scenario():
        mgr = _make_manager()
        async with mgr.get_session("s2"):
            await mgr.register_task("s2", "t1")
            await mgr.unregister_task("s2", "t1")
        return mgr

    mgr = asyncio.run(scenario())
    assert "s2" in mgr._sessions, "unmarked session must survive task drain"
    assert mgr._computer_pool.released == [], "computer must not be released for live session"


def test_cleanup_without_tasks_is_immediate():
    """cleanup_session with no active tasks reclaims immediately (unchanged behavior)."""
    async def scenario():
        mgr = _make_manager()
        async with mgr.get_session("s3"):
            pass
        await mgr.cleanup_session("s3")
        return mgr

    mgr = asyncio.run(scenario())
    assert "s3" not in mgr._sessions


if __name__ == "__main__":
    test_marked_session_reclaimed_after_last_task()
    test_unmarked_session_survives_task_drain()
    test_cleanup_without_tasks_is_immediate()
    print("OK: 3/3 zombie-session tests passed")
