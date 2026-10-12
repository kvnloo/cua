"""Public QMP drag dispatch with inert commands; no QEMU/native execution."""

import json
from itertools import count

import pytest
from cua_sandbox import Sandbox
from cua_sandbox.transport import qmp

DIRECTORIES = count()


@pytest.fixture
def recorded_qmp(monkeypatch, tmp_path_factory):
    directory = tmp_path_factory.mktemp(f"qmp-recorder-{next(DIRECTORIES)}", numbered=False)
    monkeypatch.setattr(qmp.tempfile, "mkdtemp", lambda **kwargs: str(directory))
    transport = qmp.QMPTransport(screen_width=1280, screen_height=720)
    commands = []

    async def execute(command, arguments=None):
        commands.append((command, arguments))
        return {}

    monkeypatch.setattr(transport, "_execute", execute)
    return Sandbox(transport, _telemetry_enabled=False), commands


def position(x, y):
    return [
        {"type": "abs", "data": {"axis": "x", "value": int(x * 32767 / 1280)}},
        {"type": "abs", "data": {"axis": "y", "value": int(y * 32767 / 720)}},
    ]


def command(events):
    return "input-send-event", {"events": events}


def expected_drag(button, points):
    expected = [
        command(position(*points[0]) + [{"type": "btn", "data": {"down": True, "button": button}}])
    ]
    for (sx, sy), (ex, ey) in zip(points, points[1:]):
        for i in range(1, 11):
            expected.append(command(position(sx + (ex - sx) * i // 10, sy + (ey - sy) * i // 10)))
    expected.append(
        command(
            position(*points[-1]) + [{"type": "btn", "data": {"down": False, "button": button}}]
        )
    )
    return expected


@pytest.mark.parametrize("button", ["left", "right"])
async def test_public_drag_dispatches_ordered_scaled_input(recorded_qmp, button):
    sb, commands = recorded_qmp
    try:
        await sb.mouse.drag(100, 100, 300, 300, button=button)
    except TypeError:
        print("PUBLIC_DRAG_TYPEERROR_COMMANDS", json.dumps(commands))
        assert commands == []
        raise
    assert commands == expected_drag(button, [(100, 100), (300, 300)])
    print("PUBLIC_DRAG_TRACE", json.dumps(commands))


async def test_public_click_control(recorded_qmp):
    sb, commands = recorded_qmp
    await sb.mouse.click(100, 100)
    assert commands == [
        command(
            position(100, 100)
            + [
                {"type": "btn", "data": {"down": True, "button": "left"}},
                {"type": "btn", "data": {"down": False, "button": "left"}},
            ]
        )
    ]


async def test_direct_coordinate_drag_control(recorded_qmp):
    sb, commands = recorded_qmp
    await sb._transport.send("drag", start_x=100, start_y=100, end_x=300, end_y=300, button="right")
    assert commands == expected_drag("right", [(100, 100), (300, 300)])


async def test_path_waypoints_keep_one_button_press(recorded_qmp):
    sb, commands = recorded_qmp
    points = [(100, 100), (300, 100), (300, 300)]
    await sb._transport.send("drag", path=points, button="left")
    assert commands == expected_drag("left", points)


@pytest.mark.parametrize("path", [[], [[100, 100]], [[100, 100], [300]]])
async def test_invalid_path_refuses_before_commands(recorded_qmp, path):
    sb, commands = recorded_qmp
    with pytest.raises(ValueError):
        await sb._transport.send("drag", path=path)
    assert commands == []
