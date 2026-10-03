#!/usr/bin/env python3
"""OWN-20G packet verifier (stdlib only). Run from anywhere: python3 verify_artifacts.py

Derived from the N-02 verifier. Checks:
 1. own20g-summary.json and own20g-trial-metrics.jsonl.gz recompute from raw/ (analyze.py, byte-identical);
 2. lock evidence: every counted block's trials fall inside a lock receipt for that block's label in
    raw/lock-ledger.jsonl (shared receipts carry lane/pid/loadavg_at_acquire and cover <= 20 trials;
    the timing block sits inside an EXCLUSIVE quiet-timed receipt of at most 25 minutes);
 3. PREREG order: the PREREG commit precedes the first counted trial and is an ancestor of HEAD;
    PREREG.json, plan.json and every harness file are unchanged since it (analysis files may change;
    their diffs are listed);
 4. every block ran the provenance U/G sha256 and the committed plan; 0 non-loopback connects;
 5. source: U..G touches exactly platform-linux input/focus_guard.rs in one commit; xprobe.py is the
    N-02 blob verbatim;
 6. UNIT: the committed red/green log shows the stall test failing on red only and the full
    platform-linux lib passing on green;
 7. README: every headline number and verdict in summary appears in README.md;
 8. privacy: no absolute local paths, local directory names, host name or secret-like strings in any
    packet file, nor in any blob, path or message of any commit on this branch since U;
 9. tracked: every packet file and every raw/ path cited by README.md or provenance.json is tracked
    in git, including files a .gitignore rule would hide (ignored-but-cited check).
"""

from __future__ import annotations

import gzip
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAIL: list[str] = []
U_SHA = "bdf33d9fe4d716033089244a6571db21934374d6"
XPROBE_BLOB = "f17d83691faacc9397dc4c91a1f4018622c0d75d"
HARNESS = ["PREREG.json", "plan.json", "make_plan.py", "own20g_harness.py", "r3_harness.py", "harness_common.py",
           "stealer.py", "xstall_proxy.py", "xprobe.py", "run_all.sh", "run_block.sh"]
FIX_FILE = "libs/cua-driver/rust/crates/platform-linux/src/input/focus_guard.rs"


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def ts(value: str) -> int:
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in value else "%Y-%m-%dT%H:%M:%SZ"
    return int(datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).timestamp() * 1e9)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout


def privacy_patterns():
    host = socket.gethostname()
    bad = re.compile(r"(/home/|/mnt/|/root/|/tmp/(?!\.X11-unix|\.ICE-unix)|sk-[A-Za-z0-9]{16,}"
                     r"|api[_-]?key\s*[:=]\s*\S{8,}|BEGIN [A-Z ]*PRIVATE KEY|MIT-MAGIC-COOKIE-1\s+[0-9a-f]{8,})", re.I)
    generic = {"home", "mnt", "root", "tmp", "usr", "var", "opt", "srv", "github", "src", "repos", "work", "code",
               "docs", "experiments", "libs"}
    local_names = sorted({p for p in HERE.parents[2].parent.parts if len(p) >= 4 and p.lower() not in generic})
    return host, bad, local_names


def scan(text: str, where: str, host: str, bad, local_names) -> list[str]:
    hits = [f"{where}: {m.group(0)[:40]}" for m in bad.finditer(text)]
    for name in local_names:
        if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text):
            hits.append(f"{where}: local directory name")
    if host and len(host) > 2 and re.search(rf"\b{re.escape(host)}\b", text):
        hits.append(f"{where}: host name")
    return hits


def nested(d, path: str):
    for part in path.split("."):
        d = d[part]
    return d


