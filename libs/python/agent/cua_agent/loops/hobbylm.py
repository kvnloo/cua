"""Experimental semantic-state HobbyLM loop, not a screenshot-based agent.

Supply ``hobby_runtime.complete`` and ``hobby_observe`` as generation options,
and an allowlisted ``hobby_action(action: str)`` callable in ComputerAgent.tools.
The executor owns platform mapping and event confirmation. No model output is
interpreted as shell code. The native prompt is Apache-2.0 Fuel Labs material.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from ..decorators import register_agent

# Source: fuellabs-ai/hobbylm-1b@98cca6f3, computer-use/hobby/hobbymac_data.py.
# Copyright Fuel Labs. Licensed under Apache-2.0.
SYSTEM_V2 = (
    "You are Hobby, an offline helper on a Mac. Each turn you see the user's request and the current state, "
    "and choose exactly ONE next action.\nAllowed actions:\n"
    "OPEN <app>  (apps: Calculator, Notes, Calendar, Finder, Music, Reminders)\n"
    "TYPE <keys>  (calculator keys only: digits . + - * / =)\n"
    "KEY BRIGHTNESS_DOWN | KEY BRIGHTNESS_UP | KEY VOLUME_DOWN | KEY VOLUME_UP | KEY MUTE\n"
    "DARK_MODE ON | DARK_MODE OFF\n"
    "FOLDER Downloads | FOLDER Desktop | FOLDER Documents\n"
    "TIMER <minutes>\n"
    "SCREENSHOT\n"
    "EVENT <title> | <day> | <time> [timezone] | <person name or email, or none>  (add a calendar event)\n"
    "DONE  (the request is complete)\n"
    "UNKNOWN  (the request is not something these actions can do)\n"
    "For maths, open the calculator, type the numbers and the operation, and let it compute. Reply with the action only."
)


@dataclass(frozen=True)
class Action:
    name: str
    argument: str = ""

    def __str__(self) -> str:
        return self.name + (f" {self.argument}" if self.argument else "")


def parse_action(raw: str) -> Action:
    """Parse exactly one allowlisted action. Reject extra lines and commands."""
    if not isinstance(raw, str) or len(raw) > 1024:
        raise ValueError("Expected one bounded HobbyLM action")
    text = raw.strip()
    if any(ord(char) < 32 for char in text):
        raise ValueError("Control characters are not allowed in actions")
    name, _, argument = text.partition(" ")
    allowed = {
        "OPEN": {"Calculator", "Notes", "Calendar", "Finder", "Music", "Reminders"},
        "KEY": {"BRIGHTNESS_UP", "BRIGHTNESS_DOWN", "VOLUME_UP", "VOLUME_DOWN", "MUTE"},
        "DARK_MODE": {"ON", "OFF"},
        "FOLDER": {"Downloads", "Desktop", "Documents"},
    }
    if name in allowed and argument in allowed[name]:
        return Action(name, argument)
    if name in {"DONE", "UNKNOWN", "SCREENSHOT"} and not argument and text == name:
        return Action(name)
    if name == "TYPE" and re.fullmatch(r"[0-9. +*/=\-]{1,128}", argument):
        return Action(name, argument)
    if name == "TIMER" and re.fullmatch(r"[0-9]{1,5}", argument):
        if 1 <= int(argument) <= 10080:
            return Action(name, argument)
    if name == "EVENT":
        fields = argument.split("|")
        if len(fields) == 4 and all(field.strip() for field in fields):
            return Action(name, argument)
    raise ValueError(f"Invalid HobbyLM action: {text!r}")


def format_user(
    request: str, state: str, last_action: str | None = None, result: str | None = None
) -> str:
    """Render the release user-turn contract without adding visual observations."""
    user = f"Request: {request}\n\nState:\n{state}"
    if last_action is not None:
        user += f"\n\nLast action: {last_action}. Result: {result or ''}"
    return user + "\n\nNext action:"


def _text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return "\n".join(
        item["text"] for item in content
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    )


@register_agent(models=r"^hobbylm/local$", priority=10)
class HobbyLMConfig:
    """Use the existing function-tool seam for the ten semantic actions."""

    async def predict_step(
        self, messages, model, tools=None, max_retries=None, stream=False,
        computer_handler=None, _on_api_start=None, _on_api_end=None,
        _on_usage=None, _on_screenshot=None, **kwargs,
    ):
        if stream:
            raise ValueError("HobbyLM local loop does not support streaming")
        runtime = kwargs.get("hobby_runtime")
        observe = kwargs.get("hobby_observe")
        if runtime is None or not callable(getattr(runtime, "complete", None)) or not callable(observe):
            raise ValueError("hobby_runtime.complete and hobby_observe are required")
        if not any(tool.get("name", tool.get("function", {}).get("name")) == "hobby_action"
                   for tool in (tools or [])):
            raise ValueError("Register an allowlisted hobby_action function tool")
        request_index = next(
            (i for i in range(len(messages) - 1, -1, -1)
             if messages[i].get("role") == "user"), None
        )
        if request_index is None:
            raise ValueError("A user request is required")
        request = _text(messages[request_index])
        calls = {
            item.get("call_id"): item for item in messages[request_index + 1:]
            if item.get("type") == "function_call" and item.get("name") == "hobby_action"
        }
        if len(calls) >= 6:
            raise ValueError("HobbyLM six-action limit reached")
        last_action = result = None
        for item in messages[request_index + 1:]:
            if item.get("type") == "function_call_output" and item.get("call_id") in calls:
                last_action = json.loads(calls[item["call_id"]]["arguments"])["action"]
                result = str(item.get("output", ""))
        state = observe()
        if inspect.isawaitable(state):
            state = await state
        if not isinstance(state, str):
            raise ValueError("hobby_observe must return a semantic-state string")
        user = format_user(request, state, last_action, result)
        api_kwargs = {"model": model, "system": SYSTEM_V2, "user": user, "max_new": 64}
        if _on_api_start:
            await _on_api_start(api_kwargs)
        response = await asyncio.to_thread(runtime.complete, SYSTEM_V2, user, max_new=64)
        if _on_api_end:
            await _on_api_end(api_kwargs, response)
        action = parse_action(response["raw"])
        usage = {
            "prompt_tokens": response.get("prompt_tokens", 0),
            "completion_tokens": response.get("output_tokens", 0),
            "total_tokens": response.get("prompt_tokens", 0) + response.get("output_tokens", 0),
            "response_cost": 0.0,
        }
        if _on_usage:
            await _on_usage(usage)
        if action.name in {"DONE", "UNKNOWN"}:
            text = "Done." if action.name == "DONE" else "I can't do that one offline."
            output = [{"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": text}
            ]}]
        else:
            output = [{"type": "function_call", "call_id": uuid.uuid4().hex,
                       "name": "hobby_action", "arguments": json.dumps({"action": str(action)})}]
        return {"output": output, "usage": usage}

    async def predict_click(self, model, image_b64, instruction, **kwargs):
        raise NotImplementedError("HobbyLM does not accept screenshots or predict coordinates")

    def get_capabilities(self):
        return ["step"]
