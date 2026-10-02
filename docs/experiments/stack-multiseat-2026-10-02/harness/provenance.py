#!/usr/bin/env python3
"""provenance.py <packet-dir> <prereg-commit> <extra.json> : write provenance.json (identities, commits, ledger lines).
extra.json carries the lane-local facts the packet cannot re-derive (binary hashes measured on the host, quiet-lane
ledger lines for ms-main-*, server identity), already sanitized."""
import json
import subprocess
import sys

pkt, pc, extra = sys.argv[1], sys.argv[2], json.load(open(sys.argv[3]))
ct = subprocess.run(["git", "-C", pkt, "show", "-s", "--format=%ct %cI", pc], capture_output=True, text=True).stdout.split()
prov = {"schema": "cua.stack.multiseat.provenance.v1", "prereg_commit": pc,
        "prereg_commit_epoch": int(ct[0]) if ct else None, "prereg_commit_time": ct[1] if len(ct) > 1 else None,
        "branch": "exp/stack-multiseat-20261002", "base": "exp/stack-sway-20261002 d7317fd2f56217b27742bf9c2186bdd864633787 (upstream main 352507b6c + sway kit packet)"}
prov.update(extra)
json.dump(prov, open(f"{pkt}/provenance.json", "w"), indent=1)
print("provenance written")
