"""OWN-20G: helpers shared by ``own20g_harness.py`` and ``r3_harness.py``.

Derived from the N-02 harness (``../n-02-native-transport-2026-10-02/n02_harness.py``):
the no-provider socket guard, the independent 2 ms state-file oracle
(``StateSampler``), the fixture launch, the Driver environment and the refusal to
run outside hostless + the isolated X11 session. Nothing here is Driver code.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

FIXTURE_REL = "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
JEV_REL = "libs/cua-driver/examples/jev-use"
WINDOW_TITLE = "CuaTestHarness GTK3 Tasks"
STATE_SCHEMA = "cua.gtk3_task_state_v1"
STATE_PERIOD_S = 0.002

# ----------------------------------------------------------------------------- no provider
NET: dict[str, Any] = {"refused_non_loopback_connects": 0, "targets": []}
_real_connect = socket.socket.connect


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    if self.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            NET["refused_non_loopback_connects"] += 1
            NET["targets"].append(str(host)[:64])
            raise ConnectionRefusedError("OWN-20G: provider cap 0, non-loopback connect refused")
    return _real_connect(self, address)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]


def now() -> tuple[int, int]:
    """(monotonic_ns, wall_ns) taken back to back."""
    return time.monotonic_ns(), time.time_ns()


def loadavg() -> list[float]:
    with open("/proc/loadavg", encoding="ascii") as stream:
        return [float(x) for x in stream.read().split()[:3]]


def read_state(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class StateSampler(threading.Thread):
    """Independent oracle (as N-01R / N-02): reads the app's own state file every 2 ms."""

    def __init__(self, path: Path) -> None:
        super().__init__(daemon=True)
        self.path = path
        self.stop_flag = threading.Event()
        self.t0: list[int] = []
        self.idx: list[int] = []
        self.states: list[Any] = []
        self._index: dict[str, int] = {}
        self.expected: dict[str, Any] | None = None
        self.return_ns: int | None = None
        self.confirmed = threading.Event()
        self.confirmed_ns: int | None = None

    def matches(self, state: Any) -> bool:
        exp = self.expected
        return (isinstance(state, dict) and exp is not None and state.get("schema") == STATE_SCHEMA
                and all(state.get(k) == v for k, v in exp.items()))

    def run(self) -> None:
        start = time.monotonic_ns()
        k = 0
        period = int(STATE_PERIOD_S * 1e9)
        while not self.stop_flag.is_set():
            a = time.monotonic_ns()
            try:
                raw = self.path.read_text(encoding="utf-8")
            except OSError:
                raw = ""
            i = self._index.get(raw)
            if i is None:
                try:
                    parsed: Any = json.loads(raw) if raw else None
                except ValueError:
                    parsed = {"unparsable": raw[:80]}
                i = len(self.states)
                self._index[raw] = i
                self.states.append(parsed)
            if not self.idx or self.idx[-1] != i:
                self.t0.append(a)
                self.idx.append(i)
            ret = self.return_ns
            if ret is not None and a >= ret and not self.confirmed.is_set() and self.matches(self.states[i]):
                self.confirmed_ns = a
                self.confirmed.set()
            k += 1
            delay = (start + k * period - time.monotonic_ns()) / 1e9
            if delay > 0:
                time.sleep(delay)

    def stop(self) -> dict[str, Any]:
        self.stop_flag.set()
        self.join(timeout=2)
        return {"changes_mono_ns": self.t0, "idx": self.idx, "states": self.states,
                "confirmed_ns": self.confirmed_ns}


def start_fixture(wt: Path, state_path: Path, log_path: Path) -> subprocess.Popen:
    fenv = dict(os.environ)
    fenv["CUA_GTK3_TASK_STATE"] = str(state_path)
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(["/usr/bin/python3", str(wt / FIXTURE_REL)], env=fenv,
                            stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 15
    while read_state(state_path) is None:
        if time.monotonic() > deadline or proc.poll() is not None:
            raise RuntimeError("fixture did not publish its state file")
        time.sleep(0.02)
    time.sleep(1.0)  # AT-SPI registration settle (as R2-04 / N-01R / N-02)
    return proc


def stop_process(proc: subprocess.Popen | None) -> int | None:
    if proc is None:
        return None
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    return proc.returncode


def driver_env(base: dict[str, str], phase_path: Path, extra: dict[str, str]) -> dict[str, str]:
    env = dict(base)
    for key in list(env):
        if key.startswith("CUA_DRIVER_EXP_") or key == "CUA_DRIVER_PHASE_TRACE_FILE":
            env.pop(key)
    env["CUA_DRIVER_PHASE_TRACE_FILE"] = str(phase_path)
    env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
    env["DO_NOT_TRACK"] = "1"
    env.update(extra)
    return env


def read_marks(phase_path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(x) for x in phase_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def refuse_outside_session() -> None:
    """run_all.sh checks hostless (CUA_HOSTLESS) before it enters the session, whose
    environment is rebuilt from scratch; here the session itself is checked."""
    host_runtime = Path(f"/run/user/{os.getuid()}")
    names = sorted(p.name for p in host_runtime.iterdir()) if host_runtime.is_dir() else []
    host_sockets = [n for n in names if n.startswith(("wayland-", "hypr", "pipewire"))
                    or n in ("bus", "at-spi", "systemd")]
    if (os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ)
            or not os.environ.get("DISPLAY") or host_sockets
            or os.environ.get("XDG_RUNTIME_DIR", "/run/user").startswith("/run/user")):
        raise SystemExit(f"refusing: not inside hostless + the isolated X11 session ({host_sockets})")
