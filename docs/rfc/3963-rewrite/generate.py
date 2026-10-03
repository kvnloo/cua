#!/usr/bin/env python3
"""Generate the disposition rows of the trycua/cua issue 3963 rewrite draft (stdlib only).

Inputs
  rows.spec.json   one hand-maintained record per row: the STATE locator, the claim template
                   and a pointer for every number in it (packet file + line, or packet JSON
                   path, or STATE path). Templates hold no bare numbers.
  STATE.json       the loop state (passed with --state). Branch and commit of every row come
                   from STATE, never from the spec; the budget numbers come from
                   STATE.provider_budget.
  git objects      every packet file is read with `git show <sha>:<path>` at the row's SHA.

Outputs (rewritten in place unless --check)
  dispositions.json           rendered rows, each number with its resolved pointer
  claims.json                 entries with "generated": true are replaced; curated entries kept
  README.md                   the block between the dispositions-table markers, the head-notes
                              block and every <!-- gen:NAME --> block
  PENDING.md                  the block between the moving-rows markers
  provenance.json             sha_refs (where every backticked SHA can be fetched from) and the
                              STATE hash it was generated from

Run under the loop's hostless wrapper, from the repository root:

    python3 docs/rfc/3963-rewrite/generate.py --state <loop STATE.json>
    python3 docs/rfc/3963-rewrite/generate.py --state <loop STATE.json> --check

--check exits 1 when a regeneration from the given STATE would change any generated content
(verify_artifacts.py --state runs the same comparison).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = "rows.spec.json"
TABLE_START = "<!-- dispositions-table:start -->"
TABLE_END = "<!-- dispositions-table:end -->"
NOTES_START = "<!-- head-notes:start -->"
NOTES_END = "<!-- head-notes:end -->"
MOVING_START = "<!-- moving-rows:start -->"
MOVING_END = "<!-- moving-rows:end -->"
GEN_BLOCK = re.compile(r"(<!-- gen:([a-z0-9-]+) -->)(.*?)(<!-- /gen:\2 -->)", re.S)
PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_.]+)\}")
TABLE_HEAD = ("| ID | Disposition | Class | Branch @ SHA | Packet | Claim boundary | Blocker | Pending |\n"
              "|---|---|---|---|---|---|---|---|")


class GenError(Exception):
    pass


# ---------------------------------------------------------------- git helpers
class Repo:
    def __init__(self, path: Path):
        self.path = path
        self._show: dict[tuple[str, str], str | None] = {}
        self._full: dict[str, str | None] = {}
        self._anc: dict[tuple[str, str], bool] = {}

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.path), *args], capture_output=True, text=True)

    def full(self, sha: str) -> str | None:
        if sha not in self._full:
            p = self.git("rev-parse", "--verify", "-q", sha + "^{commit}")
            self._full[sha] = p.stdout.strip() if p.returncode == 0 else None
        return self._full[sha]

    def show(self, sha: str, path: str) -> str | None:
        key = (sha, path)
        if key not in self._show:
            p = subprocess.run(["git", "-C", str(self.path), "show", "%s:%s" % key], capture_output=True)
            self._show[key] = p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None
        return self._show[key]

    def is_ancestor(self, a: str, b: str) -> bool:
        key = (a, b)
        if key not in self._anc:
            self._anc[key] = self.git("merge-base", "--is-ancestor", a, b).returncode == 0
        return self._anc[key]


# ---------------------------------------------------------------- formatting
def fmt_value(v, fmt: str) -> str:
    if fmt in ("raw", "text"):
        return v if isinstance(v, str) else json.dumps(v)
    if fmt == "int":
        return "%d" % v
    m = re.fullmatch(r"f(\d)", fmt)
    if m:
        return "%.*f" % (int(m.group(1)), v)
    m = re.fullmatch(r"pct(\d)", fmt)
    if m:
        return "%.*f%%" % (int(m.group(1)), v * 100)
    m = re.fullmatch(r"ci(\d)", fmt)
    if m:
        d = int(m.group(1))
        return "[%.*f, %.*f]" % (d, v[0], d, v[1])
    m = re.fullmatch(r"sci(\d)", fmt)  # signed CI: [-1.4, +0.5]
    if m:
        d = int(m.group(1))
        return "[%+.*f, %+.*f]" % (d, v[0], d, v[1])
    raise GenError("unknown format %r" % fmt)


def json_get(obj, path):
    for part in path:
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


def dotted(state: dict, path: str):
    obj = state
    for part in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


# ---------------------------------------------------------------- heads
def split_branch(b: str) -> str:
    return b.split(" (")[0].strip()


def state_head(state: dict, key: str | None):
    node = state.get("dispositions", {}).get(key) if key else None
    if not isinstance(node, dict):
        return None, None
    commit = node.get("commit")
    m = re.match(r"[0-9a-f]{7,40}", commit or "")
    return (split_branch(node["branch"]) if node.get("branch") else None), (m.group(0) if m else None)


def resolve_head(repo: Repo, state: dict, spec_row: dict):
    """Branch and SHA for a row, always read from STATE. Returns (branch, sha, note)."""
    head = spec_row.get("head", "state")
    if head is None:
        return None, None, None
    sb, sc = state_head(state, spec_row.get("state_key"))
    if head == "state":
        branch, commit, src = sb, sc, "STATE.dispositions.%s" % spec_row.get("state_key")
    elif "state_key" in head:
        branch, commit = state_head(state, head["state_key"])
        src = "STATE.dispositions.%s" % head["state_key"]
    elif "wave" in head:
        waves = [w for w in state.get("waves", []) if w.get("wave") == head["wave"]]
        if not waves:
            raise GenError("%s: STATE has no wave %s" % (spec_row["id"], head["wave"]))
        text = waves[0]["branches"][head["branches_key"]]
        branch, commit = [x.strip() for x in text.split(" @ ")]
        src = "STATE.waves[wave=%s].branches[%r]" % (head["wave"], head["branches_key"])
    else:
        raise GenError("%s: unknown head form %r" % (spec_row["id"], head))
    if not branch or not commit:
        raise GenError("%s: %s has no branch/commit" % (spec_row["id"], src))
    full = repo.full(commit)
    if not full:
        raise GenError("%s: commit %s from %s does not resolve" % (spec_row["id"], commit, src))
    note = None
    sfull = repo.full(sc) if sc else None
    if head != "state" and (sb != branch or sfull != full):
        reason = spec_row.get("head_reason")
        if not reason:
            raise GenError("%s: head differs from STATE.dispositions.%s and has no head_reason" % (
                spec_row["id"], spec_row.get("state_key")))
        note = {"row": spec_row["id"], "cited": "%s @ %s" % (branch, full[:9]), "source": src,
                "state_row_head": ("%s @ %s" % (sb, (sfull or sc)[:9])) if (sfull or sc) else "%s (no commit)" % (sb or "no branch"),
                "reason": reason}
    return branch, full, note


# ---------------------------------------------------------------- numbers
def resolve_num(repo: Repo, state: dict, rows_by_id: dict, row_id: str, name: str, src: dict) -> dict:
    kind = src["src"]
    where = "%s.%s" % (row_id, name)
    if kind in ("line", "json"):
        owner = rows_by_id[src.get("of", row_id)]
        sha, packet = owner["sha"], owner["packet"]
        if not (sha and packet):
            raise GenError("%s: row %s has no packet" % (where, owner["id"]))
        path = packet.rstrip("/") + "/" + src.get("file", "README.md")
        body = repo.show(sha, path)
        if body is None:
            raise GenError("%s: %s unreadable at %s" % (where, path, sha[:9]))
        if kind == "line":
            ctx, text = src["context"], src["text"]
            if text not in ctx:
                raise GenError("%s: text %r not inside context %r" % (where, text, ctx))
            hits = [i for i, ln in enumerate(body.splitlines(), 1) if ctx in ln]
            if len(hits) != 1:
                raise GenError("%s: context %r found on %d lines of %s (needs exactly 1)" % (where, ctx, len(hits), path))
            return {"kind": "packet_line", "sha": sha, "path": path, "line": hits[0], "context": ctx, "text": text}
        data = json.loads(body)
        try:
            val = json_get(data, src["path"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise GenError("%s: JSON path %s missing in %s" % (where, src["path"], path))
        fmt = src.get("fmt", "raw")
        return {"kind": "packet_json", "sha": sha, "path": path, "json_path": src["path"], "fmt": fmt,
                "value": val, "text": fmt_value(val, fmt)}
    if kind == "state":
        val = dotted(state, src["path"])
        fmt = src.get("fmt", "raw")
        return {"kind": "state", "json_path": src["path"], "fmt": fmt, "value": val, "text": fmt_value(val, fmt)}
    if kind == "state_text":
        val = dotted(state, src["path"])
        if isinstance(val, list):
            val = " | ".join(str(x) for x in val)
        ctx, text = src["context"], src["text"]
        if ctx not in str(val) or text not in ctx:
            raise GenError("%s: STATE %s does not contain %r (or text not in context)" % (where, src["path"], ctx))
        return {"kind": "state_text", "json_path": src["path"], "context": ctx, "text": text}
    raise GenError("%s: unknown number source %r" % (where, kind))


def render(template: str | None, nums: dict, where: str) -> str | None:
    if template is None:
        return None

    def sub(m):
        if m.group(1) not in nums:
            raise GenError("%s: placeholder {%s} has no pointer" % (where, m.group(1)))
        return nums[m.group(1)]["text"]
    return PLACEHOLDER.sub(sub, template)


# ---------------------------------------------------------------- build
def budget_nums(state: dict) -> dict:
    b = state["provider_budget"]
    out = {}
    for name, path in (("budget.used", "provider_budget.used_requests_reached_provider"),
                       ("budget.cap", "provider_budget.cap_requests"),
                       ("budget.remaining", "provider_budget.remaining_reached"),
                       ("budget.attempts", "provider_budget.used_attempts")):
        val = dotted(state, path)
        out[name] = {"kind": "state", "json_path": path, "fmt": "int", "value": val, "text": "%d" % val}
    if b["used_requests_reached_provider"] + b["remaining_reached"] != b["cap_requests"]:
        raise GenError("STATE.provider_budget does not add up (used + remaining != cap)")
    return out


def cell(s) -> str:
    return "" if s is None else str(s).replace("|", "/")


def build(repo: Repo, state: dict, spec: dict) -> dict:
    rows_out, claims, notes = [], [], []
    by_id: dict[str, dict] = {}
    gnums = budget_nums(state)
    # pass 1: heads
    for s in spec["rows"]:
        branch, sha, note = resolve_head(repo, state, s)
        r = {"id": s["id"], "kind": s["kind"], "disposition": s["disposition"], "class": s["class"],
             "branch": branch, "sha": sha, "packet": s.get("packet") if sha else None,
             "owner": s["owner"]}
        if s.get("packet") and not sha:
            raise GenError("%s: packet without a head" % s["id"])
        if note:
            notes.append(note)
            r["head_note"] = note["reason"]
        by_id[s["id"]] = r
        rows_out.append((s, r))
    # pass 2: numbers and text
    errors = []
    for s, r in rows_out:
        nums = dict(gnums)
        for name, src in s.get("nums", {}).items():
            try:
                nums[name] = resolve_num(repo, state, by_id, s["id"], name, src)
            except GenError as e:
                errors.append(str(e))
        if errors:
            continue
        r["blocker"] = render(s.get("blocker"), nums, s["id"] + ".blocker")
        r["pending"] = render(s.get("pending"), nums, s["id"] + ".pending")
        for k in ("state_key", "state_subkey", "state_field", "state_expect", "diff_reason"):
            if s.get(k) is not None:
                r[k] = s[k]
        r["claim_boundary"] = render(s["claim_boundary"], nums, s["id"] + ".claim_boundary")
        used = set()
        for field in ("claim_boundary", "blocker", "pending"):
            used |= set(PLACEHOLDER.findall(s.get(field) or ""))
        r["numbers"] = {}
        for name in sorted(used):
            ptr = dict(nums[name])
            ptr.pop("value", None)
            r["numbers"][name] = ptr
            c = {"id": "G-%s-%s" % (s["id"], name), "generated": True, "row": s["id"],
                 "text": ptr["text"], "readme_row": s["id"], "source": ptr}
            claims.append(c)
    if errors:
        raise GenError("%d number pointer(s) failed:\n  " % len(errors) + "\n  ".join(errors))
    for cid, name in (("S01", "budget.used"), ("S02", "budget.cap"), ("S03", "budget.remaining"),
                      ("S04", "budget.attempts")):
        ptr = dict(gnums[name])
        ptr.pop("value", None)
        claims.append({"id": cid, "generated": True, "row": "STATE", "text": ptr["text"],
                       "readme_block": "budget", "source": ptr})
    rows = [r for _, r in rows_out]
    return {"rows": rows, "claims": claims, "notes": notes, "budget": gnums}


def table(rows: list[dict]) -> str:
    out = [TABLE_HEAD]
    for r in rows:
        head = ("%s @ `%s`" % (r["branch"], r["sha"][:9])) if r.get("sha") else "—"
        out.append("| %s |" % " | ".join([
            r["id"], r["disposition"], cell(r["class"]), head, cell(r.get("packet") or "—"),
            cell(r["claim_boundary"]), cell(r.get("blocker") or ""), cell(r.get("pending") or "")]))
    return "\n".join(out)


def head_notes(notes: list[dict]) -> str:
    if not notes:
        return "No row cites a head other than its STATE row's head."
    out = ["Rows whose cited head differs from the head in their own STATE row (generated from STATE; the STATE row"
           " head is written plain because it may be unpublished):"]
    for n in notes:
        out.append("- **%s** cites %s (from %s); its STATE row names %s. %s" % (
            n["row"], n["cited"].replace(" @ ", " @ `") + "`", n["source"], n["state_row_head"], n["reason"]))
    return "\n".join(out)


def moving_rows(rows: list[dict], spec: dict) -> str:
    out = ["| Row | Disposition | What can still move it |", "|---|---|---|"]
    for r in rows:
        if r.get("pending"):
            out.append("| %s | %s | %s |" % (r["id"], r["disposition"], cell(r["pending"])))
    return "\n".join(out)


def gen_blocks(build_out: dict, spec: dict) -> dict:
    b = build_out["budget"]
    t = {k: v["text"] for k, v in b.items()}
    lanes = spec["wave7_lanes"]
    lane_rows = ["| Lane | Scope (planner follow-up) | Rows marked OPEN |", "|---|---|---|"]
    for lane, info in lanes.items():
        rows = [r["id"] for r in build_out["rows"] if r.get("pending") and re.search(
            r"OPEN: scheduled wave 7 [^.;]*\b%s\b" % re.escape(lane), r["pending"])]
        lane_rows.append("| %s | %s | %s |" % (lane, info["scope"], ", ".join(rows) or "none (no row cites it)"))
    return {
        "budget": "%s of %s reached used, %s remain (%s attempts)" % (
            t["budget.used"], t["budget.cap"], t["budget.remaining"], t["budget.attempts"]),
        "wave7-lanes": "\n" + "\n".join(lane_rows) + "\n",
    }


def replace_between(text: str, start: str, end: str, body: str, name: str) -> str:
    i, j = text.find(start), text.find(end)
    if i < 0 or j < i:
        raise GenError("%s markers missing" % name)
    return text[:i + len(start)] + "\n" + body + "\n" + text[j:]


def render_readme(readme: str, build_out: dict, spec: dict) -> str:
    readme = replace_between(readme, TABLE_START, TABLE_END, table(build_out["rows"]), "dispositions-table")
    readme = replace_between(readme, NOTES_START, NOTES_END, head_notes(build_out["notes"]), "head-notes")
    blocks = gen_blocks(build_out, spec)

    def sub(m):
        if m.group(2) not in blocks:
            raise GenError("unknown gen block %s" % m.group(2))
        return m.group(1) + blocks[m.group(2)] + m.group(4)
    return GEN_BLOCK.sub(sub, readme)


def render_pending(pending: str, build_out: dict, spec: dict) -> str:
    pending = replace_between(pending, MOVING_START, MOVING_END, moving_rows(build_out["rows"], spec), "moving-rows")
    blocks = gen_blocks(build_out, spec)
    return GEN_BLOCK.sub(lambda m: m.group(1) + blocks[m.group(2)] + m.group(4), pending)


# ---------------------------------------------------------------- sha_refs
BACKTICK = re.compile(r"`([0-9a-f]{7,40})`")


def sha_refs(repo: Repo, rows: list[dict], md_texts: list[str], spec: dict) -> dict:
    """Map every backticked SHA in the markdown to a ref that holds it, so a verifier in a
    heads-only clone knows exactly what to fetch."""
    cands = [("self", "HEAD", repo.full("HEAD"))]
    seen = set()
    for r in rows:
        if r.get("sha") and r["branch"] not in seen:
            seen.add(r["branch"])
            cands.append(("fork", "refs/heads/" + r["branch"], r["sha"]))
    for e in spec.get("extra_refs", []):
        cands.append((e["remote"], e["ref"], repo.full(e["sha"])))
    out = {}
    for text in md_texts:
        for m in BACKTICK.finditer(text):
            short = m.group(1)
            full = repo.full(short)
            if not full:
                raise GenError("backticked SHA %s does not resolve" % short)
            if full in out:
                continue
            for remote, ref, tip in cands:
                if tip and repo.is_ancestor(full, tip):
                    out[full] = {"remote": remote, "ref": ref}
                    break
            else:
                raise GenError("backticked SHA %s is on no known ref (add it to extra_refs)" % short)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- main
def load(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def dump_json(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def generate(repo_path: Path, state_path: str) -> dict:
    """Return {filename: new content} for every generated file."""
    repo = Repo(repo_path)
    raw = Path(state_path).read_bytes()
    state = json.loads(raw)
    spec = load(SPEC)
    out = build(repo, state, spec)
    disp = {"schema": "rfc3963-rewrite-dispositions/v2",
            "note": spec["dispositions_note"],
            "generated_by": "generate.py from rows.spec.json + STATE.json",
            "rows": out["rows"]}
    claims_doc = load("claims.json")
    curated = [c for c in claims_doc["claims"] if not c.get("generated")]
    claims_doc["claims"] = curated + out["claims"]
    readme = render_readme((HERE / "README.md").read_text(encoding="utf-8"), out, spec)
    pending = render_pending((HERE / "PENDING.md").read_text(encoding="utf-8"), out, spec)
    md = [readme, pending, (HERE / "REVIEW-CHECKLIST.md").read_text(encoding="utf-8")]
    prov = load("provenance.json")
    prov["sha_refs"] = sha_refs(repo, out["rows"], md, spec)
    prov["inputs"]["loop_state"]["sha256"] = hashlib.sha256(raw).hexdigest()
    return {"dispositions.json": dump_json(disp), "claims.json": dump_json(claims_doc),
            "README.md": readme, "PENDING.md": pending, "provenance.json": dump_json(prov)}


def compare(new: dict) -> list[str]:
    """Differences between a regeneration and the committed files (provenance's STATE hash is
    compared separately by the verifier and ignored here)."""
    diffs = []
    for name, text in new.items():
        old = (HERE / name).read_text(encoding="utf-8")
        if name == "provenance.json":
            a, b = json.loads(old), json.loads(text)
            a["inputs"]["loop_state"].pop("sha256", None)
            b["inputs"]["loop_state"].pop("sha256", None)
            if a != b:
                diffs.append("provenance.json sha_refs/other fields differ")
            continue
        if old != text:
            ol, nl = old.splitlines(), text.splitlines()
            first = next((i for i, (x, y) in enumerate(zip(ol, nl)) if x != y), min(len(ol), len(nl)))
            diffs.append("%s differs from regeneration at line %d" % (name, first + 1))
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", required=True)
    ap.add_argument("--repo")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    repo = Path(a.repo) if a.repo else Path(subprocess.run(
        ["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip())
    try:
        new = generate(repo, a.state)
    except GenError as e:
        print("GENERATE ERROR: %s" % e)
        return 2
    if a.check:
        d = compare(new)
        for x in d:
            print("DRIFT " + x)
        print("generated content %s" % ("is up to date" if not d else "is stale (%d files)" % len(d)))
        return 1 if d else 0
    for name, text in new.items():
        (HERE / name).write_text(text, encoding="utf-8")
    print("wrote %s at %s" % (", ".join(sorted(new)), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
