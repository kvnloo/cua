"""Backend-level element-addressing probe (pilot; not a measured run).
usage: python probe_addr.py <hermes_wt> <fixture_port>   (env: HERMES_CUA_DRIVER_CMD, TMPDIR with gtk3-state.json)"""
import json, os, sys, time, urllib.request
sys.path.insert(0, sys.argv[1])
from tools.computer_use.cua_backend import CuaDriverBackend
from tools.computer_use.tool import _action_payload
port = sys.argv[2]
def st(): return json.loads(open(os.environ["TMPDIR"] + "/gtk3-state.json").read())
def fx(): return json.loads(urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f"http://127.0.0.1:{port}/state").read().decode())
def el(cap, role, label): return next(e for e in cap.elements if e.role == role and e.label == label)
def P(r): d = _action_payload(r); return {k: d.get(k) for k in ("ok", "message", "effect", "path", "delivery_mode", "code")}
sent = []
b = CuaDriverBackend(permission_mode="standard"); b.start()
orig = b._session.call_tool
def spy(name, args, *a, **k):
    if name not in ("list_windows", "get_window_state", "list_apps"):
        sent.append({"tool": name, "keys": sorted(args), "element_token": args.get("element_token"), "element_index": args.get("element_index")})
    return orig(name, args, *a, **k)
b._session.call_tool = spy
out = {"driver": os.path.basename(os.environ["HERMES_CUA_DRIVER_CMD"]), "hermes_wt": os.path.basename(sys.argv[1])}
try:
    cap = b.capture(mode="ax", app="Main.py"); e = el(cap, "check box", "I agree")
    out["gtk_tokens"] = len(b._snapshot_tokens); out["gtk_index"] = e.index
    out["gtk_bad_index"] = P(b.click(element=999)); out["gtk_bad_index_sent"] = len(sent)
    out["gtk_elem_bg"] = P(b.click(element=e.index)); time.sleep(0.5); out["gtk_state"] = st()
    cap = b.capture(mode="ax", app="Google-chrome")
    ent, sub = el(cap, "entry", "verification value"), el(cap, "button", "Submit")
    out["chr_tokens"] = len(b._snapshot_tokens); out["chr_indices"] = [ent.index, sub.index]
    out["chr_entry_fg"] = P(b.click(element=ent.index, delivery_mode="foreground"))
    out["chr_type_fg"] = P(b.type_text("addr-probe-1", delivery_mode="foreground"))
    out["chr_submit_fg"] = P(b.click(element=sub.index, delivery_mode="foreground")); time.sleep(1)
    out["fixture_state_1"] = fx()
    cap = b.capture(mode="ax", app="Google-chrome")
    out["chr_after_submit_elements"] = [(e.index, e.role, e.label) for e in cap.elements][:12]
    ents = [e for e in cap.elements if e.role == "entry"]
    if ents:
        out["chr_setvalue"] = P(b.set_value(value="addr-probe-2", element=ents[0].index))
except Exception as exc:
    out["error"] = repr(exc)
finally:
    out["sent"] = sent
    b.stop()
print(json.dumps(out, indent=1, default=str))
