#!/usr/bin/env python3
"""Sanitize text files under raw/ in place (stdlib only): local path prefixes, session D-Bus paths and
GUIDs, terminal colour codes, and the machine names listed in CUA_PRIVACY_NAMES_FILE. The prefix map is
given on the command line (PREFIX=TOKEN), so no local path is written into this file. The unsanitized
originals are mirrored outside the packet before this runs.

usage: CUA_PRIVACY_NAMES_FILE=<file> sanitize_raw.py <raw-dir> PREFIX=TOKEN [PREFIX=TOKEN ...]
"""

import gzip
import os
import re
import sys

TEXT_EXT = (".log", ".txt", ".jsonl", ".json", ".patch", ".out", ".status", ".sha256")
GENERIC = [
    (re.compile(r"/tmp" + r"/dbus-[A-Za-z0-9]+"), "<TMPDBUS>"),
    (re.compile(r"(?<![\w<>.-])/tmp" + r"/[A-Za-z0-9_.-]+"), "<tmp-path>"),
    (re.compile(r"guid=[0-9a-f]{32}"), "guid=<GUID>"),
    (re.compile(r"\x1b\[[0-9;]*m"), ""),
]


def main(argv):
    raw, pairs = argv[0], [a.split("=", 1) for a in argv[1:]]
    pairs.sort(key=lambda kv: -len(kv[0]))
    names = []
    path = os.environ.get("CUA_PRIVACY_NAMES_FILE")
    if path:
        names = [n for n in open(path, encoding="utf-8").read().split() if len(n) >= 2]
    name_res = [re.compile(r"(?i)(?<![\w-])%s(?![\w-])" % re.escape(n)) for n in sorted(names, key=len, reverse=True)]
    changed = 0
    for root, _, files in os.walk(raw):
        for f in files:
            p = os.path.join(root, f)
            gz = f.endswith(".gz")
            if not (gz or f.endswith(TEXT_EXT)):
                continue
            opener = gzip.open if gz else open
            with opener(p, "rt", encoding="utf-8", errors="replace") as s:
                text = s.read()
            new = text
            for old, tok in pairs:
                new = new.replace(old, tok)
            for pat, rep in GENERIC:
                new = pat.sub(rep, new)
            for pat in name_res:
                new = pat.sub("<host>", new)
            if new != text:
                with opener(p, "wt", encoding="utf-8") as s:
                    s.write(new)
                changed += 1
    print(f"sanitized {changed} file(s)")


if __name__ == "__main__":
    main(sys.argv[1:])
