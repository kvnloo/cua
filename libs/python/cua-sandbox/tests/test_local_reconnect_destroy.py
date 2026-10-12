"""Explicit local reconnect lifecycle with in-memory seams only; no native SDK."""

from __future__ import annotations

import asyncio
import importlib
import importlib.abc
import os
import socket
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cua_sandbox import Sandbox, _sdk, sandbox_state
from cua_sandbox.runtime.base import RuntimeInfo
from cua_sandbox.runtime import native as native_module
from cua_sandbox.transport import env as env_module
from cua_sandbox.transport.env import EnvTransport
from cua_sandbox.transport.fleet_cloud import FleetCloudTransport

sandbox_module = importlib.import_module("cua_sandbox.sandbox")
NAME = "recorded-local"


@pytest.fixture(autouse=True)
def _offline_image_manifests(monkeypatch):
    """Override the suite's native-loading manifest fixture for this pure Python owner."""
    assert "cua" not in sys.modules, "this owner must not load the native SDK"

    def forbidden(*args, **kwargs):
        raise AssertionError("native SDK, network and filesystem deletion are forbidden")

    class RefuseNativeSDK(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "cua" or fullname.startswith("cua."):
                forbidden()
            return None

    monkeypatch.setattr(sys, "meta_path", [RefuseNativeSDK(), *sys.meta_path])

    monkeypatch.setattr(_sdk, "sdk", forbidden)
    monkeypatch.setattr(_sdk, "native", forbidden)
    monkeypatch.setattr(native_module, "native", forbidden)
    monkeypatch.setattr(env_module, "native", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket.socket, "sendto", forbidden)
    monkeypatch.setattr(os, "unlink", forbidden)
    monkeypatch.setattr(os, "remove", forbidden)
    monkeypatch.setattr(os, "rmdir", forbidden)
    monkeypatch.setattr(sandbox_module, "_TELEMETRY_AVAILABLE", False)
    yield
    assert "cua" not in sys.modules


class RecordingLocal:
    def __init__(self):
        self.calls = []
        self.deleted = False
        self.location = "local"
        self.handle_name = NAME
        self.delete_error = None
        self.info_error = None
        self.state = {
            NAME: {
                "name": NAME,
                "runtime_type": "container",
                "os_type": "linux",
                "services": {"env": 3211},
            }
        }

    def sandboxes(self):
        return self

    async def connect(self, name):
        self.calls.append(("connect", name))
        assert name == NAME
        return self

    def info(self):
        if self.info_error:
            raise self.info_error
        return SimpleNamespace(
            location=self.location,
            name=self.handle_name,
            runtime="container",
            services={"env": 3211},
        )

    async def delete(self, name=None):
        self.calls.append(("delete", name or NAME))
        if self.delete_error:
            raise self.delete_error
        self.deleted = True


@pytest.fixture
def local_record(monkeypatch, _no_real_local_sandboxes, _offline_image_manifests):
    record = RecordingLocal()
    monkeypatch.setattr(_sdk, "local_runtime", lambda: record)
    monkeypatch.setattr(native_module, "local_runtime", lambda: record)
    monkeypatch.setattr(sandbox_state, "load", lambda name: record.state.get(name))
    monkeypatch.setattr(sandbox_state, "delete", lambda name: record.state.pop(name, None))

    def unexpected_write(*args, **kwargs):
        raise AssertionError("reconnect must not persist state")

    monkeypatch.setattr(sandbox_state, "save", unexpected_write)
    monkeypatch.setattr(sandbox_state, "update", unexpected_write)
    return record


async def reconnect():
    sb = await Sandbox.connect(NAME, local=True, telemetry_enabled=False)
    assert isinstance(sb, Sandbox)
    assert isinstance(sb._transport, EnvTransport)
    assert sb._transport._native_sandbox is not None
    assert sb._runtime is None and sb._runtime_info is None
    return sb


async def test_explicit_destroy_after_local_reconnect_deletes(local_record):
    sb = await reconnect()
    await sb.destroy()
    assert local_record.calls == [("connect", NAME), ("delete", NAME)]
    assert local_record.deleted


@pytest.mark.parametrize("preserve", ["disconnect", "context_exit"])
async def test_reconnect_exit_preserves_local_sandbox(local_record, preserve):
    if preserve == "disconnect":
        sb = await reconnect()
        await sb.disconnect()
    else:
        async with Sandbox.connect(NAME, local=True, telemetry_enabled=False) as sb:
            assert isinstance(sb._transport, EnvTransport)
    assert local_record.calls == [("connect", NAME)]
    assert not local_record.deleted and NAME in local_record.state
    assert not sb._transport._connected


async def test_class_delete_dispatches_to_local_manager(local_record):
    await Sandbox.delete(NAME, local=True)
    assert local_record.calls == [("delete", NAME)]
    assert local_record.deleted and NAME not in local_record.state


async def test_explicit_destroy_after_disconnect_retains_local_handle(local_record):
    sb = await reconnect()
    await sb.disconnect()
    assert not local_record.deleted
    await sb.destroy()
    assert local_record.calls == [("connect", NAME), ("delete", NAME)]
    assert local_record.deleted


async def test_legacy_state_without_native_handle_is_not_deleted(local_record):
    local_record.state[NAME].pop("services")
    sb = await Sandbox.connect(NAME, local=True, telemetry_enabled=False)
    assert isinstance(sb._transport, EnvTransport)
    assert sb._transport._native_sandbox is None
    await sb.destroy()
    assert local_record.calls == [] and not local_record.deleted


async def test_direct_url_destroy_never_deletes_local_manager(local_record):
    sb = await Sandbox.connect(url="http://recording.invalid:3211", telemetry_enabled=False)
    await sb.destroy()
    assert local_record.calls == [] and not local_record.deleted


async def test_name_and_ephemeral_do_not_establish_local_reconnect_ownership(local_record):
    sb = Sandbox(
        EnvTransport(url="http://recording.invalid:3211", native_sandbox=local_record),
        name=NAME,
        _ephemeral=True,
        _telemetry_enabled=False,
    )
    await sb.destroy()
    assert local_record.calls == [] and not local_record.deleted


@pytest.mark.parametrize("metadata", ["cloud", "other_name", "unavailable"])
async def test_unverified_reconnect_handle_is_never_deleted(local_record, metadata):
    if metadata == "cloud":
        local_record.location = "cloud"
    elif metadata == "other_name":
        local_record.handle_name = "other"
    else:
        local_record.info_error = RuntimeError("metadata unavailable")
    sb = await reconnect()
    await sb.destroy()
    assert local_record.calls == [("connect", NAME)] and not local_record.deleted


@pytest.mark.parametrize("ephemeral", [False, True])
async def test_runtime_precedence_preserves_stop_delete_dispatch(local_record, ephemeral):
    sb = await reconnect()
    runtime = SimpleNamespace(stop=AsyncMock(), delete=AsyncMock())
    sb._runtime = runtime
    sb._runtime_info = RuntimeInfo(host="recording.invalid", api_port=0, name="runtime-owner")
    sb._ephemeral = ephemeral
    await sb.destroy()
    selected = runtime.delete if ephemeral else runtime.stop
    selected.assert_awaited_once_with("runtime-owner")
    (runtime.stop if ephemeral else runtime.delete).assert_not_awaited()
    assert not local_record.deleted


async def test_cloud_dispatch_has_precedence_over_local_reconnect(local_record):
    sb = await reconnect()
    transport = FleetCloudTransport.__new__(FleetCloudTransport)
    transport.disconnect = AsyncMock()
    transport.delete_vm = AsyncMock()
    sb._transport = transport
    await sb.destroy()
    transport.delete_vm.assert_awaited_once()
    assert not local_record.deleted


async def test_fleet_claim_release_has_precedence_over_local_reconnect(local_record):
    sb = await reconnect()
    claim = SimpleNamespace(
        name="claim-owner", pool_name="pool", release=AsyncMock(), detach=lambda: None
    )
    sb._claim_handle = claim
    await sb.destroy()
    claim.release.assert_awaited_once()
    assert sb._claim_released and not local_record.deleted


async def test_released_fleet_claim_does_not_fall_back_to_local_delete(local_record):
    sb = await reconnect()
    sb._claim_handle = SimpleNamespace(detach=lambda: None)
    sb._claim_released = True
    await sb.destroy()
    assert local_record.calls == [("connect", NAME)] and not local_record.deleted


async def test_disconnect_cancellation_keeps_existing_error_semantics(local_record):
    sb = await reconnect()
    sb._transport.disconnect = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await sb.destroy()
    assert local_record.calls == [("connect", NAME)] and not local_record.deleted


async def test_disconnect_error_does_not_skip_explicit_local_delete(local_record):
    sb = await reconnect()
    sb._transport.disconnect = AsyncMock(side_effect=OSError("disconnect failed"))
    await sb.destroy()
    sb._transport.disconnect.assert_awaited_once()
    assert local_record.calls == [("connect", NAME), ("delete", NAME)]
    assert local_record.deleted


async def test_local_delete_error_remains_best_effort(local_record, caplog):
    sb = await reconnect()
    local_record.delete_error = OSError("recording delete failed")
    await sb.destroy()
    assert local_record.calls == [("connect", NAME), ("delete", NAME)]
    assert not local_record.deleted
    assert "Failed to delete" in caplog.text


async def test_explicit_destroy_with_snapshots_still_deletes(local_record, caplog):
    sb = await reconnect()
    sb._has_snapshots = True
    await sb.destroy()
    assert local_record.deleted
    assert "which has snapshots" in caplog.text
