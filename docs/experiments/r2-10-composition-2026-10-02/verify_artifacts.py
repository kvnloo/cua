#!/usr/bin/env python3
"""R2-10 packet verifier (standard library only).

1. Recomputes the whole summary from raw/ with analyze_r2_10.analyze and requires it to equal the
   committed r2-10-summary.json (seeded bootstrap: deterministic).
2. Requires every headline number in headline-numbers.json to equal its recomputed value and to
   appear verbatim in README.md.
3. Privacy-scans EVERY commit of the branch (base..HEAD, merges included): every added/modified
   blob (tar.gz/gz members included), every path name, commit message and author/committer
   identity: no absolute home or mount paths, no lane/host names, no secret-like values.
   Private names are never committed, not even encoded: they come from the untracked file named
   by CUA_PRIVACY_NAMES_FILE plus the verifying host's own name (whole-token match). Hex runs
   (even length >= 8) and base64 runs (>= 12 chars, valid padding) are decoded and scanned too,
   and a committed list of encoded name-like strings fails (PUB-02 rewrite).
4. Publication addendum (r1b, 2026-10-03): recomputes native S on T_land next to S on T_oracle, the
   browser T_land ratio of arm medians, the fill COMP_K amortized ratio of means; checks the browser
   Driver attribution (wall_ns on every R trace line, never on U), provenance-addendum.json against
   provenance.json, the force-added raw/logs against raw/force-added-logs.sha256, and the Deviation 2
   nw2gate disclosure. Every number is recomputed from raw/ and must appear in README.md.

usage: verify_artifacts.py [--base 989cc76cec262ff8bcf6968b637820340fb9caaa] [--skip-git]
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_r2_10 as A  # noqa: E402

BASE = "989cc76cec262ff8bcf6968b637820340fb9caaa"
# Generic path patterns first (private#0-2 stay stable for ALLOW); private names follow. They are read at
# verify time and never stored in the repository, not even encoded (PUB-02 rewrite of an encoded list).
GENERIC = [re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"), re.compile(r"/Users/[A-Za-z0-9_.-]+/")]


def _private_names() -> tuple[list[str], str]:
    names = {socket.gethostname()} - {"", "localhost"}
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if src and Path(src).is_file():
        names |= {x.strip() for x in Path(src).read_text().splitlines() if x.strip() and not x.startswith("#")}
        return sorted(names), f"private names: {len(names)} (CUA_PRIVACY_NAMES_FILE + host name)"
    return sorted(names), "private names: CUA_PRIVACY_NAMES_FILE not set; the name sub-check covers the host name only"


NAMES, NAMES_NOTE = _private_names()
# whole-token match: a short local user name can be a prefix of a public handle
PRIVATE = GENERIC + [re.compile(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])") for n in NAMES]
HEXRUN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){4,}(?![0-9A-Fa-f])")
B64RUN = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{12,}={0,2}(?![A-Za-z0-9+/=])")
LITERAL = re.compile(r"[\"']([A-Za-z0-9+/]{8,}={0,2})[\"']")
NAMELIKE = re.compile(r"[A-Za-z][A-Za-z0-9._-]{2,62}")
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com"), ("kvnloo", "7121943+kvnloo@users.noreply.github.com")}
# Upstream content (trycua/cua PR 4316 head a0bca7440, brought in by the step-2 merge b10cd09f2), already
# public: a GitHub Actions runner path in the CI workflow and a placeholder key literal in a unit test
# (recorded as benign by the wave-1/2 publish scans). Matched by (commit, path, pattern); nothing else.
ALLOW = {
    ("a0bca7440", ".github/workflows/ci-jev-use.yml", "private#0"),
    ("b10cd09f2", ".github/workflows/ci-jev-use.yml", "private#0"),
    ("a0bca7440", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
    ("b10cd09f2", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
}
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, check=True).stdout


def texts_of_blob(path: str, data: bytes) -> list[tuple[str, str]]:
    # compressed bytes are not text (a short name can occur in them by chance): scan the members
    out = [] if path.endswith((".gz", ".tgz")) else [(path, data.decode("utf-8", errors="replace"))]
    if path.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for m in tar.getmembers():
                out.append((f"{path}:{m.name}", m.name))
                if m.isfile():
                    out.append((f"{path}:{m.name}", tar.extractfile(m).read().decode("utf-8", errors="replace")))
    elif path.endswith(".gz"):
        out.append((path + ":gunzip", gzip.decompress(data).decode("utf-8", errors="replace")))
    return out


def _b64(run: str) -> bytes | None:
    body = run.rstrip("=")
    if len(body) % 4 == 1 or (run != body and len(run) % 4):
        return None
    try:
        return base64.b64decode(body + "=" * (-len(body) % 4), validate=True)
    except ValueError:
        return None


def with_decoded(targets: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """targets plus the decoded text of every hex run and base64 run in them (decodings that are text)."""
    extra = []
    for where, text in targets:
        runs = [bytes.fromhex(r.group()) for r in HEXRUN.finditer(text)]
        runs += [b for r in B64RUN.finditer(text) if (b := _b64(r.group())) is not None]
        for b in runs:
            s = b.decode("utf-8", errors="replace")
            if s and sum(ch.isprintable() for ch in s) >= 0.9 * len(s):
                extra.append((where + ":decoded", s))
    return list(targets) + extra


def encoded_list(text: str) -> bool:
    """True when one text holds >= 2 quoted hex/base64 literals that each decode to a name-like token."""
    n = 0
    for r in LITERAL.finditer(text):
        run = r.group(1)
        if HEXRUN.fullmatch(run) and re.search(r"[A-Fa-f]", run):
            b = bytes.fromhex(run)
        else:
            b = _b64(run) if len(run) >= 12 else None
        n += b is not None and bool(NAMELIKE.fullmatch(b.decode("latin-1")))
    return n >= 2


def privacy_scan(base: str) -> None:
    commits = git("rev-list", f"{base}..HEAD").decode().split()
    hits: list[str] = []
    secret_hits: list[str] = []
    bad_ident: list[str] = []
    allowed: list[str] = []
    encoded_lists: list[str] = []
    blobs_scanned = 0
    for c in commits:
        meta = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", c).decode(errors="replace").split("\x00")
        if (meta[0], meta[1]) not in IDENTITY or (meta[2], meta[3]) not in IDENTITY:
            bad_ident.append(f"{c[:9]} {meta[0]} / {meta[2]}")
        targets = [("commit-message", meta[4])]
        parents = git("show", "-s", "--format=%P", c).decode().split()
        diff = git("diff-tree", "-r", "--no-commit-id", "--no-renames", parents[0] if parents else "--root", c).decode()
        for line in diff.splitlines():
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            fields, path = parts[0].split(), parts[1]
            targets.append(("path", path))
            if fields[4] == "D":
                continue
            data = git("cat-file", "blob", fields[3])
            blobs_scanned += 1
            targets.extend(texts_of_blob(path, data))
        encoded_lists += [f"{c[:9]} {w[:120]}" for w, t in targets if w != "path" and encoded_list(t)]
        for where, text in with_decoded(targets):
            for i, pat in enumerate(PRIVATE):
                if pat.search(text):
                    if (c[:9], where, f"private#{i}") in ALLOW:
                        allowed.append(f"{c[:9]} {where} private#{i}")
                    else:
                        hits.append(f"{c[:9]} {where[:120]} private#{i}")
            for i, pat in enumerate(SECRET):
                if pat.search(text):
                    if (c[:9], where, f"secret#{i}") in ALLOW:
                        allowed.append(f"{c[:9]} {where} secret#{i}")
                    else:
                        secret_hits.append(f"{c[:9]} {where[:120]} secret#{i}")
    check("privacy: no absolute local paths / lane or host names in any commit", not hits,
          f"{len(commits)} commits, {blobs_scanned} blobs; hits: {hits[:10]}")
    check("privacy: no secret-like values in any commit", not secret_hits, f"hits: {secret_hits[:10]}")
    check("privacy: no committed list of hex/base64-encoded name-like strings in any commit", not encoded_lists,
          f"hits: {encoded_lists[:10]}")
    print(NAMES_NOTE)
    check("privacy: author/committer identity", not bad_ident, f"bad: {bad_ident[:10]}")
    print(f"privacy allowlisted (upstream PR 4316 content): {sorted(set(allowed))}")


def walk(obj, path):  # noqa: ANN001, ANN201
    for key in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(key)]
        else:
            obj = obj[key]
    return obj


def s_text(st: dict) -> str:
    return f"{st['S']:.2f} [{st['ci95'][0]:.2f}, {st['ci95'][1]:.2f}]"


def trace_lines(bundle: Path) -> tuple[int, int, int]:
    """(trace files, trace lines, lines carrying wall_ns) in one trial bundle."""
    files = lines = wall = 0
    with tarfile.open(bundle, "r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile() and m.name.endswith(".driver-trace.jsonl"):
                files += 1
                for line in tar.extractfile(m).read().decode("utf-8", errors="replace").splitlines():
                    if line.strip():
                        lines += 1
                        wall += "wall_ns" in json.loads(line)
    return files, lines, wall


def verify_addendum(recomputed: dict, readme: str) -> None:
    """2026-10-03 publication repair: the numbers and records the README addendum cites."""
    flat = " ".join(readme.split())
    # native S on T_land, same paired statistic and seeded bootstrap as S on T_oracle
    raw = HERE / "raw"
    rows = [A.native_row(r) for p in sorted((raw / "native").glob("*/trials.jsonl*"))
            for r in A.read_jsonl(p) if r.get("event") == "trial"]
    main_rows = [{**r, "cls": r["task"]} for r in rows if r["kind"] == "main"]
    names = {"checkbox": "checkbox", "text": "text entry"}
    for arm in ("X", "S0"):
        land = A.pairs_by_round(main_rows, "BASE", arm, "T_land_ms")
        for task in A.TASKS:
            st = A.ratio_stat([(x[0], x[1]) for x in land.get(task, [])])
            orc = recomputed["native"]["S"][arm][task]["all"]
            row = (f"| native GTK3 | {names[task]}, {arm} | {s_text(orc)} | {s_text(st)} | "
                   f"{st['median_base_ms']:.1f} ms -> {st['median_arm_ms']:.1f} ms |")
            check(f"addendum T_land {task}/{arm}: {s_text(st)} next to T_oracle {s_text(orc)}",
                  row in readme and st["n"] == orc["n"] == 24, row)
    # browser COMP: ratio of arm medians of T_land, within 0.4% of S on T_oracle
    parts, close = [], True
    for layer in ("live", "scripted"):
        vals = []
        for cls in A.CLASSES:
            arms = recomputed["browser"][layer]["arms"][cls]
            v = arms["BASE"]["T_land_ms_median"] / arms["COMP"]["T_land_ms_median"]
            close &= abs(v / recomputed["browser"][layer]["S"]["COMP"][cls]["all"]["S"] - 1) < 0.004
            vals.append(f"{cls} {v:.2f}" if cls == "fill" else f"{cls} {v:.2f}")
        parts.append(f"{layer} " + ", ".join(vals))
    text = "; ".join(parts)
    check(f"addendum browser T_land ratio of arm medians: {text}", text in flat and close, text)
    # fill COMP_K amortized ratio of means next to the median S_COMP_K
    am = recomputed["browser"]["scripted"]["S"]["COMP_K"]["fill"]["amortized_mean_ratio"]
    check(f"addendum fill COMP_K amortized ratio of means {s_text(am)}",
          f"amortized ratio of means {s_text(am)}" in flat and am["n"] == 32, s_text(am))
    # browser Driver attribution: wall_ns on every measured/controls trace line, never on U, no smoke traces
    counts = {}
    for name in ("live", "scripted", "controls"):
        files, lines, wall = trace_lines(raw / "browser" / f"{name}-trials.tar.gz")
        counts[name] = files
        check(f"addendum attribution: {name} {files} trace files, wall_ns on {wall}/{lines} lines (R only)",
              files > 0 and lines > 0 and wall == lines, f"{wall}/{lines}")
    check("addendum attribution: trace-file counts cited (live 181, scripted 387, controls 46)",
          counts == {"live": 181, "scripted": 387, "controls": 46}
          and "live 181, scripted 387, controls 46" in flat, json.dumps(counts))
    files, lines, wall = trace_lines(raw / "phase0" / "c-nw2-U-trials.tar.gz")
    check("addendum attribution control: U traces never carry wall_ns (discriminating)",
          files > 0 and lines > 0 and wall == 0, f"{wall}/{lines}")
    smoke = [trace_lines(raw / "phase0" / f"d-smoke-{x}-trials.tar.gz")[0] for x in ("R", "C")]
    check("addendum attribution: Phase 0 (d) smoke bundles carry no trace file", smoke == [0, 0], str(smoke))
    add = json.loads((HERE / "provenance-addendum.json").read_text())
    prov = json.loads((HERE / "provenance.json").read_text())
    check("addendum binaries == provenance.json binaries R and Cn",
          add["binaries"] == {k: prov["binaries"][k] for k in ("R", "Cn")})
    mapping = {m: e["binary"] for m, e in add["browser_driver_per_manifest"].items()}
    named = all(e["name"] == prov["binaries"][e["binary"]]["name"] and e["sha256"] == prov["binaries"][e["binary"]]["sha256"]
                and e["sha256"] in readme for e in add["browser_driver_per_manifest"].values())
    manifests = sorted(str(p.relative_to(HERE)) for p in (raw / "browser").glob("*-manifests/*.json"))
    check("addendum maps every browser manifest to R, smoke R/C to R/Cn (name + sha256 == provenance.json), each named in README",
          all(mapping.get(m) == "R" for m in manifests) and len(manifests) == 5 and named
          and mapping.get("raw/phase0/d-smoke-R-manifest.json") == "R"
          and mapping.get("raw/phase0/d-smoke-C-manifest.json") == "Cn"
          and all((HERE / m).is_file() and Path(m).name in readme for m in mapping), json.dumps(mapping))
    check("addendum live_heads_at_publication is a publication-time field (filled by Publish)",
          set(add["live_heads_at_publication"]) >= {"filled_by", "utc", "upstream_main", "trycua_cua_pr_4316"})
    # force-added chunk logs: every raw/logs/*.log listed with its committed sha256
    listed = {}
    for line in (raw / "force-added-logs.sha256").read_text().splitlines():
        digest, path = line.split(None, 1)
        listed[path.strip()] = digest
    logs = sorted(str(p.relative_to(HERE)) for p in (raw / "logs").glob("*.log"))
    ok = sorted(listed) == logs and all(
        hashlib.sha256((HERE / p).read_bytes()).hexdigest() == listed[p] for p in logs)
    check(f"addendum raw/logs: {len(logs)} chunk logs present, sha256 == raw/force-added-logs.sha256",
          ok and len(logs) == 28, f"{len(logs)} logs, {len(listed)} listed")
    # Deviation 2 discloses the post-PREREG nw2gate plan kind
    harness = (HERE / "harness" / "r2_10_browser.py").read_text()
    check("addendum Deviation 2 discloses the post-PREREG nw2gate plan kind",
          'kind == "nw2gate"' in harness and "`nw2gate`" in readme and "2cedaa9a4" in readme)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=BASE)
    p.add_argument("--skip-git", action="store_true")
    args = p.parse_args()
    summary_path = HERE / "r2-10-summary.json"
    recomputed = json.loads(json.dumps(A.analyze(HERE / "raw"), sort_keys=True, default=str))
    committed = json.loads(summary_path.read_text())
    check("summary recomputes identically from raw/", recomputed == committed,
          "" if recomputed == committed else "differs")
    readme = (HERE / "README.md").read_text()
    heads = json.loads((HERE / "headline-numbers.json").read_text())
    for h in heads["numbers"]:
        val = walk(recomputed, h["path"])
        shown = h["format"].format(val) if not isinstance(val, list) else h["format"].format(*val)
        check(f"headline {h['id']} = {shown}", shown == h["text"] and h["text"] in readme,
              f"recomputed {shown!r}, listed {h['text']!r}, in README {h['text'] in readme}")
    verify_addendum(recomputed, readme)
    for f in sorted((HERE / "raw").rglob("*")):
        if f.is_file():
            for where, text in with_decoded(texts_of_blob(str(f.relative_to(HERE)), f.read_bytes())):
                if any(pat.search(text) for pat in PRIVATE):
                    check(f"raw privacy {where[:100]}", False, "private string in raw file")
    if not args.skip_git:
        privacy_scan(args.base)
    bad = [c for c in CHECKS if not c[1]]
    for name, ok, detail in CHECKS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"{len(CHECKS) - len(bad)}/{len(CHECKS)} checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
