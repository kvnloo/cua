"""Shared helpers for the kvnloo/cua#10 accounting and kvnloo/cua#74 queue deliverables.

Stdlib only. Every number in accounting.json / queue.json is a pointer into an accepted
packet's summary or headline JSON at an exact commit, read with `git show <sha>:<path>`.
"""
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
RFC_DIR = os.path.dirname(HERE)


def repo_root():
    out = subprocess.run(["git", "-C", HERE, "rev-parse", "--show-toplevel"],
                         check=True, capture_output=True, text=True).stdout.strip()
    return out


def git(*args, check=True):
    p = subprocess.run(["git", "-C", repo_root()] + list(args), capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), p.stderr.strip()))
    return p


_SHOW_CACHE = {}


def show_json(sha, path):
    key = (sha, path)
    if key not in _SHOW_CACHE:
        p = git("show", "%s:%s" % (sha, path))
        _SHOW_CACHE[key] = json.loads(p.stdout)
    return _SHOW_CACHE[key]


def sha_exists(sha):
    return git("cat-file", "-e", sha + "^{commit}", check=False).returncode == 0


def full_sha(sha):
    return git("rev-parse", "--verify", sha + "^{commit}").stdout.strip()


def resolve(obj, path):
    cur = obj
    for k in path:
        if isinstance(cur, list):
            cur = cur[int(k)]
        else:
            cur = cur[k]
    return cur


def rnd(v, nd):
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, (list, tuple)):
        return [rnd(x, nd) for x in v]
    if isinstance(v, dict):
        return {k: rnd(x, nd) for k, x in v.items()}
    if nd is None:
        return v
    r = round(float(v), nd)
    if nd == 0:
        return int(r)
    return r


def close(a, b, nd):
    """Equal within the stated rounding (half a unit in the last place, plus float slack)."""
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        return isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b) \
            and all(close(x, y, nd) for x, y in zip(a, b))
    if isinstance(a, dict) or isinstance(b, dict):
        return isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys() \
            and all(close(a[k], b[k], nd) for k in a)
    if a is None or b is None or isinstance(a, (bool, str)) or isinstance(b, (bool, str)):
        return a == b
    if nd is None:
        return float(a) == float(b)
    return abs(float(a) - float(b)) <= 0.5 * 10 ** (-nd) + 1e-9


def walk_pointers(node, where=""):
    """Yield (location, pointer-dict) for every {"value", "from"} pointer in a JSON tree."""
    if isinstance(node, dict):
        if "value" in node and "from" in node and isinstance(node["from"], dict):
            yield where, node
        for k, v in node.items():
            if k == "from":
                continue
            yield from walk_pointers(v, where + "/" + str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_pointers(v, where + "/" + str(i))


def fmt(v, nd=None, pct=False):
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(fmt(x, nd, pct) for x in v) + "]"
    if pct:
        d = 2 if nd is None else max(nd - 2, 0)
        return ("%." + str(d) + "f%%") % (float(v) * 100.0)
    if nd is None:
        return str(v)
    return ("%." + str(nd) + "f") % float(v)


# --- text checks shared by the verifier -------------------------------------------------

AUTOLINK_PATTERNS = [
    ("upstream short ref", re.compile(r"trycua/cua#\d+")),
    ("upstream URL", re.compile(r"github\.com/trycua/cua/(?:pull|issues|commit)/")),
    ("upstream commit ref", re.compile(r"trycua/cua@[0-9a-f]{7,}")),
    ("bare issue ref", re.compile(r"(?<![\w/#])#\d+\b")),
    ("GH- ref", re.compile(r"\bGH-\d+\b")),
    ("user mention", re.compile(r"(?<![\w.`/<-])@[A-Za-z][A-Za-z0-9-]{1,38}\b")),
]

ABS_PATH = re.compile(r"(?<![\w.~])/(?:home|mnt|tmp|run/user|var/tmp|Users|root)/")


def owner_type(text):
    """A STATE blocked item counts as owner-blocking when it names the owner and is not marked RESOLVED."""
    t = str(text).strip().lower()
    return "owner" in t and not t.startswith("resolved")


BARE_REF = re.compile(r"(?<![\w/#])#(\d+)\b")


def fork_refs(text):
    """STATE free text writes fork issues as bare #N; render them as kvnloo/cua#N (upstream items are plain text)."""
    return BARE_REF.sub(r"kvnloo/cua#\1", str(text))


def autolink_findings(text):
    out = []
    for name, rx in AUTOLINK_PATTERNS:
        for m in rx.finditer(text):
            out.append((name, m.group(0)))
    return out
