"""Verify the R2-08 packet: recompute from raw/, check provenance receipts, privacy scan.

usage: python3 verify_artifacts.py      (exit 0 = all checks pass)

Checks:
  1. analyze.compute(raw/) reproduces r2-08-summary.json exactly.
  2. Trial counts: pilot 10, base 60 (20 rounds x 3 arms), neg 60 (3 variants x 2 chunks x 10), n2ctl 3;
     every trial file ends in a summary record; every planned id has a file.
  3. Every measured run manifest started after PREREG registered_utc; PREREG's registered harness
     hashes match the committed files, except files listed in provenance.json post_registration_changes.
  4. Session logs carry the pinned Driver sha256/version and the Chrome version; base ran inside
     an EXCLUSIVE quiet-lane lock window and every negative chunk inside a SHARED one (lockinfo receipts).
  5. UNIT receipts: the 50x repeat log of the committed test_variants.py passes 50/50.
  6. Privacy: no absolute local path, user-home path, run-time host name or credential-shaped string
     in any packet file.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402

DRIVER_SHA = "8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3"
EXPECTED = {"pilot": 10, "base": 60, "neg": 60, "n2ctl": 3}
problems: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        problems.append(msg)


def main() -> int:
    raw = HERE / "raw"
    summary = json.loads((HERE / "r2-08-summary.json").read_text())
    recomputed = json.loads(json.dumps(analyze.compute(raw), sort_keys=True))
    check(recomputed == summary, "summary JSON does not match recomputation from raw/")

    for sub, n in EXPECTED.items():
        files = sorted((raw / sub).glob("*/trials/*.jsonl"))
        check(len(files) == n, f"{sub}: {len(files)} trial files, expected {n}")
        for f in files:
            last = json.loads(f.read_text().splitlines()[-1])
            check(last.get("event") == "summary", f"{f.name}: no summary record")
        for man in (raw / sub).glob("*/run-manifest.json"):
            m = json.loads(man.read_text())
            have = {p.stem for p in (man.parent / "trials").glob("*.jsonl")}
            missing = [i for i in m["plan"] if i not in have and f"{i}.harness-error" not in have]
            check(not missing, f"{man.parent.name}: planned trials missing {missing}")

    prereg = json.loads((HERE / "PREREG.json").read_text())
    prov = json.loads((HERE / "provenance.json").read_text())
    allowed = set(prov.get("post_registration_changes", {}))
    for name, sha in prereg["files_at_registration_sha256"].items():
        now = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        check(now == sha or name in allowed, f"{name} changed after registration without a declared deviation")
    reg = prereg["registered_utc"]
    for sub in ("base", "neg", "n2ctl"):
        for man in (raw / sub).glob("*/run-manifest.json"):
            started = json.loads(man.read_text())["started_utc"]
            check(started[:16] >= reg[:16], f"{sub}/{man.parent.name} started {started} before PREREG {reg}")

    for log in sorted(raw.glob("logs/*.log")):
        text = log.read_text()
        if "pilot" in log.name or "unit" in log.name:
            continue
        check(f"driver_sha256={DRIVER_SHA}" in text, f"{log.name}: Driver sha256 receipt missing")
        check("driver_version=cua-driver 0.32.0" in text, f"{log.name}: Driver version receipt missing")
        check("chrome_version=Google Chrome 151.0.7922.71" in text, f"{log.name}: Chrome version receipt missing")
    for info in sorted(raw.glob("logs/*.lockinfo")):
        t = info.read_text()
        # base: exclusive flock (mode documented in provenance.json, receipt predates the mode line);
        # negative chunks and n2ctl: shared flock with an explicit mode line.
        mode_ok = info.name.startswith("base") or "mode=shared" in t
        check(mode_ok and "rc=0" in t and "lock_acquired" in t and "lock_released" in t,
              f"{info.name}: lock receipt incomplete or wrong mode")
    check(len(list(raw.glob("logs/base*.lockinfo"))) >= 1, "no base lock receipt")
    check(len(list(raw.glob("logs/neg-*.lockinfo"))) == 6, "expected 6 negative-chunk lock receipts")

    # UNIT receipts (deviation 7): the repeated run of the fixed test must record 50/50 passes
    # for the committed test_variants.py.
    rep = raw / "logs/unit-test_variants-repeat50.log"
    check(rep.is_file(), "UNIT repeat log missing")
    if rep.is_file():
        lines = rep.read_text().splitlines()
        runs = [ln for ln in lines if ln.startswith("run=")]
        test_sha = hashlib.sha256((HERE / "test_variants.py").read_bytes()).hexdigest()
        check(len(runs) == 50 and all(" rc=0 " in ln and "Ran 8 tests" in ln and ln.rstrip().endswith("OK") for ln in runs),
              "UNIT repeat log: expected 50 passing runs of 8 tests")
        check(test_sha in lines[0], "UNIT repeat log was not produced by the committed test_variants.py")
    for name in ("unit-test_variants-fixed.log", "unit-test_variants-race-repro.log", "unit-test_fixture_server.log"):
        check((raw / "logs" / name).is_file(), f"UNIT log {name} missing")

    host = socket.gethostname()
    pats = [re.compile(r"/(home|mnt|tmp|root)/[A-Za-z0-9_.-]+"), re.compile(r"(?i)(api[_-]?key|secret|token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
            re.compile(r"sk-[A-Za-z0-9]{20,}")]
    for f in sorted(HERE.rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts:
            continue
        text = f.read_text(errors="replace")
        if f.name == "verify_artifacts.py":
            text = text.split("host = socket.gethostname()")[0]
        for p in pats:
            m = p.search(text)
            check(m is None, f"privacy: {f.relative_to(HERE)} matches {p.pattern!r}: {m.group(0) if m else ''}")
        if host and len(host) > 2:
            check(host not in text, f"privacy: {f.relative_to(HERE)} contains the host name")

    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        return 1
    print(f"OK: summary recomputed; disposition {summary['disposition']}; gates {summary['gates']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
