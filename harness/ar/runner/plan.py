#!/usr/bin/env python3
"""Build an AB/BA trial schedule split into sessions of <= 48 paired trials (24 pairs).

A = champion, B = candidate. Pair k runs AB when k is even and BA when k is odd; both trials of
a pair share the trace setting and a pair seed (fixture layout), and exactly round(0.2 n) task
pairs (half from AB, half from BA) run with the phase trace unset. Every session starts with two
kept warm-up trials (one per arm, excluded from the gates' statistics) and, unless disabled,
GTK sessions end with one stale-token negative and one impossible canary per arm, so a session
holds at most 48 paired trials + 2 warm-ups + 4 controls. Pairs never straddle a session, so
every session restart (fresh Xvfb, AT-SPI bus, fixture) happens between pairs. Soak trials
(candidate only) get their own sessions.

Browser spot pairs (spot_browser_fill_submit) get their own sessions with "pidns": false: the
Driver's isolated browser launch requires a root-owned Chromium, which any unprivileged bwrap
(session-pidns.sh, sandbox-driver.sh) shows as the overflow uid. run_blocks.py runs those
sessions without session-pidns.sh; GTK sessions keep it.

AA calibration = the same plan with a champion build in both arms (a rebuild of the same commit
as the "candidate" controls for binary layout).

usage: plan.py --eval-id ID --champion BIN --candidate BIN --pairs N --seed S [--spot-pairs M]
               [--spot-browser-pairs M] [--pairs-per-session P] [--soak K] [--no-controls]
               --out plan.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any

SESSION_TRIALS = 48  # paired (or soak) trials per session; warm-ups and controls ride on top
TRACE_OFF_FRACTION = 0.2
BROWSER_KIND = "spot_browser_fill_submit"


def sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pair_units(kind: str, n: int, rng: random.Random, prefix: str) -> list[list[dict[str, Any]]]:
    off_n = round(TRACE_OFF_FRACTION * n) if kind == "task" else 0
    even = [k for k in range(n) if k % 2 == 0]
    odd = [k for k in range(n) if k % 2 == 1]
    off = set(rng.sample(even, min(len(even), (off_n + 1) // 2)) + rng.sample(odd, min(len(odd), off_n // 2)))
    units = []
    for k in range(n):
        order = "AB" if k % 2 == 0 else "BA"
        arms = ("champion", "candidate") if order == "AB" else ("candidate", "champion")
        pair_seed = rng.randrange(1 << 30)
        units.append([{"kind": kind, "pair_id": f"{prefix}{k}", "order": order, "position": i, "arm": arm,
                       "trace": k not in off, "warmup": False, "seed": pair_seed} for i, arm in enumerate(arms)])
    return units


def chunk(units: list[list[dict[str, Any]]], per_session: int) -> list[list[dict[str, Any]]]:
    out: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for unit in units:
        if current and len(current) + len(unit) > 2 * per_session:
            out.append(current)
            current = []
        current.extend(unit)
    if current:
        out.append(current)
    return out


def warmups(kind: str) -> list[dict[str, Any]]:
    return [{"kind": kind, "pair_id": None, "order": None, "position": None, "arm": arm, "trace": True,
             "warmup": True, "seed": None} for arm in ("champion", "candidate")]


def build(eval_id: str, binaries: dict[str, str], n_pairs: int, seed: int, spot_pairs: int = 0,
          soak: int = 0, controls: bool = True, spot_browser_pairs: int = 0,
          pairs_per_session: int = SESSION_TRIALS // 2) -> dict[str, Any]:
    if not 1 <= pairs_per_session <= SESSION_TRIALS // 2:
        raise ValueError(f"pairs_per_session must be in 1..{SESSION_TRIALS // 2}")
    rng = random.Random(seed)
    shas = {arm: sha256(path) for arm, path in binaries.items()}
    units = pair_units("task", n_pairs, rng, "p") + pair_units("spot_gtk3_text", spot_pairs, rng, "s")
    rng.shuffle(units)
    browser = pair_units(BROWSER_KIND, spot_browser_pairs, rng, "b")
    rng.shuffle(browser)
    tail = ([{"kind": k, "pair_id": None, "order": None, "position": None, "arm": arm, "trace": True,
              "warmup": False, "seed": None} for arm in ("champion", "candidate")
             for k in ("stale_negative", "impossible_canary")] if controls else [])
    sessions: list[tuple[bool, list[dict[str, Any]]]] = []
    for body in chunk(units, pairs_per_session):
        sessions.append((True, warmups("task") + body + tail))
    for body in chunk(browser, pairs_per_session):
        sessions.append((False, warmups(BROWSER_KIND) + body))
    for start in range(0, soak, SESSION_TRIALS - 1):
        count = min(SESSION_TRIALS - 1, soak - start)
        sessions.append((True, [warmups("task")[1]] + [
            {"kind": "soak", "pair_id": None, "order": None, "position": None, "arm": "candidate",
             "trace": False, "warmup": False, "seed": None} for _ in range(count)]))
    trial_id = 0
    out = []
    for s, (pidns, trials) in enumerate(sessions):
        specs = []
        for t in trials:
            specs.append({**t, "trial_id": trial_id, "session": s, "binary": binaries[t["arm"]],
                          "binary_sha256": shas[t["arm"]]})
            trial_id += 1
        out.append({"eval_id": eval_id, "session": s, "pidns": pidns, "trials": specs})
    return {"schema": "ar.plan.v1", "eval_id": eval_id, "seed": seed, "n_pairs": n_pairs,
            "spot_pairs": spot_pairs, "spot_browser_pairs": spot_browser_pairs, "soak": soak,
            "pairs_per_session": pairs_per_session, "binaries_sha256": shas, "sessions": out}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--eval-id", required=True)
    p.add_argument("--champion", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--pairs", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--spot-pairs", type=int, default=0)
    p.add_argument("--spot-browser-pairs", type=int, default=0)
    p.add_argument("--pairs-per-session", type=int, default=SESSION_TRIALS // 2)
    p.add_argument("--soak", type=int, default=0)
    p.add_argument("--no-controls", action="store_true")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    plan = build(a.eval_id, {"champion": a.champion, "candidate": a.candidate}, a.pairs, a.seed,
                 a.spot_pairs, a.soak, not a.no_controls, a.spot_browser_pairs, a.pairs_per_session)
    Path(a.out).write_text(json.dumps(plan, indent=1) + "\n")
    print(f"{len(plan['sessions'])} sessions, {sum(len(s['trials']) for s in plan['sessions'])} trials")


if __name__ == "__main__":
    main()
