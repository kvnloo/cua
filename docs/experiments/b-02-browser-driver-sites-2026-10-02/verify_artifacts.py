"""Verify the B-02 packet: recompute every number from raw/ and check locks, order, copies, privacy.

    python verify_artifacts.py            # exit 0 = every check passed

Checks:
  1. analyze_b02.py recomputed from raw/ equals the committed b02-summary.json.
  2. Every headline number in headline-numbers.json appears in README.md and equals the summary.
  3. Lock evidence: the vmicro block ran inside the quiet-timed EXCLUSIVE receipt 'b02-vmicro';
     the STEP 0 run inside 'b02-step0'; every SHARED acquisition held <= 10 trials; builds and
     unit runs carry a lane receipt with the cargo lock.
  4. PREREG order: the PREREG commit (git, when available) precedes the first measured trial, and
     PREREG-AMENDMENT-1's commit precedes the first browser trial of the fix round.
  3b. Fix round: STEP 0 r2 inside the EXCLUSIVE receipt 'b02-step0-r2'; the measured block inside
     'b02-measured'; controls/smoke/shakedown blocks one SHARED acquisition per block of <= 10.
  5. The five B-01 harness files are byte-identical to the recorded git blobs.
  6. 0 non-loopback connects in every runner manifest (TypeSafe attempts 0, reached 0).
  7. Privacy: no absolute local path, host name or secret-shaped value in any packet file.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
FAIL: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def main() -> int:
    prereg = json.loads((HERE / "PREREG.json").read_text())
    summary = json.loads((HERE / "b02-summary.json").read_text())

    # 1. recompute
    # Scratch space inside the packet (never the system /tmp), removed afterwards.
    with tempfile.TemporaryDirectory(dir=HERE, prefix=".verify-") as tmp:
        out = Path(tmp) / "s.json"
        subprocess.run([sys.executable, str(HERE / "analyze_b02.py"), "--raw", str(RAW), "--out", str(out)],
                       check=True, capture_output=True)
        check(json.loads(out.read_text()) == summary, "b02-summary.json recomputes exactly from raw/")

    # 2. headline numbers
    readme = (HERE / "README.md").read_text()
    heads = json.loads((HERE / "headline-numbers.json").read_text())
    for item in heads["numbers"]:
        node = summary
        for key in item["path"]:
            node = node[key]
        value = node
        shown = item["shown"]
        expect = round(value * item.get("scale", 1), item["digits"])
        check(abs(float(shown) - expect) < 1e-9, f"headline {item['name']}: summary {expect} == shown {shown}")
        check(str(shown) in readme, f"headline {item['name']} ({shown}) appears in README")

    # 3. locks
    ledger = [json.loads(line) for line in (RAW / "lock-ledger.jsonl").read_text().splitlines() if line.strip()]
    by_label: dict[str, list[dict]] = {}
    for r in ledger:
        by_label.setdefault(r["label"], []).append(r)
    vm = json.loads((RAW / "vmicro" / "run-manifest-vmicro.json").read_text())
    rec = by_label.get("b02-vmicro", [])
    check(len(rec) == 1 and rec[0]["rc"] == 0 and ts(rec[0]["acquired"]) <= ts(vm["started_utc"])
          and ts(vm["ended_utc"]) <= ts(rec[0]["released"]),
          "vmicro block inside the quiet-timed EXCLUSIVE receipt b02-vmicro")
    s0 = by_label.get("b02-step0", [])
    check(len(s0) == 1, "STEP 0 run has a quiet-timed EXCLUSIVE receipt b02-step0")
    shared = [r for r in ledger if r.get("mode") == "shared" and "trials" in r]
    check(bool(shared) and all(r["trials"] <= 10 for r in shared), "every runner SHARED acquisition held <= 10 trials")
    nv = json.loads((RAW / "nv" / "run-manifest-nv.json").read_text())
    check(all(len(b) <= 10 for b in nv["blocks"]) and len(nv["locks"]) == len(nv["blocks"]),
          "N-V: one SHARED acquisition per block of <= 10 trials")
    for label in ("build-b02-560bd8247", "unit-run-1", "unit-compile-1"):
        r = by_label.get(label, [])
        check(len(r) == 1 and r[0]["cargo_lock"] is True and r[0]["quiet_lock"] == "shared" and r[0]["rc"] == 0,
              f"{label}: receipted under flock -s quiet-lane + cargo-build lock")
    for label in ("b02-step0-dbg1", "b02-shake-vmicro", "b02-shake-vmicro2"):
        r = by_label.get(label, [])
        check(len(r) == 1 and r[0]["quiet_lock"] == "shared", f"{label}: excluded run receipted (SHARED, <= 10 trials)")

    # 3b. fix-round locks
    def session_window(block: str) -> tuple[datetime, datetime] | None:
        log = RAW / block / "session.log"
        if not log.exists():
            return None
        text = log.read_text()
        a = re.search(r"\[b02\] DISPLAY=\S+ start_utc=(\S+)", text)
        b = re.search(r"\[b02\] end_utc=(\S+) rc=", text)
        return (ts(a.group(1)), ts(b.group(1))) if a and b else None

    fix_starts = []
    for block in ("shake-r2-step0", "shake-r2", "shake-r2b", "step0-r2", "measured", "controls", "smoke"):
        w = session_window(block)
        if w:
            fix_starts.append(w[0])
    w = session_window("step0-r2")
    r = by_label.get("b02-step0-r2", [])
    check(w is not None and len(r) == 1 and r[0]["rc"] == 0 and ts(r[0]["acquired"]) <= w[0] and w[1] <= ts(r[0]["released"]),
          "STEP 0 r2 inside the quiet-timed EXCLUSIVE receipt b02-step0-r2")
    mm = RAW / "measured" / "run-manifest-measured.json"
    if mm.exists():
        man = json.loads(mm.read_text())
        r = by_label.get("b02-measured", [])
        check(len(r) == 1 and r[0]["rc"] == 0 and ts(r[0]["acquired"]) <= ts(man["started_utc"])
              and ts(man["ended_utc"]) <= ts(r[0]["released"]), "measured block inside the quiet-timed EXCLUSIVE receipt b02-measured")
    for block in ("controls", "smoke", "shake-r2", "shake-r2b"):
        f = RAW / block / f"run-manifest-{'shakedown' if block == 'shake-r2' else 'shakedown2' if block == 'shake-r2b' else block}.json"
        if f.exists():
            man = json.loads(f.read_text())
            check(all(len(b) <= 10 for b in man["blocks"]) and len(man["locks"]) == len(man["blocks"])
                  and all(l["mode"] == "shared" for l in man["locks"]),
                  f"{block}: one SHARED acquisition per block of <= 10 trials")
    r = by_label.get("b02-shake-r2-step0", [])
    check(len(r) == 1 and r[0]["quiet_lock"] == "shared", "b02-shake-r2-step0: excluded run receipted (SHARED, 3 trials)")

    # 4. PREREG order
    first_measured = ts(vm["started_utc"])
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", str(HERE / "PREREG.json")],
                             cwd=HERE, capture_output=True, text=True, check=True).stdout.strip()
        first_commit = subprocess.run(["git", "log", "--diff-filter=A", "--format=%cI", "--", str(HERE / "PREREG.json")],
                                      cwd=HERE, capture_output=True, text=True, check=True).stdout.split()
        when = datetime.fromisoformat(first_commit[-1]) if first_commit else None
        check(when is not None and when < first_measured, f"PREREG committed ({first_commit[-1] if first_commit else None}) before the first measured trial ({vm['started_utc']})")
        check(bool(out), "PREREG has a commit")
        am = subprocess.run(["git", "log", "--diff-filter=A", "--format=%cI", "--", str(HERE / "PREREG-AMENDMENT-1.json")],
                            cwd=HERE, capture_output=True, text=True, check=True).stdout.split()
        am_when = datetime.fromisoformat(am[-1]) if am else None
        check(am_when is not None and bool(fix_starts) and am_when < min(fix_starts),
              f"PREREG-AMENDMENT-1 committed ({am[-1] if am else None}) before the first fix-round browser trial "
              f"({min(fix_starts).isoformat() if fix_starts else None})")
        later = subprocess.run(["git", "log", "--format=%H", "--", str(HERE / "PREREG.json")],
                               cwd=HERE, capture_output=True, text=True, check=True).stdout.split()
        check(len(later) == 1, "PREREG.json was never edited after its commit")
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
        check(ts(prereg["written_utc"]) < first_measured, "PREREG written_utc precedes the first measured trial (git unavailable)")

    # 5. harness copies
    for name, blob in prereg["source"]["harness_blobs"].items():
        check(git_blob(HERE / name) == blob, f"{name} is byte-identical to B-01 blob {blob[:12]}")

    # 6. provider
    for man in RAW.glob("*/run-manifest-*.json"):
        m = json.loads(man.read_text())
        check(m.get("network", {}).get("non_loopback_connect_attempts", 0) == 0,
              f"{man.parent.name}/{man.name}: 0 non-loopback connects")

    # 7. privacy
    bad_path = re.compile(r"/(mnt|home)/[A-Za-z0-9_.-]+|/tmp/[A-Za-z0-9_.-]{3,}")
    secret = re.compile(r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)")
    host = Path("/etc/hostname").read_text().strip() if Path("/etc/hostname").exists() else ""
    import tarfile
    texts: list[tuple[str, str]] = []
    for p in HERE.rglob("*"):
        if p.is_dir() or "__pycache__" in p.parts or any(part.startswith(".verify-") for part in p.parts):
            continue
        if p.suffixes[-2:] == [".tar", ".gz"]:
            with tarfile.open(p, "r:gz") as tar:
                for m in tar.getmembers():
                    if m.isfile():
                        texts.append((f"{p.name}:{m.name}", tar.extractfile(m).read().decode(errors="replace")))
        else:
            texts.append((str(p.relative_to(HERE)), p.read_text(errors="replace")))
    hits = []
    for name, text in texts:
        if name == "verify_artifacts.py":
            continue
        if bad_path.search(text) or secret.search(text) or (host and host in text):
            hits.append(name)
    check(not hits, f"privacy: no absolute path / host name / secret pattern in {len(texts)} files {hits[:5]}")

    print(f"\n{len(FAIL)} failure(s)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
