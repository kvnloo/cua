"""Independent evidence only; no production repair."""
import json

import pytest
import cua_bench as cb
import cua_bench.runners as runners

from .test_run_benchmark import _fake_sandboxes


def task_dir(tmp_path):
    directory = tmp_path / "task"
    directory.mkdir()
    (directory / "main.py").write_text('''
import cua_bench as cb
@cb.tasks_config(split="train")
def tasks():
    return [cb.Task(description="Independent component reward evidence", computer={"provider":"native","setup_config":{"os_type":"linux","width":800,"height":600}})]
@cb.setup_task(split="train")
async def setup(task, session):
    pass
@cb.solve_task(split="train")
async def solve(task, session):
    pass
@cb.evaluate_task(split="train")
async def evaluate(task, session):
    return [1.0, 0.0, 0.0]
''')
    return directory


@pytest.mark.asyncio
async def test_valid_components_observe_documented_mean(tmp_path):
    result = await cb.run_single_task(task_dir(tmp_path), agent_fn=lambda *_: cb.DoneAction())
    print("EVIDENCE", json.dumps(vars(result), sort_keys=True))
    assert result.error is None
    assert result.steps == 1
    assert result.reward == pytest.approx(1 / 3)
    assert result.success is False


@pytest.mark.asyncio
async def test_partial_oracle_failure_keeps_two_completed_steps(tmp_path, monkeypatch):
    original_make = runners.make
    observed = []

    def capture_make(*args, **kwargs):
        env = original_make(*args, **kwargs)
        observed.append(env)

        async def failing_solver(task, session):
            await env.step(cb.DoneAction())
            await env.step(cb.DoneAction())
            raise RuntimeError("independent oracle failure after two completed steps")

        env.solve_task_fn = failing_solver
        return env

    monkeypatch.setattr(runners, "make", capture_make)
    result = await cb.run_single_task(task_dir(tmp_path), oracle=True)
    env = observed[0]
    print("EVIDENCE", json.dumps({"result": vars(result), "environment_steps": env.step_count, "session_closed": env.session is None}, sort_keys=True))
    assert env.step_count == 2
    assert env.session is None
    assert result.success is False
    assert result.reward == 0.0
    assert result.error == "independent oracle failure after two completed steps"
    assert result.steps == 2
