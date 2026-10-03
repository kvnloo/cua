#!/usr/bin/env python3
"""INFRA-08 unit tests for the quiet-lane scripts (evidence class UNIT).

usage (under bin/hostless only):
  test_quiet_lane.py --impl v1|v2 --tmp <scratch dir> --out <results.jsonl>

Every test renders the templated scripts (render.sh) into its own scratch directory with its own lock
dir, so the live lock file is never touched. Each row records the observed result (GREEN = the
property holds), the PREREG expectation for that implementation and whether they match. The process
exits 0 only when every row matches its expectation. The tests signal and kill only processes they
started (their own daemons and the descendants of scripts they launched).
"""
import argparse
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time

PKT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDER = os.path.join(PKT, "render.sh")
V1_KEYS = ["label", "pid", "acquired", "released", "rc", "cmd_sha256"]
SNAP_HEADER_KEYS = ["label", "waiter_pid", "waited_s", "utc"]
SNAP_COLUMNS = ["state", "mode", "pid", "ppid", "elapsed_s", "exe"]
MARK_ARG = "INFRA08-MARKER-ARG-not-a-secret-7f3a"
MARK_ENV = "INFRA08-MARKER-ENV-not-a-secret-91c2"

# PREREG expectations: GREEN = property holds; RED = known bug / missing feature in that implementation.
EXPECT = {
    "v1": {"T0": "N/A", "T1": "RED", "T1s": "N/A", "T2": "GREEN", "T3": "RED", "T4": "RED",
           "T4c": "GREEN", "T4n": "N/A", "T4t": "N/A", "T5": "RED", "T6": "GREEN"},
    "v2": {"T0": "GREEN", "T1": "GREEN", "T1s": "GREEN", "T2": "GREEN", "T3": "GREEN", "T4": "GREEN",
           "T4c": "GREEN", "T4n": "GREEN", "T4t": "GREEN", "T5": "GREEN", "T6": "GREEN"},
}


