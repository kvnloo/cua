"""Verify the kvnloo/cua#107 lane CSHADOW packet from raw/ alone. Pure standard library.

Usage: python3 verify_artifacts.py [--b01-archive <trials-measured.tar.gz>]

Checks:
1. raw/admissibility.json is internally consistent (per-trial rows recompute the
   category totals and the verdict); with --b01-archive, the classifier is re-run
   on the archive (sha256 must match provenance) and must reproduce the file.
2. cshadow-summary.json and raw/ledger.jsonl are reproduced exactly by
   analyze_cshadow.py from raw/ (run into a temporary copy).
3. Every measured trial belongs to a block whose run manifest is present, records
   the lane binary sha256 (or the map binary for default-off reference trials),
   hostless v2 + landlock-scope + session script hashes, a placeholder-reduced
   session run dir, a private inner DISPLAY (> :2) and an all-pass isolation
   pre-flight; and every block has a quiet-lane ledger receipt with rc 0 that
   was acquired after the amendment commit time. Trial archive sha256 matches
   provenance.
4. PREREG.json parent hash matches the committed map PREREG; binary identity in
   PREREG and provenance agree; fixture self-test, unit logs and protocol
   inventory as recorded; the endpoint protocol read inside the session has the
   same sha256 as the resources.pak extraction.
5. Required-zero counts are zero; 0 non-loopback connects (mock chooser).
6. No file in the packet contains a local absolute path, this host's name, or a
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
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
FAIL: list[str] = []
LANE_SHA = "6b481e0e0d52d624005494f64ebe42a3475f86e14943eb36c36b9fc1d021fd23"
REF_SHA = "f3a5c01a2c1b5bce75ccb611d0bacd491a7c3b1a8c3fac65889a1fc9d6977aed"


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        FAIL.append(what)


def load(path: Path):
    return json.loads(path.read_text())


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


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
    check(all(v == 0 for v in s["required_zero"].values()), f"required-zero counts are zero {s['required_zero']}")
    check(s["non_loopback_connect_attempts"] == 0, "0 non-loopback connect attempts (mock chooser, 0 provider HTTP)")
    for key, cell in s["comparisons"].items():
        if key.startswith(("CMP-C-overhead", "CMP-C-idle")):
            first = cell.get("t_oracle_ms") or cell.get("idle_driver_cpu_s")
            check(first.get("status") == "MEASURED" and first.get("pairs", 0) >= 30, f"{key}: >= 30 valid pairs")
    for cond in ("W-quiet", "W-churn"):
        check(s["fidelity"][cond]["trials"] >= 30, f"fidelity {cond}: >= 30 C_shadow_audit trials")


def blocks() -> None:
    prov = load(HERE / "provenance.json")
    ledger = jsonl(RAW / "ledger.jsonl")
    by_label = {r["label"]: r for r in jsonl(RAW / "quiet-lane-receipts.jsonl")}
    manifests = {p.name[len("run-manifest-"):-len(".json")]: load(p) for p in (RAW / "manifests").glob("run-manifest-*.json")}
    measured_blocks = sorted({r["block"] for r in ledger if not r["excluded"]})
    amend_utc = prov["prereg_amendment"]["committed_utc"]
    iso_ref = prov["isolation"]
    bad = []
    for b in measured_blocks:
        m = manifests.get(b)
        if m is None:
            bad.append(f"{b}: no manifest")
            continue
        iso = m.get("isolation") or {}
        checks = iso.get("checks") or {}
        disp = iso.get("inner_display", "")
        ok = (m.get("driver_sha256") == LANE_SHA and m.get("ref_driver_sha256") in (None, REF_SHA)
              and iso.get("ok") is True and all(checks.values()) and len(checks) >= 9
              and iso.get("hostless_sha256") == iso_ref["hostless_sha256"]
              and iso.get("landlock_scope_sha256") == iso_ref["landlock_scope_sha256"]
              and iso.get("session_script_sha256") == iso_ref["session_script_sha256"]
              and str(iso.get("session_run_dir", "")).startswith("<lane-tmp>/")
              and disp.startswith(":") and disp[1:].isdigit() and int(disp[1:]) > 2
              and m.get("provider") == "mock" and (m.get("network") or {}).get("non_loopback_connect_attempts") == 0)
        if not ok:
            bad.append(f"{b}: manifest identity/isolation")
        rec = by_label.get(f"i107-cshadow-{b}")
        if rec is None or rec.get("rc") != 0 or rec["acquired"] < amend_utc:
            bad.append(f"{b}: quiet-lane receipt")
    check(not bad and bool(measured_blocks),
          f"{len(measured_blocks)} measured blocks: manifest, isolation pre-flight and quiet-lane receipt {bad[:8]}")
    names = {r["trial"] for r in ledger}
    listed = {t for b in measured_blocks for t in manifests.get(b, {}).get("trials", [])}
    check(listed <= names, f"every trial a manifest lists is in the ledger (missing {sorted(listed - names)[:5]})")
    archive = RAW / "trials-measured.tar.gz"
    check(hashlib.sha256(archive.read_bytes()).hexdigest() == prov["raw"]["trials_archive_sha256"],
          "trial archive sha256 matches provenance")


def identities() -> None:
    prereg = load(HERE / "PREREG.json")
    prov = load(HERE / "provenance.json")
    parent = HERE.parent / "i107-map-2026-10-02" / "PREREG.json"
    if parent.exists():
        check(hashlib.sha256(parent.read_bytes()).hexdigest() == prereg["parent_prereg"]["sha256"],
              "parent map PREREG sha256 matches")
    check(prereg["binary"]["sha256"] == prov["binary"]["sha256"] == LANE_SHA, "binary sha256 agrees (PREREG vs provenance)")
    check(hashlib.sha256((HERE / "PREREG_AMENDMENT_1.json").read_bytes()).hexdigest()
          == prov["prereg_amendment"]["sha256"], "PREREG_AMENDMENT_1 sha256 matches provenance")
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
    endpoint = load(RAW / "endpoint_protocol.json")
    check(endpoint.get("protocol_sha256") == prov["browser"]["protocol_sha256"] and endpoint.get("port_found") is True,
          "endpoint /json/protocol read inside the session equals the resources.pak extraction")


def scan() -> None:
    host = socket.gethostname()
    patterns = [re.compile(p) for p in (r"/mnt/[a-z0-9]", r"/home/[a-z]", r"/tmp/claude", r"/run/user/\d",
                                        r"(?i)typesafe_api_key\s*[=:]\s*\S", r"sk-[A-Za-z0-9]{20,}",
                                        r"(?i)bearer\s+[A-Za-z0-9._-]{20,}")]
    bad = []
    texts: list[tuple[str, str]] = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.name == "verify_artifacts.py":
            continue
        if path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.isfile():
                        texts.append((f"{path.relative_to(HERE)}:{member.name}",
                                      tar.extractfile(member).read().decode(errors="replace")))
            continue
        texts.append((str(path.relative_to(HERE)), path.read_text(errors="replace")))
    for name, text in texts:
        if host and re.search(rf"\b{re.escape(host)}\b", text):
            bad.append(f"{name}: host name")
        for pattern in patterns:
            if pattern.search(text):
                bad.append(f"{name}: {pattern.pattern}")
    check(not bad, f"no local paths, host name or secrets in {len(texts)} files {bad[:10]}")


def main() -> int:
    admissibility()
    summary()
    blocks()
    identities()
    scan()
    print("VERIFY " + ("OK" if not FAIL else f"FAILED ({len(FAIL)})"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
