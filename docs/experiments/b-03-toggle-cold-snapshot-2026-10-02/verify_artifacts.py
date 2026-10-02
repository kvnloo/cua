"""B-03 packet verifier (standard library only; needs the git checkout for the order/blob checks).

    python verify_artifacts.py

Checks:
 1. part1-summary.json recomputes byte-identically from B-02 raw/ (analyze_part1.py).
 2. b03-summary.json recomputes byte-identically from raw/ (analyze_b03.py).
 3. Every b03-summary key except ``post_hoc`` equals the output of the pre-registered analyzer
    (analyze_b03.py at 2549fc1e8, run on the same raw/).
 4. Every headline number (headline-numbers.json) equals its recomputed value and appears in README.md.
 5. PREREG.json was committed once, before the shakedown and the measured block; the amendment
    precedes the measured block.
 6. Lock receipts: both measured chunks ran inside their EXCLUSIVE quiet-timed windows.
 7. Trial counts per cell match the design (toggle 8 x 20, fill 4 x 10, nc 20; shakedown 7);
    every trial has a Driver trace and a loadavg.
 8. Binary sha256 and version are consistent across PREREG, provenance and README.
 9. B-02's harness files in this tree are byte-identical to b282ff389.
10. Provider: mock chooser, 0 non-loopback connects; README states TypeSafe 0/0.
11. Privacy: no absolute local paths, host name or secret-like strings in any packet file, any
    raw tarball member, or any blob added on the branch since b282ff389.
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
from pathlib import Path

HERE = Path(__file__).resolve().parent
REL = "docs/experiments/b-03-toggle-cold-snapshot-2026-10-02"
B02_REL = "docs/experiments/b-02-browser-driver-sites-2026-10-02"
BASE = "b282ff3894fa85a7b82257cb1edd5088c2f0ac37"
PREREG_ANALYZER_COMMIT = "2549fc1e8e58b5a7c152e66554a076a1fb8e728b"
SHA = "7e6c06090fa2f2b63152a9276fe3a4766f88d2d5cbe7b412236208ee537bd3a0"
FAIL: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        FAIL.append(msg)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout


def run_py(script: Path, *args: str) -> None:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, str(script), *args], check=True, capture_output=True, env=env)


def get(d, path):
    for p in path:
        d = d[p]
    return d


def fmt1(x: float) -> str:
    s = f"{x:.1f}"
    return s.replace("-", "−") if s.startswith("-") else s


def render(v, kind: str) -> str:
    if kind == "num":
        return fmt1(v)
    if kind == "int":
        return str(int(v))
    if kind == "pct":
        return fmt1(100 * v) + "%"
    if kind == "pct0":
        return f"{100 * v:.0f}%"
    if kind == "ci":
        return f"{fmt1(v['median'])} [{fmt1(v['ci95'][0])}, {fmt1(v['ci95'][1])}]"
    raise ValueError(kind)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="b03-verify-", dir=os.environ.get("TMPDIR")))
    # 1-2 recomputation
    run_py(HERE / "analyze_part1.py", "--out", str(tmp / "p1.json"))
    check((tmp / "p1.json").read_bytes() == (HERE / "part1-summary.json").read_bytes(), "1 part1-summary.json recomputes")
    run_py(HERE / "analyze_b03.py", "--out", str(tmp / "b03.json"))
    check((tmp / "b03.json").read_bytes() == (HERE / "b03-summary.json").read_bytes(), "2 b03-summary.json recomputes")
    # 3 pre-registered analyzer equivalence
    old = git("show", f"{PREREG_ANALYZER_COMMIT}:{REL}/analyze_b03.py")
    old = old.replace("HERE = Path(__file__).resolve().parent", f"HERE = Path({str(HERE)!r})")
    (tmp / "analyze_b03_prereg.py").write_text(old)
    run_py(tmp / "analyze_b03_prereg.py", "--out", str(tmp / "b03-prereg.json"))
    a = json.loads((tmp / "b03-prereg.json").read_text())
    b = json.loads((HERE / "b03-summary.json").read_text())
    b.pop("post_hoc", None)
    check(a == b, "3 every non-post_hoc key equals the pre-registered analyzer output (2549fc1e8)")
    diff = git("diff", PREREG_ANALYZER_COMMIT, "HEAD", "--", f":(top){REL}/analyze_b03.py")
    removed = [line for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")]
    check(not removed, "3b analyzer changes after 2549fc1e8 are additions only (post_hoc block)")
    # 4 headline numbers
    readme = (HERE / "README.md").read_text()
    hn = json.loads((HERE / "headline-numbers.json").read_text())["entries"]
    files = {"part1-summary.json": json.loads((HERE / "part1-summary.json").read_text()),
             "b03-summary.json": json.loads((HERE / "b03-summary.json").read_text())}
    bad = []
    for e in hn:
        txt = render(get(files[e["file"]], e["path"]), e["kind"])
        if txt != e["text"] or e["text"] not in readme:
            bad.append((e["id"], txt, e["text"], e["text"] in readme))
    check(not bad, f"4 {len(hn)} headline numbers recompute and appear in README {bad[:5]}")
    # 5 PREREG order
    pre = git("log", "--format=%H %cI", "--", f":(top){REL}/PREREG.json").split()
    check(len(pre) == 2, "5a PREREG.json has exactly one commit (never edited)")
    amend = git("log", "--format=%H %cI", "--", f":(top){REL}/PREREG-AMENDMENT-1.json").split()
    from datetime import datetime
    ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    ledger = [json.loads(x) for x in (HERE / "raw/lock-ledger.jsonl").read_text().splitlines()]
    shake = next(r for r in ledger if r.get("mode") == "shared")
    man = {p.name: json.loads(p.read_text()) for p in (HERE / "raw/measured").glob("run-manifest-*.json")}
    first_measured = min(m["started_utc"] for m in man.values())
    check(ts(pre[1]) < ts(shake["acquired_utc"]) and ts(pre[1]) < ts(first_measured),
          f"5b PREREG {pre[1]} precedes shakedown {shake['acquired_utc']} and measured {first_measured}")
    check(len(amend) == 2 and ts(amend[1]) < ts(first_measured), f"5c amendment {amend[1] if amend else None} precedes measured")
    # 6 locks
    ok6 = True
    for label, mname in (("b03-measured-a", "run-manifest-measured-r00-10.json"), ("b03-measured-b", "run-manifest-measured-r10-20.json")):
        r = next((x for x in ledger if x.get("label") == label), None)
        m = man.get(mname)
        ok6 &= bool(r and m and r["rc"] == 0 and ts(r["acquired"]) <= ts(m["started_utc"]) and ts(m["ended_utc"]) <= ts(r["released"]))
    check(ok6, "6 both measured chunks ran inside their EXCLUSIVE quiet-timed windows")
    # 7 counts, traces, loadavg
    def members(tgz: Path) -> dict[str, bytes]:
        with tarfile.open(tgz, "r:gz") as tar:
            return {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
    mem = members(HERE / "raw/measured-trials.tar.gz")
    sums = [json.loads(v.decode().splitlines()[-1]) for k, v in mem.items() if not k.endswith("driver-trace.jsonl")]
    traces = {Path(k).name for k in mem if k.endswith("driver-trace.jsonl")}
    cnt: dict[str, int] = {}
    for s in sums:
        key = f"{s['cls']}:{s['arm']}:{s['P']}:{s['D']}:{s['variant']}"
        cnt[key] = cnt.get(key, 0) + 1
    want = {f"toggle:{k}:{p}:{d}:task": 20 for k in ("K5V", "K5EV") for p in ("cold", "warm") for d in (0, 80)}
    want.update({f"fill:K5V:{p}:{d}:task": 10 for p in ("cold", "warm") for d in (0, 80)})
    want["toggle:K5V:cold:0:nc"] = 20
    check(cnt == want, f"7a measured cells match the design (220 trials): {len(sums)}")
    check(all(Path(s["driver_trace"]).name in traces for s in sums), "7b every measured trial has its Driver trace")
    check(all(s.get("loadavg_before", "unavailable") != "unavailable" and s.get("loadavg_after") for s in sums),
          "7c loadavg recorded before and after every trial")
    sh = members(HERE / "raw/shake-trials.tar.gz")
    check(sum(1 for k in sh if not k.endswith("driver-trace.jsonl")) == 7, "7d shakedown has 7 trials (excluded)")
    # 8 binary
    prov = json.loads((HERE / "provenance.json").read_text())
    prereg = json.loads((HERE / "PREREG.json").read_text())
    check(prov["driver_binary"]["sha256"] == SHA == prereg["driver_binary"]["sha256"] and SHA in readme
          and "cua-driver 0.32.0" in readme and prov["driver_binary"]["rehash_equal"], "8 binary sha256/version consistent")
    # 9 B-02 harness unchanged
    d = subprocess.run(["git", "-C", str(HERE), "diff", "--quiet", BASE, "HEAD", "--", f":(top){B02_REL}"])
    check(d.returncode == 0, "9 B-02 packet files unchanged since b282ff389")
    # 10 provider
    check(all(m["provider"] == "mock" and m["network"]["non_loopback_connect_attempts"] == 0 for m in man.values())
          and all((s.get("network") or {}).get("non_loopback_connect_attempts") == 0 for s in sums)
          and "TypeSafe: 0 attempts, 0 reached" in readme, "10 mock chooser, 0 non-loopback connects, TypeSafe 0/0")
    # 11 privacy
    host = Path("/etc/hostname").read_text().strip() if Path("/etc/hostname").exists() else ""
    pats = [re.compile(r"/mnt/[A-Za-z]"), re.compile(r"/home/[a-z]"), re.compile(r"zer0models"),
            re.compile(r"sk-[A-Za-z0-9]{20,}"), re.compile(r"(?i)api[_-]?key\s*[=:]\s*['\"]?[A-Za-z0-9]{12,}")]
    if host:
        pats.append(re.compile(r"(?i)\b" + re.escape(host) + r"\b"))

    def leaks(text: str) -> list[str]:
        return [p.pattern for p in pats if p.search(text)]
    hits = []
    for p in HERE.rglob("*"):
        if p.is_file() and p.suffix != ".gz":
            if p.name == "verify_artifacts.py":
                continue
            if leaks(p.read_text(errors="replace")):
                hits.append(str(p.relative_to(HERE)))
    for tgz in HERE.glob("raw/*.tar.gz"):
        for k, v in members(tgz).items():
            if leaks(v.decode(errors="replace")):
                hits.append(f"{tgz.name}:{k}")
    for c in git("rev-list", f"{BASE}..HEAD").split():
        for line in git("ls-tree", "-r", "--full-tree", c, "--", REL).splitlines():
            meta, path = line.split("\t", 1)
            blob = meta.split()[2]
            if path.endswith("verify_artifacts.py"):
                continue
            data = subprocess.run(["git", "-C", str(HERE), "cat-file", "-p", blob], capture_output=True, check=True).stdout
            if path.endswith(".gz"):
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                    for m in tar.getmembers():
                        if m.isfile() and leaks(tar.extractfile(m).read().decode(errors="replace")):
                            hits.append(f"{c[:9]}:{path}:{m.name}")
            elif leaks(data.decode(errors="replace")):
                hits.append(f"{c[:9]}:{path}")
        msg = git("log", "-1", "--format=%B", c)
        if leaks(msg):
            hits.append(f"{c[:9]}:commit-message")
    check(not hits, f"11 privacy: no local paths/host/secrets in packet files, tarballs or branch commits {sorted(set(hits))[:5]}")
    print(json.dumps({"failures": FAIL}, indent=1))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