def wait_until(fn, timeout, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return fn()


def proc_stat(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            s = f.read()
    except OSError:
        return None
    rest = s[s.rfind(")") + 2:].split()
    return {"state": rest[0], "ppid": int(rest[1]), "start": rest[19], "comm": s[s.find("(") + 1:s.rfind(")")]}


def alive(pid, start=None):
    st = proc_stat(pid)
    return bool(st) and st["state"] != "Z" and (start is None or st["start"] == start)


def descendants(root):
    """{pid: starttime} of every live descendant of root."""
    kids = {}
    for name in os.listdir("/proc"):
        if name.isdigit():
            st = proc_stat(int(name))
            if st:
                kids.setdefault(st["ppid"], []).append((int(name), st["start"]))
    out, todo = {}, [root]
    while todo:
        for pid, start in kids.get(todo.pop(), []):
            out[pid] = start
            todo.append(pid)
    return out


def lock_entries(lockfile):
    """[(state, mode, pid)] for FLOCK entries on the lock inode (same parse as quiet-holders)."""
    ino = str(os.stat(lockfile).st_ino)
    rows = []
    with open("/proc/locks") as f:
        for line in f:
            p = line.split()
            o = 1 if len(p) > 1 and p[1] == "->" else 0
            if len(p) < 7 + o or p[1 + o] != "FLOCK" or p[5 + o].split(":")[-1] != ino:
                continue
            rows.append(("waiting" if o else "holding", p[3 + o], int(p[4 + o])))
    return rows


def try_excl(lockfile):
    fd = os.open(lockfile, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


class Hold:
    """The test itself holds the lock (EXCLUSIVE or SHARED) on its own fd."""

    def __init__(self, lockfile, mode):
        self.fd = os.open(lockfile, os.O_WRONLY | os.O_CREAT, 0o644)
        fcntl.flock(self.fd, fcntl.LOCK_EX if mode == "x" else fcntl.LOCK_SH)

    def release(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def ledger_lines(lockdir):
    try:
        with open(os.path.join(lockdir, "quiet-lane-ledger.jsonl")) as f:
            return [l.rstrip("\n") for l in f if l.strip()]
    except FileNotFoundError:
        return []


class Run:
    def __init__(self, impl, tmp, out):
        self.impl, self.tmp, self.rows = impl, os.path.join(tmp, impl), []
        self.out = out
        self.base_env = {k: v for k, v in os.environ.items() if not k.startswith("QUIET_")}

    def setup(self, test, default=None):
        d = os.path.join(self.tmp, test)
        subprocess.run(["rm", "-rf", d], check=True)
        lockdir = os.path.join(d, "locks")
        os.makedirs(lockdir)
        bindir = os.path.join(d, "bin")
        subprocess.run([RENDER, default or lockdir, bindir], check=True)
        env = dict(self.base_env)
        if self.impl == "v2" and default is None:
            env["QUIET_LANE_LOCKDIR"] = lockdir
        qt = os.path.join(bindir, "v1/quiet-timed" if self.impl == "v1" else "quiet-timed")
        return d, lockdir, bindir, qt, env

    def record(self, test, case, green, valid=True, **detail):
        # INVALID = a precondition of the test did not hold (it never matches an expectation)
        observed = ("GREEN" if green else "RED") if valid else "INVALID"
        expected = EXPECT[self.impl][test]
        row = {"lane": "INFRA-08", "evidence_class": "UNIT", "impl": self.impl, "test": test, "case": case,
               "observed": observed, "expected": expected, "matches_expectation": observed == expected,
               "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **detail}
        self.rows.append(row)
        with open(self.out, "a") as f:
            f.write(json.dumps(row, sort_keys=False) + "\n")
        print(f"{self.impl} {test:4} {case:28} observed={observed:5} expected={expected:5} "
              f"{'ok' if row['matches_expectation'] else 'MISMATCH'}", flush=True)

    def na(self, test, case, why):
        row = {"lane": "INFRA-08", "evidence_class": "UNIT", "impl": self.impl, "test": test, "case": case,
               "observed": "N/A", "expected": EXPECT[self.impl][test],
               "matches_expectation": EXPECT[self.impl][test] == "N/A", "why": why}
        self.rows.append(row)
        with open(self.out, "a") as f:
            f.write(json.dumps(row) + "\n")
        print(f"{self.impl} {test:4} {case:28} N/A ({why})", flush=True)

    # ---------------------------------------------------------------- T0
    def t0(self):
        if self.impl == "v1":
            return self.na("T0", "env-override", "v1 has no lock dir override")
        d, lockdir, bindir, qt, env = self.setup("T0", default=None)
        sentinel = os.path.join(d, "sentinel-default")
        subprocess.run([RENDER, sentinel, bindir], check=True)
        r1 = subprocess.run([qt, "t0-override", "true"], env=env, timeout=30)
        with_override = (r1.returncode == 0 and not os.path.exists(sentinel)
                         and len(ledger_lines(lockdir)) == 1)
        env2 = dict(self.base_env)
        r2 = subprocess.run([qt, "t0-default", "true"], env=env2, timeout=30)
        default_used = r2.returncode == 0 and len(ledger_lines(sentinel)) == 1
        self.record("T0", "env-override", with_override and default_used,
                    override_ok=with_override, rendered_default_ok=default_used)

    # ---------------------------------------------------------------- T1
    def _leak(self, test, argv_prefix, env, lockfile, pidfile):
        cmd = argv_prefix + ["bash", "-c", 'setsid sleep 600 </dev/null >/dev/null 2>&1 & echo $! > "$1"',
                             "_", pidfile]
        r = subprocess.run(cmd, env=env, timeout=60)
        dpid = int(open(pidfile).read().strip())
        dstart = proc_stat(dpid)["start"] if alive(dpid) else None
        daemon_alive = alive(dpid, dstart)
        free = try_excl(lockfile)
        entries = lock_entries(lockfile)
        if daemon_alive:
            os.kill(dpid, signal.SIGKILL)  # our own daemon only
        wait_until(lambda: not alive(dpid, dstart), 5)
        free_after_kill = try_excl(lockfile)
        return {"rc": r.returncode, "daemon_alive_at_check": daemon_alive, "excl_trylock_ok": free,
                "lock_entries_at_check": entries, "excl_trylock_after_daemon_killed": free_after_kill,
                "daemon_reaped": not alive(dpid, dstart)}, daemon_alive and free

    def t1(self):
        d, lockdir, bindir, qt, env = self.setup("T1")
        det, green = self._leak("T1", [qt, "t1"], env, os.path.join(lockdir, "quiet-lane.lock"),
                                os.path.join(d, "daemon.pid"))
        self.record("T1", "quiet-timed daemon fd leak", green, valid=det["rc"] == 0 and det["daemon_alive_at_check"], **det)
        if self.impl == "v1":
            return self.na("T1s", "quiet-shared daemon fd leak", "v1 has no quiet-shared")
        d, lockdir, bindir, qt, env = self.setup("T1s")
        det, green = self._leak("T1s", [os.path.join(bindir, "quiet-shared"), "t1s", "30"], env,
                                os.path.join(lockdir, "quiet-lane.lock"), os.path.join(d, "daemon.pid"))
        self.record("T1s", "quiet-shared daemon fd leak", green, valid=det["rc"] == 0 and det["daemon_alive_at_check"], **det)

    # ---------------------------------------------------------------- T2
    @staticmethod
    def _parse(line):
        return json.loads(line, object_pairs_hook=lambda kv: kv)

    @staticmethod
    def _mask(line):
        line = re.sub(r'"pid":\d+', '"pid":0', line)
        return re.sub(r'"(acquired|released)":"[0-9T:.\-]+Z"', r'"\1":"T"', line)

    def t2(self):
        d, lockdir, bindir, qt, env = self.setup("T2")
        cmd = ["sh", "-c", 'exit 0', "arg with space", "x\"y"]
        ts = r'^\{"label":"t2","pid":\d+,"acquired":"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z",' \
             r'"released":"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z","rc":0,"cmd_sha256":"[0-9a-f]{16}"'
        if self.impl == "v1":
            subprocess.run([qt, "t2"] + cmd, env=env, timeout=30, check=True)
            line = ledger_lines(lockdir)[-1]
            keys = [k for k, _ in self._parse(line)]
            ok = keys == V1_KEYS and re.match(ts + r"\}$", line) is not None
            return self.record("T2", "v1 receipt schema baseline", ok, keys=keys, line_masked=self._mask(line))
        v1 = os.path.join(bindir, "v1/quiet-timed")
        subprocess.run([v1, "t2"] + cmd, env=env, timeout=30, check=True)
        subprocess.run([qt, "t2"] + cmd, env=env, timeout=30, check=True)
        subprocess.run([os.path.join(bindir, "quiet-shared"), "t2", "30"] + cmd, env=env, timeout=30, check=True)
        l1, l2, ls = ledger_lines(lockdir)[-3:]
        k1, k2, ks = ([k for k, _ in self._parse(x)] for x in (l1, l2, ls))
        h1, h2, hs = (dict(self._parse(x))["cmd_sha256"] for x in (l1, l2, ls))
        timed_ok = (k1 == k2 == V1_KEYS and h1 == h2 and self._mask(l1) == self._mask(l2)
                    and re.match(ts + r"\}$", l2) is not None)
        shared_ok = (ks == V1_KEYS + ["mode"] and dict(self._parse(ls))["mode"] == "shared" and hs == h1
                     and re.match(ts + r',"mode":"shared"\}$', ls) is not None)
        self.record("T2", "v1 vs v2 receipt schema", timed_ok, keys_v1=k1, keys_v2=k2, cmd_sha256_v1=h1,
                    cmd_sha256_v2=h2, masked_v1=self._mask(l1), masked_v2=self._mask(l2))
        self.record("T2", "quiet-shared receipt schema", shared_ok, keys_shared=ks, cmd_sha256_shared=hs,
                    masked_shared=self._mask(ls))

    # ---------------------------------------------------------------- T3
    def _reap_case(self, sig, case):
        d, lockdir, bindir, qt, env = self.setup(f"T3-{signal.Signals(sig).name}")
        lockfile = os.path.join(lockdir, "quiet-lane.lock")
        marker = os.path.join(d, "command-ran")
        open(lockfile, "a").close()
        hold = Hold(lockfile, "x")
        p = subprocess.Popen([qt, "t3", "touch", marker], env=env)

        def waiter():
            kids = descendants(p.pid)
            w = [pid for st, mode, pid in lock_entries(lockfile) if st == "waiting" and mode == "WRITE"]
            return [pid for pid in w if pid in kids]
        flock_waiters = wait_until(waiter, 10)
        time.sleep(0.3)  # let the v2 alarm subshell and its sleep start too
        tree = descendants(p.pid)
        tree_comm = {str(k): (proc_stat(k) or {}).get("comm", "gone") for k in tree}
        os.kill(p.pid, sig)
        try:
            rc = p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            rc = p.wait()
        time.sleep(0.3)
        survivors = {pid: proc_stat(pid)["comm"] for pid, st in tree.items() if alive(pid, st)}
        waiting_left = [e for e in lock_entries(lockfile) if e[0] == "waiting"]
        for pid, st in tree.items():  # clean up our own leftovers (v1 red case) before releasing
            if alive(pid, st):
                os.kill(pid, signal.SIGKILL)
        hold.release()
        time.sleep(0.3)
        ran, receipts = os.path.exists(marker), len(ledger_lines(lockdir))
        green = bool(flock_waiters) and not survivors and not waiting_left and not ran and receipts == 0
        self.record("T3", case, green, valid=bool(flock_waiters), signal=signal.Signals(sig).name, rc=rc, queued_flock_waiters=flock_waiters,
                    descendants_before_signal=tree_comm,
                    survivors=survivors, waiting_entries_left=waiting_left, command_ran=ran,
                    receipts=receipts)

    def t3(self):
        self._reap_case(signal.SIGTERM, "waiter reap on TERM")
        if self.impl == "v2":
            self._reap_case(signal.SIGINT, "waiter reap on INT")
            self._reap_case(signal.SIGHUP, "waiter reap on HUP")

    # ---------------------------------------------------------------- T4
    def _yield_case(self, case, shared_argv_fn, poll_env):
        d, lockdir, bindir, qt, env = self.setup(f"T4-{case}")
        lockfile = os.path.join(lockdir, "quiet-lane.lock")
        order = os.path.join(d, "order")
        open(lockfile, "a").close()
        hold = Hold(lockfile, "s")
        px = subprocess.Popen([qt, "t4-x", "bash", "-c", 'sleep 1; echo X >> "$1"', "_", order], env=env)
        queued = wait_until(lambda: any(e[0] == "waiting" and e[1] == "WRITE" for e in lock_entries(lockfile)), 10)
        senv = dict(env, **poll_env)
        ps = subprocess.Popen(shared_argv_fn(bindir, lockfile, order), env=senv)
        time.sleep(3)
        before_release = open(order).read().split() if os.path.exists(order) else []
        shared_waiting = ps.poll() is None
        hold.release()
        rcx, rcs = px.wait(timeout=30), ps.wait(timeout=30)
        final = open(order).read().split()
        return {"writer_queued": bool(queued), "order_before_release": before_release,
                "shared_still_waiting_at_3s": shared_waiting, "order_final": final, "rc_x": rcx, "rc_s": rcs,
                "receipts": ledger_lines(lockdir)}

    def t4(self):
        shared_cmd = ["bash", "-c", 'echo S >> "$1"', "_"]
        if self.impl == "v1":
            self.record("T4", "quiet-shared yields to EXCLUSIVE", False, why="v1 has no quiet-shared (RED by absence)")
        else:
            det = self._yield_case("yield", lambda b, lf, o: [os.path.join(b, "quiet-shared"), "t4-s", "30"]
                                   + shared_cmd + [o], {"QUIET_SHARED_POLL_S": "0.2"})
            recs = [dict(json.loads(l)) for l in det["receipts"]]
            rx = [r for r in recs if r["label"] == "t4-x"]
            rs = [r for r in recs if r["label"] == "t4-s"]
            after = bool(rx and rs) and rs[0]["acquired"] >= rx[0]["released"]
            green = (det["writer_queued"] and det["order_before_release"] == [] and det["shared_still_waiting_at_3s"]
                     and det["order_final"] == ["X", "S"] and after and det["rc_x"] == 0 and det["rc_s"] == 0)
            self.record("T4", "quiet-shared yields to EXCLUSIVE", green, valid=det["writer_queued"], shared_acquired_after_excl_released=after, **det)
        # control: a plain flock -s wrapper (no yield) acquires ahead of the queued writer
        det = self._yield_case("control", lambda b, lf, o: ["flock", "-s", lf] + shared_cmd + [o], {})
        green = det["writer_queued"] and det["order_before_release"] == ["S"] and det["order_final"] == ["S", "X"]
        self.record("T4c", "control: plain flock -s overtakes", green, valid=det["writer_queued"], **det)
        if self.impl == "v1":
            self.na("T4n", "no writer: immediate acquire", "v1 has no quiet-shared")
            return self.na("T4t", "max_s cap", "v1 has no quiet-shared")
        d, lockdir, bindir, qt, env = self.setup("T4n")
        t = time.monotonic()
        r = subprocess.run([os.path.join(bindir, "quiet-shared"), "t4n", "30", "true"], env=env, timeout=30)
        dt = time.monotonic() - t
        self.record("T4n", "no writer: immediate acquire", r.returncode == 0 and dt < 3, rc=r.returncode,
                    elapsed_s=round(dt, 3))
        t = time.monotonic()
        r = subprocess.run([os.path.join(bindir, "quiet-shared"), "t4t", "1", "sleep", "30"], env=env, timeout=60)
        dt = time.monotonic() - t
        last = dict(json.loads(ledger_lines(lockdir)[-1]))
        self.record("T4t", "max_s cap", r.returncode == 124 and dt < 5 and last["rc"] == 124
                    and try_excl(os.path.join(lockdir, "quiet-lane.lock")), rc=r.returncode,
                    elapsed_s=round(dt, 3), receipt_rc=last["rc"])

    # ---------------------------------------------------------------- T5
    def t5(self):
        d, lockdir, bindir, qt, env = self.setup("T5")
        lockfile = os.path.join(lockdir, "quiet-lane.lock")
        sdir = os.path.join(lockdir, "starvation")
        open(lockfile, "a").close()
        hold = Hold(lockfile, "x")
        env = dict(env, QUIET_STARVE_ALARM_S="2", INFRA08_ENV_MARKER=MARK_ENV)
        p = subprocess.Popen([qt, "t5", "sh", "-c", "exit 0", MARK_ARG], env=env)
        def listing():
            return sorted(n for n in os.listdir(sdir) if n.endswith(".txt")) if os.path.isdir(sdir) else []
        # alarm period 2 s: wait (up to 9 s) for the first snapshot and one repeat
        wait_until(lambda: len(listing()) >= 2, 9)
        files = listing()
        problems, rows_seen, texts = [], [], {}
        for name in files:
            text = open(os.path.join(sdir, name)).read()
            texts[name] = text
            if MARK_ARG in text or MARK_ENV in text:
                problems.append(f"{name}: marker present")
            lines = text.splitlines()
            m = re.match(r"^# quiet-lane starvation snapshot: (.*)$", lines[0]) if lines else None
            keys = [kv.split("=", 1)[0] for kv in m.group(1).split()] if m else None
            if keys != SNAP_HEADER_KEYS:
                problems.append(f"{name}: header keys {keys}")
            if len(lines) < 2 or lines[1].split("\t") != SNAP_COLUMNS:
                problems.append(f"{name}: columns {lines[1:2]}")
            for row in lines[2:]:
                f = row.split("\t")
                rows_seen.append(f)
                if len(f) != 6 or f[0] not in ("holding", "waiting") or f[1] not in ("READ", "WRITE") \
                        or not f[2].isdigit():
                    problems.append(f"{name}: bad row {f}")
        holder_row = any(f[0] == "holding" and f[2] == str(os.getpid()) for f in rows_seen)
        waiter_row = any(f[0] == "waiting" and f[1] == "WRITE" for f in rows_seen)
        hold.release()
        rc = p.wait(timeout=30)
        n_at_grant = len(listing())
        time.sleep(3)
        n_after = len(listing())
        green = len(files) >= 2 and not problems and holder_row and waiter_row and rc == 0 and n_after == n_at_grant
        self.record("T5", "starvation alarm", green, files=files, problems=problems, holder_row_for_test_pid=holder_row,
                    waiting_write_row=waiter_row, rows=rows_seen[:6], rc=rc, files_at_grant=n_at_grant,
                    files_3s_after_grant=n_after, snapshot_texts=texts, marker_arg_absent=not any("marker present" in x for x in problems))

    # ---------------------------------------------------------------- T6
    def t6(self):
        d, lockdir, bindir, qt, env = self.setup("T6")
        tools = [("quiet-timed", [qt, "t6"])]
        if self.impl == "v2":
            tools.append(("quiet-shared", [os.path.join(bindir, "quiet-shared"), "t6", "30"]))
        for name, argv in tools:
            got = {}
            for want in (0, 1, 7, 255):
                r = subprocess.run(argv + ["sh", "-c", f"exit {want}"], env=env, timeout=30)
                got[want] = (r.returncode, dict(json.loads(ledger_lines(lockdir)[-1]))["rc"])
            ok = all(rc == want and lrc == want for want, (rc, lrc) in got.items())
            self.record("T6", f"{name} rc propagation", ok, rc_and_receipt={str(k): v for k, v in got.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", choices=["v1", "v2"], required=True)
    ap.add_argument("--tmp", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.environ.get("CUA_HOSTLESS") != "1":
        sys.exit("refusing to run outside bin/hostless (CUA_HOSTLESS=1 not set)")
    open(a.out, "w").close()
    r = Run(a.impl, os.path.abspath(a.tmp), a.out)
    for t in (r.t0, r.t1, r.t2, r.t3, r.t4, r.t5, r.t6):
        t()
    bad = [x for x in r.rows if not x["matches_expectation"]]
    print(f"{a.impl}: {len(r.rows) - len(bad)} of {len(r.rows)} rows match the PREREG expectation")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
