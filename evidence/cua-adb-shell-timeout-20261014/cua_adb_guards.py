"""Run these adapter tests without native SDK loads, processes or network."""

import importlib.abc
import os
import socket
import subprocess
import sys


class _NoNativeSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "cua" or fullname.startswith("cua."):
            raise ImportError("native cua SDK deliberately unavailable in adapter qualification")
        return None


def _refuse(*args, **kwargs):
    raise AssertionError("unexpected real process or network access in adapter qualification")


sys.meta_path.insert(0, _NoNativeSDK())
subprocess.Popen = _refuse
os.system = _refuse
socket.socket.connect = _refuse
socket.socket.connect_ex = _refuse
socket.create_connection = _refuse


def pytest_sessionfinish(session, exitstatus):
    assert "cua" not in sys.modules
    assert "cua._native" not in sys.modules
