"""Tests for overlay-cursor.py color handling (no GTK required).

GTK/cairo are stubbed out so the module's pure helpers can be exercised
headlessly. The startup path (main() -> OverlayCursor -> Gtk) cannot run
here, so the color-resolution policy lives in resolve_cursor_color() and is
tested directly.

Run: python3 test_overlay_cursor.py
"""

import os
import sys
import types

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "overlay-cursor.py")


def load_script():
    class _Any:
        def __init__(self, *a, **k):
            pass

        def __call__(self, *a, **k):
            return _Any()

        def __getattr__(self, name):
            return _Any

    def _ns():
        return type("NS", (), {"__getattr__": lambda self, n: _Any})()

    gi = types.ModuleType("gi")
    gi.require_version = lambda *a, **k: None
    repo = types.ModuleType("gi.repository")
    repo.Gdk = _ns()
    repo.GdkPixbuf = _ns()
    repo.GLib = _ns()
    repo.Gtk = _ns()
    gi.repository = repo
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repo
    sys.modules["cairo"] = _ns()

    mod = types.ModuleType("overlay_cursor")
    with open(SCRIPT_PATH) as f:
        src = f.read()
    exec(compile(src, SCRIPT_PATH, "exec"), mod.__dict__)
    return mod


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
    mod = load_script()

    # 1. is_valid_hex_color recognizes exactly the 6-digit hex shape.
    def t_valid_shape():
        assert mod.is_valid_hex_color("ff0000")
        assert mod.is_valid_hex_color("#ff0000")
        assert mod.is_valid_hex_color("FF00aA")
        assert not mod.is_valid_hex_color("zzz")
        assert not mod.is_valid_hex_color("abc")      # 3-digit shorthand
        assert not mod.is_valid_hex_color("")
        assert not mod.is_valid_hex_color("ff0000ff")  # 8-digit w/ alpha
        assert not mod.is_valid_hex_color("ff00")      # truncated
    check("valid_hex_shape_recognition", t_valid_shape)

    # 2. A valid explicit color is used as-is.
    def t_valid_passthrough():
        assert mod.resolve_cursor_color("cuabot", "ff0000") == "ff0000"
        assert mod.resolve_cursor_color("cuabot", "#00ff00") == "00ff00"
    check("valid_color_passes_through", t_valid_passthrough)

    # 3. A malformed --color= value falls back to the name-derived color
    #    instead of crashing hex_to_rgb with a ValueError (the old startup
    #    path fed the raw value straight in and died with a traceback).
    def t_malformed_falls_back():
        got = mod.resolve_cursor_color("cuabot", "zzz")
        assert mod.is_valid_hex_color(got), got
        assert got == mod.name_to_color("cuabot"), got
        assert mod.resolve_cursor_color("cuabot", "abc") == mod.name_to_color("cuabot")
    check("malformed_color_falls_back", t_malformed_falls_back)

    # 4. Empty color still derives from the name (existing behavior kept).
    def t_empty_derives_from_name():
        got = mod.resolve_cursor_color("cuabot", "")
        assert got == mod.name_to_color("cuabot"), got
        assert mod.is_valid_hex_color(got)
    check("empty_color_derives_from_name", t_empty_derives_from_name)

    # 5. Documents the hazard the fix removes: on the old code path the raw
    #    malformed value reached hex_to_rgb and raised ValueError.
    def t_hex_to_rgb_rejects_garbage():
        try:
            mod.hex_to_rgb("zzz")
        except ValueError:
            return
        raise AssertionError("hex_to_rgb accepted garbage")
    check("hex_to_rgb_rejects_garbage", t_hex_to_rgb_rejects_garbage)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
