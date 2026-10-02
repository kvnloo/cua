#!/usr/bin/env python3
"""Reachability-only isolation canary for cua-sway-session.sh.

Modes
  decoy   --dir D --abstract NAME --paths P1,P2...   bind decoy listeners (run OUTSIDE the session, in
                                                     hostless); log every accepted connection to D/accepts.jsonl
  control --abstract NAME --paths ... --out F        probe ONLY the decoys from outside the session
  inside  --abstract NAME --decoy-paths ... --host-sig SIG --out F
                                                     run inside the sway session: host targets, decoys, private
                                                     compositor checks

Probes only ever connect() and close(): no byte is sent on any socket, no host input, no host window.
The host abstract X11 sockets are only probed after the abstract decoy (bound outside the session) was
refused with EPERM, i.e. after the Landlock scope is proven active; otherwise they are skipped.
"""
import argparse
import errno
import json
import os
import socket
import subprocess
import sys
import time


def probe(addr):
    """connect() then close(). addr: filesystem path, or '@name' for the abstract namespace."""
    target = "\0" + addr[1:] if addr.startswith("@") else addr
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(target)
        return "REACHABLE"
    except OSError as e:
        return errno.errorcode.get(e.errno, str(e.errno))
    finally:
        s.close()


def abstract_x11_listeners():
    """Passive read of /proc/net/unix: listening abstract X11 sockets in this network namespace."""
    out = set()
    for l in open("/proc/net/unix").read().splitlines()[1:]:
        f = l.split()
        if len(f) >= 8 and f[3] == "00010000" and f[-1].startswith("@/tmp/.X11-unix/X"):
            out.add(f[-1])
    return sorted(out)


def decoy(args):
    os.makedirs(args.dir, exist_ok=True)
    socks = []
    for p in [x for x in args.paths.split(",") if x] + ["@" + args.abstract]:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if p.startswith("@"):
            s.bind("\0" + p[1:])
        else:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            if os.path.exists(p):
                os.unlink(p)
            s.bind(p)
        s.listen(16)
        s.setblocking(False)
        socks.append((p, s))
    log = open(os.path.join(args.dir, "accepts.jsonl"), "a", buffering=1)
    open(os.path.join(args.dir, "ready"), "w").write(str(os.getpid()))
    end = time.time() + args.seconds
    while time.time() < end:
        for p, s in socks:
            try:
                c, _ = s.accept()
                log.write(json.dumps({"t": round(time.time(), 3), "decoy": p}) + "\n")
                c.close()
            except BlockingIOError:
                pass
        time.sleep(0.02)


def control(args):
    rows = []
    for p in [x for x in args.paths.split(",") if x] + ["@" + args.abstract]:
        rows.append({"target": p, "kind": "decoy", "where": "outside-session (hostless, no landlock scope)",
                     "result": probe(p), "expect": "REACHABLE"})
    json.dump({"mode": "control", "rows": rows, "t": time.time()}, open(args.out, "w"), indent=1)


def run(cmd, **kw):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20, **kw)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # noqa: BLE001
        return -1, "", repr(e)


def sway_views():
    rc, out, _ = run(["swaymsg", "-t", "get_tree", "-r"])
    if rc != 0:
        return []
    def walk(n):
        yield n
        for k in ("nodes", "floating_nodes"):
            for c in n.get(k, []):
                yield from walk(c)
    return [{"id": n["id"], "pid": n.get("pid"), "shell": n.get("shell"), "app_id": n.get("app_id"),
             "name": n.get("name")} for n in walk(json.loads(out)) if n.get("type") == "con" and n.get("pid")]


