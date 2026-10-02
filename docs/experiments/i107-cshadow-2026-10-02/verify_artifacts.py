"""Verify the kvnloo/cua#107 lane CSHADOW packet from raw/ alone. Pure standard library.

Usage: python3 verify_artifacts.py [--b01-archive <trials-measured.tar.gz>]

Checks:
1. raw/admissibility.json is internally consistent (per-trial rows recompute the
   category totals and the verdict); with --b01-archive, the classifier is re-run
   on the archive (sha256 must match provenance) and must reproduce the file.
2. cshadow-summary.json and raw/ledger.jsonl are reproduced exactly by
   analyze_cshadow.py from raw/ (run into a temporary copy).
3. PREREG.json parent hash matches the committed map PREREG; binary identity in
   PREREG and provenance agree; the fixture self-test passed; the unit logs show
   the recorded red/green results; the protocol inventory lists every event the
   map named.
4. No file in the packet contains a local absolute path, this host's name, or a
   secret-like token.
Exit 0 only if every check passes.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
FAIL: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        FAIL.append(what)


def load(path: Path):
    return json.loads(path.read_text())


def admissibility() -> None:
    data = load(RAW / "admissibility.json")
    totals: dict[str, int] = {}
    for trial in data["per_trial"]:
        for row in trial["reads"]:
            totals[row["category"]] = totals.get(row["category"], 0) + 1
    check(totals == data["by_category"], f"admissibility totals recompute {totals}")
    check(sum(totals.values()) == data["get_browser_state_calls"] == 600, "600 get_browser_state calls classified")
    check(len(data["per_trial"]) == data["trials"] == 200, "200 B-01 fill trials")
    outside = totals.get("outside", 0)
    check(data["verdict"] == ("NOT_ADMISSIBLE" if outside == 0 else "AMENDMENT_REQUIRED"), "verdict follows the rule")
    check(data["verdict"] == "NOT_ADMISSIBLE" and data["driver_reads_after_last_mutation"] == 0,
          "active C NOT_ADMISSIBLE; no Driver read after the last mutation")
    labels = {(r["label"], r["category"]) for t in data["per_trial"] for r in t["reads"]}
    check(labels == {("bind", "b"), ("snapshot1", "a"), ("snapshot2", "a")}, f"read labels/categories {sorted(labels)}")
    if "--b01-archive" in sys.argv:
        archive = Path(sys.argv[sys.argv.index("--b01-archive") + 1])
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        prov = load(HERE / "provenance.json")
        check(digest == prov["reused_evidence"]["b01_traces"]["sha256"], "B-01 archive sha256 matches provenance")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "a.json"
            subprocess.run([sys.executable, str(HERE / "classify_reads.py"), str(archive), str(out)], check=True,
                           capture_output=True)
            check(load(out) == data, "classifier re-run reproduces raw/admissibility.json")


def summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "packet"
        copy.mkdir()
        shutil.copytree(RAW, copy / "raw")
        shutil.copy(HERE / "provenance.json", copy / "provenance.json")
        subprocess.run([sys.executable, str(HERE / "analyze_cshadow.py"), str(copy)], check=True, capture_output=True)
        check(load(copy / "cshadow-summary.json") == load(HERE / "cshadow-summary.json"),
              "analyze_cshadow.py reproduces cshadow-summary.json")
        check((copy / "raw/ledger.jsonl").read_text() == (RAW / "ledger.jsonl").read_text(),
              "analyze_cshadow.py reproduces raw/ledger.jsonl")
    s = load(HERE / "cshadow-summary.json")
    check(s["active_c"]["verdict"] == "NOT_ADMISSIBLE", "summary carries the active-C verdict")
    if s["trials_measured"] == 0:
        blocked = all(c.get("t_oracle_ms", c.get("idle_driver_cpu_s", {})).get("status") == "BLOCKED"
                      for c in s["comparisons"].values())
        check(blocked and all(v["status"] == "BLOCKED" for v in s["fidelity"].values()),
              "no measured trial: every REAL cell reported BLOCKED (never zero-filled)")


def identities() -> None:
    prereg = load(HERE / "PREREG.json")
    prov = load(HERE / "provenance.json")
    parent = HERE.parent / "i107-map-2026-10-02" / "PREREG.json"
    if parent.exists():
        check(hashlib.sha256(parent.read_bytes()).hexdigest() == prereg["parent_prereg"]["sha256"],
              "parent map PREREG sha256 matches")
    check(prereg["binary"]["sha256"] == prov["binary"]["sha256"], "binary sha256 agrees (PREREG vs provenance)")
    receipt = (RAW / "build" / "build-receipt.txt").read_text()
    check(prov["binary"]["sha256"] in receipt and "Fresh workspace units: 0" in receipt, "build receipt: sha256, 0 fresh units")
    check(load(RAW / "fixture-selftest.json").get("ok") is True, "fixture self-test passed")
    red = (RAW / "unit" / "unit-red.log").read_text()
    check(red.count("error[E0") >= 100 and "could not compile" in red, "TDD red log: compile errors before implementation")
    green = (RAW / "unit" / "unit-green-full.log").read_text()
    check("test result: ok. 860 passed; 0 failed" in green, "cua-driver-core lib 860 passed")
    check("test result: ok. 602 passed; 0 failed; 10 ignored" in green, "platform-linux lib 602 passed")
    proto = load(RAW / "protocol_events.json")
    missing = {d: v["map_listed_missing_from_protocol"] for d, v in proto["domains"].items()
               if v["map_listed_missing_from_protocol"]}
    check(not missing, f"every map-listed CDP event exists in the Chrome 151 protocol {missing}")


def scan() -> None:
    host = socket.gethostname()
    patterns = [re.compile(p) for p in (r"/mnt/[a-z0-9]", r"/home/[a-z]", r"/tmp/claude", r"/run/user/\d",
                                        r"(?i)typesafe_api_key\s*[=:]\s*\S", r"sk-[A-Za-z0-9]{20,}",
                                        r"(?i)bearer\s+[A-Za-z0-9._-]{20,}")]
    bad = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        text = path.read_text(errors="replace")
        if path.name == "verify_artifacts.py":
            continue
        if host and re.search(rf"\b{re.escape(host)}\b", text):
            bad.append(f"{path.relative_to(HERE)}: host name")
        for pattern in patterns:
            if pattern.search(text):
                bad.append(f"{path.relative_to(HERE)}: {pattern.pattern}")
    check(not bad, f"no local paths, host name or secrets {bad[:10]}")


def main() -> int:
    admissibility()
    summary()
    identities()
    scan()
    print("VERIFY " + ("OK" if not FAIL else f"FAILED ({len(FAIL)})"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
