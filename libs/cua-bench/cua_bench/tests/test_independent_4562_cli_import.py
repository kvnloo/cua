"""Independent CLI-to-class evidence; no provider or production substitution."""
import importlib
import json
import sys

import pytest

from cua_bench.cli.main import build_parser
from cua_bench.cli.commands.run import _apply_config_defaults_for_task, agent_options
from cua_bench.runner.episode import load_agent_class


@pytest.mark.parametrize(
    "default_agent,explicit_import,expected",
    [(True, True, "CliAgent"), (False, True, "CliAgent"), (True, False, "RegisteredAgent")],
    ids=["default-and-explicit", "no-default-explicit", "default-only"],
)
def test_cli_import_reaches_selected_class(tmp_path, monkeypatch, default_agent, explicit_import, expected):
    home = tmp_path / "home"
    project = home / "project"
    task = project / "task"
    task.mkdir(parents=True)
    state = home / "state"
    state.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CUA_HOME", str(state))
    monkeypatch.chdir(project)
    config_dir = project / ".cua"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("agent:\n  name: first\n" if default_agent else "{}\n")
    (config_dir / "agents.yaml").write_text(
        "agents:\n  - name: first\n    import_path: selected_agent:RegisteredAgent\n"
    )
    (project / "selected_agent.py").write_text(
        "class RegisteredAgent:\n    marker = 'registered'\n\n"
        "class CliAgent:\n    marker = 'cli'\n"
    )
    monkeypatch.syspath_prepend(str(project))
    monkeypatch.delitem(sys.modules, "selected_agent", raising=False)
    importlib.invalidate_caches()
    argv = ["run", "task", str(task)]
    if explicit_import:
        argv.extend(["--agent-import-path", "selected_agent:CliAgent"])
    parsed = build_parser().parse_args(argv)
    parsed_import = parsed.agent_import_path
    configured = _apply_config_defaults_for_task(parsed)
    configured_import = configured.agent_import_path
    opts = agent_options(configured)
    loaded = load_agent_class(opts)
    instance = loaded()
    print("EVIDENCE", json.dumps({
        "default_agent": default_agent, "explicit_import": explicit_import,
        "parsed_import": parsed_import, "configured_import": configured_import,
        "options_import": opts.agent_import_path, "selected_class": loaded.__name__,
        "instance_marker": instance.marker, "oracle": opts.oracle,
    }, sort_keys=True))
    if explicit_import:
        assert parsed_import == configured_import == "selected_agent:CliAgent"
    assert opts.oracle is False
    assert loaded.__name__ == expected
    assert instance.marker == ("cli" if expected == "CliAgent" else "registered")
