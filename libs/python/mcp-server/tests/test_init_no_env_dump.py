"""Guard: mcp_server/__init__.py must not dump the environment to disk (muse).

Regression: the package __init__ used to write the full process environment
(including any API keys / tokens in env vars) to /tmp/mcp_server_debug.log on
every import — world-readable local secret disclosure from leftover debug
code. This pins its removal.
"""

from pathlib import Path

_INIT_PATH = Path(__file__).resolve().parent.parent / "mcp_server" / "__init__.py"


def test_init_does_not_dump_environment():
    source = _INIT_PATH.read_text()
    assert "mcp_server_debug.log" not in source, (
        "mcp_server/__init__.py writes a debug log again"
    )
    assert "os.environ" not in source, (
        "mcp_server/__init__.py reads the process environment again"
    )
