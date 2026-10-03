#!/usr/bin/env python3
"""Clean-checkout audit of published experiment packets (standard library only; run under bin/hostless).

For each packet head listed in packets.json (set "pushed": the heads published on the kvnloo/cua fork;
set "repairs": the r1b repair heads):
  1. head: the SHA recorded at publication vs the head read from `git ls-remote origin` (pushed set);
  2. clean checkout: `git clone --shared --no-checkout <main-clone>`, then the head checked out on a
     branch of the published name (nothing from any lane worktree is used);
  3. the packet's verify_artifacts.py, run from the packet directory of that clone, with the flags the
     packet documents (--git <clone>, --git-range <base>..HEAD, --ledger, --host) where it supports them;
  4. cited files: ../_template/verify_helper.py over the whole README and the headline JSON;
  5. privacy over every commit base..head (base = merge-base with upstream main at planning): every added
     or modified blob (decompressed .gz and .tar.gz members), path names, commit messages, identities.
Machine-specific strings (main clone, work dir, local roots, home, host) are read at run time, never
stored here; verifier output is scrubbed with them before it is written under raw/.

usage:
  audit_packets.py run --set pushed|repairs --main-clone <repo> --work <dir> --raw <packet>/raw
                       [--ls-remote <file>] [--ledger <file>] [--local-root <dir> ...] [--only ID,...]
  audit_packets.py assemble --raw <packet>/raw --out <packet>/audit.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_template"))
from verify_helper import check_cited  # noqa: E402

PACKETS = json.loads((HERE / "packets.json").read_text())
UPSTREAM_MAIN = PACKETS["upstream_main_at_planning"]
GENERIC = {"", "mnt", "home", "tmp", "github", "cua", "media", "srv", "opt", "var", "usr", "root"}
PUBLIC_ABS = ("/home/runner",)  # GitHub Actions runner home, public
GENERIC_TMP = {"/tmp/.X11-unix", "/tmp/.ICE-unix"}  # standard X11/ICE socket directories
# informational categories: public or standard locations, never counted as a privacy finding
INFO = {"public_ci_path", "generic_runtime_dir", "generic_tmp_dir"}
SECRET = {
    "openai_like": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}"),
    "aws_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "bearer": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{24,}"),
    "assigned_key": re.compile(r"(?i)(?:api[_-]?key|secret|passw(?:or)?d|access[_-]?token)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_./+-]{20,}[\"']"),
}
ABS = re.compile(r"(?<![\w<>.-])/(?:home|mnt|root|Users|media|run/user)/[\w.-]+")
TMP = re.compile(r"(?<![\w<>.-])/tmp/[\w.-]+")
PASS_LINE = re.compile(r"^\s*(?:\[\s*(?:PASS|ok|OK)\s*\]|PASS\b|ok\b|OK\b)")
FAIL_LINE = re.compile(r"^\s*(?:\[\s*(?:FAIL|fail)\s*\]|FAIL(?:ED)?\b|not ok\b)")


def sh(*cmd: str, cwd: Path | None = None, check: bool = True) -> str:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check).stdout


def git(repo: Path, *args: str, check: bool = True) -> str:
    return sh("git", "-C", str(repo), *args, check=check)


class Machine:
    """Run-time machine strings: used to scrub output and to find leaks, never written out."""

    def __init__(self, roots: list[Path]):
        host = socket.gethostname()
        self.pairs: list[tuple[str, str]] = []
        for i, r in enumerate(roots):
            self.pairs.append((str(r), f"<local-root-{i}>"))
        self.pairs += [(str(Path.home()), "<home>"), (host, "<host>")]
        self.pairs.sort(key=lambda kv: -len(kv[0]))
        names = {p for r in roots for p in Path(r).parts[1:] if len(p) >= 6} - GENERIC
        self.host = re.compile(r"(?i)(?<![\w-])(?:%s)(?![\w-])" % "|".join(
            re.escape(h) for h in {host, host.split(".")[0]} if h))
        self.home = re.compile(re.escape(str(Path.home())))
        self.local = re.compile("|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))) if names else None
        self.local_prefixes = tuple(str(r) for r in roots)

    def scrub(self, text: str) -> str:
        for old, new in self.pairs:
            text = text.replace(old, new)
        return text

    def hits(self, text: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for m in ABS.finditer(text):
            v = m.group(0)
            key = ("user_home" if self.home.match(v) else "local_root" if v.startswith(self.local_prefixes)
                   else "public_ci_path" if v.startswith(PUBLIC_ABS)
                   else "generic_runtime_dir" if re.fullmatch(r"/run/user/\d+", v) else "abs_path")
            out[key] = out.get(key, 0) + 1
        for m in TMP.finditer(text):
            key = "generic_tmp_dir" if m.group(0) in GENERIC_TMP else "tmp_path"
            out[key] = out.get(key, 0) + 1
        n = len(self.host.findall(text))
        if n:
            out["host_name"] = n
        if self.local:
            n = len(self.local.findall(text))
            if n:
                out["local_dir_name"] = n
        for name, pat in SECRET.items():
            n = len(pat.findall(text))
            if n:
                out[f"secret:{name}"] = n
        return out


def blob_texts(path: str, data: bytes):
    """(member, text) pairs: the blob itself, or the members of a .gz / .tar.gz."""
    try:
        if path.endswith((".tar.gz", ".tgz")):
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                for m in tar.getmembers():
                    if m.isfile():
                        yield m.name, tar.extractfile(m).read().decode("utf-8", "replace")
                    yield m.name + "#name", m.name
            return
        if path.endswith(".gz"):
            data = gzip.decompress(data)
    except (OSError, tarfile.TarError, EOFError):
        pass
    yield "", data.decode("utf-8", "replace")


SEVERE = ("user_home", "local_root", "abs_path", "host_name")


def privacy(repo: Path, head: str, mach: Machine, cache: dict) -> dict:
    base = git(repo, "merge-base", head, UPSTREAM_MAIN).strip()
    commits = git(repo, "rev-list", "--reverse", f"{base}..{head}").split()
    findings, idents = [], set()
    for c in commits:
        meta = git(repo, "log", "-1", "--format=%an <%ae>%x00%cn <%ce>%x00%B", c).split("\0", 2)
        idents.update(meta[:2])
        for k, n in mach.hits(meta[2]).items():
            findings.append({"commit": c[:12], "path": "<commit message>", "category": k, "count": n})
        raw = git(repo, "diff-tree", "-r", "-z", "--no-commit-id", "--no-renames", "--diff-filter=AM", c)
        parts = raw.split("\0")
        for meta_s, path in zip(parts[0::2], parts[1::2]):
            if not meta_s:
                continue
            sha = meta_s.split()[3]
            for k, n in mach.hits(path).items():
                findings.append({"commit": c[:12], "path": path + "#name", "category": k, "count": n})
            if (sha, path) not in cache:
                data = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", sha], capture_output=True).stdout
                hits: dict[str, dict[str, int]] = {}
                for member, text in blob_texts(path, data):
                    h = mach.hits(text)
                    if h:
                        hits[member] = h
                cache[(sha, path)] = hits
            for member, h in cache[(sha, path)].items():
                for k, n in h.items():
                    findings.append({"commit": c[:12], "path": path + (f"!{member}" if member else ""), "category": k, "count": n})
    return {"base": base, "commits_scanned": len(commits), "commits": [c[:12] for c in commits],
            "identities": sorted(idents), "findings": findings,
            "severe_findings": sum(1 for f in findings if f["category"] in SEVERE or f["category"].startswith("secret:"))}


def verifier_args(text: str, clone: Path, base: str, ledger: str | None) -> tuple[list[str], list[str]]:
    """(real args, recorded args) for the flags this verifier documents."""
    real, shown = [], []
    if re.search(r"[\"']--git[\"']", text):
        real += ["--git", str(clone)]; shown += ["--git", "<clone>"]
    if re.search(r"[\"']--git-range[\"']", text):
        real += ["--git-range", f"{base}..HEAD"]; shown += ["--git-range", f"{base[:12]}..HEAD"]
    if ledger and re.search(r"[\"']--ledger[\"']", text):
        real += ["--ledger", ledger]; shown += ["--ledger", "<quiet-lane-ledger>"]
    if re.search(r"[\"']--host[\"']", text):
        real += ["--host", socket.gethostname()]; shown += ["--host", "<host>"]
    return real, shown


def audit_one(entry: dict, args, mach: Machine, remote: dict, cache: dict) -> dict:
    pid, branch, head, pdir = entry["id"], entry["branch"], entry["head"], entry["packet_dir"]
    work = Path(args.work)
    clone = work / f"clone-{args.set}-{pid}"
    shutil.rmtree(clone, ignore_errors=True)
    rec: dict = {"id": pid, "branch": branch, "head": head, "packet_dir": pdir}
    if args.set == "pushed":
        rec["state_sha"] = entry["head"]
        rec["origin_sha"] = remote.get(f"refs/heads/{branch}")
        rec["head_confirmed"] = rec["origin_sha"] == head
    else:
        rec["base_pushed_head"] = entry.get("base")
    sh("git", "clone", "-q", "--shared", "--no-checkout", args.main_clone, str(clone))
    git(clone, "checkout", "-q", "-B", branch, head)
    rec["checked_out"] = git(clone, "rev-parse", "HEAD").strip()
    pkt = clone / pdir
    vf = pkt / "verify_artifacts.py"
    base = git(clone, "merge-base", "HEAD", UPSTREAM_MAIN).strip()
    if not vf.is_file():
        rec["verifier"] = {"present": False, "passed": False}
    else:
        text = vf.read_text()
        real, shown = verifier_args(text, clone, base, args.ledger)
        tmp = work / f"tmp-{args.set}-{pid}"
        shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
        env = {**os.environ, "TMPDIR": str(tmp), "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_COLORS": "0", "NO_COLOR": "1"}
        t0 = time.monotonic()
        try:
            p = subprocess.run([sys.executable, "verify_artifacts.py", *real], cwd=pkt, env=env,
                               capture_output=True, text=True, timeout=args.timeout)
            rc, out = p.returncode, p.stdout + p.stderr
        except subprocess.TimeoutExpired as e:
            rc, out = "timeout", (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        secs = round(time.monotonic() - t0, 1)
        out = mach.scrub(out.replace(str(clone), "<clone>").replace(str(work), "<work>"))
        lines = [ln for ln in out.splitlines() if ln.strip()]
        outfile = Path(args.raw) / "verifier-output" / args.set / f"{pid}.txt"
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(out)
        rec["verifier"] = {
            "present": True, "args": shown, "rc": rc, "passed": rc == 0, "seconds": secs,
            "sha256": hashlib.sha256(vf.read_bytes()).hexdigest(),
            "blob": git(clone, "rev-parse", f"HEAD:{pdir}/verify_artifacts.py").strip(),
            "pass_lines": sum(bool(PASS_LINE.match(ln)) for ln in lines),
            "fail_lines": sum(bool(FAIL_LINE.match(ln)) for ln in lines),
            "last_line": lines[-1][:300] if lines else "",
            "output": "raw/" + outfile.relative_to(Path(args.raw)).as_posix(),
            "output_sha256": hashlib.sha256(out.encode()).hexdigest(),
            "output_privacy_hits": mach.hits(out),
        }
    rec["cited_not_tracked"] = check_cited(pkt, "all")
    rec["cited_ignored"] = sum(f["kind"] == "ignored" for f in rec["cited_not_tracked"])
    rec["privacy"] = privacy(clone, head, mach, cache)
    rec["packet_files_tracked"] = len(git(clone, "ls-files", "--", pdir).splitlines())
    shutil.rmtree(clone, ignore_errors=True)
    shutil.rmtree(work / f"tmp-{args.set}-{pid}", ignore_errors=True)
    return rec


def run(args) -> None:
    roots = [Path(args.main_clone).resolve(), Path(args.work).resolve().parent, *[Path(r).resolve() for r in args.local_root]]
    mach = Machine(roots)
    remote = {}
    if args.ls_remote:
        for line in Path(args.ls_remote).read_text().splitlines():
            sha, _, ref = line.partition("\t")
            remote[ref.strip()] = sha.strip()
    entries = PACKETS[args.set]
    if args.only:
        entries = [e for e in entries if e["id"] in args.only.split(",")]
    out_path = Path(args.raw) / f"audit-{args.set}.json"
    prev = json.loads(out_path.read_text()) if out_path.is_file() and args.only else {"results": []}
    done = {r["id"]: r for r in prev["results"]}
    cache: dict = {}
    for e in entries:
        t0 = time.monotonic()
        rec = audit_one(e, args, mach, remote, cache)
        done[e["id"]] = rec
        v = rec["verifier"]
        print(f"{e['id']:8} verifier rc={v.get('rc')} {v.get('seconds')}s cited_ignored={rec['cited_ignored']} "
              f"cited_untracked={len(rec['cited_not_tracked']) - rec['cited_ignored']} "
              f"privacy_commits={rec['privacy']['commits_scanned']} severe={rec['privacy']['severe_findings']} "
              f"({time.monotonic() - t0:.0f}s)", flush=True)
    order = [e["id"] for e in PACKETS[args.set]]
    doc = {
        "schema": "packet-audit-run-v1", "set": args.set,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {"wrapper": "bin/hostless" if os.environ.get("CUA_HOSTLESS") == "1" else "NOT hostless",
                        "python": platform.python_version(), "git": sh("git", "--version").strip(),
                        "os": f"{platform.system()} {platform.release()}"},
        "upstream_main_at_planning": UPSTREAM_MAIN,
        "results": [done[i] for i in order if i in done],
    }
    out_path.write_text(json.dumps(doc, indent=1) + "\n")


def readme_row(r: dict) -> str:
    """The README table row for one audited head (verify_artifacts.py requires each row verbatim)."""
    v = r["verifier"]
    return (f"| {r['id']} | `{r['branch']}` | `{r['head'][:12]}` | {'PASS' if v['passed'] else 'FAIL'} (rc {v['rc']}) | "
            f"{' '.join(v['args']) or '-'} | {r['cited_ignored']} | {r['privacy']['commits_scanned']} | "
            f"{r['privacy']['severe_findings']} |")


def assemble(args) -> None:
    raw = Path(args.raw)
    pushed = json.loads((raw / "audit-pushed.json").read_text())
    repairs = json.loads((raw / "audit-repairs.json").read_text())
    fixes = json.loads((HERE / "publish-fixes-status.json").read_text())
    new_commits = {c for r in repairs["results"] for c in r["privacy"]["commits"]} - {
        c for r in pushed["results"] for c in r["privacy"]["commits"]}
    new_findings = [dict(f, id=r["id"]) for r in repairs["results"] for f in r["privacy"]["findings"]
                    if f["commit"] in new_commits and f["category"] not in INFO]
    failing = [r["id"] for r in pushed["results"] if not r["verifier"]["passed"]]
    ignored = {r["id"]: [f["path"] for f in r["cited_not_tracked"] if f["kind"] == "ignored"]
               for r in pushed["results"] if r["cited_ignored"]}
    gates = {
        "every_repaired_head_verifier_passes_from_clean_clone": all(r["verifier"]["passed"] for r in repairs["results"]),
        "audit_covers_every_pushed_packet": [r["id"] for r in pushed["results"]] == [e["id"] for e in PACKETS["pushed"]]
        and all(r["head_confirmed"] for r in pushed["results"]),
        "zero_privacy_findings_on_new_commits": not new_findings,
        "every_failing_pushed_packet_has_a_repair": set(failing) <= {r["id"] for r in repairs["results"]},
    }
    doc = {
        "schema": "packet-audit-v1",
        "claim_boundary": PACKETS["claim_boundary"],
        "upstream_main_at_planning": UPSTREAM_MAIN,
        "environment": {"pushed": pushed["environment"], "repairs": repairs["environment"]},
        "run_utc": {"pushed": pushed["utc"], "repairs": repairs["utc"]},
        "summary": {
            "pushed_packets": len(pushed["results"]),
            "pushed_verifier_pass": sum(r["verifier"]["passed"] for r in pushed["results"]),
            "pushed_verifier_fail": failing,
            "pushed_cited_ignored": ignored,
            "repairs": {r["id"]: {"branch": r["branch"], "head": r["head"], "verifier_passed": r["verifier"]["passed"],
                                  "cited_ignored": r["cited_ignored"]} for r in repairs["results"]},
            "new_commits": sorted(new_commits),
            "new_commit_privacy_findings": new_findings,
        },
        "gates": gates,
        "publish_fixes": fixes,
        "pushed": pushed["results"],
        "repairs": repairs["results"],
    }
    Path(args.out).write_text(json.dumps(doc, indent=1) + "\n")
    print(json.dumps({"summary": {k: v for k, v in doc["summary"].items() if k != "new_commit_privacy_findings"},
                      "gates": gates}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--set", choices=("pushed", "repairs"), required=True)
    r.add_argument("--main-clone", required=True)
    r.add_argument("--work", required=True)
    r.add_argument("--raw", required=True)
    r.add_argument("--ls-remote")
    r.add_argument("--ledger")
    r.add_argument("--local-root", action="append", default=[])
    r.add_argument("--only")
    r.add_argument("--timeout", type=int, default=1800)
    a = sub.add_parser("assemble")
    a.add_argument("--raw", required=True)
    a.add_argument("--out", required=True)
    args = ap.parse_args()
    run(args) if args.cmd == "run" else assemble(args)


if __name__ == "__main__":
    main()
