"""External per-trial checks that never read Driver output or trace marks.

* Process / socket / file inventory of the private session, taken before the
  Driver is spawned, just before it is shut down, and after it has exited. The
  diff catches a candidate that starts a new service, thread-hosting helper,
  listener or on-disk store (kvnloo/cua#73/#93 invariants): processes are matched
  by the session's process tree, sockets by the inodes those processes hold, files
  by walking the only directories the Driver sandbox can write.
* A signature (normalised names only: no pids, ports, hex ids or digits) so a
  candidate's inventory can be compared with the champion's reference set.

Linux /proc only. Everything runs inside the private session's mount and network
namespaces, so the host desktop is never inspected.
"""

from __future__ import annotations

import os
import re
import stat as _s
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_NORM = re.compile(r"[0-9a-fA-F]{6,}|\d+")
# mktemp-style 6-character suffixes: the AT-SPI per-app socket dir always, other
# components only when the suffix has an uppercase letter or a digit (so words
# such as ".cua-driver" stay readable).
_MKTEMP = re.compile(r"(?<=at-spi\d-)[A-Za-z0-9]{6}(?=/|$)|(?<=[-.])(?=[a-z]*[A-Z0-9])[A-Za-z0-9]{6}(?=/|$)")


def norm(text: str) -> str:
    """Replace digit runs and long hex runs with '#', so names compare across trials."""
    return _NORM.sub("#", text)


def norm_path(text: str) -> str:
    """``norm`` for paths, after replacing mktemp-style 6-character component suffixes."""
    return norm(_MKTEMP.sub("XXXXXX", text))


# ------------------------------------------------------------------ processes
def _stat(pid: int) -> tuple[int, str, int] | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    # comm may contain spaces/parens: it is between the first '(' and the last ')'.
    lp, rp = raw.index("("), raw.rindex(")")
    comm = raw[lp + 1:rp]
    rest = raw[rp + 2:].split()
    return int(rest[1]), comm, int(rest[19])  # ppid, comm, starttime (ticks)


def process_table() -> dict[int, dict[str, Any]]:
    table = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        st = _stat(int(entry))
        if st is not None:
            table[int(entry)] = {"ppid": st[0], "comm": st[1], "start": st[2]}
    return table


