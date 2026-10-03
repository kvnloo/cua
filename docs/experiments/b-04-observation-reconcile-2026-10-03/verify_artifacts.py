"""B-04 packet verifier (standard library only; needs the git checkout for the order/blob checks).

    python3 verify_artifacts.py

Checks:
 1. b04-summary.json recomputes byte-identically from raw/measured-trials.tar.gz (analyze_b04.py).
 2. raw/r210-comp-rows.json equals R2-10's r2-10-summary.json COMP rows @ 030f6bdbf, and
    raw/r210-observation-rows.json re-derives from R2-10's raw tarballs @ 030f6bdbf (r210_observation.py)
    (both SKIP, not PASS, when 030f6bdbf is not in the local object store).
 3. Every headline number (headline-numbers.json) equals its recomputed value and appears in README.md.
 4. PREREG.json has exactly one commit and it precedes the first measured trial.
 5. Locks: every measured manifest ran inside its EXCLUSIVE quiet-timed ledger window (rc 0, label
    match); the attempt-2 pilot has a SHARED receipt line.
 6. Trial counts per cell match the design (655 measured trial records), every record has a Driver trace
    and loadavg before/after, every planned trial name of every manifest has a record.
 7. Driver: every trial record and manifest carries sha256 12b9045a...; PREREG/provenance/README agree;
    the start and end re-hash in provenance are equal.
 8. harness/ copies are blob-identical to their source commits (SKIP per file whose source commit is
    not in the local object store).
 9. Provider: scripted chooser, 0 non-loopback connects in every record and manifest; README states
    TypeSafe 0/0.
10. Files: every path cited in README's Files table exists, is tracked, and is not ignored (the repo
    ignores *.log; the packet-local .gitignore re-includes it).
11. Privacy: no absolute local paths, host name or secret-like strings in any packet file, raw tarball
    member, or any blob/commit message on the branch since 8f3a646b4.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REL = "docs/experiments/b-04-observation-reconcile-2026-10-03"
BASE = "8f3a646b4818b757648835cf89db8886626b1cf0"
R210 = "030f6bdbf811e124e11daa2de0569bffb993b66d"
R210_REL = "docs/experiments/r2-10-composition-2026-10-02"
SHA = "12b9045aafddd208c7aeb7e49d5a2e5ab7e776c07ec6d7bd62322807291458a9"
HARNESS = {  # file -> (source commit, source path)
    "harness/run_b03.py": ("b34eef71ee40bc733670e68d9cf57f6acc92ec5c", "docs/experiments/b-03-toggle-cold-snapshot-2026-10-02/run_b03.py"),
    "harness/run_critpath.py": ("b282ff3894fa85a7b82257cb1edd5088c2f0ac37", "docs/experiments/b-02-browser-driver-sites-2026-10-02/run_critpath.py"),
    "harness/run_b02.py": ("b282ff3894fa85a7b82257cb1edd5088c2f0ac37", "docs/experiments/b-02-browser-driver-sites-2026-10-02/run_b02.py"),
    "harness/cdp_raw.py": ("b282ff3894fa85a7b82257cb1edd5088c2f0ac37", "docs/experiments/b-02-browser-driver-sites-2026-10-02/cdp_raw.py"),
    "harness/b01_fixtures.py": ("b282ff3894fa85a7b82257cb1edd5088c2f0ac37", "docs/experiments/b-02-browser-driver-sites-2026-10-02/b01_fixtures.py"),
    "harness/b01_tasks.py": ("b282ff3894fa85a7b82257cb1edd5088c2f0ac37", "docs/experiments/b-02-browser-driver-sites-2026-10-02/b01_tasks.py"),
    "harness/compiled_routine.py": (R210, f"{R210_REL}/harness/src/r2-07-2026-10-02/harness/compiled_routine.py"),
    "harness/r2-10-scripted-COMP-routine.json": (R210, f"{R210_REL}/raw/browser/scripted-routines/scripted-COMP.json"),
}
FAIL: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        FAIL.append(msg)


def skip(msg: str) -> None:
    print("SKIP " + msg)


def git(*args: str, binary: bool = False):
    r = subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode()


def has_object(spec: str) -> bool:
    return subprocess.run(["git", "-C", str(HERE), "cat-file", "-e", spec], capture_output=True).returncode == 0


def run_py(script: Path, *args: str) -> None:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, str(script), *args], check=True, capture_output=True, env=env, cwd=str(HERE))


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def get(d, path):
    for p in path:
        d = d[p]
    return d


sys.path.insert(0, str(HERE))
from make_headlines import render  # noqa: E402  (the same renderer that wrote headline-numbers.json)


def members(tgz: Path) -> dict[str, bytes]:
    with tarfile.open(tgz, "r:gz") as tar:
        return {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="b04-verify-", dir=os.environ.get("TMPDIR")))
    readme = (HERE / "README.md").read_text()
    # 1 recomputation
    run_py(HERE / "analyze_b04.py", "--out", str(tmp / "s.json"))
    check((tmp / "s.json").read_bytes() == (HERE / "b04-summary.json").read_bytes(), "1 b04-summary.json recomputes from raw/")
    summary = json.loads((HERE / "b04-summary.json").read_text())
    # 2 R2-10 inputs
    if has_object(R210):
        r2 = json.loads(git("show", f"{R210}:{R210_REL}/r2-10-summary.json"))
        rows = json.loads((HERE / "raw/r210-comp-rows.json").read_text())["rows"]
        ok = True
        for k, v in rows.items():
            layer, cls = k.split("/")
            x = r2["browser"][layer]["decomposition"][f"{cls}/COMP"]
            ok &= (v["mean_T_ms"] == x["mean_T_ms"] and v["untested_ms"] == x["untested_ms"]
                   and v["untested_share"] == x["untested_share"]
                   and v["observation_ms"] == x["components"]["observation"]["mean_ms"])
        check(ok and len(rows) == 6, "2a raw/r210-comp-rows.json equals R2-10 r2-10-summary.json COMP rows @ 030f6bdbf")
        for name in ("scripted", "live"):
            (tmp / f"{name}.tgz").write_bytes(git("show", f"{R210}:{R210_REL}/raw/browser/{name}-trials.tar.gz", binary=True))
        run_py(HERE / "r210_observation.py", "--scripted", str(tmp / "scripted.tgz"), "--live", str(tmp / "live.tgz"),
               "--out", str(tmp / "obs.json"))
        check((tmp / "obs.json").read_bytes() == (HERE / "raw/r210-observation-rows.json").read_bytes(),
              "2b raw/r210-observation-rows.json re-derives from R2-10 raw @ 030f6bdbf")
    else:
        skip("2 R2-10 commit 030f6bdbf not in the local object store (fetch exp/r2-10-composition-20261002 to run)")
    # 3 headline numbers
    hn = json.loads((HERE / "headline-numbers.json").read_text())["entries"]
    bad = []
    for e in hn:
        txt = render(get(summary, e["path"]), e["kind"])
        if txt != e["text"] or e["text"] not in readme:
            bad.append((e["id"], txt, e["text"], e["text"] in readme))
    check(not bad, f"3 {len(hn)} headline numbers recompute and appear in README {bad[:5]}")
    # 4 PREREG order
    pre = git("log", "--format=%H %cI", "--", f":(top){REL}/PREREG.json").split()
    man = {p.name: json.loads(p.read_text()) for p in (HERE / "raw/measured").glob("run-manifest-*.json")}
    first_measured = min(m["started_utc"] for m in man.values())
    check(len(pre) == 2 and ts(pre[1]) < ts(first_measured),
          f"4 PREREG.json committed once ({pre[1] if len(pre) > 1 else None}) before the first measured trial ({first_measured})")
    # 5 locks
    ledger = [json.loads(x) for x in (HERE / "raw/lock-ledger.jsonl").read_text().splitlines() if x.strip()]
    ok5 = bool(man)
    for name, m in man.items():
        r = next((x for x in ledger if x.get("label") == m.get("lock_label") and "mode" not in x), None)
        ok5 &= bool(r and r["rc"] == 0 and m.get("lock_mode") == "exclusive"
                    and ts(r["acquired"]) <= ts(m["started_utc"]) and ts(m["ended_utc"]) <= ts(r["released"]))
    pil = [x for x in ledger if x.get("mode") == "shared" and x.get("lane") == "B-04"]
    check(ok5 and len(pil) >= 1, f"5 {len(man)} measured manifests inside EXCLUSIVE quiet-timed windows; pilot SHARED receipts {len(pil)}")
    # 6 counts
    mem = members(HERE / "raw/measured-trials.tar.gz")
    sums = [json.loads(v.decode().splitlines()[-1]) for k, v in mem.items() if not k.endswith("driver-trace.jsonl")]
    traces = {Path(k).name for k in mem if k.endswith("driver-trace.jsonl")}
    cnt: dict[str, int] = {}
    for s in sums:
        cell = s["trial"].split("-", 3)[3]
        key = f"{s['probe']}/{s['cls']}/{cell}"
        cnt[key] = cnt.get(key, 0) + 1
    want = {}
    for c in ("fill", "toggle"):
        for cell in ("D80", "D160"):
            want[f"P1/{c}/{cell}"] = 30
        for cell in ("newdoc", "samedoc"):
            want[f"P3/{c}/{cell}"] = 30
        for cell in ("W0", "W80", "PREWARM"):
            want[f"P4/{c}/{cell}"] = 30
        for cell in ("inject20", "inject0"):
            want[f"POS/{c}/{cell}"] = 10
    for c in ("fill", "toggle", "modal"):
        for cell in ("cold", "warm"):
            want[f"P2/{c}/{cell}"] = 30
        want[f"SMOKE/{c}/default"] = 5
    names = {s["trial"] for s in sums}
    planned = {t for m in man.values() for t in m["trials"]}
    check(cnt == want and len(sums) == 655, f"6a measured cells match the design: {len(sums)} records")
    check(all(Path(s["driver_trace"]).name in traces for s in sums), "6b every measured trial has its Driver trace")
    check(all(s.get("loadavg_before") and s.get("loadavg_after") for s in sums), "6c loadavg before and after every trial")
    check(planned == names, f"6d every planned trial has a record (planned {len(planned)}, records {len(names)})")
    # 7 binary
    prov = json.loads((HERE / "provenance.json").read_text())
    prereg = json.loads((HERE / "PREREG.json").read_text())
    check(all(s.get("driver_sha256") == SHA for s in sums) and all(m["driver_sha256"] == SHA for m in man.values())
          and prov["driver_binary"]["sha256"] == SHA == prereg["source_and_binary"]["binary_R"]["sha256"]
          and SHA in readme and "cua-driver 0.32.0" in readme
          and prov["driver_binary"]["sha256_start"] == prov["driver_binary"]["sha256_end"] == SHA,
          "7 binary sha256/version consistent in every record, manifest, PREREG, provenance and README")
    # 8 harness copies
    for rel, (commit, path) in HARNESS.items():
        if not has_object(commit):
            skip(f"8 {rel}: source commit {commit[:9]} not in the local object store")
            continue
        src = git("show", f"{commit}:{path}", binary=True)
        check(src == (HERE / rel).read_bytes(), f"8 {rel} blob-identical to {commit[:9]}:{path}")
    # 9 provider
    check(all(m["provider"] == "mock" and m["network"].get("non_loopback_connect_attempts", 0) == 0 for m in man.values())
          and all((s.get("network") or {}).get("non_loopback_connect_attempts", 0) == 0 for s in sums)
          and "TypeSafe: 0 attempts, 0 reached" in readme, "9 scripted chooser, 0 non-loopback connects, TypeSafe 0/0")
    # 10 cited files tracked and not ignored
    m = re.search(r"## Files\n(.*?)(\n## |\Z)", readme, re.S)
    cited = sorted(set(re.findall(r"`((?:raw|lane-scripts|harness)/[^`*]+|[A-Za-z0-9_.-]+\.(?:py|json|md|gitignore))`",
                                  m.group(1) if m else "")))
    missing = []
    for c in cited:
        p = HERE / c
        tracked = subprocess.run(["git", "-C", str(HERE), "ls-files", "--error-unmatch", c], capture_output=True).returncode == 0
        ignored = subprocess.run(["git", "-C", str(HERE), "check-ignore", "-q", c], capture_output=True).returncode == 0
        if not p.exists() or not tracked or ignored:
            missing.append((c, p.exists(), tracked, ignored))
    check(bool(cited) and not missing, f"10 {len(cited)} cited files exist, tracked, not ignored {missing[:5]}")
    # 11 privacy
    host = Path("/etc/hostname").read_text().strip() if Path("/etc/hostname").exists() else ""
    pats = [re.compile(r"/mnt/[A-Za-z]"), re.compile(r"/home/[a-z]"), re.compile(r"/tmp/claude"),
            re.compile(r"sk-[A-Za-z0-9]{20,}"), re.compile(r"(?i)api[_-]?key\s*[=:]\s*['\"]?[A-Za-z0-9]{12,}")]
    if host:
        pats.append(re.compile(r"(?i)\b" + re.escape(host) + r"\b"))

    def leaks(text: str) -> list[str]:
        return [p.pattern for p in pats if p.search(text)]
    hits = []
    for p in HERE.rglob("*"):
        if p.is_file() and p.suffix != ".gz" and "__pycache__" not in p.parts and p.name != "verify_artifacts.py":
            if leaks(p.read_text(errors="replace")):
                hits.append(str(p.relative_to(HERE)))
    for tgz in HERE.glob("raw/**/*.tar.gz"):
        for k, v in members(tgz).items():
            if leaks(v.decode(errors="replace")):
                hits.append(f"{tgz.name}:{k}")
    for c in git("rev-list", f"{BASE}..HEAD").split():
        for line in git("ls-tree", "-r", "--full-tree", c, "--", REL).splitlines():
            meta, path = line.split("\t", 1)
            blob = meta.split()[2]
            if path.endswith("verify_artifacts.py"):
                continue
            data = git("cat-file", "-p", blob, binary=True)
            if path.endswith(".gz"):
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                    for mm in tar.getmembers():
                        if mm.isfile() and leaks(tar.extractfile(mm).read().decode(errors="replace")):
                            hits.append(f"{c[:9]}:{path}:{mm.name}")
            elif leaks(data.decode(errors="replace")):
                hits.append(f"{c[:9]}:{path}")
        if leaks(git("log", "-1", "--format=%B", c)):
            hits.append(f"{c[:9]}:commit-message")
        changed = git("diff-tree", "--no-commit-id", "--name-only", "-r", c).split()
        outside = [x for x in changed if not x.startswith(REL + "/")]
        if outside:
            hits.append(f"{c[:9]}:touches-outside-packet:{outside[:3]}")
    check(not hits, f"11 privacy: no local paths/host/secrets in packet files, tarballs or branch commits; packet-only commits {sorted(set(hits))[:5]}")
    print(json.dumps({"failures": FAIL}, indent=1))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
