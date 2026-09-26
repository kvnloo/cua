"""Tests for computer-use-mcp.py's request() startup-wait behavior.

The script is a self-contained `uv run --script` file (not an installed
package), so this harness exec's its source with stubbed `httpx`/`fastmcp`
modules and drives request() with a fake HTTP client.

Run: python3 test_computer_use_mcp.py
"""

import json
import os
import sys
import types

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "computer-use-mcp.py")


def load_script():
    """Exec the script source with stubbed httpx/fastmcp; return (module, httpx_stub)."""
    httpx = types.ModuleType("httpx")

    class TransportError(Exception):
        pass

    class ConnectError(TransportError):
        pass

    class Client:
        def __init__(self, *a, **k):
            pass

        def post(self, *a, **k):
            raise AssertionError("post not stubbed")

    httpx.TransportError = TransportError
    httpx.ConnectError = ConnectError
    httpx.Client = Client

    fastmcp = types.ModuleType("fastmcp")

    class FastMCP:
        def __init__(self, name):
            self.name = name

        def tool(self):
            def deco(fn):
                return fn
            return deco

        def run(self):
            pass

    fastmcp.FastMCP = FastMCP
    utils_mod = types.ModuleType("fastmcp.utilities")
    types_mod = types.ModuleType("fastmcp.utilities.types")

    class Image:
        def __init__(self, data=None, format=None):
            self.data = data
            self.format = format

    types_mod.Image = Image

    sys.modules["httpx"] = httpx
    sys.modules["fastmcp"] = fastmcp
    sys.modules["fastmcp.utilities"] = utils_mod
    sys.modules["fastmcp.utilities.types"] = types_mod

    mod = types.ModuleType("computer_use_mcp")
    with open(SCRIPT_PATH) as f:
        src = f.read()
    exec(compile(src, SCRIPT_PATH, "exec"), mod.__dict__)
    return mod, httpx


class FakeResp:
    def __init__(self, payload=None, decode_error=False):
        self._payload = payload
        self._decode_error = decode_error

    def json(self):
        if self._decode_error:
            raise json.JSONDecodeError("Expecting value", "", 0)
        return self._payload


class FakeClient:
    """Pops behaviors per post(); Exception instances are raised."""

    def __init__(self, behaviors):
        self.behaviors = list(behaviors)
        self.calls = 0

    def post(self, url, json=None):
        self.calls += 1
        b = self.behaviors.pop(0)
        if isinstance(b, Exception):
            raise b
        return b


PASS = []
FAIL = []


def check(name, fn):
    try:
        fn()
    except Exception as e:
        FAIL.append((name, e))
        print(f"FAIL {name}: {type(e).__name__}: {e}")
    else:
        PASS.append(name)
        print(f"ok   {name}")


def main():
    mod, httpx = load_script()

    def with_client(behaviors, budget=None):
        mod.client = FakeClient(behaviors)
        if budget is not None:
            mod.STARTUP_WAIT_BUDGET_S = budget
        # keep tests fast: the wait loop's sleeps are no-ops
        real_sleep = mod.time.sleep
        mod.time.sleep = lambda s: None
        return real_sleep

    def restore_sleep(real_sleep):
        mod.time.sleep = real_sleep

    # 1. Connection refused (server not listening yet — the common startup
    #    shape) is retried instead of failing the tool call immediately.
    def t_retries_connect_error():
        real = with_client([httpx.ConnectError("refused"),
                            httpx.ConnectError("refused"),
                            FakeResp({"ok": True})])
        try:
            assert mod.request("screenshot") == {"ok": True}
            assert mod.client.calls == 3, mod.client.calls
        finally:
            restore_sleep(real)
    check("retries_connect_error_then_succeeds", t_retries_connect_error)

    # 2. Non-JSON response while starting (empty body / proxy error page)
    #    is retried instead of raising JSONDecodeError.
    def t_retries_non_json():
        real = with_client([FakeResp(decode_error=True),
                            FakeResp({"ok": True})])
        try:
            assert mod.request("screenshot") == {"ok": True}
            assert mod.client.calls == 2, mod.client.calls
        finally:
            restore_sleep(real)
    check("retries_non_json_response_then_succeeds", t_retries_non_json)

    # 3. The explicit "still starting" JSON error still waits and retries.
    def t_starting_error():
        real = with_client([FakeResp({"error": "cuabotd is still starting"}),
                            FakeResp({"ok": True})])
        try:
            assert mod.request("click") == {"ok": True}
            assert mod.client.calls == 2, mod.client.calls
        finally:
            restore_sleep(real)
    check("starting_error_json_still_retries", t_starting_error)

    # 4. A genuine server error raises immediately (no pointless waiting).
    def t_real_error_raises():
        real = with_client([FakeResp({"error": "bad coordinates"})])
        try:
            try:
                mod.request("click")
            except Exception as e:
                assert str(e) == "bad coordinates", str(e)
            else:
                raise AssertionError("did not raise")
            assert mod.client.calls == 1, mod.client.calls
        finally:
            restore_sleep(real)
    check("real_server_error_raises_immediately", t_real_error_raises)

    # 5. The wait is bounded by wall-clock time, not attempt count: each
    #    attempt costs 20ms of (fake) clock here, so a 120-attempt loop
    #    would make 120 calls; the deadline must cut it off far earlier.
    def t_deadline_bounds_slow_attempts():
        clock = {"t": 1000.0}

        class SlowStarting(FakeClient):
            def post(self, url, json=None):
                clock["t"] += 0.02  # each attempt costs 20ms
                return super().post(url, json=json)

        mod.client = SlowStarting([FakeResp({"error": "cuabotd is still starting"})] * 1000)
        mod.STARTUP_WAIT_BUDGET_S = 0.12
        real_sleep = mod.time.sleep
        real_monotonic = mod.time.monotonic
        mod.time.sleep = lambda s: None
        mod.time.monotonic = lambda: clock["t"]
        try:
            try:
                mod.request("screenshot")
            except Exception as e:
                assert "Timed out waiting for cuabotd to start" in str(e), str(e)
            else:
                raise AssertionError("did not time out")
            # 0.12s budget / 0.02s per attempt -> ~6 attempts, far below 120
            assert mod.client.calls < 20, f"{mod.client.calls} attempts, no deadline"
        finally:
            mod.time.sleep = real_sleep
            mod.time.monotonic = real_monotonic
            mod.STARTUP_WAIT_BUDGET_S = 120.0
    check("deadline_bounds_slow_attempts", t_deadline_bounds_slow_attempts)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
