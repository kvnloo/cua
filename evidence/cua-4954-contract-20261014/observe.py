"""Read-only characterization; no candidate fix or unknown-time policy assertion."""
import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("no_external_activity", HERE / "guards.py")
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)

import httpx
from cua_sandbox.image import Image
from cua_sandbox.runtime.base import CheckpointInfo
from cua_sandbox.runtime.lume import LumeRuntime
import cua_sandbox.runtime.lume as module

RealClient = httpx.AsyncClient

async def observe():
    runtime = LumeRuntime()
    runtime.list = AsyncMock(return_value=[
        {"name": "cua-base-example"}, {"name": "cua-ckpt-old"}, {"name": "ordinary"}
    ])
    with patch("time.time", return_value=100.0):
        first = await runtime.list_checkpoints()
    with patch("time.time", return_value=200.0):
        second = await runtime.list_checkpoints()
    assert [x.name for x in first] == ["cua-base-example", "cua-ckpt-old"]
    assert [x.created_at for x in first] == [100.0, 100.0]
    assert [x.created_at for x in second] == [200.0, 200.0]
    results = {
        "source": str(Path(module.__file__).resolve().relative_to(Path(os.environ["QUALIFICATION_SOURCE_ROOT"]))),
        "default_created_at": CheckpointInfo("x", "lume").created_at,
        "list_first": [x.__dict__ for x in first],
        "list_second": [x.__dict__ for x in second],
        "existing_base": {},
    }
    for status in ["stopped", "suspended"]:
        requests = []
        def responder(request):
            requests.append((request.method, str(request.url)))
            return httpx.Response(200, json={"name": "cua-base-example", "status": status})
        def mock_client(*args, **kwargs):
            return RealClient(*args, **kwargs, transport=httpx.MockTransport(responder))
        with patch("httpx.AsyncClient", mock_client), patch("time.time", return_value=300.0):
            base1 = await LumeRuntime().ensure_base(Image.macos("tahoe"), "cua-base-example")
        with patch("httpx.AsyncClient", mock_client), patch("time.time", return_value=400.0):
            base2 = await LumeRuntime().ensure_base(Image.macos("tahoe"), "cua-base-example")
        assert (base1.created_at, base2.created_at) == (300.0, 400.0)
        assert len(requests) == 2 and all(method == "GET" for method, url in requests)
        results["existing_base"][status] = {
            "first": base1.created_at, "second": base2.created_at, "requests": requests
        }
    assert "cua" not in sys.modules and "cua._native" not in sys.modules
    results["scope"] = (
        "Real Python package, deterministic fake clocks, list stub and httpx MockTransport only. "
        "Native SDK loads, processes, and sockets refused by guards.py. No live Lume or guest "
        "evidence; no candidate fix or unknown-time sentinel assertion."
    )
    print(json.dumps(results, indent=2))

asyncio.run(observe())
