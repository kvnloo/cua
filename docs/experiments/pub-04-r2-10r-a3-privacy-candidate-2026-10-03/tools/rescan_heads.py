#!/usr/bin/env python3
"""PUB-04 read-only per-commit rescan of published heads (standard library only; run under bin/hostless).

usage: rescan_heads.py <repo> <heads-file> <main-sha> <upstream-sha> <out.json>
  heads-file: "<lane> <branch> <head sha>" per line. For each head, every commit of
  `git rev-list <head> --not <main-sha>` is scanned with pub04_scan.Scanner (message + identity, path
  names, added/modified blobs, gzip/tar members, decoded hex/base64 runs). Each commit row records
  whether it is upstream content (an ancestor of <upstream-sha>) and its findings by class. No ref is
  written; findings carry tags, never values. Set CUA_PRIVACY_NAMES_FILE.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pub04_scan as P  # noqa: E402


def main() -> None:
    repo, heads, main_sha, up, out = sys.argv[1:6]
    sc = P.Scanner(Path(repo))
    cache: dict = {}
    rows = []
    for line in Path(heads).read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        lane, branch, head = line.split()[:3]
        commits, found = P.scan_commits(repo, [head, "--not", main_sha], sc, cache)
        per = []
        for c in commits:
            is_up = subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", c, up]).returncode == 0
            fs = [f for f in found if f["commit"] == c[:12]]
            k: dict[str, int] = {}
            for f in fs:
                k[f["kind"]] = k.get(f["kind"], 0) + 1
            per.append({"commit": c, "upstream_content": is_up, "counts": k,
                        "private": sum(v for kk, v in k.items() if kk in P.PRIVATE),
                        "detail": [{x: f[x] for x in ("kind", "where", "detail", "n")} for f in fs]})
        priv = sum(r["private"] for r in per)
        other: dict[str, int] = {}
        for r in per:
            for kk, v in r["counts"].items():
                if kk not in P.PRIVATE:
                    other[kk] = other.get(kk, 0) + v
        rows.append({"lane": lane, "branch": branch, "head": head, "rev_list": f"{head} --not {main_sha}",
                     "commits_scanned": len(commits), "loop_commits": sum(not r["upstream_content"] for r in per),
                     "private_findings": priv, "per_commit": per})
        print(f"{lane} {branch} @ {head[:9]}: commits={len(commits)} (loop {rows[-1]['loop_commits']}) private={priv} "
              f"non-private={other}", flush=True)
    doc = {"tool": "rescan_heads.py + pub04_scan.Scanner", "names_note": sc.note(), "main": main_sha,
           "upstream_main": up, "classes": P.CLASSES, "private_classes": sorted(P.PRIVATE),
           "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rows": rows,
           "total_private_findings": sum(r["private_findings"] for r in rows)}
    Path(out).write_text(json.dumps(doc, indent=1) + "\n")
    print("total private findings:", doc["total_private_findings"])


if __name__ == "__main__":
    main()
