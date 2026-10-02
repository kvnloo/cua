"""Residual (non-index) argument mismatches on the element-addressable tools, backend level (not a measured run).
usage: python probe_residual.py <hermes_wt> <fixture_port>"""
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
from tools.computer_use.cua_backend import CuaDriverBackend
from tools.computer_use.tool import _action_payload
def P(r): d = _action_payload(r); return {k: d.get(k) for k in ("ok", "message", "code")}
def st(): return json.loads(open(os.environ["TMPDIR"] + "/gtk3-state.json").read())
sent = []
b = CuaDriverBackend(permission_mode="standard"); b.start()
orig = b._session.call_tool
def spy(name, args, *a, **k):
    if name not in ("list_windows", "get_window_state", "list_apps"):
        sent.append({"tool": name, "keys": sorted(args)})
    return orig(name, args, *a, **k)
b._session.call_tool = spy
out = {"driver": os.path.basename(os.environ["HERMES_CUA_DRIVER_CMD"]), "hermes_wt": os.path.basename(sys.argv[1])}
try:
    cap = b.capture(mode="ax", app="Main.py")
    els = {(e.role, e.label): e for e in cap.elements}
    inc = els[("button", "Increment")]
    out["double_click_element"] = P(b.click(element=inc.index, click_count=2)); time.sleep(0.4); out["state_after_double"] = st().get("counter")
    cap = b.capture(mode="ax", app="Main.py"); els = {(e.role, e.label): e for e in cap.elements}
    out["drag_elements"] = P(b.drag(from_element=els[("button", "Increment")].index, to_element=els[("button", "Reset")].index))
    cap = b.capture(mode="ax", app="Main.py"); els = {(e.role, e.label): e for e in cap.elements}
    out["right_click_element"] = P(b.click(element=els[("button", "Increment")].index, button="right"))
    out["state_end"] = st()
except Exception as exc:
    out["error"] = repr(exc)
finally:
    out["sent"] = sent
    b.stop()
print(json.dumps(out, indent=1, default=str))
