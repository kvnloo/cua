"""Verify the R2-07c packet from its own files (run under hostless; stdlib + the packet's harness).

usage: python verify_artifacts.py [--skip-git]

Checks (each prints PASS/FAIL; exit 1 on any FAIL):
 1. every raw file listed in raw/package-report.json exists; bundle member counts match;
 2. every compiled artifact in raw/artifacts/ passes the authority scan (no refs/ids/epochs/coordinates/
    capabilities) and carries only role+name targets;
 3. re-running analyze_r2_07c on raw/ reproduces r2-07c-summary.json exactly;
 4. headline numbers quoted in README.md (headline-numbers.json) exist in the summary;
 5. provider ledger: attempts/reached within the lane caps (18 reached / 22 attempts), equal to the summary;
    no ledger line carries a body, header or key-like field;
 6. lock receipts: every measured chunk label appears in raw/lock-receipts-global.jsonl (EXCLUSIVE
    T1/T2/C6/L1 from bin/quiet-timed, SHARED blocks with lane/mode/pid/acquired/released/rc/loadavg);
 7. PREREG.json was committed before the first measured trial and before the first live request (git);
 8. privacy: no absolute path, host-name-like token or key-like string in any packet text file
    (including tar.gz members);
 9. ignored-but-cited: every packet path cited in README.md exists and is not ignored by git (git).
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
sys.path[:0] = [str(HERE), str(HERE / "harness"),
                str(HERE / "harness" / "src" / "r2-10-composition-2026-10-02" / "harness" / "src" / "r2-07-2026-10-02" / "harness")]
RESULTS: list[tuple[str, bool, str]] = []
BAD = [re.compile(p) for p in (r"/mnt/", r"/home/", r"/tmp/(?!\.X11-unix)", r"x11-session\.[A-Za-z0-9]{6}",r"sk-[A-Za-z0-9]{12,}",
                               r"(?i)bearer\s+[a-z0-9]")]
_HOST = __import__("socket").gethostname()
if _HOST:
    BAD.append(re.compile(rf"\b{re.escape(_HOST)}\b"))
CAP_REACHED, CAP_ATTEMPTS = 18, 22


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, check=True).stdout


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def first_utc(block: str) -> str | None:
    path = RAW / f"{block}-trials.tar.gz"
    if not path.exists():
        return None
    best = None
    with tarfile.open(path, "r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile() and not m.name.endswith(".driver-trace.jsonl"):
                lines = tar.extractfile(m).read().decode().splitlines()
                s = json.loads(lines[-1])
                u = s.get("utc_start")
                if u and (best is None or u < best):
                    best = u
    return best


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-git", action="store_true")
    a = p.parse_args()

    # 1 raw files
    rep = json.loads((RAW / "package-report.json").read_text())
    ok, missing = True, []
    for block, entry in rep["blocks"].items():
        tb = RAW / f"{block}-trials.tar.gz"
        if not tb.exists():
            ok = False
            missing.append(tb.name)
            continue
        with tarfile.open(tb, "r:gz") as tar:
            n = sum(1 for m in tar.getmembers() if m.isfile())
        if n != entry["trial_files"]:
            ok = False
            missing.append(f"{tb.name}:{n}!={entry['trial_files']}")
        for sub in ("manifests", "routines"):
            for f in entry.get(sub, []):
                if not (RAW / f"{block}-{sub}" / f).exists():
                    ok = False
                    missing.append(f"{block}-{sub}/{f}")
        for f in entry.get("artifacts", []):
            if not (RAW / "artifacts" / f).exists():
                ok = False
                missing.append(f"artifacts/{f}")
    check("1 raw files and bundle counts", ok, ", ".join(missing[:5]))

    # 2 authority scan
    import compiled_routine_tm as crt

    arts = sorted((RAW / "artifacts").glob("*.json"))
    bad = []
    for f in arts:
        art = json.loads(f.read_text())
        probs = crt.check_artifact_authority_tm(art)
        targets_ok = all(set(s["logical_target"]) == {"role", "name"} for s in art.get("steps", []))
        if probs or not targets_ok:
            bad.append(f"{f.name}: {probs[:2]}")
    check("2 artifacts authority-clean", bool(arts) and not bad, f"{len(arts)} artifacts; {bad[:3]}")

    # 3 analysis reproduces summary
    import analyze_r2_07c as AN

    S = json.loads(json.dumps(AN.analyze(RAW), sort_keys=True, default=lambda o: dict(o)))
    saved = json.loads((HERE / "r2-07c-summary.json").read_text())
    check("3 analysis reproduces r2-07c-summary.json", S == saved)

    # 4 headline numbers
    hl = json.loads((HERE / "headline-numbers.json").read_text())
    readme = (HERE / "README.md").read_text()
    miss = []
    for item in hl["numbers"]:
        cur: object = saved
        for k in item["path"]:
            cur = cur[k] if isinstance(cur, dict) else cur[int(k)]
        val = item["fmt"].format(cur)
        if val != item["text"] or item["text"] not in readme:
            miss.append(f"{'/'.join(map(str, item['path']))}={val} vs {item['text']}")
    check("4 README headline numbers match the summary", not miss, "; ".join(miss[:4]))

    # 5 provider ledger
    led_path = RAW / "provider-ledger.jsonl"
    led = [json.loads(x) for x in led_path.read_text().splitlines() if x.strip()] if led_path.exists() else []
    att = [x for x in led if x.get("kind") == "attempt"]
    reached = sum(1 for x in att if x.get("reached"))
    allowed = {"kind", "attempt", "utc", "host", "path", "trial", "class", "arm", "layer", "reached", "latency_ms",
               "status", "request_id_present", "request_id_sha256_16", "error", "attempts"}
    extra = sorted({k for x in led for k in x} - allowed)
    check("5 provider ledger within caps and content-free",
          len(att) <= CAP_ATTEMPTS and reached <= CAP_REACHED and saved["provider"]["attempts"] == len(att)
          and saved["provider"]["reached"] == reached and not extra,
          f"attempts={len(att)} reached={reached} extra_fields={extra}")

    # 6 lock receipts
    glines = [json.loads(x) for x in (RAW / "lock-receipts-global.jsonl").read_text().splitlines() if x.strip()]
    labels = {g["label"]: g for g in glines}
    need_excl = ["R2-07c-a2-T1", "R2-07c-a2-T2", "R2-07c-a2-C6"]
    if (RAW / "live-trials.tar.gz").exists():
        need_excl.append("R2-07c-a2-L1")
    bad_l = [l for l in need_excl if l not in labels or "mode" in labels[l] or labels[l].get("rc") != 0]
    shared = [g for g in glines if g.get("mode") == "shared"]
    bad_s = [g["label"] for g in shared if not all(k in g for k in ("lane", "pid", "acquired", "released", "rc", "loadavg_at_acquire"))]
    check("6 lock receipts (EXCLUSIVE quiet-timed + SHARED)", not bad_l and not bad_s and len(shared) > 0,
          f"exclusive missing/bad={bad_l} shared_bad={bad_s[:3]} shared_n={len(shared)}")

    # 7 PREREG ordering
    if a.skip_git:
        check("7 PREREG before first measured trial / live request", True, "skipped (--skip-git)")
    else:
        rel = str((HERE / "PREREG.json").relative_to(Path(git("rev-parse", "--show-toplevel").strip())))
        first = git("log", "--diff-filter=A", "--format=%H %cI", "--", f":(top){rel}").strip().splitlines()[-1]
        sha, when = first.split()
        t_prereg = ts(when)
        measured = [u for u in (first_utc(b) for b in ("gate2", "neg", "nw2", "rec", "timed", "costs", "lshake", "live")) if u]
        live_first = min((x["utc"] for x in att), default=None)
        ok7 = all(ts(u) > t_prereg for u in measured) and (live_first is None or ts(live_first) > t_prereg)
        check("7 PREREG before first measured trial / live request", ok7,
              f"PREREG {sha[:9]} {when}; first measured {min(measured) if measured else None}; first live {live_first}")

    # 8 privacy
    hits = []
    for f in sorted(HERE.rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts or f.name in ("verify_artifacts.py", "package_raw.py"):
            continue
        if f.suffix == ".gz":
            with tarfile.open(f, "r:gz") as tar:
                for m in tar.getmembers():
                    if m.isfile():
                        text = tar.extractfile(m).read().decode(errors="replace")
                        hits += [f"{f.name}:{m.name}:{b.pattern}" for b in BAD if b.search(text)]
            continue
        try:
            text = f.read_text()
        except UnicodeDecodeError:
            continue
        hits += [f"{f.relative_to(HERE)}:{b.pattern}" for b in BAD if b.search(text)]
    check("8 privacy scan (paths, host, keys; tar members included)", not hits, "; ".join(hits[:5]))

    # 9 ignored-but-cited
    if a.skip_git:
        check("9 every README-cited packet path exists and is tracked (not ignored)", True, "skipped (--skip-git)")
    else:
        cited = sorted(set(re.findall(r"`((?:raw|harness)/[^`\s]+|[A-Za-z0-9_.-]+\.(?:py|json))`", readme)))
        problems = []
        for c in cited:
            path = HERE / c.rstrip("/")
            if "*" in c:  # a glob: every match must be tracked, and at least one must exist
                matches = sorted(HERE.glob(c))
                if not matches:
                    problems.append(f"missing:{c}")
                for m_path in matches:
                    if subprocess.run(["git", "check-ignore", "-q", str(m_path)], cwd=HERE).returncode == 0:
                        problems.append(f"ignored:{m_path.relative_to(HERE)}")
                continue
            if not path.exists() and "/" not in c:  # a bare file name: any file of that name in the packet
                found = sorted(p for p in HERE.rglob(c) if "__pycache__" not in p.parts)
                path = found[0] if found else path
            if not path.exists():
                problems.append(f"missing:{c}")
                continue
            ignored = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=HERE).returncode == 0
            if ignored:
                problems.append(f"ignored:{c}")
        check("9 every README-cited packet path exists and is tracked (not ignored)", not problems,
              f"{len(cited)} cited; {problems[:5]}")

    failed = [r for r in RESULTS if not r[1]]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
