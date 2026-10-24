"""Behavioral tests for the semantic local loop. No model or desktop required."""

import asyncio
import json

import pytest

from cua_agent import ComputerAgent
from cua_agent.decorators import find_agent_config
from cua_agent.loops.hobbylm import HobbyLMConfig, SYSTEM_V2, format_user, parse_action


@pytest.mark.parametrize(
    "raw",
    [
        "OPEN Calculator",
        "TYPE 600/4=",
        "KEY MUTE",
        "KEY BRIGHTNESS_DOWN",
        "DARK_MODE OFF",
        "FOLDER Documents",
        "TIMER 7",
        "SCREENSHOT",
        "DONE",
        "UNKNOWN",
        "EVENT Coffee with Meera | sunday | 19:00 IST | Meera",
    ],
)
def test_allowlisted_actions_roundtrip(raw):
    assert str(parse_action(raw)) == raw


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "OPEN Terminal",
        "TYPE $(id)",
        "TYPE 1=\nSCREENSHOT",
        "DONE ignored",
        "UNKNOWN ignored",
        "TIMER -1",
        "TIMER 0",
        "TIMER 10081",
        "KEY CONTROL",
        "FOLDER /etc",
        "EVENT title | sunday | 19:00",
        "EVENT title | | 19:00 | none",
        "SCREENSHOT\x00",
        "KEY MUTE\nKEY VOLUME_UP",
        "OPEN Calculator; id",
    ],
)
def test_invalid_actions_fail_closed(raw):
    with pytest.raises(ValueError):
        parse_action(raw)


class ScriptedRuntime:
    """Concrete callable with JSON-compatible state for agent callback hooks."""

    def __init__(self, *responses: str):
        self.pending = [
            {"raw": raw, "seconds": 0.1, "prompt_tokens": 20, "output_tokens": 2}
            for raw in responses
        ]
        self.calls: list[tuple[str, str, int]] = []

    def complete(self, system: str, user: str, max_new: int = 64) -> dict:
        self.calls.append((system, user, max_new))
        return self.pending.pop(0)


def runtime(*responses):
    return ScriptedRuntime(*responses)


def test_prompt_native_user_contract():
    assert format_user("split 600 among 4 people", "Calculator: closed") == (
        "Request: split 600 among 4 people\n\nState:\nCalculator: closed\n\nNext action:"
    )
    assert format_user("request", "state", "KEY MUTE", "Muted.") == (
        "Request: request\n\nState:\nstate\n\nLast action: KEY MUTE. Result: Muted.\n\nNext action:"
    )


def test_registered_loop():
    assert find_agent_config("hobbylm/local").agent_class is HobbyLMConfig
    assert HobbyLMConfig().get_capabilities() == ["step"]


def test_real_agent_dispatch_and_feedback():
    async def run():
        observed = {"state": "Calculator: closed"}
        actions = []
        callback_responses = []

        class ResponseRecorder:
            async def on_responses(self, kwargs, response):
                callback_responses.append((kwargs, response))

        async def hobby_action(action: str) -> str:
            """Execute one validated semantic action."""
            actions.append(action)
            if action == "OPEN Calculator":
                observed["state"] = "Calculator: open, display shows 0"
                return "Calculator opened."
            observed["state"] = "Calculator: open, display shows 150"
            return "display changed from 0 to 150."

        model = runtime("OPEN Calculator", "TYPE 600/4=", "DONE")
        agent = ComputerAgent(
            model="hobbylm/local",
            tools=[hobby_action],
            callbacks=[ResponseRecorder()],
            telemetry_enabled=False,
            max_retries=0,
            hobby_runtime=model,
            hobby_observe=lambda: observed["state"],
        )
        chunks = [
            chunk
            async for chunk in agent.run([{"role": "user", "content": "split 600 among 4 people"}])
        ]
        assert actions == ["OPEN Calculator", "TYPE 600/4="]
        assert chunks[-1]["output"][0]["content"][0]["text"] == "Done."
        assert len(model.calls) == 3
        assert model.calls[0] == (
            SYSTEM_V2,
            format_user("split 600 among 4 people", "Calculator: closed"),
            64,
        )
        second = model.calls[1][1]
        assert "Last action: OPEN Calculator. Result: Calculator opened." in second
        assert "display shows 0" in second
        assert "image" not in second
        third = model.calls[2][1]
        assert "Last action: TYPE 600/4=. Result: display changed from 0 to 150." in third
        assert "display shows 150" in third
        assert chunks[0]["usage"]["total_tokens"] == 22
        assert [response["output"][0]["type"] for _, response in callback_responses] == [
            "function_call",
            "function_call",
            "message",
        ]
        assert callback_responses[0][0]["hobby_runtime"]["calls"] == [
            [
                SYSTEM_V2,
                format_user("split 600 among 4 people", "Calculator: closed"),
                64,
            ]
        ]

    asyncio.run(run())


def test_refusal_does_not_execute_tool():
    async def run():
        loop = HobbyLMConfig()
        result = await loop.predict_step(
            [{"role": "user", "content": "weather tomorrow"}],
            "hobbylm/local",
            tools=[{"type": "function", "name": "hobby_action"}],
            hobby_runtime=runtime("UNKNOWN"),
            hobby_observe=lambda: "Front app: Notes",
        )
        assert result["output"][0]["type"] == "message"
        assert result["output"][0]["content"][0]["text"] == "I can't do that one offline."

    asyncio.run(run())


def test_invalid_model_output_never_emits_tool():
    async def run():
        with pytest.raises(ValueError, match="Invalid HobbyLM action"):
            await HobbyLMConfig().predict_step(
                [{"role": "user", "content": "request"}],
                "hobbylm/local",
                tools=[{"type": "function", "name": "hobby_action"}],
                hobby_runtime=runtime("OPEN Terminal"),
                hobby_observe=lambda: "state",
            )

    asyncio.run(run())


def test_action_bound_and_new_request_reset():
    async def run():
        messages = [{"role": "user", "content": "request"}]
        for index in range(6):
            messages += [
                {
                    "type": "function_call",
                    "name": "hobby_action",
                    "call_id": str(index),
                    "arguments": json.dumps({"action": "KEY MUTE"}),
                },
                {"type": "function_call_output", "call_id": str(index), "output": "muted"},
            ]
        kwargs = {
            "tools": [{"name": "hobby_action"}],
            "hobby_runtime": runtime("DONE"),
            "hobby_observe": lambda: "state",
        }
        with pytest.raises(ValueError, match="six-action limit"):
            await HobbyLMConfig().predict_step(messages, "hobbylm/local", **kwargs)
        messages.append({"role": "user", "content": "new request"})
        result = await HobbyLMConfig().predict_step(messages, "hobbylm/local", **kwargs)
        assert result["output"][0]["content"][0]["text"] == "Done."

    asyncio.run(run())
