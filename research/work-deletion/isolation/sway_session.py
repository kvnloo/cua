#!/usr/bin/env python3
"""Run one bounded experiment on private headless Sway; never the host seat.

Usage: sway_session.py --receipt /absolute/path.json -- COMMAND [ARGS...]
No product code or global desktop configuration is changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from sway_isolation import validate_environment

HERE = Path(__file__).resolve().parent
SWAY_ROOT = Path('/home/kvn/.local/opt/sway-nested')
DRIVER = Path('/mnt/zer0models/github/cua-lanes/evidence/4316-maintainer-proof-review/cua-driver-current-main')
BUILD = DRIVER.with_name('driver-build-receipt.json')


def host_focus():
    result = subprocess.run(['/usr/bin/hyprctl', 'activewindow', '-j'], capture_output=True, text=True, timeout=3)
    if result.returncode:
        return None
    data = json.loads(result.stdout)
    return {key: data.get(key) for key in ('address', 'class', 'workspace', 'monitor')}


def endpoint_ready(path):
    client = socket.socket(socket.AF_UNIX)
    client.settimeout(.1)
    try:
        client.connect(str(path))
        return True
    except OSError:
        return False
    finally:
        client.close()


def wait_ready(proc, probe, label, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise RuntimeError(label + ' exited before readiness')
        value = probe()
        if value:
            return value
        time.sleep(.03)
    raise TimeoutError(label + ' readiness deadline')


def owned_processes(marker):
    needle = ('CUA_SWAY_LEASE=' + marker).encode()
    found = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            state = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[0]
            if state != 'Z' and needle in (proc / 'environ').read_bytes().split(b'\0'):
                found.append(int(proc.name))
        except OSError:
            pass
    return found


def cleanup(marker, procs):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in owned_processes(marker):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        end = time.monotonic() + 2
        while owned_processes(marker) and time.monotonic() < end:
            time.sleep(.03)
    for proc in procs:
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    left = owned_processes(marker)
    if left:
        raise RuntimeError('owned live processes remain after cleanup')
    return {'live_owned_processes_remaining': left}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('a command is required after --')
    receipt_path = args.receipt.resolve()
    if receipt_path.exists():
        raise ValueError('preserve existing receipts; choose a new trial path')
    scratch = Path(os.environ['TMPDIR']).resolve()
    marker = uuid.uuid4().hex
    focus_before = host_focus()
    build = json.loads(BUILD.read_text())
    driver_hash = hashlib.sha256(DRIVER.read_bytes()).hexdigest()
    if build['exit_code'] != 0 or driver_hash != build['sha256']:
        raise ValueError('Driver build hash mismatch')
    record = {'schema': 1, 'cell_key': 'headless-sway-private-driver-isolation-v1',
              'trial_key': marker, 'sway_version': None, 'driver_sha256': driver_hash,
              'driver_source_rust_tree': build['source_rust_tree'], 'host_focus_before': focus_before,
              'command_exit': None, 'complete': False,
              'isolation_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'wrapper_sha256': hashlib.sha256((HERE / 'private_driver.py').read_bytes()).hexdigest()}
    procs = []
    interrupted = False
    old_handlers = {}
    def cancel(sig, frame):
        nonlocal interrupted
        interrupted = True
        raise InterruptedError('owned Sway experiment cancelled')
    for sig in (signal.SIGTERM, signal.SIGINT):
        old_handlers[sig] = signal.signal(sig, cancel)
    with tempfile.TemporaryDirectory(prefix='sway-', dir=scratch) as directory:
        root = Path(directory)
        for name in ('home', 'runtime', 'tmp'):
            (root / name).mkdir(mode=0o700)
        runtime = root / 'runtime'
        library = str(SWAY_ROOT / 'lib')
        env = {'HOME': str(root / 'home'), 'USER': os.environ.get('USER', 'kvn'),
               'LOGNAME': os.environ.get('USER', 'kvn'), 'LANG': 'C.UTF-8',
               'PATH': str(SWAY_ROOT / 'bin') + ':/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin:/home/kvn/.local/opt/cua-e2e-x11/root/usr/bin:/home/kvn/.local/bin:/usr/local/bin:/usr/bin:/bin',
               'LD_LIBRARY_PATH': library, 'TMPDIR': str(root / 'tmp'),
               'XDG_RUNTIME_DIR': str(runtime), 'XDG_CONFIG_HOME': str(root / 'home/.config'),
               'XDG_CACHE_HOME': str(root / 'home/.cache'), 'XDG_STATE_HOME': str(root / 'home/.local/state'),
               'XDG_DATA_HOME': str(root / 'home/.local/share'), 'XDG_SESSION_TYPE': 'wayland',
               'XDG_CURRENT_DESKTOP': 'sway', 'WLR_BACKENDS': 'headless',
               'WLR_RENDERER': 'pixman', 'WLR_HEADLESS_OUTPUTS': '1', 'CUA_SWAY_LEASE': marker,
               'CUA_DRIVER_PERMISSION_MODE': 'unrestricted', 'CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS': '1',
               'CUA_DRIVER_RS_TELEMETRY_ENABLED': 'false', 'CUA_DRIVER_RS_ENABLE_WAYLAND': '1',
               'CUA_DRIVER_BIN': str(HERE / 'private_driver.py'),
               'CUA_E2E_BROWSER_NO_SANDBOX': '1'}
        env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + str(runtime / 'bus')
        bus = subprocess.Popen(['/usr/bin/dbus-daemon', '--session', '--nofork', '--address=' + env['DBUS_SESSION_BUS_ADDRESS']], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        procs.append(bus)
        config = root / 'sway.conf'
        config.write_text('xwayland disable\noutput HEADLESS-1 mode 1280x720\nseat seat0 fallback true\n')
        try:
            wait_ready(bus, lambda: endpoint_ready(runtime / 'bus'), 'private DBus')
            record['sway_version'] = subprocess.check_output([str(SWAY_ROOT / 'bin/sway'), '--version'], env=env, text=True).strip()
            sway = subprocess.Popen([str(SWAY_ROOT / 'bin/sway'), '--unsupported-gpu', '--config', str(config)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            procs.append(sway)
            sock = wait_ready(sway, lambda: next(iter(runtime.glob('sway-ipc.*.sock')), None), 'headless Sway')
            display = wait_ready(sway, lambda: next((p.name for p in runtime.glob('wayland-*') if p.is_socket()), None), 'private Wayland')
            env.update(SWAYSOCK=str(sock), WAYLAND_DISPLAY=display)
            validate_environment(env, root)
            def ipc(kind):
                return json.loads(subprocess.check_output([str(SWAY_ROOT / 'bin/swaymsg'), '-s', str(sock), '-r', '-t', kind], env=env, text=True))
            outputs = ipc('get_outputs')
            if len(outputs) != 1 or not all(o['name'].startswith('HEADLESS-') and o['active'] for o in outputs):
                raise ValueError('physical or unexpected compositor output')
            inputs = ipc('get_inputs')
            if inputs:
                raise ValueError('unexpected input devices on initial headless compositor')
            for fd in (Path('/proc') / str(sway.pid) / 'fd').iterdir():
                target = os.readlink(fd)
                if target.startswith(('/dev/input/', '/dev/dri/card', '/dev/tty')):
                    raise ValueError('compositor opened a physical input/output device')
            # Move ONLY the private Sway cursor, never host hyprctl input.
            moved = json.loads(subprocess.check_output([str(SWAY_ROOT / 'bin/swaymsg'), '-s', str(sock), '-r', 'seat seat0 cursor set 80 100'], env=env, text=True))
            if not moved or not all(x.get('success') for x in moved):
                raise ValueError('private cursor probe failed')
            driver_socket = runtime / 'driver.sock'
            driver = subprocess.Popen([str(DRIVER), 'serve', '--embedded', '--socket', str(driver_socket), '--pid-file', str(runtime / 'driver.pid'), '--permission-mode', 'unrestricted', '--dangerously-bypass-approvals', '--no-overlay'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            procs.append(driver)
            wait_ready(driver, lambda: endpoint_ready(driver_socket), 'private Driver')
            lease = {'root': str(root), 'marker': marker, 'sway_socket': str(sock),
                     'driver_socket': str(driver_socket), 'driver_binary': str(DRIVER),
                     'sway_pid': sway.pid, 'driver_pid': driver.pid, 'library_path': library}
            (runtime / 'work-deletion-sway-lease.json').write_text(json.dumps(lease))
            record['runtime'] = str(runtime)
            record['environment'] = {k: env[k] for k in ('HOME', 'XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'SWAYSOCK', 'DBUS_SESSION_BUS_ADDRESS', 'WLR_BACKENDS', 'WLR_RENDERER')}
            record['outputs'] = [{k: o.get(k) for k in ('name', 'make', 'model', 'active', 'current_mode')} for o in outputs]
            record['initial_input_devices'] = inputs
            record['private_cursor_probe'] = moved
            record['host_routes_present'] = False
            record['physical_devices_open'] = False
            record['driver_endpoint_explicit'] = str(driver_socket)
            record['owned_pids'] = {'sway': sway.pid, 'driver': driver.pid, 'dbus': bus.pid}
            record['ready'] = True
            t0 = time.perf_counter()
            experiment = subprocess.Popen(command, env=env, start_new_session=True)
            procs.append(experiment)
            record['command_exit'] = experiment.wait(timeout=args.timeout)
            record['command_lifetime_ms'] = (time.perf_counter() - t0) * 1000
        except BaseException as error:
            record['error_type'] = type(error).__name__
            record['error'] = str(error) if isinstance(error, (ValueError, TimeoutError, RuntimeError, InterruptedError)) else 'see exception type; content suppressed'
            record['command_exit'] = 130 if interrupted else 70
        finally:
            record['cleanup'] = cleanup(marker, procs)
            record['host_focus_after'] = host_focus()
            record['host_focus_unchanged'] = record['host_focus_after'] == focus_before
            record['interrupted'] = interrupted
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
    record['runtime_removed'] = not (root / 'runtime').exists()
    record['complete'] = bool(record.get('ready') and record['command_exit'] == 0 and record['runtime_removed'] and record['host_focus_unchanged'])
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'receipt': str(receipt_path), 'complete': record['complete'], 'command_exit': record['command_exit'], 'error': record.get('error')}))
    return 0 if record['complete'] else (record['command_exit'] or 70)


if __name__ == '__main__':
    raise SystemExit(main())
