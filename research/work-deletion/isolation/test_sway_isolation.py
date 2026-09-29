import copy
import unittest
from pathlib import Path
import sway_isolation


class IsolationTests(unittest.TestCase):
    def test_host_input_routes_are_rejected(self):
        root = Path('/owned/private')
        env = {'HOME': str(root / 'home'), 'XDG_RUNTIME_DIR': str(root / 'runtime'),
               'WAYLAND_DISPLAY': 'wayland-1', 'SWAYSOCK': str(root / 'runtime/sway.sock'),
               'WLR_BACKENDS': 'headless', 'WLR_RENDERER': 'pixman',
               'DBUS_SESSION_BUS_ADDRESS': 'unix:path=' + str(root / 'runtime/bus'),
               'XDG_SESSION_TYPE': 'wayland'}
        mutations = [ {'DISPLAY': ':1'}, {'HYPRLAND_INSTANCE_SIGNATURE': 'physical-host'},
                      {'WLR_BACKENDS': 'wayland'}, {'CUA_INJECT_SOCKET': '/run/user/1000/inject.sock'},
                      {'XDG_RUNTIME_DIR': '/run/user/1000'}, {'SWAYSOCK': '/run/user/1000/sway.sock'},
                      {'WAYLAND_DISPLAY': '/run/user/1000/wayland-1'},
                      {'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus'} ]
        for changes in mutations:
            with self.subTest(changes=changes):
                bad = {**env, **changes}
                with self.assertRaises(ValueError):
                    sway_isolation.validate_environment(bad, root)
        sway_isolation.validate_environment(env, root)


if __name__ == '__main__':
    unittest.main()