def inside(args):
    uid = os.getuid()
    rt = f"/run/user/{uid}"
    rows = []

    def add(target, kind, expect, result=None, note=""):
        r = result if result is not None else probe(target)
        rows.append({"target": target, "kind": kind, "expect": expect, "result": r,
                     "pass": (r == expect) if isinstance(expect, str) else (r in expect), "note": note})
        return r

    env = {k: os.environ.get(k) for k in ("WAYLAND_DISPLAY", "DISPLAY", "SWAYSOCK", "XDG_RUNTIME_DIR",
                                           "DBUS_SESSION_BUS_ADDRESS", "AT_SPI_BUS_ADDRESS", "CUA_LANDLOCK_SCOPE",
                                           "CUA_HOSTLESS", "XDG_SESSION_TYPE")}
    env["HYPRLAND_vars"] = sorted(k for k in os.environ if k.startswith("HYPRLAND_"))
    private_root = os.environ.get("CUA_SWAY_RUN", "")
    env_checks = {
        "no_HYPRLAND_vars": not env["HYPRLAND_vars"],
        "XDG_RUNTIME_DIR_private": bool(private_root) and (env["XDG_RUNTIME_DIR"] or "").startswith(private_root),
        "WAYLAND_DISPLAY_socket_private": os.path.realpath(os.path.join(env["XDG_RUNTIME_DIR"] or "/nonexistent",
                                                                        env["WAYLAND_DISPLAY"] or "x")).startswith(private_root),
        "SWAYSOCK_private": (env["SWAYSOCK"] or "").startswith(private_root),
        "DBUS_private": "/run/user/" not in (env["DBUS_SESSION_BUS_ADDRESS"] or "/run/user/"),
        "landlock_scope": env["CUA_LANDLOCK_SCOPE"] == "abstract-unix,signal",
    }

    # 1. Gate: abstract decoy bound OUTSIDE this Landlock domain must be refused.
    gate = add("@" + args.abstract, "decoy-abstract (bound outside session)", "EPERM",
               note="Landlock LANDLOCK_SCOPE_ABSTRACT_UNIX_SOCKET gate")
    # 2. Host path sockets (the hostless tmpfs and the private /tmp must hide them).
    hypr_dir = f"{rt}/hypr"
    for name in (".socket.sock", ".socket2.sock"):
        add(f"{hypr_dir}/{args.host_sig}/{name}", "host-hyprland", "ENOENT")
    for w in ("wayland-0", "wayland-1", "wayland-2"):
        add(f"{rt}/{w}", "host-wayland", "ENOENT")
    add(f"{rt}/bus", "host-session-bus", "ENOENT")
    add(f"{rt}/at-spi/bus_1", "host-atspi-bus", "ENOENT")
    host_x = [int(n) for n in open(os.path.join(private_root, "host-x-displays")).read().split()]
    priv_x = int((env["DISPLAY"] or ":-1")[1:].split(".")[0])
    for n in host_x:
        add(f"/tmp/.X11-unix/X{n}", "host-x11-path", "ENOENT")
    # The session's own Xwayland socket, and proof it lives in the session's private /tmp.
    own = f"/tmp/.X11-unix/X{priv_x}"
    add(own, "private-x11-path (own Xwayland)", "REACHABLE")
    st_in, st_priv = os.stat(own), os.stat(os.path.join(private_root, "slash-tmp", ".X11-unix", f"X{priv_x}"))
    same = (st_in.st_dev, st_in.st_ino) == (st_priv.st_dev, st_priv.st_ino)
    rows.append({"target": f"{own} is the session's private /tmp inode", "kind": "private-x11-path (own Xwayland)",
                 "expect": True, "result": same, "pass": same, "note": ""})
    collide = priv_x in host_x
    rows.append({"target": f"private Xwayland :{priv_x} not in host display set {host_x}", "kind": "x11-display-number",
                 "expect": False, "result": collide, "pass": not collide, "note": "seeded lock files"})
    # 3. Host abstract X11 names: only after the gate proved the scope is active. EPERM = bound outside
    #    the domain and refused; ECONNREFUSED = nothing bound under that name.
    for n in host_x:
        if gate == "EPERM":
            add(f"@/tmp/.X11-unix/X{n}", "host-x11-abstract", ["EPERM", "ECONNREFUSED"])
        else:
            add(f"@/tmp/.X11-unix/X{n}", "host-x11-abstract", ["EPERM", "ECONNREFUSED"], result="SKIPPED_GATE_FAILED")
    # 4. Decoy path sockets: the probe must see what IS exposed (sensitivity), and the private /tmp
    #    must hide a decoy placed in hostless' /tmp/.X11-unix.
    for p in [x for x in args.decoy_paths.split(",") if x]:
        exp = "ENOENT" if p.startswith("/tmp/") else "REACHABLE"
        add(p, "decoy-path", exp, note="exposed decoy: probe sensitivity" if exp == "REACHABLE" else "hidden by private /tmp")
    try:
        listing = {rt: sorted(os.listdir(rt)), hypr_dir: sorted(os.listdir(hypr_dir)) if os.path.isdir(hypr_dir) else None}
    except OSError as e:
        listing = {"error": repr(e)}
    # 5. Abstract listeners visible in this network namespace (informational: shared netns).
    abstract_listeners = abstract_x11_listeners()
    pre = [x for x in args.pre_abstract.split(",") if x]
    added = sorted(set(abstract_listeners) - set(pre))
    want_added = [f"@/tmp/.X11-unix/X{priv_x}"]
    rows.append({"target": "abstract X11 listeners added to the shared netns by this session", "kind": "x11-abstract-shadowing",
                 "expect": want_added, "result": added, "pass": added == want_added,
                 "note": "exactly the private display; no host display name shadowed"})
    # 6. Private compositor: clients launched here connect to it.
    private = {}
    private["wayland_socket"] = add(os.path.join(env["XDG_RUNTIME_DIR"], env["WAYLAND_DISPLAY"]), "private-wayland", "REACHABLE")
    private["sway_ipc"] = add(env["SWAYSOCK"], "private-sway-ipc", "REACHABLE")
    rc, out, _ = run(["swaymsg", "-t", "get_version", "-r"])
    private["sway_version"] = json.loads(out)["human_readable"] if rc == 0 else None
    rc, out, _ = run(["xdpyinfo", "-display", env["DISPLAY"]])
    private["xdpyinfo_rc"] = rc
    private["xdpyinfo_has_XWAYLAND"] = "XWAYLAND" in out
    private["xdpyinfo_vendor"] = next((l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("vendor string")), None)
    wl = subprocess.Popen(["seatprobe", "canary-wayland-client", "6"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x11 = subprocess.Popen(["glxgears", "-geometry", "300x300"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env={**os.environ, "LIBGL_ALWAYS_SOFTWARE": "1"})
    views = []
    for _ in range(50):
        views = sway_views()
        if {wl.pid, x11.pid} <= {v["pid"] for v in views}:
            break
        time.sleep(0.1)
    private["clients_in_private_tree"] = views
    private["wayland_client_mapped"] = any(v["pid"] == wl.pid and v["shell"] == "xdg_shell" for v in views)
    private["x11_client_mapped_via_xwayland"] = any(v["pid"] == x11.pid and v["shell"] == "xwayland" for v in views)
    for p in (wl, x11):
        p.terminate()
        p.wait()
    rows.append({"target": "wayland client (seatprobe) mapped in private sway tree", "kind": "private-client",
                 "expect": True, "result": private["wayland_client_mapped"], "pass": private["wayland_client_mapped"], "note": ""})
    rows.append({"target": "X11 client (glxgears) mapped in private sway tree via Xwayland", "kind": "private-client",
                 "expect": True, "result": private["x11_client_mapped_via_xwayland"],
                 "pass": private["x11_client_mapped_via_xwayland"], "note": ""})
    # 7. PID namespace: the host Hyprland process is not visible/signalable from here.
    try:
        os.kill(args.host_pid, 0)
        sig = "VISIBLE"
    except ProcessLookupError:
        sig = "ESRCH"
    except PermissionError:
        sig = "EPERM"
    rows.append({"target": f"signal 0 to host Hyprland pid {args.host_pid}", "kind": "host-process", "expect": "ESRCH",
                 "result": sig, "pass": sig == "ESRCH", "note": "private PID namespace (+ Landlock signal scope)"})
    result = {
        "mode": "inside", "t": time.time(), "env": env, "env_checks": env_checks, "rows": rows,
        "listing": listing, "abstract_x11_listeners_visible_in_netns": abstract_listeners, "private": private,
        "pass": all(r["pass"] for r in rows) and all(env_checks.values()),
    }
    json.dump(result, open(args.out, "w"), indent=1)
    for r in rows:
        print(("PASS " if r["pass"] else "FAIL ") + f"{r['kind']:<40} {r['target']}: {r['result']} (expect {r['expect']})")
    print("env_checks", env_checks)
    print("RESULT", "PASS" if result["pass"] else "FAIL")
    return 0 if result["pass"] else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["decoy", "control", "inside", "list-abstract"])
    ap.add_argument("--dir")
    ap.add_argument("--abstract", default="")
    ap.add_argument("--paths", default="")
    ap.add_argument("--decoy-paths", default="")
    ap.add_argument("--host-sig", default="")
    ap.add_argument("--host-pid", type=int, default=0)
    ap.add_argument("--pre-abstract", default="")
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.mode == "list-abstract":
        print(",".join(abstract_x11_listeners()))
    elif a.mode == "decoy":
        decoy(a)
    elif a.mode == "control":
        control(a)
    else:
        sys.exit(inside(a))


if __name__ == "__main__":
    main()
