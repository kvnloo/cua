"""US-style ASCII payloads through real public typing; no QEMU delivery."""

import json
from itertools import count

import pytest
from cua_sandbox import Sandbox
from cua_sandbox.transport import qmp

DIRECTORIES = count()
SHIFTED = [
    ("~", "grave_accent"),
    ("!", "1"),
    ("@", "2"),
    ("#", "3"),
    ("$", "4"),
    ("%", "5"),
    ("^", "6"),
    ("&", "7"),
    ("*", "8"),
    ("(", "9"),
    (")", "0"),
    ("_", "minus"),
    ("+", "equal"),
    ("{", "bracket_left"),
    ("}", "bracket_right"),
    ("|", "backslash"),
    (":", "semicolon"),
    ('"', "apostrophe"),
    ("<", "comma"),
    (">", "dot"),
    ("?", "slash"),
]


@pytest.fixture
def recorded_qmp(monkeypatch, tmp_path_factory):
    directory = tmp_path_factory.mktemp(f"qmp-text-{next(DIRECTORIES)}", numbered=False)
    monkeypatch.setattr(qmp.tempfile, "mkdtemp", lambda **kwargs: str(directory))
    transport = qmp.QMPTransport()
    commands = []

    async def execute(command, arguments=None):
        commands.append((command, arguments))
        return {}

    monkeypatch.setattr(transport, "_execute", execute)
    return Sandbox(transport, _telemetry_enabled=False), commands


def typed(qcode, shifted=False):
    keys = [{"type": "qcode", "data": "shift"}] if shifted else []
    keys.append({"type": "qcode", "data": qcode})
    return "send-key", {"keys": keys, "hold-time": 50}


@pytest.mark.parametrize("symbol,qcode", SHIFTED)
async def test_each_shifted_punctuation(recorded_qmp, symbol, qcode):
    sb, commands = recorded_qmp
    assert await sb.keyboard.type(symbol) is None
    print("SHIFTED_TRACE", json.dumps({"text": symbol, "commands": commands}))
    assert commands == [typed(qcode, shifted=True)]


async def test_mixed_sentence_and_hi_bang(recorded_qmp):
    sb, commands = recorded_qmp
    await sb.keyboard.type("Hi! a_2+Z?")
    print("MIXED_TRACE", json.dumps(commands))
    assert commands == [
        typed("h", True),
        typed("i"),
        typed("1", True),
        typed("spc"),
        typed("a"),
        typed("minus", True),
        typed("2"),
        typed("equal", True),
        typed("z", True),
        typed("slash", True),
    ]


async def test_public_hi_bang(recorded_qmp):
    sb, commands = recorded_qmp
    assert await sb.keyboard.type("Hi!") is None
    print("HI_BANG_TRACE", json.dumps(commands))
    assert commands == [typed("h", True), typed("i"), typed("1", True)]


async def test_unshifted_text_control(recorded_qmp):
    sb, commands = recorded_qmp
    await sb.keyboard.type("Az0 -=[]\\;',./`")
    assert commands == [
        typed("a", True),
        typed("z"),
        typed("0"),
        typed("spc"),
        *[
            typed(q)
            for q in [
                "minus",
                "equal",
                "bracket_left",
                "bracket_right",
                "backslash",
                "semicolon",
                "apostrophe",
                "comma",
                "dot",
                "slash",
                "grave_accent",
            ]
        ],
    ]


async def test_direct_key_apis_control(recorded_qmp):
    sb, commands = recorded_qmp
    await sb.keyboard.keypress(["shift", "1"])
    await sb.keyboard.key_down("1")
    await sb.keyboard.key_up("1")
    assert commands == [
        (
            "send-key",
            {
                "keys": [{"type": "qcode", "data": "shift"}, {"type": "qcode", "data": "1"}],
                "hold-time": 100,
            },
        ),
        *[
            (
                "input-send-event",
                {
                    "events": [
                        {
                            "type": "key",
                            "data": {"down": down, "key": {"type": "qcode", "data": "1"}},
                        }
                    ]
                },
            )
            for down in (True, False)
        ],
    ]


@pytest.mark.parametrize("method", ["keypress", "key_down", "key_up"])
async def test_direct_symbol_is_still_unknown(recorded_qmp, method):
    sb, commands = recorded_qmp
    with pytest.raises(ValueError, match="^Unknown key '!'$"):
        await getattr(sb.keyboard, method)("!")
    assert commands == []
