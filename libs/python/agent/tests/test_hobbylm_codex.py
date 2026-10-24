"""Exercise the CLI adapter through a mocked subprocess boundary, not source scans."""

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "hobbylm_codex_runtime", Path(__file__).parents[1] / "examples/hobbylm_eval/codex_runtime.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def events(*items):
    return "\n".join(json.dumps(item) for item in items)


def test_cli_receives_matched_input_without_native_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(MODULE.Path, "mkdir", lambda *args, **kwargs: None)
    run = Mock(
        return_value=subprocess.CompletedProcess(
            [],
            0,
            events(
                {"type": "item.completed", "item": {"type": "agent_message", "text": "KEY MUTE"}},
                {"type": "turn.completed", "usage": {"input_tokens": 300, "output_tokens": 3}},
            ),
            "",
        )
    )
    monkeypatch.setattr(MODULE.subprocess, "run", run)
    monkeypatch.setenv("WAYLAND_DISPLAY", "host-display")
    runtime = MODULE.CodexRuntime(max_calls=1)
    output = runtime.complete("matched system", "matched user")
    argv = run.call_args.args[0]
    assert argv[:5] == ["codex", "--no-daemon", "-a", "never", "exec"]
    assert "--ignore-user-config" in argv and "--ignore-rules" in argv
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert argv[argv.index("--model") + 1] == "gpt-6.1-sol"
    assert 'developer_instructions="matched system"' in argv
    assert "shell_tool" in argv and "computer_use" in argv
    assert run.call_args.kwargs["input"] == "matched user"
    assert "WAYLAND_DISPLAY" not in run.call_args.kwargs["env"]
    assert run.call_args.kwargs["timeout"] == 90
    assert output["raw"] == "KEY MUTE"
    assert output["prompt_tokens"] == 300
    assert output["model_only_seconds"] is None
    assert output["timing_regime"] == "codex_cli_startup_plus_network"
    with pytest.raises(RuntimeError, match="call cap"):
        runtime.complete("system", "user")
    assert run.call_count == 1


@pytest.mark.parametrize(
    "item",
    [
        {"type": "command_execution", "command": "id"},
        {"type": "mcp_tool_call", "server": "test"},
        {"type": "web_search", "query": "weather"},
        {"type": "file_change"},
    ],
)
def test_tool_attempt_is_not_a_valid_baseline_completion(monkeypatch, item):
    monkeypatch.setattr(MODULE.Path, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, events({"type": "item.started", "item": item}), ""
            )
        ),
    )
    with pytest.raises(RuntimeError, match="forbidden tool"):
        MODULE.CodexRuntime(1).complete("system", "user")


def test_provider_diagnostics_are_not_disclosed(monkeypatch):
    monkeypatch.setattr(MODULE.Path, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess([], 4, "", "private account details")),
    )
    with pytest.raises(RuntimeError, match="exited 4") as error:
        MODULE.CodexRuntime(1).complete("system", "user")
    assert "private" not in str(error.value)


def test_timeout_is_not_a_fake_completion(monkeypatch):
    monkeypatch.setattr(MODULE.Path, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        MODULE.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("codex", 90))
    )
    with pytest.raises(subprocess.TimeoutExpired):
        MODULE.CodexRuntime(1).complete("system", "user")
