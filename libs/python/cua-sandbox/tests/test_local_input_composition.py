"""Joined bench input/reconnect/lifecycle proof through inert native/state seams."""

from __future__ import annotations

import json

import pytest
from cua_bench.computers.remote import RemoteDesktopSession
from cua_bench.types import ScrollAction
from cua_sandbox import SpacesdNotAvailable
from cua_sandbox import _refs

from tests.test_local_reconnect_destroy import (
    NAME,
    _offline_image_manifests,  # noqa: F401 - preserve the native/deletion guards
    local_record as published_local_record,
)


# Register the unchanged published fixture in this owning module.
local_record = published_local_record


class RecordingInputClient:
    def __init__(self):
        self.trace = []

    async def keyboard_json(self, payload):
        self.trace.append(("keyboard_json", json.loads(payload)))

    async def pointer_json(self, payload):
        self.trace.append(("pointer_json", json.loads(payload)))


@pytest.fixture
def joined_record(local_record, monkeypatch):
    client = RecordingInputClient()
    local_record.parser_calls = []

    def resolved_local_reference(value):
        # Native parsing is explicitly mocked and unverified by this proof.
        assert value == "local:recorded-local"
        local_record.parser_calls.append(value)
        return _refs.Ref("local", "recorded-local")

    monkeypatch.setattr(_refs, "parse", resolved_local_reference)

    async def spacesd(handle, timeout_ms):
        assert handle is local_record.handle
        local_record.calls.append(("spacesd", timeout_ms))
        return client

    monkeypatch.setattr(type(local_record.handle), "spacesd", spacesd, raising=False)
    return local_record, client


@pytest.mark.parametrize(
    "key,direction,delta_y", [("KEY_A", "up", -3), ("KEY_NUMPAD_ENTER", "down", 3)]
)
async def test_joined_local_input_close_then_explicit_destroy(
    joined_record, key, direction, delta_y
):
    record, client = joined_record
    session = RemoteDesktopSession(api_url=f"local:{NAME}", width=1280, height=720, headless=True)
    assert session.sandbox is None and record.calls == [] and client.trace == []
    await session.start()
    sb = session.sandbox
    assert record.parser_calls == ["local:recorded-local"]
    assert sb._transport._native_sandbox is record.handle
    assert sb._transport._client is None
    assert record.calls == [("connect", NAME)] and client.trace == []

    await sb.keyboard.key_down(key)
    await session.execute_action(ScrollAction(direction=direction, amount=350))
    await sb.keyboard.key_up(key)
    expected = [
        ("keyboard_json", {"down": {"key": {"named": key}}}),
        (
            "pointer_json",
            {
                "scroll": {
                    "position": {"x": 640.0, "y": 360.0},
                    "deltaX": 0.0,
                    "deltaY": float(delta_y),
                    "unit": "SCROLL_UNIT_LINE",
                }
            },
        ),
        ("keyboard_json", {"up": {"key": {"named": key}}}),
    ]
    assert client.trace == expected
    assert record.calls == [("connect", NAME), ("spacesd", 15000)]
    assert sb._transport._client is client

    await session.close()
    assert session.sandbox is None and not session._initialized
    assert not record.deleted and NAME in record.state
    assert sb._transport._client is None and not sb._transport._connected
    assert record.calls == [("connect", NAME), ("spacesd", 15000)]
    assert client.trace == expected

    await sb.destroy()
    assert record.deleted
    assert record.calls == [("connect", NAME), ("spacesd", 15000), ("handle_delete", NAME)]
    assert client.trace == expected and sb._transport._client is None
    print(
        "JOINED_TRACE", json.dumps({"calls": record.calls, "actions": client.trace}, sort_keys=True)
    )


async def test_reconnect_without_spacesd_refuses_before_client_but_can_destroy(joined_record):
    record, client = joined_record
    record.state[NAME]["services"] = {}
    session = RemoteDesktopSession(api_url=f"local:{NAME}", width=1280, height=720, headless=True)
    await session.start()
    sb = session.sandbox
    assert record.parser_calls == ["local:recorded-local"]
    assert record.calls == [("connect", NAME)] and sb._transport._client is None
    with pytest.raises(SpacesdNotAvailable, match="this sandbox's image does not run cua-spacesd"):
        await sb.keyboard.key_down("KEY_A")
    assert record.calls == [("connect", NAME)] and client.trace == []
    await session.close()
    assert not record.deleted and NAME in record.state
    await sb.destroy()
    assert record.deleted and record.calls == [("connect", NAME), ("handle_delete", NAME)]
    assert client.trace == [] and sb._transport._client is None
    print(
        "REFUSAL_TRACE",
        json.dumps({"calls": record.calls, "actions": client.trace}, sort_keys=True),
    )
