"""Ended-session revival probe, both trigger types (backend level; not a measured run).
For each trigger: capture, end the driver session behind the backend's back (raw MCP end_session, declared id kept),
run the trigger call, then click "I agree" by its OLD element index, then capture again and click by the fresh index.
Triggers: element click (token-carrying), type_text and key (token-free).
usage: python probe_revive2.py <hermes_wt>"""
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
import tools.computer_use.cua_backend as cb
from tools.computer_use.tool import _action_payload


def P(r):
    d = _action_payload(r)
    return {k: d.get(k) for k in ("ok", "message", "code")}


def st():
    return json.loads(open(os.environ["TMPDIR"] + "/gtk3-state.json").read()).get("agreed")


def agree(cap):
    return next(x for x in cap.elements if x.role == "check box" and x.label == "I agree").index


out = {"hermes_module": os.path.relpath(cb.__file__, sys.argv[1]), "hermes_wt": os.path.basename(sys.argv[1]),
       "driver": os.path.basename(os.environ["HERMES_CUA_DRIVER_CMD"]), "scenarios": []}
sent = []
b = cb.CuaDriverBackend(permission_mode="standard")
b.start()
s = b._session
orig = s._call_tool_async


async def spy(name, args):
    sent.append({"tool": name, "element_token": args.get("element_token")})
    return await orig(name, args)


s._call_tool_async = spy
TRIGGERS = {"click_element": lambda idx: b.click(element=idx),
            "type_text": lambda idx: b.type_text("z"),
            "key": lambda idx: b.key("Escape")}
try:
    for trig, fn in TRIGGERS.items():
        sc = {"trigger": trig}
        idx = agree(b.capture(mode="ax", app="Main.py"))
        sc["tokens_before"], sc["agreed_before"] = len(b._snapshot_tokens), st()
        mark = len(sent)
        end = s._bridge.run(orig("end_session", {"session": b._session_id}), timeout=10)
        sc["raw_end_session_isError"] = end.get("isError")
        sc["trigger_result"] = P(fn(idx))
        sc["tokens_after_trigger"] = len(b._snapshot_tokens)
        if trig != "click_element":
            sc["old_index_click"] = P(b.click(element=idx))
        time.sleep(0.4)
        sc["agreed_after_old_token_path"] = st()
        idx = agree(b.capture(mode="ax", app="Main.py"))
        sc["fresh_click"] = P(b.click(element=idx))
        time.sleep(0.4)
        sc["agreed_final"] = st()
        sc["sent"] = [x for x in sent[mark:] if x["tool"] not in ("list_windows", "get_window_state")]
        tokens = [x["element_token"] for x in sc["sent"] if x["element_token"]]
        # a token is stale when it was sent after end_session but before the fresh capture's token
        sc["stale_tokens_sent"] = tokens[:-1] if trig != "click_element" else tokens[1:-1]
        out["scenarios"].append(sc)
except Exception as exc:
    out["error"] = repr(exc)
finally:
    b.stop()
print(json.dumps(out, indent=1, default=str))
