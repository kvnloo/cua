"""Evidence-local isolation gates; no product or Driver changes."""
from pathlib import Path


def validate_environment(env, root: Path):
    root = root.resolve()
    runtime = root / 'runtime'
    for key in ('DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE', 'CUA_INJECT_SOCKET', 'AT_SPI_BUS_ADDRESS', 'XAUTHORITY'):
        if env.get(key):
            raise ValueError('host input/session route present: ' + key)
    for key, value in {'HOME': str(root / 'home'), 'XDG_RUNTIME_DIR': str(runtime),
                       'WLR_BACKENDS': 'headless', 'WLR_RENDERER': 'pixman',
                       'XDG_SESSION_TYPE': 'wayland'}.items():
        if env.get(key) != value:
            raise ValueError('isolation setting mismatch: ' + key)
    display = env.get('WAYLAND_DISPLAY', '')
    if not display or '/' in display or display in ('.', '..'):
        raise ValueError('Wayland display must name the private runtime socket')
    sway = Path(env.get('SWAYSOCK', '/'))
    if sway.parent.resolve() != runtime:
        raise ValueError('Sway IPC outside private runtime')
    bus = env.get('DBUS_SESSION_BUS_ADDRESS', '').split(',guid=')[0]
    if not bus.startswith('unix:path=') or Path(bus.removeprefix('unix:path=')).parent.resolve() != runtime:
        raise ValueError('DBus outside private runtime')
