#!/usr/bin/env python3
"""Bounded private endpoint smoke and host-routing negative controls."""
import json
import os
from pathlib import Path
import subprocess

runtime = Path(os.environ['XDG_RUNTIME_DIR'])
wrapper = os.environ['CUA_DRIVER_BIN']
result = subprocess.run([wrapper, 'status'], capture_output=True, text=True, timeout=10)
assert result.returncode == 0
# Exercise the exact desktop/Driver allowlist shape that the jev-use MCP
# transport forwards; SWAYSOCK/WLR/library/marker are deliberately omitted.
kept = {'HOME', 'PATH', 'USER', 'LOGNAME', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR',
        'DBUS_SESSION_BUS_ADDRESS', 'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP'}
filtered = {k: v for k, v in os.environ.items() if k in kept or k.startswith('CUA_DRIVER_')}
assert 'SWAYSOCK' not in filtered and 'CUA_SWAY_LEASE' not in filtered
filtered_status = subprocess.run([wrapper, 'status'], env=filtered, capture_output=True, text=True, timeout=10)
assert filtered_status.returncode == 0, 'MCP allowlist could not reach the private endpoint'
for label, changes, arguments in (
    ('host_hyprland_env', {'HYPRLAND_INSTANCE_SIGNATURE': 'host-negative-control'}, ['status']),
    ('host_display', {'DISPLAY': ':1'}, ['status']),
    ('host_endpoint_override', {}, ['status', '--socket', '/run/user/1000/cua-driver.sock']),
    ('direct_runtime_override', {}, ['mcp', '--direct']),
    ('management_override', {}, ['serve']),
):
    changed = {**os.environ, **changes}
    rejected = subprocess.run([wrapper, *arguments], env=changed, capture_output=True, text=True, timeout=10)
    assert rejected.returncode == 70, label
    assert 'Sway isolation refused' in rejected.stderr, label
    print(json.dumps({'negative_control': label, 'rejected_before_driver_exec': True}))
# Independently damage the endpoint lease; the client must fail without host fallback.
lease_path = runtime / 'work-deletion-sway-lease.json'
original = lease_path.read_text()
try:
    lease = json.loads(original)
    lease['driver_socket'] = '/run/user/1000/cua-driver.sock'
    lease_path.write_text(json.dumps(lease))
    rejected = subprocess.run([wrapper, 'status'], capture_output=True, text=True, timeout=10)
    assert rejected.returncode == 70
finally:
    lease_path.write_text(original)
print(json.dumps({'negative_control': 'corrupt_private_endpoint_lease', 'rejected_before_driver_exec': True}))
# Learn the genuine schema inside the private session; never touch the host.
schema = subprocess.run([wrapper, 'describe', 'move_cursor'], capture_output=True, text=True, timeout=10)
assert schema.returncode == 0
schema_text = schema.stdout.split('input_schema:\n', 1)[1]
actual_schema = json.loads(schema_text)
assert {'x', 'y'} <= set(actual_schema['required'])
# This is the ONLY actual input probe: explicit desktop input is confined to the
# private compositor/runtime, never the physical host desktop.
move_args = {'x': 120, 'y': 140,
             'target': {'kind': 'desktop', 'display_id': 'primary'},
             'session': 'private-sway-isolation-probe'}
move = subprocess.run([wrapper, 'call', 'move_cursor', json.dumps(move_args)],
                      capture_output=True, text=True, timeout=20)
print(json.dumps({'private_native_driver_cursor_exit': move.returncode,
                  'private_native_driver_cursor_response': move.stdout,
                  'private_native_driver_cursor_stderr': move.stderr}))
assert move.returncode == 0, 'private native Driver cursor probe failed'
private_inputs = json.loads(subprocess.check_output(
    ['swaymsg', '-s', os.environ['SWAYSOCK'], '-r', '-t', 'get_inputs'], text=True))
print(json.dumps({'independent_private_sway_inputs_after_driver': private_inputs}))
Path(__file__).with_name('sway-probe-negative-controls.json').write_text(json.dumps({
    'private_driver_status': 'passed',
    'negative_controls_rejected': ['host_hyprland_env', 'host_display',
                                  'host_endpoint_override', 'direct_runtime_override',
                                  'management_override', 'corrupt_private_endpoint_lease'],
    'genuine_schema_checked': True,
    'native_driver_cursor_probe': 'delivery_acknowledged_effect_unverifiable',
    'independent_private_sway_inputs_after_driver': private_inputs,
    'independent_pointer_position_verified': False,
    'oracle': 'private headless Sway IPC; parent wrapper preserves host focus and checks cleanup',
    'protected_field_contents_persisted': False,
}, indent=2) + '\n')