def descendants(table: Mapping[int, Mapping[str, Any]], root: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, info in table.items():
        children.setdefault(int(info["ppid"]), []).append(pid)
    out, stack = set(), [root]
    while stack:
        pid = stack.pop()
        for child in children.get(pid, []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def session_root(pid: int | None = None) -> int:
    """The private session's top process (xvfb-run), found by walking up from us.
    Falls back to the outermost ancestor that is still a dbus-run-session/bash child."""
    table = process_table()
    pid = os.getpid() if pid is None else pid
    chain = []
    while pid in table and pid > 1:
        chain.append(pid)
        if table[pid]["comm"] == "xvfb-run":
            return pid
        pid = int(table[pid]["ppid"])
    for candidate in chain:
        if table[candidate]["comm"] == "dbus-run-sessio":  # comm is truncated to 15 chars
            return candidate
    raise RuntimeError("not inside a private session (no xvfb-run / dbus-run-session ancestor)")


# -------------------------------------------------------------------- sockets
def _socket_inodes(pid: int) -> set[int]:
    inodes = set()
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                target = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            if target.startswith("socket:["):
                inodes.add(int(target[8:-1]))
    except OSError:
        pass
    return inodes


def listening_sockets() -> dict[int, str]:
    """inode -> description, for every listening/bound socket in this net namespace."""
    out: dict[int, str] = {}
    try:
        lines = Path("/proc/net/unix").read_text().splitlines()[1:]
    except OSError:
        lines = []
    for line in lines:
        parts = line.split()
        if len(parts) < 7:
            continue
        flags, inode = int(parts[3], 16), int(parts[6])
        if flags & 0x10000:  # __SO_ACCEPTCON: a listening unix socket
            path = parts[7] if len(parts) > 7 else "<unnamed>"
            out[inode] = f"unix:{path}"
    for proto, listen_state in (("tcp", "0A"), ("tcp6", "0A"), ("udp", "07"), ("udp6", "07")):
        try:
            rows = Path(f"/proc/net/{proto}").read_text().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            parts = row.split()
            if len(parts) > 9 and parts[3] == listen_state:
                out[int(parts[9])] = f"{proto}:{parts[1].split(':')[0]}:<port>"
    return out


# ---------------------------------------------------------------------- files
def file_inventory(roots: Mapping[str, str | Path]) -> dict[str, str]:
    """label/relative-path -> kind ('f', 'd', 's' socket, 'l' link, 'o' other)."""
    out = {}
    for label, root in roots.items():
        root = Path(root)
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            for name in dirnames + filenames:
                full = Path(dirpath) / name
                try:
                    mode = full.lstat().st_mode
                except OSError:
                    continue
                kind = ("d" if _s.S_ISDIR(mode) else "f" if _s.S_ISREG(mode) else "s" if _s.S_ISSOCK(mode)
                        else "l" if _s.S_ISLNK(mode) else "o")
                out[f"{label}/{full.relative_to(root)}"] = kind
    return out


# ------------------------------------------------------------------ snapshot
def snapshot(root_pid: int, file_roots: Mapping[str, str | Path], exclude_pids: Iterable[int] = ()) -> dict[str, Any]:
    table = process_table()
    tree = descendants(table, root_pid) - set(exclude_pids)
    listening = listening_sockets()
    procs = {pid: table[pid] for pid in tree if pid in table}
    sockets = {}
    for pid in procs:
        for inode in _socket_inodes(pid) & listening.keys():
            sockets[inode] = {"desc": listening[inode], "pid": pid, "comm": procs[pid]["comm"]}
    return {"procs": procs, "sockets": sockets, "files": file_inventory(file_roots)}


def diff(before: Mapping[str, Any], after: Mapping[str, Any], ignore_pids: Iterable[int] = ()) -> dict[str, Any]:
    """New processes / listeners / files in ``after``. ``ignore_pids`` and all their
    descendants (e.g. the fixture app's own image-loader helpers) are harness-owned."""
    ignore = set(ignore_pids)
    for snap in (before, after):
        for pid in list(ignore):
            ignore |= descendants(snap["procs"], pid)
    new_procs = sorted(
        {norm(after["procs"][p]["comm"]) for p in after["procs"]
         if p not in before["procs"] and p not in ignore}
    )
    new_sockets = sorted(
        {f"{norm(s['comm'])}|{norm_path(s['desc'])}" for i, s in after["sockets"].items()
         if i not in before["sockets"] and s["pid"] not in ignore}
    )
    new_files = sorted({f"{kind}:{norm_path(path)}" for path, kind in after["files"].items()
                        if path not in before["files"]})
    return {"new_processes": new_procs, "new_listening_sockets": new_sockets, "new_files": new_files}


def driver_tree(after: Mapping[str, Any], driver_root: int) -> dict[str, Any]:
    """Processes and listeners that belong to the Driver's own tree (bwrap included)."""
    table = {p: i for p, i in after["procs"].items()}
    tree = descendants(table, driver_root) | ({driver_root} if driver_root in table else set())
    return {
        "processes": sorted({norm(table[p]["comm"]) for p in tree}),
        "process_count": len(tree),
        "listening_sockets": sorted({norm_path(s["desc"]) for s in after["sockets"].values() if s["pid"] in tree}),
    }


def signature(record: Mapping[str, Any]) -> list[str]:
    """Flatten a trial's external diff into comparable strings."""
    sig = []
    for phase in ("during", "leftover"):
        d = record.get(phase) or {}
        for key in ("new_processes", "new_listening_sockets", "new_files"):
            sig.extend(f"{phase}:{key}:{v}" for v in d.get(key, []))
    tree = record.get("driver_tree") or {}
    sig.extend(f"driver:proc:{v}" for v in tree.get("processes", []))
    sig.extend(f"driver:listen:{v}" for v in tree.get("listening_sockets", []))
    return sorted(set(sig))


def extra_vs_reference(trial_signature: Iterable[str], reference: Iterable[str]) -> list[str]:
    """Signature entries the champion never produced: G2 'no new process/socket/file'."""
    return sorted(set(trial_signature) - set(reference))
