#!/usr/bin/env python3
"""Drive the measured chunks of run_b09.py until rounds 0-35 are complete, then the control chunk (standard
library only). Derived from B-08's run_all.py.

Run as: hostless python3 run_all.py [--chunk-rounds 12]  (same B09_* environment as run-chunk.sh)

- Before each chunk it waits on the host side until the 1-min loadavg is <= 4.0 (10 s polls) AND the cargo-build
  lock is free (a non-blocking SHARED probe, `flock -s -n`, 10 s polls), so the EXCLUSIVE quiet lock is not held
  only to wait. This is a convenience, not the pre-registered rule: the runner's own load rule and the bounded
  `flock -w 60` on the cargo lock inside the acquisition still decide.
- Rounds come from the chunk manifests: a round is done when a manifest lists it in rounds_completed; a cut round
  (rounds_cut) is re-run with attempt + 1; rounds not started are re-run with the same attempt.
- exit 74 (cargo lock not acquired in 60 s) and 75 (load rule / time budget) are retried after a pause.
- A chunk that ends with any other exit code and no manifest (e.g. killed by the 900 s cap) leaves its rounds
  unlisted; they are re-run with attempt + 1 (recorded in <lane tmp>/attempt-bumps.json), so no trial file is
  overwritten and the killed attempt stays a cut attempt.
- The runner names its manifest by plan, block, attempt and first/last round, so a retry of the same rounds would
  overwrite it: right after each chunk the manifest is renamed with the chunk's try number (-kN) before anything
  else runs. Nothing inside it changes.
- After rounds 0-35: one control chunk (plan ctl: 5 SMOKE + 3 N-W2, round index 36), same lock order.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LT = Path(os.environ["B09_TMPDIR"])
LOCKDIR = Path(os.environ["B09_LOCKDIR"])
OUT = LT / "main"
ROUNDS = list(range(36))
CTL = 36


def load1() -> float:
    return float(Path("/proc/loadavg").read_text().split()[0])


def cargo_free() -> bool:
    return subprocess.run(["flock", "-s", "-n", str(LOCKDIR / "cargo-build.lock"), "true"]).returncode == 0


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] run_all {msg}"
    print(line, flush=True)
    with (LT / "logs" / "b09r-run_all.log").open("a") as f:
        f.write(line + "\n")


def state() -> tuple[set[int], dict[int, int]]:
    done: set[int] = set()
    attempt: dict[int, int] = {}
    for p in sorted(OUT.glob("run-manifest-*.json")):
        m = json.loads(p.read_text())
        a = int(m.get("attempt", 1))
        done |= set(m.get("rounds_completed", []))
        for r in m.get("rounds_cut", []):
            attempt[r] = max(attempt.get(r, 1), a + 1)
    bumps = LT / "attempt-bumps.json"
    if bumps.exists():
        for r, v in json.loads(bumps.read_text()).items():
            attempt[int(r)] = max(attempt.get(int(r), 1), int(v))
    return done, attempt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk-rounds", type=int, default=12)
    ap.add_argument("--max-tries", type=int, default=60)
    a = ap.parse_args()
    (LT / "logs").mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    k = len(list(OUT.glob("run-manifest-*-k*.json")))
    failures = 0
    for _ in range(a.max_tries):
        done, attempt = state()
        todo = [r for r in ROUNDS if r not in done]
        if not todo and CTL in done:
            log("all rounds and the control chunk complete")
            return 0
        plan = "main" if todo else "ctl"
        if todo:
            att = attempt.get(todo[0], 1)
            batch = [r for r in todo if attempt.get(r, 1) == att][: a.chunk_rounds]
        else:
            att, batch = attempt.get(CTL, 1), [CTL]
        t_wait = time.monotonic()
        while load1() > 4.0 or not cargo_free():
            time.sleep(10)
        k += 1
        label = f"{plan}-a{att}-r{batch[0]:02d}-{batch[-1]:02d}-k{k}"
        log(f"start {label} rounds={batch} host_wait_s={time.monotonic() - t_wait:.0f} load1={load1()} cargo_free=1")
        rc = subprocess.run(["bash", str(HERE / "run-chunk.sh"), label, ",".join(map(str, batch)), "m", str(att),
                             plan]).returncode
        man = OUT / f"run-manifest-{plan}-m-a{att}-r{batch[0]:02d}-{batch[-1]:02d}.json"
        had = man.exists()
        if had:
            man.rename(OUT / f"run-manifest-{plan}-m-a{att}-r{batch[0]:02d}-{batch[-1]:02d}-k{k}.json")
        log(f"end {label} rc={rc} manifest={'renamed -k%d' % k if had else 'missing'}")
        if not had and rc not in (74,):
            bumps = LT / "attempt-bumps.json"
            cur = json.loads(bumps.read_text()) if bumps.exists() else {}
            for r in batch:
                cur[str(r)] = max(int(cur.get(str(r), 1)), att + 1)
            bumps.write_text(json.dumps(cur, indent=1))
            log(f"no manifest after rc={rc}: rounds {batch} bumped to attempt {att + 1}")
        if rc in (74, 75):
            time.sleep(30)
            continue
        if rc != 0:
            failures += 1
            if failures > 3:
                log("stopping: more than 3 failed chunks")
                return rc
            time.sleep(30)
    log("stopping: max tries")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
