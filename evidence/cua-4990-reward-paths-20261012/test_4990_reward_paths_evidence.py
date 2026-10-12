"""Downstream evidence only: real package paths, existing hermetic SDK fixture."""
import asyncio
import builtins
import json
import os
from pathlib import Path

import pytest
import cua_bench as cb
from cua_bench import core
from cua_bench.runner import AgentOptions, run_episode
from .test_cli_golden import cli_env  # noqa: F401


@pytest.mark.parametrize('value,mean,first', [([1, 0, 0], 1/3, 1.0), (0.75, 0.75, 0.75), ([0.75], 0.75, 0.75)], ids=['multi', 'scalar', 'single'])
def test_actual_reward_paths(cli_env, monkeypatch, tmp_path, capsys, value, mean, first):
    task = tmp_path / 'controlled'
    task.mkdir()
    (task / 'main.py').write_text('''import json
import cua_bench as cb
@cb.tasks_config
def tasks():
    return [cb.Task(description="controlled reward", computer={"provider":"native", "setup_config":{"os_type":"linux", "image":"registry.example/desktop:docker-1"}})]
@cb.setup_task
async def setup(task, session):
    await session.write_file("/tmp/evaluation", %r)
@cb.evaluate_task
async def evaluate(task, session):
    return json.loads(await session.read_file("/tmp/evaluation"))
''' % json.dumps(value))
    monkeypatch.setattr(builtins, 'input', lambda: '')
    cb.interact(str(task))
    interactive = capsys.readouterr().out
    assert 'Error:' not in interactive
    assert 'Evaluation result: ' + str(value) in interactive
    assert len(cli_env.calls) == 1 and cli_env.released == 1
    env = cb.make(str(task))
    async def episode():
        try:
            return await run_episode(env, 0, AgentOptions(dump=True), tmp_path / 'episode')
        finally:
            await env.close()
    result = asyncio.run(episode())
    unified = capsys.readouterr().out
    assert result.evaluation == value
    assert result.reward == pytest.approx(mean)
    assert len(cli_env.calls) == 2 and cli_env.released == 2 and cli_env.live == 0
    def envelopes(output):
        return [json.loads(line.split('CUA_BENCH_RESULT ', 1)[1])['reward'] for line in output.splitlines() if 'CUA_BENCH_RESULT ' in line]
    i, u = envelopes(interactive), envelopes(unified)
    added = os.environ['EXPECT_ENVELOPES'] == '1'
    assert i == ([first] if added else [])
    assert u == ([mean] if added else [])
    if added:
        from cua_bench.reward import parse_reward
        assert parse_reward(interactive) == pytest.approx(first)
        assert parse_reward(unified) == pytest.approx(mean)
    name = 'multi' if isinstance(value, list) and len(value) > 1 else 'single' if isinstance(value, list) else 'scalar'
    receipt = Path(os.environ['RECEIPT_DIR'])
    receipt.mkdir(parents=True, exist_ok=True)
    (receipt / (name + '.json')).write_text(json.dumps({'evaluation': value, 'documented_mean': mean, 'interactive_envelopes': i, 'episode_envelopes': u, 'episode_reward': result.reward, 'claims': len(cli_env.calls), 'released': cli_env.released, 'package': cb.__file__, 'core': core.__file__, 'episode_module': run_episode.__module__}, indent=2))
    (receipt / (name + '-interactive.log')).write_text(interactive)
    (receipt / (name + '-episode.log')).write_text(unified)
    if os.environ.get('ASSERT_MEAN') == '1':
        assert i == [pytest.approx(mean)], 'interactive envelope must follow documented mean'
