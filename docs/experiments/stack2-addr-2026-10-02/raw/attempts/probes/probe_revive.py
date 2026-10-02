"""Ended-session revival probe (backend level; not a measured run).
Capture, end the driver session behind the backend's back (raw MCP end_session, declared id kept), click by element.
usage: python probe_revive.py <hermes_wt> <fixture_port>"""
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
import tools.computer_use.cua_backend as cb
from tools.computer_use.tool import _action_payload
def P(r): d = _action_payload(r); return {k: d.get(k) for k in ("ok", "message", "code")}
def st(): return json.loads(open(os.environ["TMPDIR"] + "/gtk3-state.json").read())
out = {"hermes_module": os.path.relpath(cb.__file__, sys.argv[1]), "hermes_wt": os.path.basename(sys.argv[1]),
       "driver": os.path.basename(os.environ["HERMES_CUA_DRIVER_CMD"])}
sent = []
b = cb.CuaDriverBackend(permission_mode="standard"); b.start()
s = b._session
orig = s._call_tool_async
async def spy(name, args):
    sent.append({"tool": name, "element_token": args.get("element_token")})
    return await orig(name, args)
s._call_tool_async = spy
try:
    cap = b.capture(mode="ax", app="Main.py")
    e = next(x for x in cap.elements if x.role == "check box" and x.label == "I agree")
    end = s._bridge.run(orig("end_session", {"session": b._session_id}), timeout=10)
    out["raw_end_session_isError"] = end.get("isError")
    out["click_after_end"] = P(b.click(element=e.index)); time.sleep(0.4)
    out["state_after_click"] = st().get("agreed")
    out["tokens_after"] = len(b._snapshot_tokens)
    cap = b.capture(mode="ax", app="Main.py")
    e = next(x for x in cap.elements if x.role == "check box" and x.label == "I agree")
    out["click_after_recapture"] = P(b.click(element=e.index)); time.sleep(0.4)
    out["state_final"] = st().get("agreed")
except Exception as exc:
    out["error"] = repr(exc)
finally:
    out["sent"] = [x for x in sent if x["tool"] not in ("list_windows", "get_window_state")]
    b.stop()
print(json.dumps(out, indent=1, default=str))
