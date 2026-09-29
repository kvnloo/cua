#!/usr/bin/env bash
# Sanitized (no titles, no window content) Hyprland state: monitor->workspace, focused class, client classes+workspace.
# usage: hypr-snapshot.sh <out.json>
out="$1"
python3 - "$out" <<'PY'
import json, subprocess, sys, time
def hj(*a):
    try: return json.loads(subprocess.check_output(["hyprctl", *a, "-j"], text=True, stderr=subprocess.DEVNULL))
    except Exception as e: return {"error": str(e)}
mons = hj("monitors", "all")
aw = hj("activewindow")
clients = hj("clients")
snap = {
  "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
  "monitors": [{"name": m.get("name"), "activeWorkspace": (m.get("activeWorkspace") or {}).get("name"), "focused": m.get("focused")} for m in mons] if isinstance(mons, list) else mons,
  "focused_class": aw.get("class") if isinstance(aw, dict) else None,
  "focused_workspace": (aw.get("workspace") or {}).get("name") if isinstance(aw, dict) else None,
  "clients": sorted([{"class": c.get("class"), "workspace": (c.get("workspace") or {}).get("name"), "monitor": c.get("monitor")} for c in clients], key=lambda x: (str(x["class"]), str(x["workspace"]))) if isinstance(clients, list) else clients,
}
json.dump(snap, open(sys.argv[1], "w"), indent=1, sort_keys=True)
print(json.dumps({"monitors": snap["monitors"], "focused_class": snap["focused_class"], "n_clients": len(snap["clients"]), "classes": sorted({str(c["class"]) for c in snap["clients"]})}))
PY
