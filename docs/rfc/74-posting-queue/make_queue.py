#!/usr/bin/env python3
"""Build queue.json, raw/ gate evidence and the generated part of README.md for kvnloo/cua#74.

Stdlib only; run under the lane's hostless wrapper. Inputs:
  - accepted packets at exact commits (`git show <sha>:<path>`),
  - the loop STATE.json, path given by the CUA_LOOP_STATE environment variable (never committed;
    only a small extract plus its sha256 is committed under inputs/),
  - read-only `git ls-remote` of origin (kvnloo/cua) and upstream (trycua/cua) heads and PR refs,
  - read-only `git diff --name-only` for drift against the pinned upstream main.
Every number in an evidence line is a pointer into a packet; free text carries no bare numbers.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = os.path.join(os.path.dirname(HERE), "10-final-accounting")
sys.path.insert(0, ACC)
import rfc_common as C  # noqa: E402

OUT_JSON = os.path.join(HERE, "queue.json")
README = os.path.join(HERE, "README.md")
EXTRACT = os.path.join(HERE, "inputs", "state-extract.json")
RAW = os.path.join(HERE, "raw")
BEGIN = "<!-- BEGIN GENERATED: make_queue.py -->"
END = "<!-- END GENERATED: make_queue.py -->"

MAIN_PIN = "5de1a37997e6c423899dd0a56aaa63bcf5abee8f"
DRIFT_ALLOW = re.compile(r"(platform-macos/|platform-windows/|Skills/cua-driver/MACOS\.md$|"
                         r"cua-driver-e2e/tests/harness_appkit_test\.rs$|tests/fixtures/apps/macos/|"
                         r"tests/fixtures/shared/scenarios\.json$)")

# Packet registry for queue evidence pointers: lane -> (branch, full sha, packet dir, summary file).
QP = {
    "FIX-01": ("exp/fix-01-detached-node-refusal-20261002", "4a301d32a96d0a5d54a77d7147af1191c7df4c4e",
               "docs/experiments/fix-01-detached-node-refusal-2026-10-02", "fix01-summary.json"),
    "FIX-02": ("exp/fix-02-token-ownership-retry-scope-20261002", "cea02cb74cc1ad64497804d5da1270a8775f6c75",
               "docs/experiments/fix-02-token-ownership-retry-scope-2026-10-02", "fix02-summary.json"),
    "RECERT-FIX": ("exp/fix-recert-a3-20261003", "939580fc64073d0159865b547566d3522ce1565f",
                   "docs/experiments/fix-recert-a3-2026-10-03", "dispositions.json"),
    "OWN-09R": ("exp/own-09r-84-revision-20261002", "0c2896a53e185ed6b92e61fdb405e42137cc0720",
                "docs/experiments/own-09r-84-revision-2026-10-02", "summary.json"),
    "OWN-16W": ("exp/own-16w-sway-modality-20261002", "1b981915777f7fe6628eb3917906f9d0e345b107",
                "docs/experiments/own-16w-sway-modality-2026-10-02", "own-16w-summary.json"),
    "OWN-20P": ("exp/own-20p-guard-port-a11y-20261003", "64081dded4e0a3ddf144e68ab1ea43579f85f572",
                "docs/experiments/own-20p-guard-port-a11y-2026-10-03", "own20p-summary.json"),
    "OWN-20G": ("exp/own-20g-guard-final-diff-a2-20261003", "ce7544cc064cecfd9ba4702466a1d0f24b1799b6",
                "docs/experiments/own-20g-guard-final-diff-2026-10-03", "own20g-summary.json"),
    "BUG-01": ("exp/bug-01-delivery-cdp-sessions-20261002", "097b4f0974d5c161360fc3683c17f298ff681c70",
               "docs/experiments/bug-01-delivery-cdp-2026-10-02", "bug01-summary.json"),
    "OWN-105": ("exp/own-105-runner-reconcile-20261002", "b97daa4ba08605c08f6a5da8baf1bf32c5ff4093",
                "docs/experiments/own-105-runner-reconcile-2026-10-02", "own-105-summary.json"),
    "OWN-75R": ("exp/own-75r-timing-parity-4336-20261002", "e02621fdc1fe5098efd48af295964f25902553ea",
                "docs/experiments/own-75-timing-parity-4336-2026-10-02", "own-75-summary.json"),
    "OWN-78A": ("exp/own-78a-abstain-isolation-4394-20261003", "6f6c67955505e5b48f130a69feac9ea11c6e9ed6",
                "docs/experiments/own-78a-abstain-isolation-4394-2026-10-03", "own78a-summary.json"),
    "B-02": ("exp/b-02-browser-driver-sites-20261002", "b282ff3894fa85a7b82257cb1edd5088c2f0ac37",
             "docs/experiments/b-02-browser-driver-sites-2026-10-02", "b02-summary.json"),
    "B-01R": ("exp/b-01r-browser-critpath-textfix-20261002", "0cd63f786290f967f41a5a6b615d54f98045ebec",
              "docs/experiments/b-01-browser-critpath-2026-10-02", "b01-summary.json"),
    "N-01R": ("exp/n-01r-native-wait-ab-20261002", "3bb4a7fc70d1d58984b19a7a357892a7c9af31fa",
              "docs/experiments/n-01r-native-wait-ab-2026-10-02", "n01r-summary.json"),
    "N-02": ("exp/n-02-native-transport-20261002", "9846ac8033a8b5e952b0d44f39858625375d54e1",
             "docs/experiments/n-02-native-transport-2026-10-02", "n02-summary.json"),
    "N-03": ("exp/n-03-native-closure-axfg-a3-20261003", "6b70ec9024cc3921f7637bba2ffabcc93e29fc77",
             "docs/experiments/n-03-native-closure-axfg-2026-10-03", "n03-summary.json"),
    "N-04": ("exp/n-04-native-composition-rprime-20261003", "9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2",
             "docs/experiments/n-04-native-composition-rprime-2026-10-03", "n04-summary.json"),
    "R2-09": ("exp/r2-09-native-event-wake-20261002", "3539e34ae16d8c49d8de65452663a916dd6647fa",
              "docs/experiments/r2-09-native-event-wake-2026-10-02", "r209-summary.json"),
    "R2-03": ("exp/r2-03-guarded-live-20261001", "6bab214abb707a3db9e8a7d641d160c3f58e08d5",
              "docs/experiments/r2-03-2026-10-01", "r2-03-summary.json"),
    "R2-08": ("exp/r2-08-cross-surface-20261002", "afba150d55426bf775cb10adaa698cf99493b229",
              "docs/experiments/r2-08-2026-10-02", "r2-08-summary.json"),
    "R2-07c": ("exp/r2-07c-toggle-modal-compiled-a2-20261003", "7f46edd1681fbf58586f8b4972636c3da56e3be6",
               "docs/experiments/r2-07c-toggle-modal-compiled-2026-10-03", "r2-07c-summary.json"),
    "R2-07d": ("exp/r2-07d-quiet-timing-phase-l-20261003", "79f6dd29958b2a73b477544ca9e777efade8a6c3",
               "docs/experiments/r2-07d-quiet-timing-phase-l-2026-10-03", "r2-07d-summary.json"),
    "R2-10": ("exp/r2-10-composition-20261002", "030f6bdbf811e124e11daa2de0569bffb993b66d",
              "docs/experiments/r2-10-composition-2026-10-02", "r2-10-summary.json"),
    "R2-10R": ("exp/r2-10r-recert-a3-20261003", "d22eeb2ecf8a679d1425c21120a599775aa0817d",
               "docs/experiments/r2-10r-recert-2026-10-03", "r2-10r-summary.json"),
    "B-06": ("exp/b-06-per-process-cold-snapshot-20261003", "31bc98a95b746080d1b74b895fe575071d4a94e9",
             "docs/experiments/b-06-per-process-cold-snapshot-2026-10-03", "b06-summary.json"),
    "OWN-36": ("exp/own-36-session-isolation-native-20261002", "ff77554f46db2799334a20cb55111decc02582de",
               "docs/experiments/own-36-session-isolation-native-2026-10-02", "summary.json"),
    "PUB-02": ("docs/packet-template-privacy-20261003", "c4342323bf51d9dcaea824c10aad59a5dd7a3c1c",
               "docs/experiments/pub-02-privacy-gate-2026-10-03", "pub02-summary.json"),
}

# Wave-6 lanes still running (refresh in wave 7). Branch names are the planner's assignments.
PENDING_W6 = {
    "B-08": "exp/b-08-per-process-cold-b7-20261003",
    "FIX-03": "exp/fix-03-file-input-toctou-session-routing-20261003",
    "OWN-20Q": "exp/own-20q-a11y-triggers-dialog-markfree-20261003",
    "OWN-78L": "exp/own-78l-r1-lite-f-20261003",
    "R2-07e": "exp/r2-07e-modal-gate-phase-l-20261003",
    "PUB-03": "exp/own-20g-guard-final-diff-r1c-20261003 + exp/n-03-native-closure-axfg-r1c-20261003 + "
              "exp/n-04-native-composition-rprime-r1c-20261003",
    "DOC-3963": "docs/rfc3963-rewrite-draft-20261003",
}

ORIGIN_URL = "https://github.com/kvnloo/cua.git"
UPSTREAM_URL = "https://github.com/trycua/cua.git"

PR_PINS = {
    ("trycua/cua", 4316): "a0bca744067d04f05904319d3d919be30c336556",
    ("trycua/cua", 4336): "8391cf80275d2a5e7288f9d7c6b0a3e5f7822939",
    ("trycua/cua", 4394): "039257811e0bbb2348c616c52562409923d2856f",
    ("kvnloo/cua", 84): "566b9c73245266005c958d40e93d46ee5d463325",
    ("kvnloo/cua", 105): "98a45e6c528da9e2715288c20c2a0feeeef8e73f",
    ("kvnloo/cua", 106): "c45845797b714ccfd76a9569d3238a0724107a83",
}

FRESH_REVIEW_BASIS = ("not yet: no fresh reviewer has reviewed this queue entry against the pinned main; the "
                      "DOC-10-74 verifier review is the first, and the wave-7 refresh records its outcome")


def Q(lane, path, nd=None, file=None):
    br, sha, d, f = QP[lane]
    data = C.show_json(sha, d + "/" + (file or f))
    return {"value": C.rnd(C.resolve(data, path), nd),
            "from": {"lane": lane, "sha": sha, "file": d + "/" + (file or f), "path": list(path), "round": nd}}


def E(template, **nums):
    """An evidence line: free text with {name} slots filled from packet pointers."""
    return {"t": template, "n": nums}


def gate(lane, path, file=None):
    """A gate whose key text (written by the packet) is rendered next to its value."""
    p = Q(lane, path, file=file)
    k = {"value": path[-1], "from": dict(p["from"], key=True)}
    return E("{k}: {g}", k=k, g=p)


# ------------------------------------------------------------------------------- STATE extract

def state_extract():
    path = os.environ.get("CUA_LOOP_STATE")
    if not path:
        raise SystemExit("set CUA_LOOP_STATE to the loop STATE.json (read-only input)")
    raw = open(path, "rb").read()
    st = json.loads(raw)
    lanes_cited = sorted(set(QP) | {"R2-07", "R2-04", "B-01", "B-03", "OWN-36", "OWN-16", "OWN-78", "N-01",
                                    "PKT-01", "R2-01", "R2-05", "R2-06"})
    disp = {}
    for k in lanes_cited:
        dv = st["dispositions"].get(k)
        if isinstance(dv, dict):
            disp[k] = {kk: dv.get(kk) for kk in ("branch", "commit", "accepted_branch", "accepted_commit",
                                                  "accepted_wave", "rejected_wave") if dv.get(kk) is not None}
            dtext = dv.get("disposition") or dv.get("verdict") or ""
            disp[k]["disposition_head"] = str(dtext)[:160]
    accepted = {}
    for w in st["waves"]:
        acc = w.get("accepted")
        if isinstance(acc, list):
            accepted[str(w["wave"])] = acc
        elif isinstance(acc, int):
            accepted[str(w["wave"])] = ["R2-01", "R2-02", "R2-03", "R2-04", "R2-05", "R2-06"][:acc]
    pb = st["provider_budget"]
    w5 = [w for w in st["waves"] if w.get("wave") == 5][0]
    ext = {
        "schema": "cua-rfc-74-state-extract/v1",
        "state_sha256": hashlib.sha256(raw).hexdigest(),
        "note": "extract of the loop STATE.json (not committed); lane ids, commits, owner decisions and budget only",
        "accepted_by_wave": accepted,
        "accepted_note": "wave 0 accepted the six P0 packets R2-01..R2-06 (STATE records the count only)",
        "dispositions": disp,
        "wave5_pushed_branches": w5.get("pushed_branches", {}),
        "wave5_not_pushed": w5.get("not_pushed", {}),
        "owner_decisions_pending": st["owner_decisions_pending"],
        "blocked_items_w5": st["blocked_items_w5"],
        "provider_budget": {k: pb[k] for k in ("provider", "cap_requests", "used_requests_reached_provider",
                                               "used_attempts", "remaining_reached")},
    }
    return ext


# --------------------------------------------------------------------------------- the queue

def items():
    I = []

    def add(**kw):
        I.append(kw)

    # ---------------------------------------------------------------- fixes and fix candidates
    add(id="Q01", title="FIX-01 detached-node refusal (dom_event route) + refused-is-refused runner rule",
        delta="Driver refuses dom_event browser_click / browser_pointer / browser_download on a detached ref node "
              "(isConnected checked inside the dispatching callFunctionOn; browser_ref_stale, effect refused); "
              "jev-use runners treat refused as refused and never re-dispatch an unverified accepted mutation.",
        owner=["kvnloo/cua#73 (stale-dispatch invariant)", "kvnloo/cua#93 (R2-07 gap)", "kvnloo/cua#105 (runner rule)"],
        sha={"candidate": {"branch": "exp/r2-10r-control-a2-20261003", "sha": "8a2362770f2120c136c69a50b711a6b9e3a69b8f",
                           "commits": ["a4cda75bdf066a697116a6f84c1b5f234cf5b81d", "8a2362770f2120c136c69a50b711a6b9e3a69b8f"],
                           "note": "FIX-01 Part A + Part B rebased on 0f1955d2f (the R2-10R control binary source); "
                                   "original commits 8cfa8c1db + 6eb9319fe on the FIX-01 packet branch"},
             "packets": [{"lane": "FIX-01"}, {"lane": "R2-10R"}]},
        evidence=[
            E("N4a re-render on the FIX-01 fixed tree: first click refused {r} of {n} (browser_ref_stale), then rebound "
              "and verified {rb}; unfixed tree accepted {u} of {n}; old-node page events on the fixed tree {old}",
              r=Q("FIX-01", ["C1", "F", "first_click_refused_browser_ref_stale"]), n=Q("FIX-01", ["C1", "F", "n"]),
              rb=Q("FIX-01", ["C1", "F", "rebind_redispatch_after_refusal"]),
              u=Q("FIX-01", ["C1", "U", "first_click_accepted"]),
              old=Q("FIX-01", ["C1", "F", "old_node_page_events_gt0"])),
            E("Recertified on 0f1955d2f inside R2-10R: N4a controls passed {p} of {n}",
              p=Q("R2-10R", ["controls", "N4a", "pass"]), n=Q("R2-10R", ["controls", "N4a", "n"])),
            E("Runner: re-dispatches after an unverified accepted mutation on the fixed runner {fx}; on the old runner, "
              "cells with a re-dispatch {old}",
              fx=Q("FIX-01", ["C2", "F+fixed", "redispatches_after_unverified_accepted"]),
              old=Q("FIX-01", ["C2", "U+old", "cells_with_redispatch"])),
        ],
        missing=["The trusted-input route keeps a residual re-render window between send and landing (FIX-01 follow-up; "
                 "characterised under a shared lock only).",
                 "kvnloo/cua#107 D (other track) found the same detached-node acceptance on its unfixed binary (DC05b); "
                 "no re-run of that cell on a fixed tree."],
        action="fork candidate review, then a reviewed upstream PR proposal (not posted; upstream owner named at that time)",
        dependency=["fresh review of this entry", "FIX-02 F3 (retry scope) travels with Part B"],
        stop="Any false refusal on a connected node, or a refused dispatch whose effect landed.",
        gate_in=dict(lanes=["FIX-01", "R2-10R"],
                     published=[("exp/r2-10r-control-a2-20261003", "8a2362770f2120c136c69a50b711a6b9e3a69b8f"),
                                ("exp/fix-01-detached-node-refusal-20261002", "4a301d32a96d0a5d54a77d7147af1191c7df4c4e"),
                                ("exp/r2-10r-recert-a3-20261003", "d22eeb2ecf8a679d1425c21120a599775aa0817d")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "8a2362770f2120c136c69a50b711a6b9e3a69b8f"},
                     owner=[], blocked=[], pending=[], prs=[]))

    add(id="Q02", title="FIX-02 F1-F3: native token ownership, runtime generation, runner re-dispatch scope",
        delta="F1 binds native element tokens to the publishing session; F2 starts snapshot ids at a random per-process "
              "base (runtime generation); F3 lets jev-use runners re-dispatch only after pre-dispatch refusals.",
        owner=["kvnloo/cua#36", "kvnloo/cua#105 (F3 runner rule)"],
        sha={"candidate": {"branch": "exp/fix-02r-a3-20261003", "sha": "df4f1edf56a6b1ca01cd2f9facbed3dc4843280c",
                           "commits": ["8e0e8aea0abbcdddd66b9ed2011e888dcdb103ed", "205a4ecb2e33e846e67b55b8d72cbb61513c2fc6",
                                       "cdffb32130c98ddb7b9196d587c5ef19053bac2d"],
                           "note": "F1-F3 rebased on 0f1955d2f (on top of the FIX-01 picks)"},
             "packets": [{"lane": "RECERT-FIX"}, {"lane": "FIX-02"}]},
        evidence=[gate("RECERT-FIX", ["FIX-02 F1", "gates", "I2 F' 40/40"]),
                  gate("RECERT-FIX", ["FIX-02 F1", "gates", "I2d F' 40/40"]),
                  gate("RECERT-FIX", ["FIX-02 F2", "gates", "I5p F' 20/20"]),
                  gate("RECERT-FIX", ["FIX-02 F2", "gates", "I5pt F' 10/10"]),
                  gate("RECERT-FIX", ["FIX-02 F3", "gates", "0 blind re-dispatches on F'"]),
                  gate("RECERT-FIX", ["kvnloo/cua#36 same-process two-window row", "gates", "0 cross-session mutations on F'"]),
                  E("Recertification verdicts: F1 {a}, F2 {b}, F3 {c}",
                    a=Q("RECERT-FIX", ["FIX-02 F1", "verdict"]), b=Q("RECERT-FIX", ["FIX-02 F2", "verdict"]),
                    c=Q("RECERT-FIX", ["FIX-02 F3", "verdict"]))],
        missing=["A dedicated recording-lookup test (the F1 recording.rs session check has no session-published test).",
                 "Session checks on window_for_snapshot and the (pid, xid) side index (non-authority routing) - FIX-03 is running.",
                 "Discriminating unfixed rows for W2c / W2d (the unfixed tree also refuses them)."],
        action="fork candidate review, then a reviewed upstream PR proposal (not posted)",
        dependency=["FIX-03 (wave 6) session-routing result", "fresh review of this entry"],
        stop="Upstream main changes snapshot_store.rs or the Linux token path; any cross-session mutation on the fixed tree.",
        gate_in=dict(lanes=["RECERT-FIX", "FIX-02"],
                     published=[("exp/fix-02r-a3-20261003", "df4f1edf56a6b1ca01cd2f9facbed3dc4843280c"),
                                ("exp/fix-recert-a3-20261003", "939580fc64073d0159865b547566d3522ce1565f")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "df4f1edf56a6b1ca01cd2f9facbed3dc4843280c"},
                     owner=[], blocked=[], pending=["FIX-03"], prs=[]))

    add(id="Q03", title="FIX-02 F4: browser_set_input_files detached-input refusal (FIX-03 PENDING)",
        delta="Refuse browser_set_input_files on a file input that is detached before the call.",
        owner=["kvnloo/cua#36"],
        sha={"candidate": {"branch": "exp/fix-02r-a3-20261003", "sha": "df4f1edf56a6b1ca01cd2f9facbed3dc4843280c",
                           "commits": ["a357d061d62d0e6e90615a538a099c9d81bccf0f"], "note": "F4 rebased on 0f1955d2f"},
             "packets": [{"lane": "RECERT-FIX"}, {"lane": "FIX-02"}]},
        evidence=[gate("RECERT-FIX", ["FIX-02 F4", "gates", "F4 F' 20/20 (narrower claim; TOCTOU not covered)"]),
                  E("Disposition {d} (recertification verdict {v})", d=Q("RECERT-FIX", ["FIX-02 F4", "disposition"]),
                    v=Q("RECERT-FIX", ["FIX-02 F4", "verdict"]))],
        missing=["The check is a separate call before DOM.setFileInputFiles: a re-render inside the check-to-set window is "
                 "not covered (TOCTOU). FIX-03 is measuring an in-call check."],
        action="hold (REVISE); fork candidate after FIX-03",
        dependency=["FIX-03 (wave 6)"],
        stop="FIX-03 cannot close the window inside the call path, or any old-node event on the fixed tree.",
        gate_in=dict(lanes=["RECERT-FIX", "FIX-02"],
                     published=[("exp/fix-02r-a3-20261003", "df4f1edf56a6b1ca01cd2f9facbed3dc4843280c")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "df4f1edf56a6b1ca01cd2f9facbed3dc4843280c"},
                     owner=[], blocked=[], pending=["FIX-03"], prs=[]))

    add(id="Q04", title="kvnloo/cua#84 revision (OWN-09R): cancel before admission, guard ownership",
        delta="Revised kvnloo/cua#84: cancellation checked before admission, admission holds owned by the operation, "
              "Linux spawn_blocking sites converted to spawn_blocking_owned.",
        owner=["kvnloo/cua#9", "kvnloo/cua#84"],
        sha={"candidate": {"branch": "exp/own-09r2-a3-20261003", "sha": "ba611b51a48f6798eb3b3114f0c98af03c2d7d52",
                           "commits": [], "note": "kvnloo/cua#84 head plus the OWN-09R revision commits, rebased on 0f1955d2f; "
                                                  "kvnloo/cua#84 itself is not modified"},
             "packets": [{"lane": "RECERT-FIX"}, {"lane": "OWN-09R"}]},
        evidence=[gate("RECERT-FIX", ["OWN-09R (kvnloo/cua#84 revision)", "gates", "P_R1D_pass_40"]),
                  gate("RECERT-FIX", ["OWN-09R (kvnloo/cua#84 revision)", "gates", "P_R6_pass_80"]),
                  gate("RECERT-FIX", ["OWN-09R (kvnloo/cua#84 revision)", "gates", "M_R1D_fail_40"]),
                  E("Recertification verdict {v}; strict PREREG reading {s}",
                    v=Q("RECERT-FIX", ["OWN-09R (kvnloo/cua#84 revision)", "verdict"]),
                    s=Q("RECERT-FIX", ["OWN-09R (kvnloo/cua#84 revision)", "strict_prereg_reading", "verdict"]))],
        missing=["Owner call on the timeout path: guards held by a leaked closure after a foreground timeout vs a bounded "
                 "coordinator wait with a structured refusal.",
                 "Owner call on R8 (MCP notifications/cancelled is ignored on both arms).",
                 "Owner call on the strict unit-row reading (Deviation 6 re-run rule).",
                 "R3 on macOS (held-input oracle): BLOCKED, hardware."],
        action="hold; revision staged on the fork for the kvnloo/cua#84 owner",
        dependency=["owner rulings OR-06, OR-07 and OR-16", "fresh review of this entry"],
        stop="Upstream main changes the coordinator / barrier path, or kvnloo/cua#84 head moves.",
        gate_in=dict(lanes=["RECERT-FIX", "OWN-09R"],
                     published=[("exp/own-09r2-a3-20261003", "ba611b51a48f6798eb3b3114f0c98af03c2d7d52"),
                                ("exp/own-09r-84-revision-20261002", "0c2896a53e185ed6b92e61fdb405e42137cc0720")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "ba611b51a48f6798eb3b3114f0c98af03c2d7d52"},
                     owner=[6, 7, 19], blocked=[], pending=[], prs=[("kvnloo/cua", 84)]))

    add(id="Q05", title="OWN-16W fix dd205d17b: refuse non-boolean modality selectors",
        delta="get_window_state refuses non-boolean include_screenshot / modality selectors with invalid_arguments before "
              "any producer runs (Linux).",
        owner=["kvnloo/cua#16"],
        sha={"candidate": {"branch": "exp/own-16w2-a3-20261003", "sha": "7e31eae59d2316c3e41d31a3eb872837bb945283",
                           "commits": [], "note": "dd205d17b rebased on 0f1955d2f"},
             "packets": [{"lane": "RECERT-FIX"}, {"lane": "OWN-16W"}]},
        evidence=[gate("RECERT-FIX", ["OWN-16W", "gates", "X11 F'' string_false refused 42/42"]),
                  gate("RECERT-FIX", ["OWN-16W", "gates", "X11 U'' accepts 42/42 (both string rows)"]),
                  gate("RECERT-FIX", ["OWN-16W", "gates", "S-W F'' rows meet the wave-3 gates"]),
                  E("Recertification verdict {v}", v=Q("RECERT-FIX", ["OWN-16W", "verdict"]))],
        missing=["Owner call: the fix also refuses JSON null (formerly the default).",
                 "Owner call: accept the PREREG F'' gate where the wave-3 analyzer prints REVISE.",
                 "macOS and Windows parity: BLOCKED (hardware); the Windows get_window_state file has also drifted on main."],
        action="hold; fork candidate after the owner rulings",
        dependency=["owner ruling OR-09", "fresh review of this entry"],
        stop="Upstream main changes get_window_state selector parsing on Linux.",
        gate_in=dict(lanes=["RECERT-FIX", "OWN-16W"],
                     published=[("exp/own-16w2-a3-20261003", "7e31eae59d2316c3e41d31a3eb872837bb945283")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "7e31eae59d2316c3e41d31a3eb872837bb945283"},
                     owner=[9, 21], blocked=[], pending=[], prs=[]))

    add(id="Q06", title="OWN-20P G: focus-guard final read on deadline exit, ported to clean main",
        delta="focus_guard: a final focus read when the settle watch ends on its deadline after a read that began before it "
              "(restores a focus steal the watch would otherwise miss silently).",
        owner=["kvnloo/cua#20"],
        sha={"candidate": {"branch": "exp/own-20p-guard-port-a11y-20261003", "sha": "64081dded4e0a3ddf144e68ab1ea43579f85f572",
                           "commits": ["a761f1f1f"], "note": "G port commit a761f1f1f on clean main cb685fad7"},
             "packets": [{"lane": "OWN-20P"}]},
        evidence=[E("R1 stall row on the marked twins: G restored {g} of {ga}; U missed {u} of {ua} silently",
                    g=Q("OWN-20P", ["r1", "G0m_restored"]), ga=Q("OWN-20P", ["r1", "G0m_attempted"]),
                    u=Q("OWN-20P", ["r1", "U0m_silent_miss"]), ua=Q("OWN-20P", ["r1", "U0m_attempted"])),
                  E("Product G on the normal path: verified {v} of {n}; failures plus false restores {f}",
                    v=Q("OWN-20P", ["normal", "G0_verified"]), n=Q("OWN-20P", ["normal", "G0_n"]),
                    f=Q("OWN-20P", ["normal", "G0_failures_plus_false_restores"]))],
        missing=["R1 on a product binary: needs a mark-free stall method (OWN-20Q is running).",
                 "Owner acceptance of the marked-twin substitution (R1 ran with the post-action-sleep knob at zero).",
                 "The same_app_dialog misclassification is not fixed by G (OWN-20Q is running)."],
        action="fork candidate review after OWN-20Q",
        dependency=["OWN-20Q (wave 6)", "owner ruling OR-17", "fresh review of this entry"],
        stop="The port changes quiet-path behaviour, or any false restore on the normal path.",
        gate_in=dict(lanes=["OWN-20P"],
                     published=[("exp/own-20p-guard-port-a11y-20261003", "64081dded4e0a3ddf144e68ab1ea43579f85f572")],
                     drift={"base": "cb685fad7", "candidate": "a761f1f1f"},
                     owner=[20], blocked=[], pending=["OWN-20Q"], prs=[]))

    add(id="Q07", title="OWN-20P A: in-process AT-SPI bus-restart reconnect (OWN-20Q PENDING)",
        delta="The Driver reconnects to a restarted accessibility bus in-process (today a fresh Driver process is needed).",
        owner=["kvnloo/cua#20"],
        sha={"candidate": {"branch": "exp/own-20p-guard-port-a11y-20261003", "sha": "64081dded4e0a3ddf144e68ab1ea43579f85f572",
                           "commits": ["064d2e4ad"], "note": "A commit 064d2e4ad on the G port"},
             "packets": [{"lane": "OWN-20P"}]},
        evidence=[E("R3 bus restart: liveness GA {ga} of the pre-registered twenty ({gl}); G0 passes {g0}; safety GA {gs}, G0 {g0s}",
                    ga=Q("OWN-20P", ["r3", "bus/GA", "pass"]), gl=Q("OWN-20P", ["r3", "liveness_GA_20"]),
                    g0=Q("OWN-20P", ["r3", "bus/G0", "pass"]), gs=Q("OWN-20P", ["r3", "bus/GA", "pass_safety"]),
                    g0s=Q("OWN-20P", ["r3", "bus/G0", "pass_safety"])),
                  E("R3 gate {r}", r=Q("OWN-20P", ["dispositions", "r3_gate"]))],
        missing=["Reconnect triggers only on event-stream end: NoReply and org.a11y.Bus name-owner change are not "
                 "implemented (OWN-20Q is running).",
                 "Owner call: is the current trigger set enough."],
        action="fork candidate review after OWN-20Q",
        dependency=["OWN-20Q (wave 6)", "owner ruling OR-17", "fresh review of this entry"],
        stop="Any stale mutation after a reconnect, or reconnect breaks the quiet path.",
        gate_in=dict(lanes=["OWN-20P"],
                     published=[("exp/own-20p-guard-port-a11y-20261003", "64081dded4e0a3ddf144e68ab1ea43579f85f572")],
                     drift={"base": "cb685fad7", "candidate": "064d2e4ad"},
                     owner=[20], blocked=[], pending=["OWN-20Q"], prs=[]))

    add(id="Q08", title="OWN-20G guard a30cbbc3b (superseded by the OWN-20P G port; privacy rewrite PUB-03 PENDING)",
        delta="The original focus-guard final-read diff, tested on 0f1955d2f plus measurement picks.",
        owner=["kvnloo/cua#20"],
        sha={"candidate": {"branch": "exp/own-20g-guard-final-diff-a2-20261003", "sha": "ce7544cc064cecfd9ba4702466a1d0f24b1799b6",
                           "commits": ["a30cbbc3b230e8bad7d86ae1e89866d4f9cdd1af"],
                           "note": "a30cbbc3b does not apply to clean main; superseded by a761f1f1f (Q06)"},
             "packets": [{"lane": "OWN-20G"}]},
        evidence=[E("R1 reply-delay row: gate (G restores every trial) {r}; specified XGrabServer row gate {g}",
                    r=Q("OWN-20G", ["r1", "reply", "gate_G_20_of_20"]), g=Q("OWN-20G", ["r1", "grab", "gate_G_20_of_20"])),
                  E("R3 bus restart: safety gate {s}; in-process liveness gate {l}",
                    s=Q("OWN-20G", ["r3", "safety_bus_20_each"]), l=Q("OWN-20G", ["r3", "gate_bus_20_each"]))],
        missing=["The published branch carries the local user name in raw xhost output (privacy); PUB-03 is preparing a "
                 "rewrite candidate.",
                 "Owner calls: the reply-delay row in place of the XGrabServer row, and the settle-overshoot IRREDUCIBLE judgement."],
        action="privacy rewrite candidate (owner ruling) - no posting; the product delta moves to Q06",
        dependency=["PUB-03 (wave 6)", "owner rulings PRIV-B and OR-14"],
        stop="Superseded once Q06 is accepted for posting.",
        gate_in=dict(lanes=["OWN-20G"],
                     published=[("exp/own-20g-guard-final-diff-a2-20261003", "ce7544cc064cecfd9ba4702466a1d0f24b1799b6")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "ce7544cc064cecfd9ba4702466a1d0f24b1799b6"},
                     owner=[14, 23], blocked=[13], pending=["PUB-03"], prs=[]))

    add(id="Q09", title="BUG-01 A: foreground trusted click receipt labelled background (fix 2533db6d5 + 49a3adf0f)",
        delta="The click receipt reports delivery=foreground only when the executed branch activates the window. The fix is "
              "the pair 2533db6d5 + 49a3adf0f; neither commit is cited alone (d86b3b1d1 and the superseded fix binary are not cited).",
        owner=["kvnloo/cua#38 (upstream compatibility: trycua/cua 4009, plain text)"],
        sha={"candidate": {"branch": "exp/bug-01-delivery-cdp-sessions-20261002", "sha": "097b4f0974d5c161360fc3683c17f298ff681c70",
                           "commits": ["2533db6d5ad0305c2eeec96ea5e7a5b1aaacab2e", "49a3adf0f0b33446e77c1413fec579090ff2f29a"],
                           "note": "fix pair on base c4d0c6625"},
             "packets": [{"lane": "BUG-01"}]},
        evidence=[E("Baseline trusted-foreground arm: mislabelled background {m} of {n}; fixed: delivery foreground {f}",
                    m=Q("BUG-01", ["part_a", "baseline", "arms", "T", "mislabel_trusted_fg_as_background"]),
                    n=Q("BUG-01", ["part_a", "baseline", "arms", "T", "n"]),
                    f=Q("BUG-01", ["part_a", "fix2", "arms", "T", "click_delivery_mode", "foreground"])),
                  E("Only the delivery mode changed between baseline and the fix pair: {o}",
                    o=Q("BUG-01", ["part_a", "only_delivery_mode_changed_fix2"]))],
        missing=["Recertification on 0f1955d2f or later (Linux/core paths changed on main since c4d0c6625).",
                 "Windows, macOS and embedded labels are UNIT-only."],
        action="fork fix branch for owner review; upstream routing decided by the kvnloo/cua#38 owner (not posted)",
        dependency=["recertification on current main", "fresh review of this entry"],
        stop="The producer branch structure changes upstream, or any other receipt field changes.",
        gate_in=dict(lanes=["BUG-01"],
                     published=[("exp/bug-01-delivery-cdp-sessions-20261002", "097b4f0974d5c161360fc3683c17f298ff681c70")],
                     drift={"base": "c4d0c6625", "candidate": "097b4f0974d5c161360fc3683c17f298ff681c70"},
                     owner=[], blocked=[], pending=[], prs=[]))

    add(id="Q10", title="BUG-01 B: CDP sessions accumulate (attach per call, never detach)",
        delta="Each browser call attaches one CDP session and never detaches it; the post-navigation event burst scales "
              "with the session count. Accumulation only - no fix and no cost on a no-op page.",
        owner=["trycua/cua 4052 (plain text; evidence owner)"],
        sha={"candidate": None, "packets": [{"lane": "BUG-01"}]},
        evidence=[E("Live CDP sessions at the end of each long run: {s}",
                    s=Q("BUG-01", ["part_b", "M1_live_sessions_end_of_L"]))],
        missing=["A cost on a non-trivial page (none measured)."],
        action="evidence note only (no fix)",
        dependency=["fresh review of this entry"],
        stop="Upstream changes CDP session lifetime.",
        gate_in=dict(lanes=["BUG-01"],
                     published=[("exp/bug-01-delivery-cdp-sessions-20261002", "097b4f0974d5c161360fc3683c17f298ff681c70")],
                     drift={"base": "c4d0c6625", "claim_paths": ["libs/cua-driver/rust/crates/cua-driver-core/src/browser"]},
                     owner=[], blocked=[], pending=[], prs=[]))

    add(id="Q11", title="OWN-105 runner reconcile (kvnloo/cua#105 gaps G1-G3 + pre-write rule)",
        delta="Python and TS jev-use runners reconcile an ambiguous mutation receipt before any second dispatch "
              "(no new service).",
        owner=["kvnloo/cua#105"],
        sha={"candidate": {"branch": "exp/own-105-runner-reconcile-20261002", "sha": "b97daa4ba08605c08f6a5da8baf1bf32c5ff4093",
                           "commits": [], "note": "on base 345ff6d9d"},
             "packets": [{"lane": "OWN-105"}]},
        evidence=[E("Fixed runners: trials {t}; duplicates {d}; receipts present {r}; second dispatches {s}",
                    t=Q("OWN-105", ["totals", "fixed_trials"]), d=Q("OWN-105", ["totals", "fixed_duplicates"]),
                    r=Q("OWN-105", ["totals", "fixed_receipts_ok"]), s=Q("OWN-105", ["totals", "fixed_second_dispatches"])),
                  E("Gate verdict {v}; unfixed base reproduces the gap: {u}",
                    v=Q("OWN-105", ["disposition_by_gates", "verdict"]),
                    u=Q("OWN-105", ["disposition_by_gates", "keep_gates", "unfixed_reproduces_gap"]))],
        missing=["Red/green counts live only in gitignored logs: force-add them before posting.",
                 "TS R6 is emulated-state evidence (Python R6 carries the gate alone).",
                 "Recertification on current main (Linux/core paths changed since 345ff6d9d)."],
        action="fork branch + kvnloo/cua#105 comment (fork only)",
        dependency=["fresh review of this entry", "kvnloo/cua#105 head unchanged"],
        stop="kvnloo/cua#105 head moves, or any duplicate mutation on a fixed runner.",
        gate_in=dict(lanes=["OWN-105"],
                     published=[("exp/own-105-runner-reconcile-20261002", "b97daa4ba08605c08f6a5da8baf1bf32c5ff4093")],
                     drift={"base": "345ff6d9d", "candidate": "b97daa4ba08605c08f6a5da8baf1bf32c5ff4093"},
                     owner=[], blocked=[], pending=[], prs=[("kvnloo/cua", 105)]))

    add(id="Q12", title="trycua/cua PR 4336 native timing parity (OWN-75R)",
        delta="trycua/cua PR 4336 adds native timing fields to the jev-use runners with no cross-language field mismatch and "
              "no behaviour change versus its base.",
        owner=["kvnloo/cua#75", "upstream trycua/cua PR 4336 (plain text)"],
        sha={"candidate": {"branch": "exp/own-75r-timing-parity-4336-r1b-20261003", "sha": "efe36d1a1efda084fa37e061dc58c3a98d607c68",
                           "commits": [], "note": "r1b = publish fixes on the accepted packet e02621fdc; PR head 8391cf802"},
             "packets": [{"lane": "OWN-75R"}]},
        evidence=[E("REAL trials verified {v} of {t}; non-loopback refusals by the net guard {g}",
                    v=Q("OWN-75R", ["real_analysis", "trials_verified"]), t=Q("OWN-75R", ["real_analysis", "trials"]),
                    g=Q("OWN-75R", ["real_analysis", "netguard_refused_total"]))],
        missing=["Owner call: the PR emits the timing fields unconditionally (log-only) vs the env-gated / default-off wording.",
                 "kvnloo/cua#75 body still cites an older head (d301a076c).",
                 "Recertification against current main (the PR base predates many Linux/core changes)."],
        action="evidence comment for the trycua/cua PR 4336 owner (drafted on the fork; not posted upstream)",
        dependency=["owner ruling OR-08", "PR head unchanged", "fresh review of this entry"],
        stop="The PR head moves from 8391cf802.",
        gate_in=dict(lanes=["OWN-75R"],
                     published=[("exp/own-75r-timing-parity-4336-r1b-20261003", "efe36d1a1efda084fa37e061dc58c3a98d607c68"),
                                ("exp/own-75r-timing-parity-4336-20261002", "e02621fdc1fe5098efd48af295964f25902553ea")],
                     drift={"base": "2ca90d338", "candidate": "8391cf80275d2a5e7288f9d7c6b0a3e5f7822939"},
                     owner=[8], blocked=[], pending=[], prs=[("trycua/cua", 4336)]))

    add(id="Q13", title="OWN-78A candidate F for trycua/cua PR 4394 (restore form + page + outline) (OWN-78L PENDING)",
        delta="Restore the form, page and outline context in the PR 4394 browser request so the live provider stops "
              "abstaining at step one.",
        owner=["kvnloo/cua#78", "upstream trycua/cua PR 4394 (plain text)"],
        sha={"candidate": {"branch": "exp/own-78a-abstain-isolation-4394-20261003", "sha": "6f6c67955505e5b48f130a69feac9ea11c6e9ed6",
                           "commits": ["61eec09092fd161f62651a890c882f276a642855"], "note": "fix candidate F head 61eec0909"},
             "packets": [{"lane": "OWN-78A"}]},
        evidence=[E("Live TypeSafe step-one isolation: PR abstained {a0}; PR plus form correct {a1}; F correct {a2}; pre-PR correct {a3}",
                    a0=Q("OWN-78A", ["attribution", "A0_abstain"]), a1=Q("OWN-78A", ["attribution", "A1_correct_type"]),
                    a2=Q("OWN-78A", ["attribution", "A2_correct_type"]), a3=Q("OWN-78A", ["attribution", "A3_correct_type"])),
                  E("Attribution {v}; disposition {d}", v=Q("OWN-78A", ["attribution", "verdict"]),
                    d=Q("OWN-78A", ["disposition"]))],
        missing=["R1-lite on F (OWN-78L is running).",
                 "Full-n live R1 / R4: BLOCKED (paid budget).",
                 "S1 backend row: BLOCKED (owner decision; adapter not local).",
                 "The remaining A2-vs-A3 gap (question key, instructions, goal / history placement, visual): BLOCKED (budget)."],
        action="hold; evidence comment for kvnloo/cua#78 after OWN-78L (fork only)",
        dependency=["OWN-78L (wave 6)", "owner rulings OR-11 and OR-20", "PR head unchanged"],
        stop="The trycua/cua PR 4394 head moves from 039257811.",
        gate_in=dict(lanes=["OWN-78A"],
                     published=[("exp/own-78a-abstain-isolation-4394-20261003", "6f6c67955505e5b48f130a69feac9ea11c6e9ed6")],
                     drift={"base": "2ca90d338", "candidate": "61eec0909"},
                     owner=[22], blocked=[4, 6, 7], pending=["OWN-78L"], prs=[("trycua/cua", 4394)]))

    # ------------------------------------------------------------- measured deletions (knob evidence)
    add(id="Q14", title="B-02 H_V browser admission tools-list cache",
        delta="Cache the validated tools/list at MCP admission instead of re-validating it per call (browser).",
        owner=["kvnloo/cua#93", "kvnloo/cua#10"],
        sha={"candidate": {"branch": "exp/r2-10r-recert-a3-20261003", "sha": "d22eeb2ecf8a679d1425c21120a599775aa0817d",
                           "commits": ["770a715edc080d432134f7d10b30d025e78509d6"],
                           "note": "measurement-only env-gated knob (B-02) carried in R'; no product diff exists yet"},
             "packets": [{"lane": "B-02"}, {"lane": "R2-10R"}]},
        evidence=[E("B-02 fill: verdict {v}; admission component saving {s} ms", v=Q("B-02", ["browser", "measured", "classes", "fill", "V", "verdict"]),
                    s=Q("B-02", ["browser", "measured", "classes", "fill", "V", "saving_median_ms"], 1)),
                  E("B-02 toggle verdict {t}; modal verdict {m}", t=Q("B-02", ["browser", "measured", "classes", "toggle", "V", "verdict"]),
                    m=Q("B-02", ["browser", "measured", "classes", "modal", "V", "verdict"])),
                  E("On R' inside COMP: admission work removed per fill trial {w} ms",
                    w=Q("R2-10R", ["browser", "scripted", "work_deleted_vs_wall_clock", "fill", "component_mean_ms_deleted", "mcp_admission"], 1))],
        missing=["A product (non-env-gated) diff with unit tests; the knob is measurement-only.",
                 "Modal is NOT_MATERIAL on the B-02 binary."],
        action="product-change proposal (default behaviour change; needs a reviewed product diff first)",
        dependency=["a reviewed product diff", "fresh review of this entry"],
        stop="A product diff changes the tools/list envelope bytes.",
        gate_in=dict(lanes=["B-02", "R2-10R"],
                     published=[("exp/b-02-browser-driver-sites-20261002", "b282ff3894fa85a7b82257cb1edd5088c2f0ac37"),
                                ("exp/r2-10r-recert-a3-20261003", "d22eeb2ecf8a679d1425c21120a599775aa0817d")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "45dff8f32"},
                     owner=[], blocked=[], pending=[], prs=[]))

    add(id="Q15", title="N-04 V native admission tools-list cache",
        delta="The same admission tools-list cache on the native GTK3 path.",
        owner=["kvnloo/cua#93", "kvnloo/cua#10"],
        sha={"candidate": {"branch": "exp/n-04-native-composition-rprime-20261003", "sha": "9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2",
                           "commits": [], "note": "measurement-only knob on R'n; PUB-03 is preparing a privacy rewrite (r1c) of this branch"},
             "packets": [{"lane": "N-04"}, {"lane": "N-03"}]},
        evidence=[E("N-04 verdict {v}; T saved checkbox {c} ms {cc}, text {t} ms {tc}",
                    v=Q("N-04", ["gates", "V", "verdict"]),
                    c=Q("N-04", ["k1", "contrasts", "checkbox/X-vs-X+V", "wall_clock_T_ms", "median"], 2),
                    cc=Q("N-04", ["k1", "contrasts", "checkbox/X-vs-X+V", "wall_clock_T_ms", "ci95"], 2),
                    t=Q("N-04", ["k1", "contrasts", "text/X-vs-X+V", "wall_clock_T_ms", "median"], 2),
                    tc=Q("N-04", ["k1", "contrasts", "text/X-vs-X+V", "wall_clock_T_ms", "ci95"], 2)),
                  E("Admission work deleted: checkbox {c} ms, text {t} ms",
                    c=Q("N-04", ["k1", "contrasts", "checkbox/X-vs-X+V", "work_admission_v_ms", "median"], 2),
                    t=Q("N-04", ["k1", "contrasts", "text/X-vs-X+V", "work_admission_v_ms", "median"], 2)),
                  E("Replicated on N3 (N-03): checkbox verdict {c}, text verdict {t}",
                    c=Q("N-03", ["gates", "V/checkbox", "verdict"]), t=Q("N-03", ["gates", "V/text", "verdict"]))],
        missing=["A product (non-env-gated) diff with unit tests; the knob is measurement-only."],
        action="product-change proposal (with Q14; one admission cache for both paths)",
        dependency=["PUB-03 (wave 6) r1c publication head", "a reviewed product diff", "fresh review of this entry"],
        stop="A product diff changes the tools/list envelope bytes.",
        gate_in=dict(lanes=["N-04", "N-03"],
                     published=[("exp/n-04-native-composition-rprime-20261003", "9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2"),
                                ("exp/n-03-native-closure-axfg-a3-20261003", "6b70ec9024cc3921f7637bba2ffabcc93e29fc77")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218", "candidate": "9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2"},
                     owner=[], blocked=[], pending=["PUB-03"], prs=[]))

    add(id="Q16", title="Post-DoAction sleep deletion scope (N-01R / R2-09 / N-03)",
        delta="Delete the fixed post-DoAction sleep on the measured routes: GTK3 AT-SPI background (N-01R), Chromium AT-SPI "
              "background (R2-09, qualified by the focus-change condition) and GTK3 X11 ax_fg at the default config (N-03).",
        owner=["kvnloo/cua#93", "kvnloo/cua#10", "kvnloo/cua#20 (settle watch)"],
        sha={"candidate": {"branch": "exp/r2-10r-recert-a3-20261003", "sha": "d22eeb2ecf8a679d1425c21120a599775aa0817d",
                           "commits": ["8f4f8b54211f0bc0530c61aba016966142fc11a9"],
                           "note": "measurement-only N-01R knob carried in R'; no product diff yet"},
             "packets": [{"lane": "N-01R"}, {"lane": "R2-09"}, {"lane": "N-03"}, {"lane": "N-04"}]},
        evidence=[E("N-01R GTK3 background: checkbox verdict {c} (saving {cs} ms), text verdict {t} (saving {ts} ms)",
                    c=Q("N-01R", ["gates", "H_S", "checkbox", "verdict"]), cs=Q("N-01R", ["gates", "H_S", "checkbox", "saving_ms"], 1),
                    t=Q("N-01R", ["gates", "H_S", "text", "verdict"]), ts=Q("N-01R", ["gates", "H_S", "text", "saving_ms"], 1)),
                  E("R2-09 Chromium background: S0 saves {s} ms {ci} on checkbox",
                    s=Q("R2-09", ["paired_vs_base", "M/checkbox/B-S0", "T_base_minus_arm_median"], 1),
                    ci=Q("R2-09", ["paired_vs_base", "M/checkbox/B-S0", "ci95"], 1)),
                  E("N-03 X11 ax_fg: verdict {v}; click wrapper saved {s} ms {ci}",
                    v=Q("N-03", ["gates", "axfg_S0/D", "verdict"]),
                    s=Q("N-03", ["part_b", "D/checkbox", "click_wrapper_saved_ms", "median"], 2),
                    ci=Q("N-03", ["part_b", "D/checkbox", "click_wrapper_saved_ms", "ci95"], 2)),
                  E("On R'n the sleep is gone from the best arm: post-action sleep work deleted {w} ms (checkbox)",
                    w=Q("N-04", ["e2", "checkbox", "work_deleted_BASE_minus_best_ms", "post_action_sleep"], 2))],
        missing=["WebKitGTK targets: NOT_RUN (owner decision on installing WebKitGTK).",
                 "Hyprland foreground route: BLOCKED (real seat).",
                 "A product diff: the deletion is measured through an env-gated knob only."],
        action="product-change proposal, scoped to the measured routes (default behaviour change)",
        dependency=["owner ruling OR-10", "a reviewed product diff", "fresh review of this entry"],
        stop="A focus-steal control misses silently with the sleep removed, or a new route lacks the settle watch.",
        gate_in=dict(lanes=["N-01R", "R2-09", "N-03", "N-04"],
                     published=[("exp/n-01r-native-wait-ab-20261002", "3bb4a7fc70d1d58984b19a7a357892a7c9af31fa"),
                                ("exp/r2-09-native-event-wake-r1b-20261003", "ffb4919a7b5bff9cc92e2a798663439a76d8f0b3"),
                                ("exp/n-03-native-closure-axfg-a3-20261003", "6b70ec9024cc3921f7637bba2ffabcc93e29fc77")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218", "candidate": "45dff8f32"},
                     owner=[10], blocked=[9], pending=[], prs=[]))

    add(id="Q17", title="R2-03 guarded completion = trycua/cua PR 4316",
        delta="trycua/cua PR 4316 completes a guarded fill->submit without the second provider decision.",
        owner=["kvnloo/cua#10", "kvnloo/cua#87", "upstream trycua/cua PR 4316 (plain text)"],
        sha={"candidate": {"branch": "exp/r2-03-guarded-live-20261001", "sha": "6bab214abb707a3db9e8a7d641d160c3f58e08d5",
                           "commits": [], "note": "tested PR head a0bca7440"},
             "packets": [{"lane": "R2-03"}]},
        evidence=[E("Live TypeSafe: provider requests baseline {b}, guarded {g}; paired verified-time difference {d} ms {ci}",
                    b=Q("R2-03", ["main", "baseline", "provider_http_attempts_total"]),
                    g=Q("R2-03", ["main", "guarded", "provider_http_attempts_total"]),
                    d=Q("R2-03", ["paired_guarded_minus_baseline", "task_verified_ms", "median_diff_ms"], 1),
                    ci=Q("R2-03", ["paired_guarded_minus_baseline", "task_verified_ms", "bootstrap95_median"], 1)),
                  E("Disposition {d}", d=Q("R2-03", ["gates", "disposition"]))],
        missing=["kvnloo/cua#107 D (other track, exp/i107-d-20261002 at 6d1c60926): the guard accepted a Submit relocated into "
                 "another form and submitted to a decoy (missing form-scope fact). Wrong-target breach; blocks promotion.",
                 "Guarded completion binds nothing on toggle / modal (no saving there).",
                 "Recertification of the live claim on current main (live layer on R' is BLOCKED by budget)."],
        action="evidence comment for the trycua/cua PR 4316 owner, including the wrong-target finding (drafted on the fork; not posted upstream)",
        dependency=["a form-scope fix for the decoy case", "PR head unchanged", "fresh review of this entry"],
        stop="The PR head moves from a0bca7440, or any wrong-target submit.",
        gate_in=dict(lanes=["R2-03"],
                     published=[("exp/r2-03-guarded-live-20261001", "6bab214abb707a3db9e8a7d641d160c3f58e08d5"),
                                ("exp/i107-d-20261002", "6d1c609261289d73833395d390d1150ad2187285")],
                     drift={"base": "345ff6d9d", "candidate": "a0bca744067d04f05904319d3d919be30c336556"},
                     owner=[], blocked=[0], pending=[], prs=[("trycua/cua", 4316)]))

    add(id="Q18", title="R2-07b fill compiled replay (re-qualified by FIX-01)",
        delta="A compiled fresh-bound fill->submit routine replays without provider decisions on warm runs, with fresh "
              "authority before each replayed mutation and bounded fallback.",
        owner=["kvnloo/cua#93 (R2-07)", "kvnloo/cua#10"],
        sha={"candidate": {"branch": "exp/r2-10-composition-20261002", "sha": "030f6bdbf811e124e11daa2de0569bffb993b66d",
                           "commits": [], "note": "measured inside R2-10's fill COMP arm on R; the R2-07 packet itself stays KILL"},
             "packets": [{"lane": "R2-10"}, {"lane": "FIX-01"}]},
        evidence=[E("Live fill on R: provider requests per trial BASE {b} -> COMP {c}; provider work removed {w} ms per trial",
                    b=Q("R2-10", ["browser", "live", "work_deleted_vs_wall_clock", "fill", "provider_decisions_per_trial", "BASE"]),
                    c=Q("R2-10", ["browser", "live", "work_deleted_vs_wall_clock", "fill", "provider_decisions_per_trial", "COMP"], 3),
                    w=Q("R2-10", ["browser", "live", "work_deleted_vs_wall_clock", "fill", "component_mean_ms_deleted", "provider_decision"], 1)),
                  E("Live fill amortized S (all invocations incl. training) {s} {ci}",
                    s=Q("R2-10", ["browser", "live", "S", "COMP", "fill", "amortized_mean_ratio", "S"], 2),
                    ci=Q("R2-10", ["browser", "live", "S", "COMP", "fill", "amortized_mean_ratio", "ci95"], 2))],
        missing=["Live recertification on R' (0f1955d2f): BLOCKED (paid budget).",
                 "A product shape: no routine framework or route miner is proposed (parked by kvnloo/cua#74); this stays research evidence."],
        action="research evidence for the trycua/cua issue 3963 rewrite draft (DOC-3963); no upstream posting",
        dependency=["owner ruling OR-11 (budget)", "DOC-3963 (wave 6)"],
        stop="Any blind replay of a may-have-landed effect, or a fallback that skips fresh authority.",
        gate_in=dict(lanes=["R2-10", "FIX-01"],
                     published=[("exp/r2-10-composition-20261002", "030f6bdbf811e124e11daa2de0569bffb993b66d")],
                     drift={"base": "989cc76ce", "claim_paths": ["libs/cua-driver/examples/jev-use",
                                                                 "libs/cua-driver/rust/crates/cua-driver-core/src/browser"]},
                     owner=[22], blocked=[0], pending=["DOC-3963"], prs=[]))

    add(id="Q19", title="R2-07c/d/e toggle and modal compiled replay (R2-07e PENDING)",
        delta="The compiled fresh-bound routine for toggle->confirm and modal->act.",
        owner=["kvnloo/cua#93 (R2-07)", "kvnloo/cua#10"],
        sha={"candidate": {"branch": "exp/r2-07d-quiet-timing-phase-l-20261003", "sha": "79f6dd29958b2a73b477544ca9e777efade8a6c3",
                           "commits": [], "note": "tested on R (12b9045a); no Driver change"},
             "packets": [{"lane": "R2-07c"}, {"lane": "R2-07d"}]},
        evidence=[E("Quiet-window non-regression (CR - COMP): toggle {t} ms {tc} gate {tg}; modal {m} ms {mc} gate {mg}",
                    t=Q("R2-07d", ["phase_S", "toggle", "timing", "diff_COMP_CR_minus_COMP_ms", "median"], 1),
                    tc=Q("R2-07d", ["phase_S", "toggle", "timing", "diff_COMP_CR_minus_COMP_ms", "ci95"], 1),
                    tg=Q("R2-07d", ["phase_S", "toggle", "timing", "gate_ci_upper_le_2ms"]),
                    m=Q("R2-07d", ["phase_S", "modal", "timing", "diff_COMP_CR_minus_COMP_ms", "median"], 1),
                    mc=Q("R2-07d", ["phase_S", "modal", "timing", "diff_COMP_CR_minus_COMP_ms", "ci95"], 1),
                    mg=Q("R2-07d", ["phase_S", "modal", "timing", "gate_ci_upper_le_2ms"])),
                  E("Correctness (R2-07c): accepted mutations all fresh, non-fresh attempts refused ({n} attempts)",
                    n=Q("R2-07c", ["G3", "nonfresh_attempts"])),
                  E("Phase L status: {p}", p=Q("R2-07d", ["disposition", "phase_L_status"]))],
        missing=["A passing modal gate (R2-07e is running a new pre-registered block).",
                 "Live Phase L (provider decisions are most of live toggle / modal T): NOT_RUN; paid budget."],
        action="hold (research evidence; excluded from the composed toggle / modal configuration)",
        dependency=["R2-07e (wave 6)", "owner ruling OR-11 (budget)"],
        stop="The modal gate fails again, or any E4 violation.",
        gate_in=dict(lanes=["R2-07c", "R2-07d"],
                     published=[("exp/r2-07d-quiet-timing-phase-l-20261003", "79f6dd29958b2a73b477544ca9e777efade8a6c3"),
                                ("exp/r2-07c-toggle-modal-compiled-a2-20261003", "7f46edd1681fbf58586f8b4972636c3da56e3be6")],
                     drift={"base": "989cc76ce", "claim_paths": ["libs/cua-driver/examples/jev-use",
                                                                 "libs/cua-driver/rust/crates/cua-driver-core/src/browser"]},
                     owner=[17, 22], blocked=[1, 2], pending=["R2-07e"], prs=[]))

    add(id="Q20", title="R2-08 API route per task (owner ruling)",
        delta="Use the fixture's existing POST /submit route instead of the GUI route when per-task equivalence and "
              "authorization evidence exist.",
        owner=["kvnloo/cua#93 (R2-08)", "kvnloo/cua#10"],
        sha={"candidate": None, "packets": [{"lane": "R2-08"}]},
        evidence=[E("Equivalence on the base fixture: {e} of {r} rounds; disposition {d}",
                    e=Q("R2-08", ["base_equivalence", "equivalent"]), r=Q("R2-08", ["base_equivalence", "rounds"]),
                    d=Q("R2-08", ["disposition"]))],
        missing=["Per-task equivalence and authorization evidence for any real task; the measured route is a fixture route."],
        action="owner ruling",
        dependency=["owner"],
        stop="An API route is proposed as a default.",
        gate_in=dict(lanes=["R2-08"], published=[("exp/r2-08-cross-surface-20261002", "afba150d55426bf775cb10adaa698cf99493b229")],
                     drift=None, owner=[5], blocked=[], pending=[], prs=[]))

    add(id="Q21", title="B-01 fast feedback glide / glide-off policy (owner ruling)",
        delta="Shorten the awaited agent-cursor glide (fast glide) or turn feedback off; the glide is most of default "
              "browser BASE T.",
        owner=["kvnloo/cua#10", "kvnloo/cua#93 (R2-01)"],
        sha={"candidate": None, "packets": [{"lane": "B-01R"}, {"lane": "R2-10"}]},
        evidence=[E("Fast glide (H_V) fill: verdict {v}; share of the feedback-off saving recovered {r}",
                    v=Q("B-01R", ["hypotheses", "H_V", "fill", "verdict"]), r=Q("B-01R", ["hypotheses", "H_V", "fill", "ratio", "R"], 3)),
                  E("KEEP-only composition on R (glide left on): fill S {s}",
                    s=Q("R2-10", ["browser", "scripted", "S", "COMP_K", "fill", "all", "S"], 2))],
        missing=["A product decision on visual-feedback policy; the knob is measurement-only."],
        action="owner ruling",
        dependency=["owner"],
        stop="Visual feedback becomes a user-facing contract.",
        gate_in=dict(lanes=["B-01R", "R2-10"], published=[("exp/b-01r-browser-critpath-textfix-20261002", "0cd63f786290f967f41a5a6b615d54f98045ebec")],
                     drift=None, owner=[3], blocked=[], pending=[], prs=[]))

    add(id="Q22", title="B-01 H_C / N-02 HC caller-compiled output validators",
        delta="The caller compiles output-schema validators once instead of validating each result from scratch (client side).",
        owner=["kvnloo/cua#10", "kvnloo/cua#93"],
        sha={"candidate": None, "packets": [{"lane": "B-01R"}, {"lane": "N-02"}]},
        evidence=[E("Browser H_C toggle verdict {v}", v=Q("B-01R", ["hypotheses", "H_C", "toggle", "verdict"])),
                  E("Native HC checkbox verdict {c} (saving {cs} ms); text verdict {t} (saving {ts} ms)",
                    c=Q("N-02", ["gates", "HC", "checkbox", "verdict"]), cs=Q("N-02", ["gates", "HC", "checkbox", "saving_ms"], 1),
                    t=Q("N-02", ["gates", "HC", "text", "verdict"]), ts=Q("N-02", ["gates", "HC", "text", "saving_ms"], 1))],
        missing=["Eager compilation costs time per session; the lazy form (HCL) is an owner decision on session shape (Q23)."],
        action="client-side change proposal for the jev-use runners (after the HCL ruling)",
        dependency=["owner ruling Q23 (HCL)", "fresh review of this entry"],
        stop="Any validation outcome differs from the uncompiled validator.",
        gate_in=dict(lanes=["B-01R", "N-02"], published=[("exp/n-02-native-transport-20261002", "9846ac8033a8b5e952b0d44f39858625375d54e1")],
                     drift=None, owner=[16], blocked=[], pending=[], prs=[]))

    add(id="Q23", title="HCL lazy per-schema validators (owner ruling)",
        delta="Compile each output validator lazily on first use: about zero at one task per session, a saving per multi-task session.",
        owner=["kvnloo/cua#10"],
        sha={"candidate": None, "packets": [{"lane": "N-04"}, {"lane": "N-03"}]},
        evidence=[E("N-04 checkbox: at one task {k1} ms; per five-task session {k5} ms; verdict {v}",
                    k1=Q("N-04", ["k1", "contrasts", "checkbox/X+V-vs-X+V+HCL", "wall_clock_T_ms", "median"], 2),
                    k5=Q("N-04", ["k5", "contrasts", "checkbox/X+V-vs-X+V+HCL", "sum_T_ms", "median"], 2),
                    v=Q("N-04", ["gates", "HCL/checkbox", "verdict"]))],
        missing=["The expected session shape (tasks per session) - an owner decision."],
        action="owner ruling",
        dependency=["owner"],
        stop="—",
        gate_in=dict(lanes=["N-04", "N-03"], published=[], drift=None, owner=[16], blocked=[], pending=[], prs=[]))

    # ------------------------------------------------------------------------ owner rulings
    def ruling(id_, title, refs, blocked=(), lanes=(), pending=(), evidence=(), dep=None, stop="—", owner=("kvnloo/cua#73",),
               delta=None):
        add(id=id_, title=title, delta=delta or title, owner=list(owner), sha={"candidate": None, "packets": [{"lane": l} for l in lanes]},
            evidence=list(evidence), missing=["The owner's ruling."], action="owner ruling",
            dependency=dep or ["owner"], stop=stop,
            gate_in=dict(lanes=list(lanes), published=[], drift=None, owner=list(refs), blocked=list(blocked),
                         pending=list(pending), prs=[]))

    ruling("OR-01", "OWN-36 I3s: shared-window replacement retirement", [0], lanes=["OWN-36"], owner=["kvnloo/cua#36"])
    ruling("OR-02", "B-02 H_E endpoint re-proof bound check (security policy)", [1], lanes=["B-02"], owner=["kvnloo/cua#73", "kvnloo/cua#10"],
           evidence=[E("B-02 fill endpoint verdict {v}; saving {s} ms",
                       v=Q("B-02", ["browser", "measured", "classes", "fill", "E", "verdict"]),
                       s=Q("B-02", ["browser", "measured", "classes", "fill", "E", "saving_median_ms"], 1))])
    ruling("OR-03", "B-01 H_T: 100 ms insert_text focus settle", [2], lanes=["B-01R"], owner=["kvnloo/cua#10"],
           evidence=[E("Verdict {v}", v=Q("B-01R", ["hypotheses", "H_T", "verdict"]))])
    ruling("OR-04", "N-01R H_C: native cursor reveal (text entry)", [4], lanes=["N-04"], owner=["kvnloo/cua#10"],
           evidence=[E("Reveal work removed on R'n text, BASE to best: {w} ms",
                       w=Q("N-04", ["e2", "text", "work_deleted_BASE_minus_best_ms", "reveal"], 1))])
    ruling("OR-06", "OWN-09R timeout semantics: bounded coordinator wait vs leaked-closure guards", [6], lanes=["OWN-09R"],
           owner=["kvnloo/cua#9", "kvnloo/cua#84"])
    ruling("OR-07", "OWN-09R / kvnloo/cua#9 R8: implement MCP notifications/cancelled or keep it ignored", [7], lanes=["OWN-09R"],
           owner=["kvnloo/cua#9", "kvnloo/cua#84"])
    ruling("OR-08", "trycua/cua PR 4336 timing fields emitted unconditionally vs env-gated wording", [8], lanes=["OWN-75R"],
           owner=["kvnloo/cua#75"])
    ruling("OR-09", "OWN-16W: JSON null refusal and the analyzer-vs-PREREG reading", [9, 21], lanes=["RECERT-FIX"], owner=["kvnloo/cua#16"])
    ruling("OR-10", "R2-09 T3: install WebKitGTK (or use the flatpak runtime), or accept BLOCKED", [10], blocked=[8], lanes=["R2-09"],
           owner=["kvnloo/cua#93"])
    ruling("OR-11", "TypeSafe budget allocation for the remaining reached requests (live R' recertification, live toggle/modal, "
                    "kvnloo/cua#78 R1/R4, native live arms) or a cap raise", [11, 17, 22], blocked=[0, 1, 6, 7],
           owner=["kvnloo/cua#73"])
    ruling("OR-12", "RECERT-FIX wave-4 cross-lane pkill ruling", [12], blocked=[14], owner=["kvnloo/cua#73"])
    ruling("OR-14", "OWN-20G: reply-delay R1 row in place of the XGrabServer row; settle overshoot as IRREDUCIBLE coverage", [14],
           lanes=["OWN-20G"], owner=["kvnloo/cua#20"])
    ruling("OR-15", "Browser per-process cold first snapshot: accept B-06's post-hoc amendment reading or fund a fresh run (B-08 PENDING)",
           [15, 18], blocked=[11], lanes=["B-06"], pending=["B-08"], owner=["kvnloo/cua#10", "kvnloo/cua#73"],
           evidence=[E("B-06 primary verdict fill {p}; amended fill {a} (D {d} ms {ci})",
                       p=Q("B-06", ["classes", "fill", "verdict"]),
                       a=Q("B-06", ["block_x_amendment_1", "classes", "fill", "verdict"]),
                       d=Q("B-06", ["block_x_amendment_1", "classes", "fill", "D_C_minus_Wa", "median"], 1),
                       ci=Q("B-06", ["block_x_amendment_1", "classes", "fill", "D_C_minus_Wa", "ci"], 1))])
    ruling("OR-16", "OWN-09R strict PREREG reading of the head-core unit row (Deviation 6)", [19], lanes=["RECERT-FIX"],
           owner=["kvnloo/cua#9", "kvnloo/cua#84"])
    ruling("OR-17", "OWN-20P: marked-twin R1 substitution and A's trigger set", [20], lanes=["OWN-20P"], pending=["OWN-20Q"],
           owner=["kvnloo/cua#20"])
    ruling("OR-18", "Driver telemetry on by default in lane sessions (set it off in the shared session wrapper)", [24],
           owner=["kvnloo/cua#73"])
    ruling("OR-19", "Fail-closed guard that rejects code-executing commands outside the hostless wrapper", [], blocked=[15],
           owner=["kvnloo/cua#73"])
    ruling("OR-20", "kvnloo/cua#78 S1 backend row (adapter not local; only TypeSafe permitted)", [], blocked=[4],
           lanes=["OWN-78A"], owner=["kvnloo/cua#78"])
    ruling("OR-21", "Native T definition: may native whole-task T exclude provider decisions (scripted chooser), or fund live native arms",
           [], blocked=[3], owner=["kvnloo/cua#10"])

    # ----------------------------------------------------------- published-fork privacy candidates
    add(id="PRIV-A", title="Published fork branch exp/r2-10-composition-20261002 carries an encoded private-name list (PUB-02 r1c)",
        delta="Replace the published R2-10 branch history with the clean rewrite r1c, or delete and re-push, or accept.",
        owner=["kvnloo/cua#73"],
        sha={"candidate": {"branch": "exp/r2-10-composition-r1c-20261003", "sha": "eaca68df9d7f4757028ba787f2e2fa82c92bafe7",
                           "commits": [], "note": "held locally, not pushed (PUB-02 B)"},
             "packets": [{"lane": "PUB-02"}, {"lane": "R2-10"}]},
        evidence=[E("The R2-10 summary blob is identical at the published head and at r1c: {same}",
                    same={"value": True, "check": {"op": "same_blob", "a": ["030f6bdbf811e124e11daa2de0569bffb993b66d",
                                                                            "docs/experiments/r2-10-composition-2026-10-02/r2-10-summary.json"],
                                                    "b": ["eaca68df9d7f4757028ba787f2e2fa82c92bafe7",
                                                          "docs/experiments/r2-10-composition-2026-10-02/r2-10-summary.json"]}})],
        missing=["The owner's ruling (force-replace, delete and re-push, or accept)."],
        action="owner ruling, then a privacy rewrite on the fork",
        dependency=["owner"],
        stop="—",
        gate_in=dict(lanes=["PUB-02", "R2-10"],
                     published=[("exp/r2-10-composition-20261002", "030f6bdbf811e124e11daa2de0569bffb993b66d")],
                     not_published=[("exp/r2-10-composition-r1c-20261003", "eaca68df9d7f4757028ba787f2e2fa82c92bafe7")],
                     drift=None, owner=[13, 23], blocked=[13], pending=[], prs=[]))

    add(id="PRIV-B", title="Published fork branch exp/own-20g-guard-final-diff-a2-20261003 carries the local user name in raw output (PUB-03 PENDING)",
        delta="Replace the published OWN-20G branch with a scrubbed rewrite, or delete and re-push, or accept.",
        owner=["kvnloo/cua#73", "kvnloo/cua#20"],
        sha={"candidate": None, "packets": [{"lane": "OWN-20G"}]},
        evidence=[],
        missing=["A rewrite candidate (PUB-03 is preparing r1c).", "The owner's ruling."],
        action="owner ruling, then a privacy rewrite on the fork",
        dependency=["PUB-03 (wave 6)", "owner"],
        stop="—",
        gate_in=dict(lanes=["OWN-20G"],
                     published=[("exp/own-20g-guard-final-diff-a2-20261003", "ce7544cc064cecfd9ba4702466a1d0f24b1799b6")],
                     drift=None, owner=[23], blocked=[13], pending=["PUB-03"], prs=[]))
    return I


# ------------------------------------------------------------------------------ gate checks

def ls_remote(remote, refs):
    p = C.git("ls-remote", remote, *refs, check=False)
    out = {}
    for line in p.stdout.splitlines():
        sha, ref = line.split("\t")
        out[ref] = sha
    return out, p.returncode


def drift_check(spec):
    base = C.full_sha(spec["base"])
    drift = [x for x in C.git("diff", "--name-only", base, MAIN_PIN, "--", "libs/cua-driver").stdout.splitlines() if x]
    nonallow = [x for x in drift if not DRIFT_ALLOW.search(x)]
    if spec.get("candidate"):
        cand = C.full_sha(spec["candidate"])
        claim = [x for x in C.git("diff", "--name-only", base, cand, "--", "libs").stdout.splitlines() if x]
        inter = sorted(set(claim) & set(drift))
    else:
        cand = None
        claim = list(spec["claim_paths"])
        inter = sorted(x for x in drift if any(x.startswith(p) for p in claim))
    return {"base": base, "candidate": cand, "pin": MAIN_PIN, "drift_files": len(drift),
            "drift_non_allowlisted": nonallow, "claim_files": len(claim), "intersection": inter,
            "value": (not inter) and (not nonallow)}


def gates_for(it, ext, heads, prheads):
    g = it["gate_in"]
    acc_all = set(x for v in ext["accepted_by_wave"].values() for x in v)
    lanes_ok = all(l in acc_all or (l == "B-01R" and "B-01R" in acc_all) for l in g["lanes"])
    out = {}
    out["accepted_packet"] = {"value": bool(g["lanes"]) and lanes_ok,
                              "basis": "lanes %s accepted in STATE (accepted_by_wave)" % ", ".join(g["lanes"]) if g["lanes"]
                              else "no packet backs this entry"}
    pub = []
    pubs = list(g["published"])
    for l in g["lanes"]:
        br, sha, _d, _f = QP[l]
        if not any(b == br for b, _ in pubs):
            pubs.append((br, sha))
    for br, sha in pubs:
        full = C.full_sha(sha)
        got = heads.get("refs/heads/" + br)
        pub.append({"branch": br, "sha": full, "origin": got, "ok": got == full})
    for br, sha in g.get("not_published", []):
        got = heads.get("refs/heads/" + br)
        pub.append({"branch": br, "sha": C.full_sha(sha), "origin": got, "ok": got is None, "expect": "absent"})
    out["published_on_origin"] = {"value": bool(pub) and all(p["ok"] for p in pub), "refs": pub,
                                  "basis": "git ls-remote origin" if pub else "nothing to publish for this entry"}
    if g["drift"]:
        d = drift_check(g["drift"])
        out["recertified_or_drift_free"] = dict(d, basis="libs/cua-driver drift from the certified base to the pinned main: "
                                                         "no overlap with the claim and only non-Linux allowlisted paths")
    else:
        out["recertified_or_drift_free"] = {"value": True, "basis": "not applicable: no libs/cua-driver claim"}
    odp = ext["owner_decisions_pending"]
    blk = ext["blocked_items_w5"]
    owner_blk = [i for i in g["blocked"] if "owner" in blk[i].lower()]
    out["no_pending_owner_decision"] = {
        "value": not g["owner"] and not owner_blk,
        "owner_decisions_pending": [{"index": i, "head": odp[i][:90]} for i in g["owner"]],
        "blocked_items_owner": [{"index": i, "head": blk[i][:90]} for i in owner_blk],
        "basis": "STATE owner_decisions_pending / blocked_items_w5 entries cited by index"}
    out["no_pending_w6_lane"] = {"value": not g["pending"], "lanes": [{"lane": l, "branch": PENDING_W6[l]} for l in g["pending"]],
                                 "basis": "wave-6 lanes still running (planner assignment)"}
    prs = []
    for repo, num in g["prs"]:
        pin = PR_PINS[(repo, num)]
        got = prheads.get((repo, num))
        prs.append({"repo": repo, "number": num, "pinned": pin, "live": got, "ok": got == pin})
    out["pr_head_unchanged"] = {"value": all(p["ok"] for p in prs), "prs": prs,
                                "basis": "git ls-remote refs/pull/N/head" if prs else "no live PR for this entry"}
    out["fresh_review_done"] = {"value": False, "basis": FRESH_REVIEW_BASIS}
    out["READY_NOW"] = all(v["value"] for k, v in out.items() if k != "READY_NOW")
    return out


def render_evidence(e):
    vals = {}
    for k, p in e["n"].items():
        x = p["value"]
        nd = p.get("from", {}).get("round") if isinstance(p, dict) and "from" in p else None
        vals[k] = C.fmt(x, nd) if not isinstance(x, (dict,)) else json.dumps(x, sort_keys=True)
    return e["t"].format(**vals)


def build():
    ext = state_extract()
    os.makedirs(os.path.dirname(EXTRACT), exist_ok=True)
    with open(EXTRACT, "w") as f:
        json.dump(ext, f, indent=1)
        f.write("\n")
    its = items()
    branches = sorted({br for it in its for br, _ in it["gate_in"]["published"] + it["gate_in"].get("not_published", [])} |
                      {QP[l][0] for it in its for l in it["gate_in"]["lanes"]})
    t0 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    heads, rc = ls_remote(ORIGIN_URL, ["refs/heads/" + b for b in branches])
    pr_refs_t = ["refs/pull/%d/head" % n for (r, n) in PR_PINS if r == "trycua/cua"]
    pr_refs_k = ["refs/pull/%d/head" % n for (r, n) in PR_PINS if r == "kvnloo/cua"]
    up, rc2 = ls_remote(UPSTREAM_URL, pr_refs_t + ["refs/heads/main"])
    ok, rc3 = ls_remote(ORIGIN_URL, pr_refs_k)
    prheads = {}
    for (r, n) in PR_PINS:
        src = up if r == "trycua/cua" else ok
        prheads[(r, n)] = src.get("refs/pull/%d/head" % n)
    t1 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, "ls-remote.json"), "w") as f:
        json.dump({"read_utc": [t0, t1], "origin_heads": heads, "upstream": up, "origin_prs": ok,
                   "rc": [rc, rc2, rc3]}, f, indent=1, sort_keys=True)
        f.write("\n")
    drift_main = [x for x in C.git("diff", "--name-only", "0f1955d2f1ee2b01b40775aa53ea2af0b5544218", MAIN_PIN, "--",
                                   "libs/cua-driver").stdout.splitlines() if x]
    upstream_main_live = up.get("refs/heads/main")
    post_pin = []
    if upstream_main_live and C.sha_exists(upstream_main_live):
        post_pin = [x for x in C.git("diff", "--name-only", MAIN_PIN, upstream_main_live, "--", "libs/cua-driver").stdout.splitlines() if x]
    with open(os.path.join(RAW, "drift.json"), "w") as f:
        json.dump({"pin": MAIN_PIN, "since": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218", "libs_cua_driver_files": drift_main,
                   "non_allowlisted": [x for x in drift_main if not DRIFT_ALLOW.search(x)],
                   "upstream_main_live": upstream_main_live,
                   "post_pin_libs_cua_driver_files": post_pin}, f, indent=1)
        f.write("\n")
    out_items = []
    for it in its:
        gates = gates_for(it, ext, heads, prheads)
        for p in it["sha"].get("packets", []):
            br, sha, d, fsum = QP[p["lane"]]
            p.update({"branch": br, "sha": sha, "packet": d})
        if it["sha"].get("candidate"):
            c = it["sha"]["candidate"]
            c["sha"] = C.full_sha(c["sha"])
            c["commits"] = [C.full_sha(x) for x in c.get("commits", [])]
        out_items.append({
            "id": it["id"], "title": it["title"],
            "fields": {"delta": it["delta"], "canonical_owner": it["owner"], "exact_sha": it["sha"],
                       "completed_evidence": it["evidence"], "missing_evidence": it["missing"],
                       "action_type": it["action"], "dependency": it["dependency"], "stop_condition": it["stop"]},
            "gate_inputs": {k: v for k, v in it["gate_in"].items()},
            "ready_now": gates,
        })
    doc = {
        "schema": "cua-rfc-74-posting-queue/v1",
        "lane": "DOC-10-74 (wave 6)",
        "format": "delta -> canonical owner -> exact SHA -> completed evidence -> missing evidence -> action type -> "
                  "dependency -> stop condition",
        "pinned_main": MAIN_PIN,
        "ready_now_rule": "READY NOW = accepted_packet AND published_on_origin AND recertified_or_drift_free AND "
                          "no_pending_owner_decision AND no_pending_w6_lane AND pr_head_unchanged AND fresh_review_done",
        "pending_w6": PENDING_W6,
        "pr_pins": [{"repo": r, "number": n, "pinned": s} for (r, n), s in PR_PINS.items()],
        "state_extract": os.path.relpath(EXTRACT, HERE),
        "items": out_items,
        "ready_now_count": sum(1 for i in out_items if i["ready_now"]["READY_NOW"]),
    }
    return doc


# --------------------------------------------------------------------------------- rendering

GATE_ORDER = ["accepted_packet", "published_on_origin", "recertified_or_drift_free", "no_pending_owner_decision",
              "no_pending_w6_lane", "pr_head_unchanged", "fresh_review_done"]
GATE_SHORT = ["packet", "origin", "drift", "owner", "w6", "PR", "review"]


def yn(b):
    return "yes" if b else "**no**"


def render(doc):
    L = [BEGIN, ""]
    L.append("Format: `%s`. READY NOW = all seven gates true. Pinned main `%s`." % (doc["format"], doc["pinned_main"][:9]))
    L.append("")
    L.append("**READY NOW: %d of %d entries.**" % (doc["ready_now_count"], len(doc["items"])))
    L.append("")
    L.append("| ID | Entry | Action type | " + " | ".join(GATE_SHORT) + " | READY NOW |")
    L.append("|---|---|---|" + "---|" * len(GATE_SHORT) + "---|")
    for it in doc["items"]:
        g = it["ready_now"]
        L.append("| %s | %s | %s | %s | %s |" % (it["id"], it["title"], it["fields"]["action_type"],
                                               " | ".join(yn(g[k]["value"]) for k in GATE_ORDER), yn(g["READY_NOW"])))
    L.append("")
    for it in doc["items"]:
        f = it["fields"]
        g = it["ready_now"]
        L.append("### %s. %s" % (it["id"], it["title"]))
        L.append("")
        L.append("- **delta** -> %s" % f["delta"])
        L.append("- **canonical owner** -> %s" % "; ".join(f["canonical_owner"]))
        s = f["exact_sha"]
        bits = []
        if s.get("candidate"):
            c = s["candidate"]
            bits.append("candidate `%s` @ `%s`%s (%s)" % (c["branch"], c["sha"][:9],
                        (" commits " + ", ".join("`%s`" % x[:9] for x in c["commits"])) if c.get("commits") else "", c["note"]))
        for p in s.get("packets", []):
            bits.append("packet %s `%s` @ `%s`" % (p["lane"], p["branch"], p["sha"][:9]))
        L.append("- **exact SHA** -> %s" % ("; ".join(bits) if bits else "none (ruling only)"))
        ev = [render_evidence(e) for e in f["completed_evidence"]]
        L.append("- **completed evidence** -> %s" % ("; ".join(ev) if ev else "none beyond the cited packet"))
        L.append("- **missing evidence** -> %s" % " ".join(f["missing_evidence"]))
        L.append("- **action type** -> %s" % f["action_type"])
        L.append("- **dependency** -> %s" % "; ".join(f["dependency"]))
        L.append("- **stop condition** -> %s" % f["stop_condition"])
        why = []
        for k in GATE_ORDER:
            if not g[k]["value"]:
                if k == "no_pending_owner_decision":
                    why.append("owner decision pending (%s)" % ", ".join(
                        ["owner_decisions_pending[%d]" % x["index"] for x in g[k]["owner_decisions_pending"]] +
                        ["blocked_items_w5[%d]" % x["index"] for x in g[k]["blocked_items_owner"]]))
                elif k == "no_pending_w6_lane":
                    why.append("wave-6 lane pending (%s)" % ", ".join(x["lane"] for x in g[k]["lanes"]))
                elif k == "recertified_or_drift_free":
                    why.append("not recertified on pinned main (%d non-allowlisted drift paths, %d overlapping the claim)" % (
                        len(g[k].get("drift_non_allowlisted", [])), len(g[k].get("intersection", []))))
                elif k == "published_on_origin":
                    why.append("not published at the cited SHA" if g[k]["refs"] else "nothing published")
                elif k == "accepted_packet":
                    why.append("no accepted packet")
                elif k == "pr_head_unchanged":
                    why.append("live PR head moved")
                elif k == "fresh_review_done":
                    why.append("fresh review not done")
        L.append("- **READY NOW: %s.** %s" % ("YES" if g["READY_NOW"] else "NO",
                                              ("Failing: " + "; ".join(why) + ".") if why else ""))
        L.append("")
    L.append(END)
    return "\n".join(L)


def main():
    doc = build()
    with open(OUT_JSON, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    gen = render(doc)
    if os.path.exists(README):
        txt = open(README).read()
        if BEGIN in txt and END in txt:
            txt = txt.split(BEGIN)[0] + gen + txt.split(END)[1]
        else:
            txt = txt + "\n" + gen + "\n"
    else:
        txt = gen + "\n"
    with open(README, "w") as f:
        f.write(txt)
    print("queue.json written: %d items, READY NOW %d" % (len(doc["items"]), doc["ready_now_count"]))


if __name__ == "__main__":
    main()
