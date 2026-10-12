"""Run unchanged scoped pytest files while refusing native SDK and side effects."""
import importlib.abc
import os
import socket
import sys


class RefuseNativeSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "cua" or fullname.startswith("cua."):
            raise AssertionError("native SDK import forbidden by the in-memory test boundary")
        return None


sys.meta_path.insert(0, RefuseNativeSDK())
from cua_sandbox import _sdk  # noqa: E402


def no_native():
    # The existing optional manifest fixture explicitly handles ImportError.
    # No package import is stubbed; this refuses the accessor before SDK load.
    raise ImportError("native SDK accessor disabled for pure Python lifecycle tests")


def forbidden(*args, **kwargs):
    raise AssertionError("native execution, network or filesystem deletion forbidden")


_sdk.native = no_native
_sdk.sdk = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.socket.sendto = forbidden
os.unlink = forbidden
os.remove = forbidden
import pytest  # noqa: E402


# Runner preparation only: do not create pytest's "current" symlink.
# Keep the original isolation fixture and all deletion refusal guards intact.
from itertools import count  # noqa: E402
from unittest.mock import patch  # noqa: E402


class NonNumberedIsolation:
    def __init__(self):
        self.sequence = count()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_fixture_setup(self, fixturedef, request):
        if fixturedef.argname == "_isolate_live_env":
            factory = request.getfixturevalue("tmp_path_factory")
            mktemp = factory.mktemp

            def unique_directory(basename, numbered=True):
                return mktemp(f"{basename}-{next(self.sequence)}", numbered=False)

            with patch.object(factory, "mktemp", unique_directory):
                yield
        else:
            yield

code = pytest.main(sys.argv[1:], plugins=[NonNumberedIsolation()])
assert "cua" not in sys.modules
print("PURE_PYTHON_BOUNDARY native SDK unloaded; network and filesystem deletion refused")
raise SystemExit(code)
