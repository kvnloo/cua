#!/usr/bin/env python3
"""N-03 packet verifier (standard library + git). Passes from a clean clone of the branch.

Checks:
 1. raw/MANIFEST.json: every listed raw file exists with the listed sha256 and size; no unlisted file.
 2. analyze_n03.py re-run from raw/ reproduces n03-summary.json exactly (and the metrics file).
 3. headline-numbers.json: every cited number equals the value at its path in n03-summary.json
    (or hc-control.json), and every headline number appears in README.md.
 4. Ignored-but-cited: every packet-relative path cited in README.md in backticks exists and is
    tracked by git (not ignored by the packet .gitignore or any other ignore rule).
 5. PREREG.json was committed before the first measured trial: the commit time of the first commit
    that added PREREG.json precedes the earliest 'acquired' of this attempt's EXCLUSIVE (quiet-timed)
    receipts in raw/locks/quiet-lane-receipts.jsonl.
 6. Privacy: no absolute local path pattern in any tracked packet text file (gzip members included);
    pass --forbid <token> (repeatable) to also forbid e.g. a host name without writing it here;
    with CUA_PRIVACY_NAMES_FILE set, every non-empty line of that untracked file is forbidden too as a
    whole word, case-insensitive (the names are never printed).
 7. Lock evidence: every measured block label has an EXCLUSIVE receipt (rc 0) and every control/pilot
    block label a SHARED receipt with the required fields.

usage: python3 verify_artifacts.py [--forbid TOKEN ...]
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
MEASURED = {"a1", "k1", "b1", "a2", "k2", "bu1"}
FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], check=True, capture_output=True, text=True).stdout


def get_path(obj, path: str):  # noqa: ANN001
    for part in path.split("|"):
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--forbid", action="append", default=[])
    args = ap.parse_args()
    # 1 manifest
    manifest = json.loads((RAW / "MANIFEST.json").read_text(encoding="utf-8"))
    bad = [k for k, v in manifest.items()
           if not (RAW / k).is_file() or hashlib.sha256((RAW / k).read_bytes()).hexdigest() != v["sha256"]
           or (RAW / k).stat().st_size != v["bytes"]]
    extra = [str(p.relative_to(RAW)) for p in RAW.rglob("*") if p.is_file() and p.name != "MANIFEST.json"
             and str(p.relative_to(RAW)) not in manifest]
    check(not bad and not extra, f"raw manifest: {len(manifest)} files, mismatched {bad[:5]}, unlisted {extra[:5]}")
    # 2 re-analysis
    with tempfile.TemporaryDirectory() as tmp:
        out, met = Path(tmp) / "s.json", Path(tmp) / "m.jsonl.gz"
        subprocess.run([sys.executable, str(HERE / "analyze_n03.py"), "--raw", str(RAW), "--out", str(out),
                        "--metrics", str(met)], check=True, capture_output=True)
        same = json.loads(out.read_text(encoding="utf-8")) == json.loads((HERE / "n03-summary.json").read_text(encoding="utf-8"))
        check(same, "analyze_n03.py reproduces n03-summary.json from raw/")
        check(gzip.decompress(met.read_bytes()) == gzip.decompress((HERE / "n03-trial-metrics.jsonl.gz").read_bytes()),
              "analyze_n03.py reproduces n03-trial-metrics.jsonl.gz")
    # 3 headline numbers
    summary = json.loads((HERE / "n03-summary.json").read_text(encoding="utf-8"))
    hc = json.loads((HERE / "hc-control.json").read_text(encoding="utf-8"))
    heads = json.loads((HERE / "headline-numbers.json").read_text(encoding="utf-8"))
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    nbad = []
    for h in heads["numbers"]:
        src = summary if h["source"] == "n03-summary.json" else hc
        try:
            v = get_path(src, h["path"])
        except (KeyError, IndexError, TypeError):
            nbad.append(f"{h['id']}: path missing")
            continue
        if v != h["value"]:
            nbad.append(f"{h['id']}: {v!r} != {h['value']!r}")
        if h.get("cited_in_readme") and h["text"] not in readme:
            nbad.append(f"{h['id']}: README lacks {h['text']!r}")
    check(not nbad, f"headline numbers: {len(heads['numbers'])} checked, problems {nbad[:6]}")
    # 4 ignored-but-cited
    cited = sorted({m for m in re.findall(r"`([A-Za-z0-9_./-]+\.(?:py|sh|json|jsonl|gz|txt|log|md))`", readme)
                    if not m.startswith(("/", "libs/", "crates/", "docs/")) and "*" not in m})
    tracked = set(git("ls-files", "--", ".").splitlines())
    missing = [c for c in cited if not (HERE / c).exists()]
    untracked = [c for c in cited if (HERE / c).exists() and c not in tracked]
    ignored = []
    for c in cited:
        res = subprocess.run(["git", "-C", str(HERE), "check-ignore", "-q", "--no-index", c], capture_output=True)
        if res.returncode == 0:
            ignored.append(c)
    check(not missing and not untracked and not ignored,
          f"README-cited paths: {len(cited)} cited; missing {missing[:5]}, untracked {untracked[:5]}, ignored {ignored[:5]}")
    # 5 PREREG before first measured trial
    first = git("log", "--diff-filter=A", "--format=%cI", "--", "PREREG.json").split()
    prereg_t = dt.datetime.fromisoformat(first[-1]) if first else None
    receipts = [json.loads(x) for x in (RAW / "locks" / "quiet-lane-receipts.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    meas = [x for x in receipts if str(x.get("label", "")).startswith("n03a2-")
            and str(x["label"]).split("-")[1] in MEASURED and x.get("mode") is None]
    t_first = min((dt.datetime.fromisoformat(x["acquired"].replace("Z", "+00:00")) for x in meas), default=None)
    check(bool(prereg_t and t_first and prereg_t < t_first),
          f"PREREG.json first committed {prereg_t} before the first measured lock {t_first}")
    # 7 lock evidence
    labels = {p.name for p in (RAW / "runs").iterdir() if p.is_dir()}
    nolock = []
    for lab in sorted(labels):
        block = lab.split("-")[1]
        mine = [x for x in receipts if x.get("label") == lab]
        if block in MEASURED:
            ok = any(x.get("mode") is None and x.get("rc") == 0 for x in mine)
        else:
            ok = any(x.get("mode") == "shared" and all(k in x for k in ("lane", "pid", "acquired", "released", "rc", "loadavg_at_acquire"))
                     for x in mine)
        if not ok:
            nolock.append(lab)
    check(not nolock, f"lock receipts for {len(labels)} block labels; missing {nolock}")
    # 6 privacy
    names_file = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    names = ([x.strip() for x in Path(names_file).read_text(encoding="utf-8").splitlines() if x.strip()]
             if names_file else [])
    # whole-word, case-insensitive: a private name must not match inside a public handle
    name_pat = (re.compile("|".join(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])" for n in names), re.I)
                if names else None)
    print(f"privacy: CUA_PRIVACY_NAMES_FILE {'set' if names_file else 'not set'}; {len(names)} private names")
    # built from fragments so this file does not match itself
    pat = re.compile("(" + "|".join(["/" + "mnt/", "/" + "home/", "/" + "Users/", "/" + "root/", "cua-lane" + "-tmp", "cua-" + "lanes/"]) + ")")
    hits = []
    for rel in sorted(tracked):
        p = HERE / rel
        if not p.is_file():
            continue
        data = p.read_bytes()
        if rel.endswith(".gz"):
            data = gzip.decompress(data)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if (pat.search(text) or any(tok and tok in text for tok in args.forbid)
                or (name_pat is not None and name_pat.search(text))):
            hits.append(rel)
    check(not hits, f"privacy: {len(tracked)} tracked files scanned, hits {hits[:5]}")
    print("VERIFY", "FAILED" if FAILS else "OK", f"({len(FAILS)} failures)")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
