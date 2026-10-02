#!/usr/bin/env python3
"""N-02 packet verifier (stdlib only). Run from anywhere: python3 verify_artifacts.py

Derived from the N-01R verifier. Checks:
 1. every number in n02-summary.json recomputes from raw/ (analyze.py, byte-identical JSON);
 2. lock evidence: each block's trials fall inside a lock receipt for that block's label in
    raw/lock-ledger.jsonl (EXCLUSIVE quiet-timed receipts for e01/e02, shared receipts for the
    smoke and control blocks), each exclusive acquisition is under 15 minutes;
 3. PREREG order: the PREREG commit precedes the first measured trial, is an ancestor of HEAD,
    and PREREG.json and plan.json are unchanged since;
 4. every block ran the provenance Driver sha256 and the committed plan; 0 non-loopback connects;
 5. HC equivalence: hc-equivalence.json reports 80/80 agreement over 40 real + 40 mutated results,
    and the mutants are rejected by the reference path (discriminating);
 6. default-off smoke passed; CL steal controls are 10 trials per arm per kind;
 7. README: headline numbers and every verdict appear in the README;
 8. privacy: no absolute local paths, local directory names (derived from this checkout's path),
    host name or secret-like strings in any packet file, nor in any blob or message of any commit
    on this branch since the N-01R head (when git is available);
 9. tracked: every packet file and every raw/ path cited by README.md or provenance.json is
    tracked in git.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402

FAIL: list[str] = []
BRANCH_BASE = "3bb4a7fc70d1d58984b19a7a357892a7c9af31fa"


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def ts(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp() * 1e9)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout


def privacy_patterns():
    host = socket.gethostname()
    bad = re.compile(r"(/home/|/mnt/|/root/|/tmp/(?!\.X11-unix)|sk-[A-Za-z0-9]{16,}|api[_-]?key\s*[:=]\s*\S{8,}"
                     r"|BEGIN [A-Z ]*PRIVATE KEY)", re.I)
    generic = {"home", "mnt", "root", "tmp", "usr", "var", "opt", "srv", "github", "src", "repos", "work", "code"}
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


def main() -> None:
    summary, allm = analyze.analyze()
    committed = (HERE / "n02-summary.json").read_text(encoding="utf-8")
    check(committed == json.dumps(summary, indent=1, sort_keys=True) + "\n", "n02-summary.json recomputes from raw/")
    prov = json.loads((HERE / "provenance.json").read_text(encoding="utf-8"))
    plan_text = (HERE / "plan.json").read_bytes()
    plan = json.loads(plan_text)
    plan_sha = hashlib.sha256(plan_text).hexdigest()
    lock_of = {b["block"]: b["lock"] for b in plan["blocks"]}

    # 2. lock evidence
    ledger = [json.loads(x) for x in (HERE / "raw" / "lock-ledger.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    intervals: dict[str, list[tuple[int, int, str]]] = {}
    pending: dict[str, int] = {}
    for row in ledger:
        if "acquired" in row and "released" in row:
            intervals.setdefault(row["label"], []).append((ts(row["acquired"]), ts(row["released"]), row.get("mode", "exclusive")))
        elif "acquired" in row:
            pending[row["label"]] = ts(row["acquired"])
        elif "released" in row and row["label"] in pending:
            intervals.setdefault(row["label"], []).append((pending.pop(row["label"]), ts(row["released"]), row.get("mode", "shared")))
    for label in pending:
        check(False, f"{label}: acquisition without a release receipt")
    blocks = analyze.load_blocks()
    first_measured = None
    for label, rows in blocks:
        meta = next((r for r in rows if r.get("event") == "meta"), {})
        block = meta.get("block")
        trials = [r for r in rows if r.get("event") == "trial"]
        iv = intervals.get(label, [])
        want = "shared" if lock_of.get(block) == "shared" else "exclusive"
        inside = bool(iv) and all(any(a <= t["w_begin"] and t.get("w_end", t["w_begin"]) <= b for a, b, _ in iv) for t in trials)
        modes_ok = bool(iv) and all(m == want for _, _, m in iv)
        check(inside and modes_ok, f"{label}: {len(trials)} trials inside a {want} lock receipt")
        if want == "exclusive":
            check(all(b - a <= 15 * 60 * 1e9 for a, b, _ in iv), f"{label}: exclusive acquisition under 15 minutes")
        check(meta.get("driver_sha256") == prov["driver"]["sha256"], f"{label}: Driver sha256 matches provenance")
        check(meta.get("plan_sha256") == plan_sha, f"{label}: plan sha256 matches plan.json")
        end = next((r for r in rows if r.get("event") == "end"), None)
        check(((end or {}).get("net") or {}).get("refused_non_loopback_connects") == 0,
              f"{label}: 0 non-loopback connects (provider cap 0)")
        if trials:
            w0 = min(t["w_begin"] for t in trials)
            first_measured = w0 if first_measured is None else min(first_measured, w0)

    # 3. PREREG order
    pre = prov["prereg_commit"]
    pre_ns = int(datetime.strptime(pre["committed_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1e9)
    check(first_measured is not None and pre_ns < first_measured,
          f"PREREG commit {pre['committed_utc']} precedes the first measured trial")
    try:
        sha = pre["sha"]
        check(int(git("log", "-1", "--format=%ct", sha).strip()) * 1e9 < first_measured,
              f"git commit time of {sha[:9]} precedes the first measured trial")
        subprocess.run(["git", "-C", str(HERE), "merge-base", "--is-ancestor", sha, "HEAD"], check=True)
        check(True, f"PREREG commit {sha[:9]} is an ancestor of HEAD")
        for name in ("PREREG.json", "plan.json"):
            then = git("rev-parse", f"{sha}:./{name}").strip()
            now = git("hash-object", name).strip()
            check(then == now, f"{name} unchanged since its pre-registration commit")
    except (subprocess.CalledProcessError, FileNotFoundError, KeyError) as exc:
        check(False, f"git PREREG checks: {exc}")

    # 5. HC equivalence
    eq = json.loads((HERE / "hc-equivalence.json").read_text(encoding="utf-8"))["summary"]
    check(eq["total"] == 80 and eq["agree"] == 80 and eq["real"] == 40 and eq["mutants"] == 40,
          f"HC equivalence: compiled vs library accept/reject agree {eq['agree']}/{eq['total']}")
    check(eq["mutants_rejected_by_reference"] == 40 and eq["real_accepted_by_reference"] == 40,
          "HC equivalence is discriminating: 40/40 real accepted, 40/40 mutants rejected by the library path")

    # 6. smoke + control sizes
    check(summary["control_smoke"]["passed"], "default-off smoke: no knobs, no knob marks, 50 ms sleep and >=220 ms settle")
    sizes = {k: v["trials"] for k, v in summary["control_cl"].items()}
    check(len(sizes) == 24 and all(n == 10 for n in sizes.values()), "CL controls: 10 trials per arm per task per kind (24 cells)")

    # 7. README numbers
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    g = summary["gates"]
    for task in analyze.TASKS:
        for arm in analyze.ARMS[task]:
            m = summary["cells"][f"main/{task}/{arm}"]["T_ms"]["median"]
            check(f"{m:.1f}" in readme, f"README has median T {task}/{arm} = {m:.1f} ms")
            e2 = g["E2"][task][arm]
            for key in ("untested_share_standard", "untested_share_conservative"):
                check(f"{e2[key] * 100:.1f}%" in readme, f"README has {task}/{arm} {key} {e2[key] * 100:.1f}%")
        for h in ("HC", "CL"):
            v = g[h][task]
            check(v["verdict"] in readme, f"README names {h} {task} verdict {v['verdict']}")
            check(f"{v['saving_ms']:.1f}" in readme, f"README has {h} {task} saving {v['saving_ms']:.1f} ms")
            check(all(f"{x:.1f}" in readme for x in v["ci95"]), f"README has {h} {task} CI {v['ci95']}")

    # 8. privacy: packet files, then every commit on this branch since the N-01R head
    host, bad, local_names = privacy_patterns()
    hits = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or path.name == "verify_artifacts.py" or "__pycache__" in path.parts:
            continue
        data = gzip.open(path, "rt", encoding="utf-8", errors="replace").read() if path.suffix == ".gz" else path.read_text(encoding="utf-8", errors="replace")
        hits += scan(data, str(path.relative_to(HERE)), host, bad, local_names)
    check(not hits, f"privacy scan of packet files clean ({len(hits)} hits; {len(local_names)} local directory names checked)"
          f"{': ' + '; '.join(hits[:8]) if hits else ''}")
    try:
        commits = git("rev-list", f"{BRANCH_BASE}..HEAD").split()
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
                    # compressed raw data: scan the whole decompressed blob
                    raw = subprocess.run(["git", "-C", str(HERE), "cat-file", "-p", blob], capture_output=True, check=True).stdout
                    text = gzip.decompress(raw).decode("utf-8", "replace")
                else:
                    # text: scan the lines this commit added (pre-existing upstream text is not this lane's)
                    diff = git("show", "--format=", "-U0", "--no-ext-diff", c, "--", name)
                    text = "\n".join(x[1:] for x in diff.splitlines() if x.startswith("+") and not x.startswith("+++"))
                chits += scan(text, f"{c[:9]}:{name}", host, bad, local_names)
            if "Co-Authored-By: Claude" not in msg:
                chits.append(f"{c[:9]}: missing Co-Authored-By trailer")
            if "7121943+kvnloo@users.noreply.github.com" not in msg.splitlines()[0]:
                chits.append(f"{c[:9]}: author identity")
        check(not chits, f"privacy scan of {len(commits)} branch commits (blobs, paths, messages, identities) clean"
              f"{': ' + '; '.join(chits[:8]) if chits else ''}")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        check(False, f"git commit privacy scan: {exc}")

    # 9. tracked in git
    try:
        tracked = set(git("ls-files", "-z", "--", ".").split("\0")) - {""}
        on_disk = {str(p.relative_to(HERE)) for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        untracked = sorted(on_disk - tracked)
        check(not untracked, f"every packet file is tracked in git ({len(untracked)} untracked)"
              f"{': ' + '; '.join(untracked[:8]) if untracked else ''}")
        cited_text = readme + (HERE / "provenance.json").read_text(encoding="utf-8")
        cited = sorted({c.rstrip("/.,);`") for c in re.findall(r"raw/[A-Za-z0-9_./<>\[\]-]+", cited_text)})
        missing = []
        for ref in cited:
            pattern = re.sub(r"\*+", "*", re.sub(r"<[^>]+>", "*", re.sub(r"\[[^\]]*\]", "*", ref)))
            matches = [p for p in HERE.glob(pattern) if p.is_file()] + \
                      [q for p in HERE.glob(pattern) if p.is_dir() for q in p.rglob("*") if q.is_file()]
            if not matches or any(str(m.relative_to(HERE)) not in tracked for m in matches):
                missing.append(ref)
        check(not missing, f"all {len(cited)} raw/ paths cited by README.md and provenance.json exist and are tracked"
              f"{': ' + '; '.join(missing[:8]) if missing else ''}")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        check(False, f"git tracked-file checks: {exc}")
    print(f"\n{'PASS' if not FAIL else 'FAIL'}: {len(FAIL)} failing checks")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
