#!/usr/bin/env python3
"""FRESH-07 packet verifier (standard library only; run under hostless from anywhere).

usage: verify_artifacts.py [--repo <git clone with the cited commits>]
Checks: files present; PREREG / PREREG-P2 committed before the first probe / Phase 2 trial (needs --repo);
the probe summary recomputes byte-for-byte from raw; the inventory is complete and its Linux set is the
expected one; the original analyzers reproduce the committed OWN-20P / OWN-20Q summaries and the numbers
quoted in README; the R2-10R default-off smoke passes under the original phase0 code; every claim has a
verdict; provenance hashes are well formed; no machine path, home path or host name in any packet file
(text and .gz); and, with --repo, orig/ is blob-identical to the accepted packets.
"""

from __future__ import annotations

import argparse
import gzip
import os
import json
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OK, BAD = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (OK if cond else BAD).append(f"{name}{(': ' + detail) if detail else ''}")


def jl(path: Path) -> list[dict]:
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "rt", encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo")
    args = ap.parse_args()

    for f in ("README.md", "PREREG.json", "PREREG-P2.json", "claims.json", "provenance.json", "probe-summary.json",
              "fresh07-summary.json", "raw/probe/probe.jsonl", "raw/source/inventory.json", "raw/source/version-bump.txt",
              "raw/source/expectation-source.txt", "raw/source/orig-manifest.tsv", "raw/build/patch-ids.txt",
              "raw/unit/steps.txt", "p2/own-20p/own20p-recert-summary.json", "p2/own-20q/own20q-summary.json"):
        check(f"present {f}", (HERE / f).exists())

    # probe summary recomputes from raw
    sys.path.insert(0, str(HERE))
    import summarize_probe  # noqa: E402
    recomputed = summarize_probe.summarize(HERE / "raw/probe/probe.jsonl")
    committed = json.loads((HERE / "probe-summary.json").read_text())
    check("probe summary recomputes from raw", json.loads(json.dumps(recomputed, sort_keys=True)) == committed)
    b = committed["binaries"]
    old = ("Rp", "B7", "Rn")
    check("probe: old idle VIEWABLE empty 15/15", sum(b[n]["points"]["S1_idle"].get("VIEWABLE(b0,i0)", 0) for n in old) == 15)
    check("probe: new idle UNMAPPED 5/5", b["M"]["points"]["S1_idle"].get("UNMAPPED(b0,i0)", 0) == 5)
    check("probe: grab text M 5/5 on, 4/5 off; old 0", b["M"]["grab_held_by_on"] == 5 and b["M"]["grab_held_by_off"] == 4
          and all(b[n]["grab_held_by_on"] == 0 and b[n]["grab_held_by_off"] == 0 for n in old))
    check("probe: T3 old overlay viewable before initialize 15/15", sum(b[n]["startup_viewable_before_init"] for n in old) == 15)
    check("probe: oracle verified 20/20 on and off", all(b[n]["oracle_verified_on"] == 5 and b[n]["oracle_verified_off"] == 5 for n in b))
    check("probe: 0 failures", all(not b[n]["failures"] for n in b) and committed["end"].get("failures") == 0)

    inv = json.loads((HERE / "raw/source/inventory.json").read_text())
    check("inventory complete and Linux set as expected", inv["complete"] and inv["linux_relevant_equals_expected"] and inv["files_changed"] == 39)

    steps = (HERE / "raw/unit/steps.txt").read_text()
    check("unit steps all rc=0", steps.count("rc=0") == 4 and "rc=1" not in steps)
    exp_log = (HERE / "raw/unit/core-expectation.log").read_text()
    check("unit expectation 20 passed", "test result: ok. 20 passed; 0 failed" in exp_log)
    check("unit core lib 823 passed", "test result: ok. 823 passed; 0 failed" in (HERE / "raw/unit/core-full.log").read_text())
    check("unit platform-linux lib 602 passed", "test result: ok. 602 passed; 0 failed" in (HERE / "raw/unit/linux-full.log").read_text())

    # guard rows: re-run the original analyzers into a temp dir and compare
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as td:
        td = Path(td)
        subprocess.run([sys.executable, str(HERE / "orig/own-20p/analyze.py"), "--raw", str(HERE / "p2/own-20p/raw"),
                        "--out", str(td / "p.json"), "--metrics", str(td / "p.jsonl.gz")], check=True, capture_output=True)
        p_new, p_old = json.loads((td / "p.json").read_text()), json.loads((HERE / "p2/own-20p/own20p-recert-summary.json").read_text())
        check("OWN-20P analyzer reproduces committed summary", p_new == p_old)
        r1 = p_old["r1"]
        check("OWN-20P R1: G0m'' 20/40, checkbox grab_held 20, U0m'' silent 40/40, gate False",
              r1["G0m_restored"] == 20 and r1["checkbox/G0m"]["receipt_outcomes"] == {"grab_held": 20}
              and r1["text/G0m"]["pass"] == 20 and r1["U0m_silent_miss"] == 40 and r1["gate"] is False and r1["control_ok"])
        check("OWN-20P NORMAL gate holds 40/40", p_old["normal"]["gate"] is True and p_old["normal"]["G0_verified"] == 40)
        qdir = td / "q"
        qdir.mkdir()
        (qdir / "provenance.json").write_text((HERE / "p2/own-20q/provenance.json").read_text())
        (qdir / "raw").symlink_to(HERE / "p2/own-20q/raw")
        subprocess.run([sys.executable, str(HERE / "orig/own-20q/analyze.py"), str(qdir), "--out-dir", str(qdir)], check=True,
                       capture_output=True)
        q_new = json.loads((qdir / "own20q-summary.json").read_text())
        q_old = json.loads((HERE / "p2/own-20q/own20q-summary.json").read_text())
        check("OWN-20Q analyzer reproduces committed summary", q_new == q_old)
        check("OWN-20Q R1m: G0'' 20/40 restore, U0'' 40/40 silent, gate False",
              q_old["r1m"]["G0_verified_restore"] == 20 and q_old["r1m"]["U0_silent_miss"] == 40 and q_old["r1m"]["gate"] is False)
        check("OWN-20Q DLG: GA'' misclassified 20, GQ'' 0 restored, receipts grab_held 20, gate False",
              q_old["dlg"]["GA_misclassified"] == 20 and q_old["dlg"]["GQ_verified_restore"] == 0
              and q_old["dlg"]["receipts"]["GQ"] == {"grab_held": 20} and q_old["dlg"]["gate"] is False)
        check("OWN-20Q normal path holds 40/40", q_old["normal"]["gate"] is True and q_old["normal"]["GQ_verified"] == 40)

    # R2-10R default-off smoke with the original phase0 code
    sys.path.insert(0, str(HERE / "orig/r2-10r"))
    import analyze_r2_10  # noqa: E402
    d = analyze_r2_10.phase0(HERE / "p2/r2-10r/raw/phase0")["d_default_off"]
    check("R2-10R default-off smoke pass", d["pass"] is True)
    check("tools/list digest equals R2-10R's 33772fab", d["toolslist"]["sha256"].get("R", [None])[0].startswith("33772fab"))

    claims = json.loads((HERE / "claims.json").read_text())
    check("every overlay claim has a verdict", all(c["verdict"] in ("AFFECTED", "UNAFFECTED") for c in claims["overlay_rs_per_claim"]))
    prov = json.loads((HERE / "provenance.json").read_text())
    check("provenance sha256 well formed", all(re.fullmatch(r"[0-9a-f]{64}", v["sha256"]) for v in prov["binaries"].values()))

    summ = json.loads((HERE / "fresh07-summary.json").read_text())
    check("summary provider 0/0", summ["provider"] == {"attempts": 0, "reached": 0})

    # privacy over every file (text and gz members)
    host = socket.gethostname()
    pat = re.compile(r"/mnt/|/home/" + (rf"|\b{re.escape(host)}\b" if len(host) >= 3 else ""))
    leaks = []
    for f in HERE.rglob("*"):
        if not f.is_file() or "__pycache__" in f.parts:
            continue
        try:
            if f.name.endswith(".tar.gz"):
                with tarfile.open(f) as t:
                    text = "".join(t.extractfile(m).read().decode("utf-8", "replace") for m in t.getmembers() if m.isfile())
            elif f.suffix == ".gz":
                text = gzip.decompress(f.read_bytes()).decode("utf-8", "replace")
            else:
                text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError, tarfile.TarError):
            continue
        if f.name == "verify_artifacts.py":
            continue
        if pat.search(text):
            leaks.append(str(f.relative_to(HERE)))
    check("privacy: no /mnt/, /home/ or host name in packet files", not leaks, ", ".join(leaks[:5]))

    if args.repo:
        r = subprocess.run(["bash", str(HERE / "orig_manifest.sh"), args.repo, str(HERE)], capture_output=True, text=True)
        check("orig/ blob-identical to accepted packets", r.returncode == 0 and r.stdout.count("\tyes") == 90)

        def ctime(path: str) -> datetime:
            out = subprocess.run(["git", "-C", args.repo, "log", "--diff-filter=A", "--format=%cI", "exp/fresh-07-main-9a2b1d99e-20261003",
                                  "--", f"docs/experiments/{HERE.name}/{path}"], capture_output=True, text=True).stdout.split()
            return utc(out[-1]) if out else datetime.max.replace(tzinfo=None)
        probe_start = utc(jl(HERE / "raw/probe/probe.jsonl")[0]["start_wall"])
        check("PREREG committed before the counted probe", ctime("PREREG.json") < probe_start)
        man = json.loads((HERE / "p2/r2-10r/raw/phase0/d-smoke-R-manifest.json").read_text())
        check("PREREG-P2 committed before the first Phase 2 smoke", ctime("PREREG-P2.json") < utc(man["started_utc"]))

    print(json.dumps({"ok": len(OK), "bad": BAD, "checks": OK}, indent=1))
    return 0 if not BAD else 1


if __name__ == "__main__":
    sys.exit(main())
