#!/usr/bin/env python3
"""Recipe-local fail-closed client for one parent-owned headless Sway Driver."""
import json
import os
from pathlib import Path
import sys

from sway_isolation import validate_environment


def main():
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/')).resolve()
    lease = json.loads((runtime / 'work-deletion-sway-lease.json').read_text())
    root = Path(lease['root']).resolve()
    if runtime != root / 'runtime':
        raise ValueError('wrong lease runtime')
    env = dict(os.environ)
    # MCP allowlists omit SWAYSOCK. Restore only the recorded PRIVATE socket.
    env['SWAYSOCK'] = lease['sway_socket']
    env['WLR_BACKENDS'] = 'headless'
    env['WLR_RENDERER'] = 'pixman'
    env['LD_LIBRARY_PATH'] = lease['library_path']
    env['CUA_SWAY_LEASE'] = lease['marker']
    validate_environment(env, root)
    for key in ('sway_socket', 'driver_socket'):
        path = Path(lease[key])
        if path.parent.resolve() != runtime or not path.is_socket():
            raise ValueError('private endpoint unavailable: ' + key)
    for key in ('sway_pid', 'driver_pid'):
        proc = Path('/proc') / str(lease[key])
        if not proc.exists():
            raise ValueError('private owner exited: ' + key)
        environ = dict(item.split(b'=', 1) for item in (proc / 'environ').read_bytes().split(b'\0') if b'=' in item)
        if environ.get(b'CUA_SWAY_LEASE') != lease['marker'].encode():
            raise ValueError('private owner marker mismatch')
        if environ.get(b'XDG_RUNTIME_DIR') != str(runtime).encode() or environ.get(b'HYPRLAND_INSTANCE_SIGNATURE'):
            raise ValueError('private owner session mismatch')
    args = sys.argv[1:]
    if not args:
        raise ValueError('no Driver operation')
    # No caller may replace ownership or select the user's daemon.
    if any(arg in ('--socket', '--direct', '--embedded') or arg.startswith('--socket=') for arg in args[1:]):
        raise ValueError('caller ownership override refused')
    if args[0] in ('serve', 'autostart', 'permissions', 'update', 'config', 'stop'):
        raise ValueError('runtime management is parent-owned')
    if args[0] in ('mcp', 'call', 'status', 'sessions', 'revoke'):
        args += ['--socket', lease['driver_socket']]
    binary = lease['driver_binary']
    os.execve(binary, [binary, *args], env)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Sway isolation refused: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(70)
