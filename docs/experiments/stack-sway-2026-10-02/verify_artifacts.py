#!/usr/bin/env python3
"""Verify the stack-sway-2026-10-02 packet from its own files (stdlib only, no display needed).

1. Every file listed in MANIFEST.sha256 exists with that sha256.
2. Every multi-seat rep is re-graded from raw receipts with scripts/verify_multiseat.py and must
   reproduce the stored per-check results and PASS.
3. Every canary run: each row's pass flag is recomputed from result vs expect, the environment checks
   hold, and the decoys' own accept logs total exactly one control connect per decoy plus one
   inside-session connect to the exposed hypr-layout decoy (abstract and /tmp decoys: zero inside).
4. The recorded failed canary attempt still shows the failing row it is documented for.
5. No local absolute path, host Hyprland signature or secret assignment survives in text files.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent
fails, notes = [], []

for line in (root / "MANIFEST.sha256").read_text().splitlines():
    digest, rel = line.split("  ", 1)
    p = root / rel
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
        fails.append(f"manifest mismatch: {rel}")
notes.append("manifest checked")

reps = sorted((root / "raw" / "multiseat").glob("rep*"))
for rep in reps:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "summary.json"
        rc = subprocess.run([sys.executable, str(root / "scripts" / "verify_multiseat.py"), str(rep), str(out)],
                            capture_output=True, text=True).returncode
        new, old = json.loads(out.read_text()), json.loads((rep / "summary.json").read_text())
        same = [(c["check"], c["pass"]) for c in new["checks"]] == [(c["check"], c["pass"]) for c in old["checks"]]
        if rc != 0 or new["result"] != "PASS" or not same:
            fails.append(f"multiseat {rep.name}: regrade rc={rc} result={new['result']} same_as_stored={same}")
notes.append(f"multiseat reps regraded: {len(reps)}")


def row_ok(r):
    # A list expect means "one of" for a scalar result (e.g. ["EPERM", "ECONNREFUSED"]) and exact
    # equality for a list result (the shadowing row: added listeners == [own display]).
    e, got = r["expect"], r["result"]
    if isinstance(e, list) and not isinstance(got, list):
        return got in e
    return got == e


runs = sorted((root / "raw" / "canary").glob("run*"))
for run in runs:
    s = json.loads((run / "summary.json").read_text())
    inside = json.loads((run / "inside.json").read_text())
    control = json.loads((run / "control.json").read_text())
    rows_ok = all(row_ok(r) == r["pass"] and r["pass"] for r in inside["rows"])
    env_ok = all(inside["env_checks"].values())
    control_ok = all(r["result"] == "REACHABLE" for r in control["rows"])
    accepts = [json.loads(l) for l in (run / "decoy" / "accepts.jsonl").read_text().splitlines() if l.strip()]
    targets = [r["target"] for r in control["rows"]]  # [hypr-layout path, /tmp X11 path, @abstract]
    totals = {t: sum(1 for a in accepts if a["decoy"] == t) for t in targets}
    want = {targets[0]: 2, targets[1]: 1, targets[2]: 1}
    if not (rows_ok and env_ok and control_ok and totals == want and s["result"] == "PASS"):
        fails.append(f"canary {run.name}: rows={rows_ok} env={env_ok} control={control_ok} totals={totals} result={s['result']}")
notes.append(f"canary runs checked: {len(runs)}")

att = root / "raw" / "attempts" / "canary-run1-fail-x11-display-shadowing" / "inside.json"
a = json.loads(att.read_text())
bad = [r for r in a["rows"] if not r["pass"]]
if a["pass"] or [r["target"] for r in bad] != ["/tmp/.X11-unix/X1"]:
    fails.append("failed canary attempt does not show the documented single failing row")
notes.append("failed canary attempt retained with its failing row")

forbidden = [re.compile(r"(^|[\s\"'=:(\[,])/(home|mnt|run/media)/"), re.compile(r"[0-9a-f]{40}_\d{10}_\d+"),
             re.compile(r"(API_KEY|_TOKEN|SECRET)=[A-Za-z0-9_\-]{8,}")]
for p in root.rglob("*"):
    if p.is_file() and p.suffix in {".json", ".jsonl", ".txt", ".log", ".sh", ".py", ".c", ".md", ".env", ".err", ""}:
        t = p.read_text(errors="replace")
        for rx in forbidden:
            if rx.search(t):
                fails.append(f"forbidden pattern {rx.pattern!r} in {p.relative_to(root)}")
notes.append("path/secret scan done")

for n in notes:
    print("ok  ", n)
for f in fails:
    print("FAIL", f)
print("RESULT", "PASS" if not fails else "FAIL")
sys.exit(1 if fails else 0)
