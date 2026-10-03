#!/usr/bin/env python3
"""Write provenance.json for the kvnloo/cua#10 / #74 deliverables (stdlib only; run under hostless).

Inputs: accounting.json, ../74-posting-queue/queue.json, its state extract and raw/ls-remote.json, raw/drift.json.
The gh reads (PR heads and states, upstream main, fork branch heads) come from ../74-posting-queue/raw/gh-reads.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rfc_common as C  # noqa: E402

HERE = C.HERE
Q_DIR = os.path.join(C.RFC_DIR, "74-posting-queue")


def main():
    acc = json.load(open(os.path.join(HERE, "accounting.json")))
    q = json.load(open(os.path.join(Q_DIR, "queue.json")))
    ext = json.load(open(os.path.join(Q_DIR, q["state_extract"])))
    lsr = json.load(open(os.path.join(Q_DIR, "raw", "ls-remote.json")))
    drift = json.load(open(os.path.join(Q_DIR, "raw", "drift.json")))
    gh = json.load(open(os.path.join(Q_DIR, q["gh_reads"])))
    shas = {}
    for k, m in acc["packets"].items():
        shas["accounting:" + k] = {"branch": m["branch"], "sha": m["sha"], "packet": m["dir"]}
    for it in q["items"]:
        for p in it["fields"]["exact_sha"].get("packets", []):
            shas.setdefault("queue:" + p["lane"], {"branch": p["branch"], "sha": p["sha"], "packet": p["packet"]})
        c = it["fields"]["exact_sha"].get("candidate")
        if c:
            shas["candidate:" + it["id"]] = {"branch": c["branch"], "sha": c["sha"], "commits": c.get("commits", [])}
    prov = {
        "schema": "cua-rfc-10-74-provenance/v1",
        "lane": "DOC-10-74b (wave 7)",
        "branch": "docs/accounting-10-queue-74-r2-20261003",
        "base": "5de1a37997e6c423899dd0a56aaa63bcf5abee8f",
        "refreshes": {"branch": "docs/accounting-10-queue-74-20261003",
                      "sha": "a3e3cb86e37885db84e3f43fe81c3b882d1a4b49"},
        "evidence_class": "SOURCE (document; every number re-read from accepted packets)",
        "provider": {"name": "TypeSafe", "attempts": 0, "reached": 0},
        "tested_sources": "none: this lane runs no Driver; every number comes from the cited packets' tested sources",
        "inputs": {
            "state_sha256": ext["state_sha256"],
            "state_extract": "../74-posting-queue/" + q["state_extract"],
            "end_condition": "loop END_CONDITION.md (v1, 2026-10-01): E5 deliverables",
            "syntheses": ["SYNTHESIS-w1.md", "SYNTHESIS-w2.md", "SYNTHESIS-w3.md", "SYNTHESIS-w4.md", "SYNTHESIS-w5.md",
                          "SYNTHESIS-w6.md"],
            "shas": shas,
        },
        "gh_reads": {"read_utc": gh["read_utc"], "tool": gh["tool"],
                     "prs": [{k: x.get(k) for k in ("repo", "number", "state", "head_sha")} for x in gh["prs"]],
                     "upstream_main": gh["upstream_main"].get("sha"), "fork_branches_read": len(gh["fork_branches"])},
        "ls_remote": {"read_utc": lsr["read_utc"], "upstream_main_live": lsr["upstream"].get("refs/heads/main")},
        "pinned_main": q["pinned_main"],
        "drift_since_0f1955d2f": {"files": drift["libs_cua_driver_files"], "non_allowlisted": drift["non_allowlisted"]},
        "drift_since_previous_pin": {"previous_pin": drift["previous_pin"], "files": drift["since_previous_pin"],
                                     "non_allowlisted": drift["since_previous_pin_non_allowlisted"]},
        "post_pin": {"upstream_main_live": drift["upstream_main_live"],
                     "libs_cua_driver_files": drift["post_pin_libs_cua_driver_files"],
                     "note": "the drift pin is the live upstream main read with gh at the fresh review; post_pin lists any "
                             "libs/cua-driver change after it at build time"},
        "pr_pins": q["pr_pins"],
        "live_heads_vs_tested_vs_publication": "packet SHAs are the tested/accepted heads; publication SHA of this "
                                               "deliverable is set by the Publish agent",
        "publication_sha": None,
    }
    with open(os.path.join(HERE, "provenance.json"), "w") as f:
        json.dump(prov, f, indent=1)
        f.write("\n")
    print("provenance.json written: %d SHAs" % len(shas))


if __name__ == "__main__":
    main()
