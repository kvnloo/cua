"""Tests: playground /responses endpoint tolerates malformed input shapes.

Two defects, same endpoint:

1. A non-object JSON body (array, string, ...) hit body.get("model")
   unguarded, raising an unhandled AttributeError (HTTP 500) instead of a
   400. Now rejected with 400 "Request body must be a JSON object".

2. The pending-computer-call bookkeeping ran msg.get("type") on every agent
   output entry and msg["call_id"] unconditionally: a non-dict entry raised
   AttributeError and a call entry missing call_id raised KeyError, flipping
   the whole /responses call to status "failed" even though the agent run
   itself was fine. Malformed entries are now skipped/tolerated, matching the
   run loop's own tolerance.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SERVER_FILE = REPO / "libs/python/agent/cua_agent/playground/server.py"


class HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class JSONResponse:
    def __init__(self, content, headers=None):
        self.content = content
        self.headers = headers or {}


class FakeApp:
    def __init__(self, **kwargs):
        self.routes = {}

    def get(self, path):
        def deco(fn):
            self.routes["GET " + path] = fn
            return fn

        return deco

    def post(self, path):
        def deco(fn):
            self.routes["POST " + path] = fn
            return fn

        return deco

    def add_middleware(self, *args, **kwargs):
        pass


class FakeAgent:
    """Stand-in for ComputerAgent; yields canned step results."""

    results = []

    def __init__(self, model=None, **kwargs):
        self.model = model

    async def run(self, messages):
        for r in self.results:
            yield r


def _load_server():
    for name in list(sys.modules):
        if name == "cua_agent" or name.startswith(("fastapi", "uvicorn", "pg_pkg")):
            del sys.modules[name]

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = FakeApp
    fastapi.HTTPException = HTTPException
    fastapi.Request = object
    sys.modules["fastapi"] = fastapi

    mw = types.ModuleType("fastapi.middleware")
    cors = types.ModuleType("fastapi.middleware.cors")
    cors.CORSMiddleware = object
    mw.cors = cors
    sys.modules["fastapi.middleware"] = mw
    sys.modules["fastapi.middleware.cors"] = cors
    fastapi.middleware = mw

    resp = types.ModuleType("fastapi.responses")
    resp.JSONResponse = JSONResponse
    sys.modules["fastapi.responses"] = resp

    uvicorn = types.ModuleType("uvicorn")
    uvicorn.Config = object
    uvicorn.Server = object
    sys.modules["uvicorn"] = uvicorn

    cua_agent = types.ModuleType("cua_agent")
    cua_agent.ComputerAgent = FakeAgent
    sys.modules["cua_agent"] = cua_agent

    pkg = types.ModuleType("pg_pkg")
    pkg.__path__ = []
    sys.modules["pg_pkg"] = pkg

    spec = importlib.util.spec_from_file_location("pg_pkg.server", SERVER_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pg_pkg.server"] = mod
    spec.loader.exec_module(mod)
    return mod


def _endpoint(mod):
    server = mod.PlaygroundServer()
    return server.app.routes["POST /responses"]


def _request(body):
    async def _json():
        return body

    req = types.SimpleNamespace()
    req.json = _json
    return req


def test_non_object_body_rejected_400():
    mod = _load_server()
    endpoint = _endpoint(mod)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(endpoint(_request(["not", "an", "object"])))
    assert exc.value.status_code == 400


def test_non_dict_output_entry_does_not_fail_run():
    mod = _load_server()
    FakeAgent.results = [{"output": ["oops-not-a-dict"], "usage": {}}]
    endpoint = _endpoint(mod)
    resp = asyncio.run(
        endpoint(_request({"model": "m", "input": "hi"}))
    )
    assert resp.content["status"] == "completed"
    assert resp.content["error"] is None


def test_call_entry_missing_call_id_tolerated():
    mod = _load_server()
    FakeAgent.results = [
        {"output": [{"type": "computer_call"}], "usage": {}},
        {"output": [{"type": "computer_call_output"}], "usage": {}},
    ]
    endpoint = _endpoint(mod)
    resp = asyncio.run(endpoint(_request({"model": "m", "input": "hi"})))
    assert resp.content["status"] == "completed"
    assert resp.content["error"] is None


def test_normal_pending_call_flow_control():
    mod = _load_server()
    FakeAgent.results = [
        {
            "output": [{"type": "computer_call", "call_id": "c1"}],
            "usage": {"input_tokens": 3},
        },
        {
            "output": [{"type": "computer_call_output", "call_id": "c1"}],
            "usage": {"input_tokens": 2},
        },
    ]
    endpoint = _endpoint(mod)
    resp = asyncio.run(endpoint(_request({"model": "m", "input": "hi"})))
    assert resp.content["status"] == "completed"
    assert resp.content["usage"] == {"input_tokens": 5}
