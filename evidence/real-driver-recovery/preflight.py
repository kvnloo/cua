#!/usr/bin/env python3
"""Read-only native prerequisites. Exit 2 means BLOCKED, never E2E success."""
import datetime
import json
import os
import shutil
import socket
import subprocess
import tempfile

checks = {}
for name, family in (("unix_socket", socket.AF_UNIX), ("inet_socket", socket.AF_INET)):
    try:
        with socket.socket(family, socket.SOCK_STREAM):
            pass
        checks[name] = {"ok": True}
    except OSError as error:
        checks[name] = {"ok": False, "errno": error.errno, "error": str(error)}
checks["desktop"] = {"ok": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))}
checks["session_bus"] = {"ok": bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))}
for name in ("cargo", "uv", "node", "npm", "dbus-run-session"):
    checks[name] = {"ok": bool(shutil.which(name))}
if shutil.which("dbus-run-session"):
    with tempfile.TemporaryDirectory(prefix="cua-dbus-preflight-") as runtime:
        environment = {**os.environ, "XDG_RUNTIME_DIR": runtime}
        try:
            result = subprocess.run(["dbus-run-session", "--", "true"], env=environment,
                                    capture_output=True, text=True, timeout=10)
            checks["dbus_start"] = {"ok": result.returncode == 0, "exit_code": result.returncode,
                                    "stderr": result.stderr.strip()}
        except subprocess.TimeoutExpired:
            checks["dbus_start"] = {"ok": False, "error": "timeout after 10 seconds"}
try:
    result = subprocess.run(["python3", "-c", "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk"],
                            capture_output=True, text=True, timeout=10)
    checks["gtk3"] = {"ok": result.returncode == 0, "exit_code": result.returncode,
                       "stderr": result.stderr.strip()}
except subprocess.TimeoutExpired:
    checks["gtk3"] = {"ok": False, "error": "timeout after 10 seconds"}
blocked = [name for name, check in checks.items() if not check["ok"]]
print(json.dumps({"time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "status": "BLOCKED" if blocked else "PREREQUISITES_ONLY",
                  "e2e_executed": False, "failed_checks": blocked, "checks": checks}, indent=2))
raise SystemExit(2 if blocked else 0)