def main() -> None:
    prov = json.loads((HERE / "provenance.json").read_text(encoding="utf-8"))
    summary = json.loads((HERE / "own20g-summary.json").read_text(encoding="utf-8"))

    # 1. recompute
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        out, met = Path(tmp) / "s.json", Path(tmp) / "m.jsonl.gz"
        subprocess.run([sys.executable, str(HERE / "analyze.py"), "--raw", str(HERE / "raw"), "--out", str(out),
                        "--metrics", str(met)], check=True, capture_output=True)
        check(out.read_bytes() == (HERE / "own20g-summary.json").read_bytes(), "own20g-summary.json recomputes from raw/")
        check(gzip.decompress(met.read_bytes()) == gzip.decompress((HERE / "own20g-trial-metrics.jsonl.gz").read_bytes()),
              "own20g-trial-metrics.jsonl.gz recomputes from raw/")

    # 2 + 4. lock evidence, binaries, plan, provider
    import hashlib
    lock_of, plan_sha_of = {}, {}
    for name in ("plan.json", "plan-supp.json"):
        plan = json.loads((HERE / name).read_text(encoding="utf-8"))
        sha = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        for b in plan["blocks"]:
            lock_of[b["block"]] = b["lock"]
            plan_sha_of[b["block"]] = (name, sha)
    ledger = [json.loads(x) for x in (HERE / "raw" / "lock-ledger.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    intervals: dict[str, list] = {}
    for row in ledger:
        if "acquired" in row and "released" in row:
            intervals.setdefault(row["label"], []).append((ts(row["acquired"]), ts(row["released"]),
                                                           row.get("mode", "exclusive"), row))
    want_sha = {"U": prov["binaries"]["U"]["sha256"], "G": prov["binaries"]["G"]["sha256"]}
    first_counted = None
    counted_labels = set(prov.get("counted_labels", []))
    for d in sorted((HERE / "raw").iterdir()):
        f = d / "trials.jsonl.gz"
        if not f.exists():
            continue
        rows = [json.loads(x) for x in gzip.open(f, "rt", encoding="utf-8") if x.strip()]
        meta = next((r for r in rows if r.get("event") == "meta"), {})
        trials = [r for r in rows if r.get("event") == "trial"]
        block = meta.get("block")
        want = "shared" if lock_of.get(block) == "shared" else "exclusive"
        iv = intervals.get(d.name, [])
        inside = bool(iv) and all(any(a <= t["w_begin"] and t.get("w_end", t["w_begin"]) <= b for a, b, _, _ in iv)
                                  for t in trials)
        modes_ok = bool(iv) and all(m == want for _, _, m, _ in iv)
        check(inside and modes_ok, f"{d.name}: {len(trials)} trials inside a {want} lock receipt")
        if want == "shared":
            check(len(trials) <= 20 and all({"lane", "pid", "loadavg_at_acquire", "rc"} <= set(r) for *_, r in iv),
                  f"{d.name}: shared receipt complete, <= 20 trials per acquisition")
        else:
            check(all(b - a <= 25 * 60 * 1e9 for a, b, _, _ in iv), f"{d.name}: exclusive acquisition under 25 minutes")
        check(meta.get("driver_sha256") == want_sha, f"{d.name}: U/G sha256 match provenance")
        pname, psha = plan_sha_of.get(block, ("?", None))
        check(meta.get("plan_sha256") == psha, f"{d.name}: plan sha256 matches {pname}")
        end = next((r for r in rows if r.get("event") == "end"), None)
        check(((end or {}).get("net") or {}).get("refused_non_loopback_connects") == 0,
              f"{d.name}: 0 non-loopback connects (provider cap 0)")
        if trials and d.name in counted_labels:
            w0 = min(t["w_begin"] for t in trials)
            first_counted = w0 if first_counted is None else min(first_counted, w0)

    # 3. PREREG order and frozen harness
    supp = prov["supplement_commit"]
    supp_first = min((t["w_begin"] for d in (HERE / "raw").iterdir() if d.name.startswith(("own20g-ecs", "own20g-dts"))
                      for t in [json.loads(x) for x in gzip.open(d / "trials.jsonl.gz", "rt", encoding="utf-8")]
                      if t.get("event") == "trial"), default=None)
    check(supp_first is not None and ts(supp["committed_utc"]) < supp_first,
          f"supplement plan commit {supp['committed_utc']} precedes the first supplementary trial")
    pre = prov["prereg_commit"]
    check(first_counted is not None and ts(pre["committed_utc"]) < first_counted,
          f"PREREG commit {pre['committed_utc']} precedes the first counted trial")
    try:
        subprocess.run(["git", "-C", str(HERE), "merge-base", "--is-ancestor", pre["sha"], "HEAD"], check=True)
        check(True, "PREREG commit is an ancestor of HEAD")
        changed = [n for n in HARNESS if git("diff", "--name-only", pre["sha"], "HEAD", "--", n).strip()]
        check(not changed, f"PREREG.json, plan.json and harness unchanged since PREREG ({changed})")
        schanged = [n for n in ("make_plan_supp.py", "plan-supp.json")
                    if git("diff", "--name-only", supp["sha"], "HEAD", "--", n).strip()]
        check(not schanged, f"supplement plan unchanged since its commit ({schanged})")
        later = git("diff", "--stat", pre["sha"], "HEAD", "--", "analyze.py").strip()
        print(f"info analyze.py changes since PREREG: {later.splitlines()[-1] if later else 'none'}")
        # 5. source
        g = prov["source"]["G"]
        files = git("diff", "--name-only", U_SHA, g).split()
        n = len(git("rev-list", f"{U_SHA}..{g}").split())
        check(files == [FIX_FILE] and n == 1, f"U..G is one commit touching only {FIX_FILE}")
        check(git("hash-object", str(HERE / "xprobe.py")).strip() == XPROBE_BLOB, "xprobe.py is the N-02 blob verbatim")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        check(False, f"git checks: {exc}")

    # 6. UNIT log
    unit = (HERE / "raw" / "unit" / "unit-red-green.log").read_text(encoding="utf-8")
    red, _, green = unit.partition("=== green:")
    check("a_steal_during_a_read_stalled_past_the_watch_is_seen ... FAILED" in red
          and "610 passed; 1 failed" in red, "red: only the stall test fails (610 others pass)")
    check("test result: ok. 2 passed; 0 failed" in green and "test result: ok. 16 passed; 0 failed" in green
          and "test result: ok. 611 passed; 0 failed" in green, "green: 2/2 new, 16/16 focus_guard, 611/611 lib")

    # 7. README numbers
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    for key in prov.get("readme_numbers", []):
        value = nested(summary, key)
        check(str(value) in readme, f"README cites {key} = {value}")

    # 8. privacy
    host, bad, local_names = privacy_patterns()
    hits = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts or p.name == "verify_artifacts.py":
            continue
        text = gzip.decompress(p.read_bytes()).decode("utf-8", "replace") if p.suffix == ".gz" \
            else p.read_text(encoding="utf-8", errors="replace")
        hits += scan(text, str(p.relative_to(HERE)), host, bad, local_names)
    check(not hits, f"privacy scan of packet files clean{': ' + '; '.join(hits[:8]) if hits else ''}")
    try:
        commits = git("rev-list", f"{U_SHA}..HEAD").split()
        chits = []
        for c in commits:
            msg = git("log", "-1", "--format=%an <%ae>%n%cn <%ce>%n%B", c)
            chits += scan(msg, f"{c[:9]} message", host, bad, local_names)
            for line in git("diff-tree", "--no-commit-id", "-r", c).splitlines():
                fields = line.split()
                if len(fields) < 6 or fields[4] == "D":
                    continue
                blob, name = fields[3], line.split("\t", 1)[1]
                chits += scan(name, f"{c[:9]} path", host, bad, local_names)
                if name.endswith("verify_artifacts.py"):
                    continue
                if name.endswith(".gz"):
                    raw = subprocess.run(["git", "-C", str(HERE), "cat-file", "-p", blob], capture_output=True,
                                         check=True).stdout
                    text = gzip.decompress(raw).decode("utf-8", "replace")
                else:
                    diff = git("show", "--format=", "-U0", "--no-ext-diff", c, "--", name)
                    text = "\n".join(x[1:] for x in diff.splitlines() if x.startswith("+") and not x.startswith("+++"))
                chits += scan(text, f"{c[:9]}:{name}", host, bad, local_names)
            if "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" not in msg:
                chits.append(f"{c[:9]}: missing Co-Authored-By trailer")
            if msg.splitlines()[0] != "Kevin Rajan <7121943+kvnloo@users.noreply.github.com>" \
                    or msg.splitlines()[1] != "Kevin Rajan <7121943+kvnloo@users.noreply.github.com>":
                chits.append(f"{c[:9]}: author/committer identity")
        check(not chits, f"privacy scan of {len(commits)} branch commits (blobs, paths, messages, identities) clean"
              f"{': ' + '; '.join(chits[:8]) if chits else ''}")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        check(False, f"git commit privacy scan: {exc}")

    # 9. tracked (and ignored-but-cited)
    try:
        tracked = set(git("ls-files", "-z", "--", ".").split("\0")) - {""}
        on_disk = {str(p.relative_to(HERE)) for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        untracked = sorted(on_disk - tracked)
        check(not untracked, f"every packet file is tracked in git ({len(untracked)} untracked)"
              f"{': ' + '; '.join(untracked[:8]) if untracked else ''}")
        cited_text = readme + (HERE / "provenance.json").read_text(encoding="utf-8")
        cited = sorted({c.rstrip("/.,);`'\"") for c in re.findall(r"raw/[A-Za-z0-9_./<>*-]+", cited_text)})
        missing, ignored = [], []
        for ref in cited:
            pattern = re.sub(r"<[^>]+>", "*", ref)
            matches = [p for p in HERE.glob(pattern) if p.is_file()] + \
                      [q for p in HERE.glob(pattern) if p.is_dir() for q in p.rglob("*") if q.is_file()]
            if not matches or any(str(m.relative_to(HERE)) not in tracked for m in matches):
                missing.append(ref)
            for m in matches:
                res = subprocess.run(["git", "-C", str(HERE), "check-ignore", "--no-index", "-q", str(m)])
                if res.returncode == 0:
                    ignored.append(str(m.relative_to(HERE)))
        check(not missing, f"all {len(cited)} raw/ paths cited by README.md and provenance.json exist and are tracked"
              f"{': ' + '; '.join(missing[:8]) if missing else ''}")
        print(f"info ignored-but-cited files (force-added, tracked): {len(ignored)}"
              f"{' e.g. ' + ', '.join(ignored[:3]) if ignored else ''}")
        check(all(i in tracked for i in ignored), "every ignored-but-cited file is tracked")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        check(False, f"git tracked-file checks: {exc}")
    print(f"\n{'PASS' if not FAIL else 'FAIL'}: {len(FAIL)} failing checks")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
