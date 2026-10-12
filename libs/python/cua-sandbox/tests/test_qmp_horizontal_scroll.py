"""Public wheel-notch dispatch, using an inert recorder rather than QEMU."""

import json
from collections import Counter
from itertools import count

import pytest
from cua_sandbox import Sandbox
from cua_sandbox.transport import qmp

DIRECTORIES = count()


@pytest.fixture
def recorded_qmp(monkeypatch, tmp_path_factory):
    directory = tmp_path_factory.mktemp(f"qmp-scroll-{next(DIRECTORIES)}", numbered=False)
    monkeypatch.setattr(qmp.tempfile, "mkdtemp", lambda **kwargs: str(directory))
    transport = qmp.QMPTransport(screen_width=1280, screen_height=720)
    commands = []

    async def execute(command, arguments=None):
        commands.append((command, arguments))
        return {}

    monkeypatch.setattr(transport, "_execute", execute)
    return Sandbox(transport, _telemetry_enabled=False), commands


def assert_notches(commands, expected):
    assert commands[0] == (
        "input-send-event",
        {
            "events": [
                {"type": "abs", "data": {"axis": "x", "value": 2559}},
                {"type": "abs", "data": {"axis": "y", "value": 4550}},
            ]
        },
    )
    buttons = []
    for name, arguments in commands[1:]:
        assert name == "input-send-event"
        down, up = arguments["events"]
        button = down["data"]["button"]
        assert down == {"type": "btn", "data": {"down": True, "button": button}}
        assert up == {"type": "btn", "data": {"down": False, "button": button}}
        buttons.append(button)
    # Mixed axes are independent notches, with no simultaneous/diagonal promise.
    assert Counter(buttons) == Counter(expected)
    assert len(commands) == 1 + sum(expected.values())


@pytest.mark.parametrize(
    "scroll_x,scroll_y,expected",
    [
        (2, 0, {"wheel-right": 2}),
        (-2, 0, {"wheel-left": 2}),
        (2, 3, {"wheel-right": 2, "wheel-up": 3}),
        (-2, -3, {"wheel-left": 2, "wheel-down": 3}),
        (0, 0, {}),
        (0, 3, {"wheel-up": 3}),
        (0, -3, {"wheel-down": 3}),
        (1, 0, {"wheel-right": 1}),
        (-3, 0, {"wheel-left": 3}),
    ],
)
async def test_public_scroll_preserves_each_signed_notch(
    recorded_qmp, scroll_x, scroll_y, expected
):
    sb, commands = recorded_qmp
    result = await sb.mouse.scroll(100, 100, scroll_x=scroll_x, scroll_y=scroll_y)
    assert result is None
    print("SCROLL_TRACE", json.dumps({"x": scroll_x, "y": scroll_y, "commands": commands}))
    assert_notches(commands, expected)


async def test_default_vertical_scroll_control(recorded_qmp):
    sb, commands = recorded_qmp
    await sb.mouse.scroll(100, 100)
    assert_notches(commands, {"wheel-up": 3})
