"""Regression for trycua/cua#4954: Lume reports no VM creation time, so
checkpoint listings must not stamp each entry with the time of the call."""

import httpx
import pytest

from cua_sandbox.runtime.lume import LumeRuntime


@pytest.fixture
def runtime():
    return LumeRuntime()


async def test_list_checkpoints_does_not_invent_created_at(runtime, monkeypatch):
    async def fake_list():
        return [{"name": "cua-base-macos"}, {"name": "cua-ckpt-old"}, {"name": "my-sandbox"}]

    monkeypatch.setattr(runtime, "list", fake_list)
    clock = iter([1000.0, 2000.0, 3000.0, 4000.0])
    monkeypatch.setattr("time.time", lambda: next(clock))

    first = await runtime.list_checkpoints()
    second = await runtime.list_checkpoints()

    assert [c.name for c in first] == ["cua-base-macos", "cua-ckpt-old"]
    assert [c.created_at for c in first] == [0.0, 0.0]
    assert [c.created_at for c in second] == [0.0, 0.0]


async def test_reused_base_vm_does_not_invent_created_at(runtime, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "cua-base-macos", "status": "stopped"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: real_client(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr("time.time", lambda: 1234.0)

    info = await runtime.ensure_base(image=None, base_name="cua-base-macos")

    assert info.name == "cua-base-macos"
    assert info.created_at == 0.0
