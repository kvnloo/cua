#!/usr/bin/env python3
"""Write inputs/state-extract.json from the loop STATE.json (stdlib only; run under the lane's hostless wrapper).

  CUA_LOOP_STATE=<STATE.json> python3 docs/rfc/74-posting-queue/make_state_extract.py

The STATE file itself is never committed. The extract keeps only what the queue's gates and evidence read: accepted
lanes by wave, the cited lanes' dispositions (branch, commit, disposition text), the wave-5 and wave-6 published and
held heads, the pending owner decisions, the wave-6 blocked items and the TypeSafe budget, plus the STATE sha256.
verify_artifacts.py re-derives the extract with the same function and compares its gate inputs.
"""
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRACT = os.path.join(HERE, "inputs", "state-extract.json")

# Lanes whose STATE disposition the queue cites (packet lanes plus lanes named in evidence or dependencies).
CITED_LANES = sorted({
    "FIX-01", "FIX-02", "RECERT-FIX", "OWN-09R", "OWN-16W", "OWN-20P", "OWN-20G", "BUG-01", "OWN-105", "OWN-75R",
    "OWN-78A", "B-02", "B-01R", "N-01R", "N-02", "N-03", "N-04", "R2-09", "R2-03", "R2-08", "R2-07c", "R2-07d",
    "R2-10", "R2-10R", "B-06", "OWN-36", "PUB-02", "R2-07", "R2-04", "B-01", "B-03", "OWN-16", "OWN-78", "N-01",
    "PKT-01", "R2-01", "R2-05", "R2-06",
    # wave 6
    "B-08", "R2-07e", "OWN-78L", "FIX-03", "OWN-20Q", "PUB-03", "DOC-3963", "DOC-10-74",
})

# The keys the READY NOW gates read; the verifier compares exactly these against a fresh derivation.
GATE_KEYS = ("accepted_by_wave", "owner_decisions_pending", "blocked_items_w6", "provider_budget", "dispositions",
             "published_heads")

P0 = ["R2-01", "R2-02", "R2-03", "R2-04", "R2-05", "R2-06"]


def state_extract(path=None):
    path = path or os.environ.get("CUA_LOOP_STATE")
    if not path:
        raise SystemExit("set CUA_LOOP_STATE to the loop STATE.json (read-only input)")
    raw = open(path, "rb").read()
    st = json.loads(raw)
    disp = {}
    for k in CITED_LANES:
        dv = st["dispositions"].get(k)
        if isinstance(dv, dict):
            disp[k] = {kk: dv.get(kk) for kk in ("branch", "commit", "accepted_branch", "accepted_commit",
                                                  "accepted_wave", "rejected_wave") if dv.get(kk) is not None}
            disp[k]["disposition_head"] = str(dv.get("disposition") or dv.get("verdict") or "")[:600]
    accepted = {}
    for w in st["waves"]:
        acc = w.get("accepted")
        if isinstance(acc, list):
            accepted[str(w["wave"])] = acc
        elif isinstance(acc, int):
            accepted[str(w["wave"])] = P0[:acc]
    by_wave = {w.get("wave"): w for w in st["waves"]}
    w5 = by_wave.get(5, {})
    w6 = by_wave.get(6, {})
    pub6 = w6.get("publication") or {}
    held = {}
    for grp, refs in (pub6.get("held_not_pushed") or {}).items():
        if isinstance(refs, dict):
            held.update(refs)
    pb = st["provider_budget"]
    return {
        "schema": "cua-rfc-74-state-extract/v2",
        "state_sha256": hashlib.sha256(raw).hexdigest(),
        "note": "extract of the loop STATE.json (not committed); lane ids, commits, owner decisions, blocked items and "
                "budget only",
        "accepted_by_wave": accepted,
        "accepted_note": "wave 0 accepted the six P0 packets R2-01..R2-06 (STATE records the count only)",
        "dispositions": disp,
        "published_heads": {
            "wave5_pushed": w5.get("pushed_branches", {}),
            "wave6_pushed": pub6.get("pushed_branch_heads", {}),
            "wave6_held": held,
        },
        "owner_decisions_pending": st["owner_decisions_pending"],
        "blocked_items_w6": st["blocked_items_w6"],
        "provider_budget": {k: pb[k] for k in ("provider", "cap_requests", "used_requests_reached_provider",
                                               "used_attempts", "remaining_reached")},
    }


def main():
    ext = state_extract()
    os.makedirs(os.path.dirname(EXTRACT), exist_ok=True)
    with open(EXTRACT, "w") as f:
        json.dump(ext, f, indent=1)
        f.write("\n")
    pb = ext["provider_budget"]
    print("state-extract.json written: %d owner decisions, %d blocked items, budget %s reached / %s remaining" % (
        len(ext["owner_decisions_pending"]), len(ext["blocked_items_w6"]), pb["used_requests_reached_provider"],
        pb["remaining_reached"]))


if __name__ == "__main__":
    main()
