#!/usr/bin/env python3
"""Build queue.json, raw/ gate evidence and the generated part of README.md for kvnloo/cua#74.

Stdlib only; run under the lane's hostless wrapper. Inputs:
  - accepted packets at exact commits (`git show <sha>:<path>`),
  - the loop STATE.json, path given by CUA_LOOP_STATE (never committed; make_state_extract.py writes the small
    extract under inputs/ with its sha256),
  - raw/gh-reads.json: the read-only gh reads of the live PR heads / states, upstream main and the fork branch heads
    (written by collect_gh_reads.sh; the fresh review records them per entry),
  - read-only `git ls-remote` of origin (kvnloo/cua) and upstream (trycua/cua) heads and PR refs,
  - read-only `git diff --name-only` for drift against the pinned upstream main.
Every number in an evidence line is a pointer into a packet (or into the state extract); free text carries no bare
numbers.

  python3 make_queue.py                 # build
  python3 make_queue.py --list-branches # print the fork branches the gh reads must cover
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = os.path.join(os.path.dirname(HERE), "10-final-accounting")
sys.path.insert(0, ACC)
sys.path.insert(0, HERE)
import rfc_common as C  # noqa: E402
import make_state_extract as MSE  # noqa: E402

OUT_JSON = os.path.join(HERE, "queue.json")
README = os.path.join(HERE, "README.md")
EXTRACT = MSE.EXTRACT
RAW = os.path.join(HERE, "raw")
GH_READS = os.path.join(RAW, "gh-reads.json")
BEGIN = "<!-- BEGIN GENERATED: make_queue.py -->"
END = "<!-- END GENERATED: make_queue.py -->"

LANE_ID = "DOC-10-74b (wave 7)"
# Live upstream main at the fresh review (gh read, raw/gh-reads.json); the drift gate measures against it.
MAIN_PIN = "9a2b1d99ec8044ff58b2a2b46802edd2609c057b"
PREV_PIN = "5de1a37997e6c423899dd0a56aaa63bcf5abee8f"
DRIFT_ALLOW = re.compile(r"(platform-macos/|platform-windows/|Skills/cua-driver/MACOS\.md$|"
                         r"cua-driver-e2e/tests/harness_appkit_test\.rs$|tests/fixtures/apps/macos/|"
                         r"tests/fixtures/apps/windows/|cua-driver-e2e/tests/harness_(winui3|wpf)_test\.rs$|"
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
    # ---- wave 6
    "B-08": ("exp/b-08-per-process-cold-b7-20261003", "49ae94590f3b7e25cf7bf5fbfbbf67d51aaadff3",
             "docs/experiments/b-08-per-process-cold-b7-2026-10-03", "b08-summary.json"),
    "R2-07e": ("exp/r2-07e-modal-gate-phase-l-20261003", "67b99ddc6a66a217c76dc491977de78180434751",
               "docs/experiments/r2-07e-modal-gate-phase-l-2026-10-03", "r2-07e-summary.json"),
    "OWN-78L": ("exp/own-78l-r1-lite-f-20261003", "d9edde70e8b1254e1352c660d859d8dfd6932d02",
                "docs/experiments/own-78l-r1-lite-f-2026-10-03", "own78l-summary.json"),
    "FIX-03": ("exp/fix-03-file-input-toctou-session-routing-20261003", "e300edbd318f33b907741ca7aaec2ee666a2dac0",
               "docs/experiments/fix-03-toctou-session-routing-2026-10-03", "summary.json"),
    "OWN-20Q": ("exp/own-20q-a11y-triggers-dialog-markfree-20261003", "44116546d54047f01d7318eecbc2f36303ec1013",
                "docs/experiments/own-20q-a11y-triggers-dialog-markfree-2026-10-03", "own20q-summary.json"),
    # PUB-03's accepted head is a held privacy candidate: it is expected to be absent from origin.
    "PUB-03": ("exp/own-20g-guard-final-diff-r1c-20261003", "cb18ebfbdfa41b733b8c68c1971760ab39f392f4",
               "docs/experiments/own-20g-guard-final-diff-2026-10-03", None),
}
HELD_LANES = {"PUB-03"}

# Wave-7 lanes still running (planner assignments). An entry they touch is "pending wave 7 <id>".
PENDING_W7 = {
    "B-09": "exp/b-09-fill-verify-poll-b7-20261003",
    "R2-07f": "exp/r2-07f-compiled-replay-b7-decomp-20261003",
    "R2-07g": "exp/r2-07g-live-fallback-ln-20261003",
    "FIX-04": "exp/fix-04-unknown-delivery-effect-20261003",
    "FRESH-07": "exp/fresh-07-main-9a2b1d99e-20261003",
    "PUB-04": "exp/r2-10r-recert-a3-r1c-20261003",
}
PENDING_W7_SCOPE = {
    "B-09": "stamps the compiled routine's verify poll on B7 (fill runner verdict)",
    "R2-07f": "compiled-replay decomposition on B7",
    "R2-07g": "live forced-fallback re-run and the LN toggle row (uses the remaining TypeSafe budget)",
    "FIX-04": "effect=unknown mapping for delivery=unknown refusals; runner re-dispatch rule; FIX-03 verifier fix",
    "FRESH-07": "freshness against upstream main 9a2b1d99e (overlay.rs SOURCE check vs the X11 native and focus rows)",
    "PUB-04": "privacy rewrite candidate of the published R2-10R a3 head",
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
# Merged upstream PRs recorded by the review because they moved main after the tested sources (no gate).
PR_RECORDED = [("trycua/cua", 4529), ("trycua/cua", 4531)]


def Q(lane, path, nd=None, file=None):
    br, sha, d, f = QP[lane]
    data = C.show_json(sha, d + "/" + (file or f))
    return {"value": C.rnd(C.resolve(data, path), nd),
            "from": {"lane": lane, "sha": sha, "file": d + "/" + (file or f), "path": list(path), "round": nd}}


_EXT = {}


def ST(*path):
    """A pointer into the committed state extract (re-derived from STATE.json by the verifier)."""
    return {"value": C.resolve(_EXT["ext"], path), "from": {"state_extract": list(path)}}


def E(template, **nums):
    """An evidence line: free text with {name} slots filled from packet pointers."""
    return {"t": template, "n": nums}


def gate(lane, path, file=None):
    """A gate whose key text (written by the packet) is rendered next to its value."""
    p = Q(lane, path, file=file)
    k = {"value": path[-1], "from": dict(p["from"], key=True)}
    return E("{k}: {g}", k=k, g=p)


# --------------------------------------------------------------------------------- the queue
# Index notes (STATE, wave 6): owner_decisions_pending[0..30]; blocked_items_w6[0..16]. The verifier checks every
# cited index against the state extract and that every pending owner decision is covered by an entry.

B_PR4316 = ("trycua/cua", 4316)


def items():
    I = []

    def add(**kw):
        kw.setdefault("review_note", "")
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
             "packets": [{"lane": "FIX-01"}, {"lane": "R2-10R"}, {"lane": "FIX-03"}]},
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
            E("FIX-03 (wave 6): a refusal issued after the assignment carries delivery unknown ({u} of {n} on F5) while "
              "the change still reached the server in {g} cells; this is the receipt the runner rule must not treat as "
              "refused",
              u=Q("FIX-03", ["part_a", "A1", "F5", "refused_post_check_unknown"]),
              n=Q("FIX-03", ["part_a", "A1", "F5", "n"]), g=Q("FIX-03", ["part_a", "A1", "F5", "gen0_events_cells"])),
        ],
        missing=["The runner rule must honour delivery=unknown / retryable=false refusals as unknown (no re-dispatch, "
                 "reconcile first); FIX-04 is building and measuring that in wave 7.",
                 "The trusted-input route keeps a residual re-render window between send and landing (FIX-01 follow-up; "
                 "characterised under a shared lock only).",
                 "Recertification on upstream main 9a2b1d99e (drift gate)."],
        action="fork candidate review, then a reviewed upstream PR proposal (not posted; upstream owner named at that time)",
        dependency=["FIX-04 (wave 7)", "FIX-02 F3 (retry scope) travels with Part B", "drift-free or recertified on "
                    "upstream main 9a2b1d99e"],
        stop="Any false refusal on a connected node, a refused dispatch whose effect landed reported as refused, or a "
             "re-dispatch after a delivery=unknown refusal.",
        review_note="FIX-01 and R2-10R pointers re-read at their packet SHAs; candidate head re-read on origin. The "
                    "FIX-03 receipt evidence (delivery unknown with a landed effect) is new since wave 6 and makes the "
                    "runner half depend on FIX-04; missing evidence updated accordingly.",
        gate_in=dict(lanes=["FIX-01", "R2-10R", "FIX-03"],
                     published=[("exp/r2-10r-control-a2-20261003", "8a2362770f2120c136c69a50b711a6b9e3a69b8f")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "8a2362770f2120c136c69a50b711a6b9e3a69b8f"},
                     owner=[], blocked=[], pending=["FIX-04"], prereq=[], prs=[]))

    add(id="Q02", title="FIX-02 F1-F3 + FIX-03 side-index fix: native token ownership, runtime generation, re-dispatch scope",
        delta="F1 binds native element tokens to the publishing session; F2 starts snapshot ids at a random per-process "
              "base (runtime generation); F3 lets jev-use runners re-dispatch only after pre-dispatch refusals. The "
              "kvnloo/cua#36 candidate must also carry FIX-03's 2237cf9c6 (element-addressed writes and focus use the "
              "token's own window snapshot), because F' alone lets a valid token write into another session's window.",
        owner=["kvnloo/cua#36", "kvnloo/cua#105 (F3 runner rule)"],
        sha={"candidate": {"branch": "exp/fix-03-file-input-toctou-session-routing-20261003",
                           "sha": "e300edbd318f33b907741ca7aaec2ee666a2dac0",
                           "commits": ["8e0e8aea0abbcdddd66b9ed2011e888dcdb103ed", "205a4ecb2e33e846e67b55b8d72cbb61513c2fc6",
                                       "cdffb32130c98ddb7b9196d587c5ef19053bac2d", "2237cf9c6"],
                           "note": "F5 line: F1-F3 rebased on 0f1955d2f (RECERT-FIX F') plus the FIX-03 commits; the "
                                   "head also carries FIX-03's measurement-only seam 5a1e209ab (env-gated, default off)"},
             "packets": [{"lane": "RECERT-FIX"}, {"lane": "FIX-02"}, {"lane": "FIX-03"}]},
        evidence=[gate("RECERT-FIX", ["FIX-02 F1", "gates", "I2 F' 40/40"]),
                  gate("RECERT-FIX", ["FIX-02 F1", "gates", "I2d F' 40/40"]),
                  gate("RECERT-FIX", ["FIX-02 F2", "gates", "I5p F' 20/20"]),
                  gate("RECERT-FIX", ["FIX-02 F2", "gates", "I5pt F' 10/10"]),
                  gate("RECERT-FIX", ["FIX-02 F3", "gates", "0 blind re-dispatches on F'"]),
                  gate("RECERT-FIX", ["kvnloo/cua#36 same-process two-window row", "gates", "0 cross-session mutations on F'"]),
                  E("Recertification verdicts: F1 {a}, F2 {b}, F3 {c}",
                    a=Q("RECERT-FIX", ["FIX-02 F1", "verdict"]), b=Q("RECERT-FIX", ["FIX-02 F2", "verdict"]),
                    c=Q("RECERT-FIX", ["FIX-02 F3", "verdict"])),
                  E("FIX-03 side index: cross-session mutations on F' {f}, on F5 {f5}; F5 own-window gates WS {ws}, "
                    "WK {wk}; W2dX discriminating {w}",
                    f=Q("FIX-03", ["e4", "F", "cross_session_mutation"]), f5=Q("FIX-03", ["e4", "F5", "cross_session_mutation"]),
                    ws=Q("FIX-03", ["part_c_d", "WS-F5", "gate_pass"]), wk=Q("FIX-03", ["part_c_d", "WK-F5", "gate_pass"]),
                    w=Q("FIX-03", ["part_c_d", "W2dX-discriminating"]))],
        missing=["Native AT-SPI fallbacks still index the whole application walk by pid when the cached object is "
                 "missing (FIX-03 remaining limit; E4 residue).",
                 "The runner F3 rule against delivery=unknown / retryable=false refusals (FIX-04, wave 7).",
                 "Freshness of the X11 rows against upstream main 9a2b1d99e (FRESH-07, wave 7)."],
        action="fork candidate review (F5 line), then a reviewed upstream PR proposal (not posted)",
        dependency=["FIX-04 (wave 7)", "FRESH-07 (wave 7)", "drift-free or recertified on upstream main 9a2b1d99e"],
        stop="Upstream main changes snapshot_store.rs or the Linux token path; any cross-session mutation on the fixed tree.",
        review_note="RECERT-FIX gate keys re-read; the wave-6 FIX-03 finding (F' cross-session hole, fixed in F5) moves "
                    "the candidate from exp/fix-02r-a3-20261003 to the FIX-03 head, which contains F1-F3 (ancestry checked) "
                    "and 2237cf9c6. The recording-lookup and W2c/W2d gaps listed in wave 6 are closed by FIX-03 and removed.",
        gate_in=dict(lanes=["RECERT-FIX", "FIX-02", "FIX-03"],
                     published=[("exp/fix-03-file-input-toctou-session-routing-20261003",
                                 "e300edbd318f33b907741ca7aaec2ee666a2dac0")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "e300edbd318f33b907741ca7aaec2ee666a2dac0"},
                     owner=[], blocked=[], pending=["FIX-04", "FRESH-07"], prereq=[], prs=[]))

    add(id="Q03", title="FIX-02 F4 + FIX-03 F5: set_input_files on a detached input (honest receipt, effect can land)",
        delta="Refuse browser_set_input_files on a file input detached before the call (F4) and never report success "
              "for a node detached after the check (F5, post-assignment isConnected check).",
        owner=["kvnloo/cua#36"],
        sha={"candidate": {"branch": "exp/fix-03-file-input-toctou-session-routing-20261003",
                           "sha": "e300edbd318f33b907741ca7aaec2ee666a2dac0",
                           "commits": ["a357d061d62d0e6e90615a538a099c9d81bccf0f", "b235fabef"],
                           "note": "F4 rebased on 0f1955d2f plus F5 b235fabef"},
             "packets": [{"lane": "RECERT-FIX"}, {"lane": "FIX-02"}, {"lane": "FIX-03"}]},
        evidence=[gate("RECERT-FIX", ["FIX-02 F4", "gates", "F4 F' 20/20 (narrower claim; TOCTOU not covered)"]),
                  E("FIX-03 A1 (seam-forced race): F5 success receipts {s} of {n}; refused with delivery unknown {u}; the "
                    "change event still reached the server in {g} cells; F'S positive control success receipts {p}",
                    s=Q("FIX-03", ["part_a", "A1", "F5", "success_receipts"]), n=Q("FIX-03", ["part_a", "A1", "F5", "n"]),
                    u=Q("FIX-03", ["part_a", "A1", "F5", "refused_post_check_unknown"]),
                    g=Q("FIX-03", ["part_a", "A1", "F5", "gen0_events_cells"]),
                    p=Q("FIX-03", ["part_a", "A1", "FS", "success_receipt_for_detached_node"])),
                  E("Disposition {d}", d=Q("FIX-03", ["F4", "verdict"], file="dispositions.json"))],
        missing=["The refusal is mapped to effect=refused although the effect can land: it must become effect=unknown "
                 "(FIX-04, wave 7).",
                 "Owner acceptance of IRREDUCIBLE-with-honest-unknown (CDP cannot make the check and the assignment atomic)."],
        action="hold (REVISE); fork candidate after the owner ruling and FIX-04",
        dependency=["owner ruling OR-24", "FIX-04 (wave 7)"],
        stop="Any success receipt for a detached node on the fixed tree, or a delivery=unknown refusal still reported as "
             "effect=refused after FIX-04.",
        review_note="Wave-6 FIX-03 replaces the pending marker: F5 measured; F4 stays REVISE with an honest-unknown "
                    "boundary. Candidate moved to the FIX-03 head (a357d061d and b235fabef are ancestors).",
        gate_in=dict(lanes=["RECERT-FIX", "FIX-02", "FIX-03"],
                     published=[("exp/fix-03-file-input-toctou-session-routing-20261003",
                                 "e300edbd318f33b907741ca7aaec2ee666a2dac0")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "e300edbd318f33b907741ca7aaec2ee666a2dac0"},
                     owner=[27], blocked=[], pending=["FIX-04"], prereq=[], prs=[]))

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
        dependency=["owner rulings OR-06, OR-07 and OR-16", "kvnloo/cua#84 head unchanged"],
        stop="Upstream main changes the coordinator / barrier path, or kvnloo/cua#84 head moves.",
        review_note="Gate keys re-read; kvnloo/cua#84 head re-read with gh (open, unchanged). No wave-6 lane touched it.",
        gate_in=dict(lanes=["RECERT-FIX", "OWN-09R"],
                     published=[("exp/own-09r2-a3-20261003", "ba611b51a48f6798eb3b3114f0c98af03c2d7d52"),
                                ("exp/own-09r-84-revision-20261002", "0c2896a53e185ed6b92e61fdb405e42137cc0720")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "ba611b51a48f6798eb3b3114f0c98af03c2d7d52"},
                     owner=[6, 7, 19], blocked=[9, 10], pending=[], prereq=[], prs=[("kvnloo/cua", 84)]))

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
                 "macOS and Windows parity: BLOCKED (hardware); the macOS get_window_state file changed again on main "
                 "(trycua/cua PR 4531)."],
        action="hold; fork candidate after the owner rulings",
        dependency=["owner ruling OR-09"],
        stop="Upstream main changes get_window_state selector parsing on Linux.",
        review_note="Gate keys re-read. Upstream main now also changes platform-macos get_window_state (allowlisted, "
                    "non-Linux); the Linux claim is unaffected, but the drift gate fails on other Linux/core paths.",
        gate_in=dict(lanes=["RECERT-FIX", "OWN-16W"],
                     published=[("exp/own-16w2-a3-20261003", "7e31eae59d2316c3e41d31a3eb872837bb945283")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "7e31eae59d2316c3e41d31a3eb872837bb945283"},
                     owner=[9, 21], blocked=[], pending=[], prereq=[], prs=[]))

    add(id="Q06", title="OWN-20P G: focus-guard final read on deadline exit (R1 now mark-free, OWN-20Q)",
        delta="focus_guard: a final focus read when the settle watch ends on its deadline after a read that began before it "
              "(restores a focus steal the watch would otherwise miss silently).",
        owner=["kvnloo/cua#20"],
        sha={"candidate": {"branch": "exp/own-20q-a11y-triggers-dialog-markfree-20261003",
                           "sha": "44116546d54047f01d7318eecbc2f36303ec1013",
                           "commits": ["a761f1f1f"], "note": "G port a761f1f1f (clean main cb685fad7) under the OWN-20Q head"},
             "packets": [{"lane": "OWN-20P"}, {"lane": "OWN-20Q"}]},
        evidence=[E("Mark-free R1m on product binaries (OWN-20Q): unguarded U0 silent misses {u} of {un}; guarded G0 "
                    "verified restores {g} of {gn}; false restores {f}",
                    u=Q("OWN-20Q", ["r1m", "U0_silent_miss"]), un=Q("OWN-20Q", ["r1m", "n", "U0"]),
                    g=Q("OWN-20Q", ["r1m", "G0_verified_restore"]), gn=Q("OWN-20Q", ["r1m", "n", "G0"]),
                    f=Q("OWN-20Q", ["r1m", "false_restores"])),
                  E("Product G on the normal path (OWN-20P): verified {v} of {n}; failures plus false restores {f}",
                    v=Q("OWN-20P", ["normal", "G0_verified"]), n=Q("OWN-20P", ["normal", "G0_n"]),
                    f=Q("OWN-20P", ["normal", "G0_failures_plus_false_restores"]))],
        missing=["Hyprland/Wayland focus rows: BLOCKED (real seat).",
                 "Freshness against upstream main 9a2b1d99e, whose X11 overlay change may interact with focus (FRESH-07)."],
        action="fork candidate review (with Q26)",
        dependency=["FRESH-07 (wave 7)", "drift-free or recertified on upstream main 9a2b1d99e"],
        stop="The port changes quiet-path behaviour, or any false restore on the normal path.",
        review_note="OWN-20Q R1m replaces the marked-twin substitution (STATE blocked_items_w6 notes it superseded), so "
                    "the R1 half of that owner decision no longer gates this entry; A's trigger set stays with Q07.",
        gate_in=dict(lanes=["OWN-20P", "OWN-20Q"],
                     published=[("exp/own-20q-a11y-triggers-dialog-markfree-20261003",
                                 "44116546d54047f01d7318eecbc2f36303ec1013")],
                     drift={"base": "cb685fad7", "candidate": "a761f1f1f"},
                     owner=[], blocked=[7], pending=["FRESH-07"], prereq=[], prs=[]))

    add(id="Q07", title="OWN-20P A + OWN-20Q A2: in-process AT-SPI bus-restart reconnect and its triggers",
        delta="The Driver reconnects to a restarted accessibility bus in-process (stream end, plus NoReply with a "
              "Peer.Ping probe from 31318e374); the org.a11y.Bus name-owner trigger is not built.",
        owner=["kvnloo/cua#20"],
        sha={"candidate": {"branch": "exp/own-20q-a11y-triggers-dialog-markfree-20261003",
                           "sha": "44116546d54047f01d7318eecbc2f36303ec1013",
                           "commits": ["064d2e4ad", "31318e374"], "note": "A 064d2e4ad plus the A2 trigger 31318e374"},
             "packets": [{"lane": "OWN-20P"}, {"lane": "OWN-20Q"}]},
        evidence=[E("R3 bus restart (OWN-20P): liveness GA {ga} of the pre-registered twenty ({gl}); safety GA {gs}",
                    ga=Q("OWN-20P", ["r3", "bus/GA", "pass"]), gl=Q("OWN-20P", ["r3", "liveness_GA_20"]),
                    gs=Q("OWN-20P", ["r3", "bus/GA", "pass_safety"])),
                  E("OWN-20Q A2: real restarts live where killed {l} of {k}; stale mutations {m}; r3s gate {s}; "
                    "name-owner row r3n gate {n} (GQ passes {np} of {nn})",
                    l=Q("OWN-20Q", ["a2", "r3_carry", "restart_happened_view", "live_where_killed"]),
                    k=Q("OWN-20Q", ["a2", "r3_carry", "restart_happened_view", "killed_total"]),
                    m=Q("OWN-20Q", ["a2", "r3_carry", "GQ", "stale_mutated"]), s=Q("OWN-20Q", ["a2", "r3s_gate"]),
                    n=Q("OWN-20Q", ["a2", "r3n_gate"]), np=Q("OWN-20Q", ["a2", "r3n", "GQ", "pass"]),
                    nn=Q("OWN-20Q", ["a2", "r3n", "GQ", "n"]))],
        missing=["The name-owner trigger needs a second persistent session-bus connection: owner/design decision.",
                 "Owner call: is the trigger set (stream end + NoReply/Peer.Ping) enough.",
                 "Hyprland/Wayland: BLOCKED (seat)."],
        action="fork candidate review after the owner rulings",
        dependency=["owner rulings OR-17 and OR-25", "FRESH-07 (wave 7)"],
        stop="Any stale mutation after a reconnect, or reconnect breaks the quiet path.",
        review_note="OWN-20Q A2 measured (REVISE on r3n). r3s is cited with its boundary (GA passes trivially) and "
                    "r3_carry with the real-restart view, as the wave-6 verifier asked.",
        gate_in=dict(lanes=["OWN-20P", "OWN-20Q"],
                     published=[("exp/own-20q-a11y-triggers-dialog-markfree-20261003",
                                 "44116546d54047f01d7318eecbc2f36303ec1013")],
                     drift={"base": "cb685fad7", "candidate": "31318e374"},
                     owner=[20, 28], blocked=[7, 11], pending=["FRESH-07"], prereq=[], prs=[]))

    add(id="Q08", title="OWN-20G guard a30cbbc3b (superseded by the G port; privacy candidate cb18ebfbd held)",
        delta="The original focus-guard final-read diff, tested on 0f1955d2f plus measurement picks.",
        owner=["kvnloo/cua#20"],
        sha={"candidate": {"branch": "exp/own-20g-guard-final-diff-r1c-20261003",
                           "sha": "cb18ebfbdfa41b733b8c68c1971760ab39f392f4",
                           "commits": ["a30cbbc3b230e8bad7d86ae1e89866d4f9cdd1af"],
                           "note": "PUB-03 privacy candidate of the published a2 head ce7544cc0, held for the owner ruling; "
                                   "a30cbbc3b does not apply to clean main and is superseded by a761f1f1f (Q06)"},
             "packets": [{"lane": "OWN-20G"}, {"lane": "PUB-03"}]},
        evidence=[E("R1 reply-delay row: gate (G restores every trial) {r}; specified XGrabServer row gate {g}",
                    r=Q("OWN-20G", ["r1", "reply", "gate_G_20_of_20"]), g=Q("OWN-20G", ["r1", "grab", "gate_G_20_of_20"])),
                  E("R3 bus restart: safety gate {s}; in-process liveness gate {l}",
                    s=Q("OWN-20G", ["r3", "safety_bus_20_each"]), l=Q("OWN-20G", ["r3", "gate_bus_20_each"]))],
        missing=["The owner's privacy ruling on the published a2 head (replace with cb18ebfbd, delete and re-push, or accept).",
                 "Owner calls: the reply-delay row in place of the XGrabServer row, and the settle-overshoot IRREDUCIBLE judgement."],
        action="privacy rewrite on the fork after the owner ruling - no posting; the product delta moves to Q06",
        dependency=["owner rulings PRIV-B, OR-14 and OR-26"],
        stop="Superseded once Q06 is accepted for posting.",
        review_note="PUB-03 built and verified the candidate (accepted wave 6); it is held, so the origin gate is false "
                    "by design. Evidence pointers re-read at the OWN-20G packet SHA.",
        gate_in=dict(lanes=["OWN-20G", "PUB-03"],
                     published=[("exp/own-20g-guard-final-diff-a2-20261003", "ce7544cc064cecfd9ba4702466a1d0f24b1799b6")],
                     not_published=[("exp/own-20g-guard-final-diff-r1c-20261003", "cb18ebfbdfa41b733b8c68c1971760ab39f392f4")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "ce7544cc064cecfd9ba4702466a1d0f24b1799b6"},
                     owner=[14, 23, 29], blocked=[12], pending=[], prereq=[], prs=[]))

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
        missing=["Recertification on upstream main 9a2b1d99e (Linux/core paths changed on main since c4d0c6625).",
                 "Windows, macOS and embedded labels are UNIT-only."],
        action="fork fix branch for owner review; upstream routing decided by the kvnloo/cua#38 owner (not posted)",
        dependency=["recertification on current main"],
        stop="The producer branch structure changes upstream, or any other receipt field changes.",
        review_note="Pointers re-read; unchanged since wave 6. Recertification is the only open gate besides drift.",
        gate_in=dict(lanes=["BUG-01"],
                     published=[("exp/bug-01-delivery-cdp-sessions-20261002", "097b4f0974d5c161360fc3683c17f298ff681c70")],
                     drift={"base": "c4d0c6625", "candidate": "097b4f0974d5c161360fc3683c17f298ff681c70"},
                     owner=[], blocked=[], pending=[], prereq=[], prs=[]))

    add(id="Q10", title="BUG-01 B: CDP sessions accumulate (attach per call, never detach)",
        delta="Each browser call attaches one CDP session and never detaches it; the post-navigation event burst scales "
              "with the session count. Accumulation only - no fix and no cost on a no-op page.",
        owner=["trycua/cua 4052 (plain text; evidence owner)"],
        sha={"candidate": None, "packets": [{"lane": "BUG-01"}]},
        evidence=[E("Live CDP sessions at the end of each long run: {s}",
                    s=Q("BUG-01", ["part_b", "M1_live_sessions_end_of_L"]))],
        missing=["A cost on a non-trivial page (none measured)."],
        action="evidence note only (no fix)",
        dependency=["drift-free on upstream main 9a2b1d99e for the browser paths"],
        stop="Upstream changes CDP session lifetime.",
        review_note="Pointer re-read; unchanged since wave 6.",
        gate_in=dict(lanes=["BUG-01"],
                     published=[("exp/bug-01-delivery-cdp-sessions-20261002", "097b4f0974d5c161360fc3683c17f298ff681c70")],
                     drift={"base": "c4d0c6625", "claim_paths": ["libs/cua-driver/rust/crates/cua-driver-core/src/browser"]},
                     owner=[], blocked=[], pending=[], prereq=[], prs=[]))

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
        dependency=["red/green logs committed", "kvnloo/cua#105 head unchanged"],
        stop="kvnloo/cua#105 head moves, or any duplicate mutation on a fixed runner.",
        review_note="Pointers re-read; kvnloo/cua#105 head re-read with gh (open, unchanged). The red/green-log "
                    "prerequisite was a missing-evidence line in wave 6 and is now an explicit gate input.",
        gate_in=dict(lanes=["OWN-105"],
                     published=[("exp/own-105-runner-reconcile-20261002", "b97daa4ba08605c08f6a5da8baf1bf32c5ff4093")],
                     drift={"base": "345ff6d9d", "candidate": "b97daa4ba08605c08f6a5da8baf1bf32c5ff4093"},
                     owner=[], blocked=[], pending=[],
                     prereq=["red/green counts committed (they live only in gitignored logs)"],
                     prs=[("kvnloo/cua", 105)]))

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
        dependency=["owner ruling OR-08", "PR head unchanged"],
        stop="The PR head moves from 8391cf802.",
        review_note="Pointers re-read; trycua/cua PR 4336 re-read with gh (open, head unchanged).",
        gate_in=dict(lanes=["OWN-75R"],
                     published=[("exp/own-75r-timing-parity-4336-r1b-20261003", "efe36d1a1efda084fa37e061dc58c3a98d607c68"),
                                ("exp/own-75r-timing-parity-4336-20261002", "e02621fdc1fe5098efd48af295964f25902553ea")],
                     drift={"base": "2ca90d338", "candidate": "8391cf80275d2a5e7288f9d7c6b0a3e5f7822939"},
                     owner=[8], blocked=[], pending=[], prereq=[], prs=[("trycua/cua", 4336)]))

    add(id="Q13", title="Fork fix candidate F for trycua/cua PR 4394 (restore form + page + outline): KEEP (OWN-78L)",
        delta="Restore the form, page and outline context in the PR 4394 browser request so the live provider stops "
              "abstaining at step one.",
        owner=["kvnloo/cua#78", "upstream trycua/cua PR 4394 (plain text)"],
        sha={"candidate": {"branch": "exp/own-78l-r1-lite-f-20261003", "sha": "d9edde70e8b1254e1352c660d859d8dfd6932d02",
                           "commits": ["61eec09092fd161f62651a890c882f276a642855"], "note": "fix candidate F head 61eec0909"},
             "packets": [{"lane": "OWN-78A"}, {"lane": "OWN-78L"}]},
        evidence=[E("Live TypeSafe step-one isolation: PR abstained {a0}; PR plus form correct {a1}; F correct {a2}; pre-PR correct {a3}",
                    a0=Q("OWN-78A", ["attribution", "A0_abstain"]), a1=Q("OWN-78A", ["attribution", "A1_correct_type"]),
                    a2=Q("OWN-78A", ["attribution", "A2_correct_type"]), a3=Q("OWN-78A", ["attribution", "A3_correct_type"])),
                  E("R1-lite on F (OWN-78L, live TypeSafe): verified {v} of {n}; backend == responder {b}; replays or "
                    "restarts {r}; disposition {d}",
                    v=Q("OWN-78L", ["r1_lite", "verified"]), n=Q("OWN-78L", ["r1_lite", "n"]),
                    b=Q("OWN-78L", ["r1_lite", "backend_equals_responder"]),
                    r=Q("OWN-78L", ["r1_lite", "replays_or_restarts"]), d=Q("OWN-78L", ["disposition"]))],
        missing=["Full-n live R1 / R4: BLOCKED (paid budget).",
                 "S1 backend row: BLOCKED (owner decision; adapter not local).",
                 "The remaining A2-vs-A3 gap (question key, instructions, goal / history placement, visual): BLOCKED (budget).",
                 "The step-one margin is thin and n is small: KEEP is a gate result, not a rate."],
        action="evidence comment for kvnloo/cua#78 (fork only); upstream routing by the PR 4394 owner",
        dependency=["owner rulings OR-11 and OR-20 (blocked rows)", "PR head unchanged"],
        stop="The trycua/cua PR 4394 head moves from 039257811.",
        review_note="OWN-78L closes R1-lite (KEEP on F). Candidate moved to the OWN-78L head (61eec0909 is an ancestor). "
                    "PR 4394 re-read with gh (open, head unchanged).",
        gate_in=dict(lanes=["OWN-78A", "OWN-78L"],
                     published=[("exp/own-78l-r1-lite-f-20261003", "d9edde70e8b1254e1352c660d859d8dfd6932d02")],
                     drift={"base": "2ca90d338", "candidate": "61eec0909"},
                     owner=[22, 30], blocked=[3], pending=[], prereq=[], prs=[("trycua/cua", 4394)]))

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
        missing=["A reviewed product (non-env-gated) diff with unit tests; the knob is measurement-only.",
                 "Modal is NOT_MATERIAL on the B-02 binary."],
        action="product-change proposal (default behaviour change; needs a reviewed product diff first)",
        dependency=["a reviewed product diff", "drift-free or recertified on upstream main 9a2b1d99e"],
        stop="A product diff changes the tools/list envelope bytes.",
        review_note="Pointers re-read. The wave-6 gate row did not record the missing product diff; it is now the "
                    "prerequisite gate. The candidate branch is the published R2-10R a3 head, whose privacy rewrite "
                    "(PUB-04) changes no number.",
        gate_in=dict(lanes=["B-02", "R2-10R"],
                     published=[("exp/b-02-browser-driver-sites-20261002", "b282ff3894fa85a7b82257cb1edd5088c2f0ac37"),
                                ("exp/r2-10r-recert-a3-20261003", "d22eeb2ecf8a679d1425c21120a599775aa0817d")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "45dff8f32"},
                     owner=[], blocked=[], pending=[], prereq=["reviewed product diff missing"], prs=[]))

    add(id="Q15", title="N-04 V native admission tools-list cache",
        delta="The same admission tools-list cache on the native GTK3 path.",
        owner=["kvnloo/cua#93", "kvnloo/cua#10"],
        sha={"candidate": {"branch": "exp/n-04-native-composition-rprime-20261003", "sha": "9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2",
                           "commits": [], "note": "measurement-only knob on R'n; PUB-03 privacy candidate 32299f857 is held"},
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
        missing=["A reviewed product (non-env-gated) diff with unit tests; the knob is measurement-only.",
                 "Freshness of the native rows against upstream main 9a2b1d99e (FRESH-07)."],
        action="product-change proposal (with Q14; one admission cache for both paths)",
        dependency=["a reviewed product diff", "owner ruling OR-26 (the published N-04 head)", "FRESH-07 (wave 7)"],
        stop="A product diff changes the tools/list envelope bytes.",
        review_note="Pointers re-read. PUB-03 built the N-04 privacy candidate (held), so the wave-6 PUB-03 dependency "
                    "becomes the owner privacy ruling.",
        gate_in=dict(lanes=["N-04", "N-03"],
                     published=[("exp/n-04-native-composition-rprime-20261003", "9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2"),
                                ("exp/n-03-native-closure-axfg-a3-20261003", "6b70ec9024cc3921f7637bba2ffabcc93e29fc77")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218", "candidate": "9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2"},
                     owner=[29], blocked=[12], pending=["FRESH-07"], prereq=["reviewed product diff missing"], prs=[]))

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
                 "A reviewed product diff: the deletion is measured through an env-gated knob only.",
                 "Freshness against upstream main 9a2b1d99e (X11 overlay change; FRESH-07)."],
        action="product-change proposal, scoped to the measured routes (default behaviour change)",
        dependency=["owner ruling OR-10", "a reviewed product diff", "FRESH-07 (wave 7)"],
        stop="A focus-steal control misses silently with the sleep removed, or a new route lacks the settle watch.",
        review_note="Pointers re-read; no wave-6 lane changed these numbers. FRESH-07 decides whether the X11 rows "
                    "ran with a mapped idle overlay.",
        gate_in=dict(lanes=["N-01R", "R2-09", "N-03", "N-04"],
                     published=[("exp/n-01r-native-wait-ab-20261002", "3bb4a7fc70d1d58984b19a7a357892a7c9af31fa"),
                                ("exp/r2-09-native-event-wake-r1b-20261003", "ffb4919a7b5bff9cc92e2a798663439a76d8f0b3"),
                                ("exp/n-03-native-closure-axfg-a3-20261003", "6b70ec9024cc3921f7637bba2ffabcc93e29fc77")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218", "candidate": "45dff8f32"},
                     owner=[10], blocked=[6, 7], pending=["FRESH-07"], prereq=["reviewed product diff missing"], prs=[]))

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
        dependency=["a form-scope fix for the decoy case", "PR head unchanged"],
        stop="The PR head moves from a0bca7440, or any wrong-target submit.",
        review_note="Pointers re-read; trycua/cua PR 4316 re-read with gh (open, head unchanged). The wrong-target "
                    "finding is an explicit prerequisite gate now.",
        gate_in=dict(lanes=["R2-03"],
                     published=[("exp/r2-03-guarded-live-20261001", "6bab214abb707a3db9e8a7d641d160c3f58e08d5"),
                                ("exp/i107-d-20261002", "6d1c609261289d73833395d390d1150ad2187285")],
                     drift={"base": "345ff6d9d", "candidate": "a0bca744067d04f05904319d3d919be30c336556"},
                     owner=[], blocked=[0], pending=[],
                     prereq=["form-scope fix for the decoy wrong-target case missing (kvnloo/cua#107 D)"],
                     prs=[("trycua/cua", 4316)]))

    add(id="Q18", title="R2-07b fill compiled replay (re-qualified by FIX-01)",
        delta="A compiled fresh-bound fill->submit routine replays without provider decisions on warm runs, with fresh "
              "authority before each replayed mutation and bounded fallback.",
        owner=["kvnloo/cua#93 (R2-07)", "kvnloo/cua#10"],
        sha={"candidate": {"branch": "exp/r2-10-composition-20261002", "sha": "030f6bdbf811e124e11daa2de0569bffb993b66d",
                           "commits": [], "note": "measured inside R2-10's fill COMP arm on R; the R2-07 packet itself stays KILL"},
             "packets": [{"lane": "R2-10"}, {"lane": "FIX-01"}, {"lane": "B-08"}]},
        evidence=[E("Live fill on R: provider requests per trial BASE {b} -> COMP {c}; provider work removed {w} ms per trial",
                    b=Q("R2-10", ["browser", "live", "work_deleted_vs_wall_clock", "fill", "provider_decisions_per_trial", "BASE"]),
                    c=Q("R2-10", ["browser", "live", "work_deleted_vs_wall_clock", "fill", "provider_decisions_per_trial", "COMP"], 3),
                    w=Q("R2-10", ["browser", "live", "work_deleted_vs_wall_clock", "fill", "component_mean_ms_deleted", "provider_decision"], 1)),
                  E("Live fill amortized S (all invocations incl. training) {s} {ci}",
                    s=Q("R2-10", ["browser", "live", "S", "COMP", "fill", "amortized_mean_ratio", "S"], 2),
                    ci=Q("R2-10", ["browser", "live", "S", "COMP", "fill", "amortized_mean_ratio", "ci95"], 2)),
                  E("B-08 on B7: the compiled routine's verify poll is unstamped and filed under runner ({p} ms, UNTESTED)",
                    p=Q("B-08", ["part_E", "classes", "fill", "C", "post_hoc_unmarked_verify_poll", "mean_ms"], 2))],
        missing=["Live recertification on R' (0f1955d2f): BLOCKED (paid budget).",
                 "The verify poll inside the routine has no verdict (B-09 is stamping it in wave 7).",
                 "A product shape: no routine framework or route miner is proposed (parked by kvnloo/cua#74); this stays research evidence."],
        action="research evidence for the trycua/cua issue 3963 rewrite draft (DOC-3963); no upstream posting",
        dependency=["owner ruling OR-11 (budget)", "B-09 and R2-07f (wave 7)"],
        stop="Any blind replay of a may-have-landed effect, or a fallback that skips fresh authority.",
        review_note="Pointers re-read. DOC-3963 is accepted (wave 6), so that dependency is gone; B-08 found the "
                    "unstamped verify poll, which B-09 measures.",
        gate_in=dict(lanes=["R2-10", "FIX-01", "B-08"],
                     published=[("exp/r2-10-composition-20261002", "030f6bdbf811e124e11daa2de0569bffb993b66d")],
                     drift={"base": "989cc76ce", "claim_paths": ["libs/cua-driver/examples/jev-use",
                                                                 "libs/cua-driver/rust/crates/cua-driver-core/src/browser"]},
                     owner=[22, 30], blocked=[0], pending=["B-09", "R2-07f"], prereq=[], prs=[]))

    add(id="Q19", title="R2-07c/d/e toggle and modal compiled replay (toggle KEEP, modal REVISE)",
        delta="The compiled fresh-bound routine for toggle->confirm and modal->act; R2-07e admits it into the composed "
              "toggle configuration (live provider decision DELETED on warm invocations) and keeps it out of modal.",
        owner=["kvnloo/cua#93 (R2-07)", "kvnloo/cua#10"],
        sha={"candidate": {"branch": "exp/r2-07e-modal-gate-phase-l-20261003", "sha": "67b99ddc6a66a217c76dc491977de78180434751",
                           "commits": [], "note": "tested on R (12b9045a); no Driver change"},
             "packets": [{"lane": "R2-07c"}, {"lane": "R2-07d"}, {"lane": "R2-07e"}]},
        evidence=[E("Modal non-regression, second look (R2-07e Part Q, CR - COMP at the alpha-adjusted level): {m} ms {mc}; "
                    "gate {mg}; first look (R2-07d) {l1} ms {l1c}, gate {l1g}",
                    m=Q("R2-07e", ["part_Q", "modal", "timing", "gate_975", "median"], 1),
                    mc=Q("R2-07e", ["part_Q", "modal", "timing", "gate_975", "ci"], 1),
                    mg=Q("R2-07e", ["part_Q", "modal", "timing", "gate_ci975_upper_le_2ms"]),
                    l1=Q("R2-07d", ["phase_S", "modal", "timing", "diff_COMP_CR_minus_COMP_ms", "median"], 1),
                    l1c=Q("R2-07d", ["phase_S", "modal", "timing", "diff_COMP_CR_minus_COMP_ms", "ci95"], 1),
                    l1g=Q("R2-07d", ["phase_S", "modal", "timing", "gate_ci_upper_le_2ms"])),
                  E("Toggle non-regression (R2-07d Phase S): {t} ms {tc}, gate {tg}",
                    t=Q("R2-07d", ["phase_S", "toggle", "timing", "diff_COMP_CR_minus_COMP_ms", "median"], 1),
                    tc=Q("R2-07d", ["phase_S", "toggle", "timing", "diff_COMP_CR_minus_COMP_ms", "ci95"], 1),
                    tg=Q("R2-07d", ["phase_S", "toggle", "timing", "gate_ci_upper_le_2ms"])),
                  E("Phase L live (R2-07e): toggle verdict {tv} (warm valid {tw}, warm provider requests {tp}); modal "
                    "verdict {mv} (forced fallback outcome {mf})",
                    tv=Q("R2-07e", ["disposition", "per_class", "toggle", "phase_L_verdict"]),
                    tw=Q("R2-07e", ["part_L", "toggle", "warm", "valid"]),
                    tp=Q("R2-07e", ["part_L", "toggle", "warm", "provider_requests"]),
                    mv=Q("R2-07e", ["disposition", "per_class", "modal", "phase_L_verdict"]),
                    mf=Q("R2-07e", ["part_L", "modal", "LF", "outcome"])),
                  E("Correctness (R2-07c): accepted mutations all fresh, non-fresh attempts refused ({n} attempts)",
                    n=Q("R2-07c", ["G3", "nonfresh_attempts"]))],
        missing=["Modal: the verdict-bearing forced fallback did not verify; R2-07g re-runs it (wave 7), and the "
                 "n7_presat substitution for the spec's rename fallback needs an owner ruling.",
                 "Toggle non-regression was not re-confirmed in R2-07e's window (descriptive block only).",
                 "Paired live BASE vs COMP+CR S: BLOCKED (paid budget)."],
        action="research evidence (compiled replay in the composed toggle configuration; excluded for modal)",
        dependency=["R2-07f and R2-07g (wave 7)", "owner rulings OR-22 and OR-11"],
        stop="The modal forced fallback fails again, a gated toggle block fails non-regression, or any E4 violation.",
        review_note="R2-07e (wave 6) replaces the pending marker. The modal second look uses the alpha-adjusted gate "
                    "and is reported beside the first look, not pooled. The candidate moves to the R2-07e head.",
        gate_in=dict(lanes=["R2-07c", "R2-07d", "R2-07e"],
                     published=[("exp/r2-07e-modal-gate-phase-l-20261003", "67b99ddc6a66a217c76dc491977de78180434751"),
                                ("exp/r2-07d-quiet-timing-phase-l-20261003", "79f6dd29958b2a73b477544ca9e777efade8a6c3"),
                                ("exp/r2-07c-toggle-modal-compiled-a2-20261003", "7f46edd1681fbf58586f8b4972636c3da56e3be6")],
                     drift={"base": "989cc76ce", "claim_paths": ["libs/cua-driver/examples/jev-use",
                                                                 "libs/cua-driver/rust/crates/cua-driver-core/src/browser"]},
                     owner=[17, 22, 25, 30], blocked=[1, 4, 5], pending=["R2-07f", "R2-07g"], prereq=[], prs=[]))

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
        review_note="Pointers re-read; its owner decision is still pending in STATE.",
        gate_in=dict(lanes=["R2-08"], published=[("exp/r2-08-cross-surface-20261002", "afba150d55426bf775cb10adaa698cf99493b229")],
                     drift=None, owner=[5], blocked=[13], pending=[], prereq=[], prs=[]))

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
        review_note="Pointers re-read; its owner decision is still pending in STATE.",
        gate_in=dict(lanes=["B-01R", "R2-10"], published=[("exp/b-01r-browser-critpath-textfix-20261002", "0cd63f786290f967f41a5a6b615d54f98045ebec")],
                     drift=None, owner=[3], blocked=[13], pending=[], prereq=[], prs=[]))

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
        dependency=["owner ruling Q23 (HCL)"],
        stop="Any validation outcome differs from the uncompiled validator.",
        review_note="Pointers re-read; no wave-6 lane touched this entry.",
        gate_in=dict(lanes=["B-01R", "N-02"], published=[("exp/n-02-native-transport-20261002", "9846ac8033a8b5e952b0d44f39858625375d54e1")],
                     drift=None, owner=[16], blocked=[], pending=[], prereq=[], prs=[]))

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
        stop="The owner sets the expected session shape, or a later packet measures HCL on a different session shape.",
        review_note="Pointers re-read; its owner decision is still pending in STATE.",
        gate_in=dict(lanes=["N-04", "N-03"], published=[], drift=None, owner=[16], blocked=[13], pending=[], prereq=[], prs=[]))

    # ----------------------------------------------------------------------- new in wave 7 (wave-6 inputs)
    add(id="Q24", title="FIX-03 side-index session check 2237cf9c6 (kvnloo/cua#36 native ownership)",
        delta="Element-addressed text writes and focus use the token's own window snapshot instead of the (pid, xid) side "
              "index, so a session's valid token cannot write into, or focus, another session's window.",
        owner=["kvnloo/cua#36"],
        sha={"candidate": {"branch": "exp/fix-03-file-input-toctou-session-routing-20261003",
                           "sha": "e300edbd318f33b907741ca7aaec2ee666a2dac0",
                           "commits": ["2237cf9c6", "37d17e0b3"],
                           "note": "side-index scoping (Linux call sites) plus the recording-lookup session test"},
             "packets": [{"lane": "FIX-03"}]},
        evidence=[E("Cross-session mutations through the side index: F' {f}, F5 {f5}, unfixed U' {u}",
                    f=Q("FIX-03", ["e4", "F", "cross_session_mutation"]), f5=Q("FIX-03", ["e4", "F5", "cross_session_mutation"]),
                    u=Q("FIX-03", ["e4", "U", "cross_session_mutation"])),
                  E("F5 rows: WS gate {ws}, WK gate {wk}, WR gate {wr}; W2dX unfixed lands {wu}, F5 refuses {wf}",
                    ws=Q("FIX-03", ["part_c_d", "WS-F5", "gate_pass"]), wk=Q("FIX-03", ["part_c_d", "WK-F5", "gate_pass"]),
                    wr=Q("FIX-03", ["part_c_d", "WR-F5", "gate_pass"]), wu=Q("FIX-03", ["part_c_d", "W2dX-U", "B_landed"]),
                    wf=Q("FIX-03", ["part_c_d", "W2dX-F5", "B_refused"])),
                  E("Routing verdict {v}; routing fix needed {n}",
                    v=Q("FIX-03", ["C", "verdict"], file="dispositions.json"),
                    n=Q("FIX-03", ["C", "routing_fix_needed"], file="dispositions.json"))],
        missing=["Native AT-SPI pid-wide fallbacks still index the whole application walk by pid (E4 residue).",
                 "The FIX-03 packet verifier fix and the fallback pin (FIX-04, wave 7).",
                 "Freshness of the X11 rows against upstream main 9a2b1d99e (FRESH-07)."],
        action="fork candidate review together with Q02 (the kvnloo/cua#36 candidate is the F5 line)",
        dependency=["FIX-04 (wave 7)", "FRESH-07 (wave 7)", "drift-free or recertified on upstream main 9a2b1d99e"],
        stop="Any cross-session mutation on the F5 line or later.",
        review_note="New entry from the wave-6 FIX-03 packet (accepted); all pointers re-read at e300edbd3; candidate "
                    "head re-read on origin.",
        gate_in=dict(lanes=["FIX-03"],
                     published=[("exp/fix-03-file-input-toctou-session-routing-20261003",
                                 "e300edbd318f33b907741ca7aaec2ee666a2dac0")],
                     drift={"base": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218",
                            "candidate": "e300edbd318f33b907741ca7aaec2ee666a2dac0"},
                     owner=[], blocked=[], pending=["FIX-04", "FRESH-07"], prereq=[], prs=[]))

    add(id="Q25", title="effect=unknown for delivery=unknown refusals (FIX-03 follow-up; FIX-04 pending)",
        delta="Map a refusal issued after the effect may have landed (delivery=unknown, retryable=false) to "
              "effect=unknown instead of effect=refused, and keep the runner from re-dispatching it before reconciliation.",
        owner=["kvnloo/cua#36", "kvnloo/cua#105 (runner rule)", "kvnloo/cua#73 (E4: a possibly landed effect stays unknown)"],
        sha={"candidate": None, "packets": [{"lane": "FIX-03"}]},
        evidence=[E("F5 refusals with delivery unknown {u} of {n}, while the change still reached the server in {g} "
                    "cells; strict E4 count on F5 {s} (the seam-forced residue), {x} without it",
                    u=Q("FIX-03", ["part_a", "A1", "F5", "refused_post_check_unknown"]),
                    n=Q("FIX-03", ["part_a", "A1", "F5", "n"]), g=Q("FIX-03", ["part_a", "A1", "F5", "gen0_events_cells"]),
                    s=Q("FIX-03", ["e4_F5_strict"]), x=Q("FIX-03", ["e4_F5_excluding_seam_forced_residue"]))],
        missing=["A fix candidate with red/green tests and a REAL re-run (FIX-04 is building it in wave 7)."],
        action="fork fix candidate (FIX-04), then review",
        dependency=["FIX-04 (wave 7)", "owner ruling OR-24"],
        stop="Any possibly landed effect reported as refused, or any re-dispatch after a delivery=unknown refusal.",
        review_note="New entry for the wave-6 E4 residue (a); evidence re-read at e300edbd3. No candidate exists yet.",
        gate_in=dict(lanes=["FIX-03"], published=[], drift=None,
                     owner=[27], blocked=[], pending=["FIX-04"], prereq=[], prs=[]))

    add(id="Q26", title="OWN-20Q same_app_dialog fix 4ac191a7c (kvnloo/cua#20)",
        delta="The focus guard no longer treats a steal by the application's own dialog as same-app noise when it is "
              "a real steal, and leaves the app's own dialog focused when it should be.",
        owner=["kvnloo/cua#20"],
        sha={"candidate": {"branch": "exp/own-20q-a11y-triggers-dialog-markfree-20261003",
                           "sha": "44116546d54047f01d7318eecbc2f36303ec1013",
                           "commits": ["4ac191a7c"], "note": "focus_guard.rs (GQ source)"},
             "packets": [{"lane": "OWN-20Q"}]},
        evidence=[E("GA misclassified {ga} of {gan}; GQ verified restores {gq} of {gqn}; the app's own dialog stays "
                    "focused {d} of {dn} with false restores {f}",
                    ga=Q("OWN-20Q", ["dlg", "GA_misclassified"]), gan=Q("OWN-20Q", ["dlg", "n", "GA"]),
                    gq=Q("OWN-20Q", ["dlg", "GQ_verified_restore"]), gqn=Q("OWN-20Q", ["dlg", "n", "GQ"]),
                    d=Q("OWN-20Q", ["dlg", "dialog_control", "GQ", "dialog_left_focused"]),
                    dn=Q("OWN-20Q", ["dlg", "dialog_control", "GQ", "n"]),
                    f=Q("OWN-20Q", ["dlg", "dialog_control", "GQ", "false_restore"])),
                  E("Normal path with GQ: verified {v}; false restores {f}; spurious reconnects {r}",
                    v=Q("OWN-20Q", ["normal", "GQ_verified"]), f=Q("OWN-20Q", ["normal", "GQ_false_restores"]),
                    r=Q("OWN-20Q", ["normal", "GQ_spurious_reconnects"]))],
        missing=["Hyprland/Wayland: BLOCKED (seat).",
                 "Freshness against upstream main 9a2b1d99e (FRESH-07)."],
        action="fork candidate review (with Q06)",
        dependency=["FRESH-07 (wave 7)", "drift-free or recertified on upstream main 9a2b1d99e"],
        stop="The app's own dialog loses focus to a restore, or any false restore on the normal path.",
        review_note="New entry from the wave-6 OWN-20Q packet; pointers re-read at 44116546d.",
        gate_in=dict(lanes=["OWN-20Q"],
                     published=[("exp/own-20q-a11y-triggers-dialog-markfree-20261003",
                                 "44116546d54047f01d7318eecbc2f36303ec1013")],
                     drift={"base": "cb685fad7", "candidate": "4ac191a7c"},
                     owner=[], blocked=[7], pending=["FRESH-07"], prereq=[], prs=[]))

    # ------------------------------------------------------------------------ owner rulings
    def ruling(id_, title, refs, evidence, stop, blocked=(), lanes=(), pending=(), dep=None,
               owner=("kvnloo/cua#73",), delta=None, missing=None, note="", held=()):
        add(id=id_, title=title, delta=delta or title, owner=list(owner),
            sha={"candidate": None, "packets": [{"lane": l} for l in lanes]},
            evidence=list(evidence), missing=missing or ["The owner's ruling."], action="owner ruling",
            dependency=dep or ["owner"], stop=stop,
            review_note=note or "Owner item(s) re-read in the state extract; cited evidence re-read.",
            gate_in=dict(lanes=list(lanes), published=[], not_published=list(held), drift=None, owner=list(refs),
                         blocked=list(blocked), pending=list(pending), prereq=[], prs=[]))

    def st_owner(i):
        return E("STATE records the pending decision: {d}", d=ST("owner_decisions_pending", i))

    def st_blocked(i):
        return E("STATE records the blocker: {d}", d=ST("blocked_items_w6", i))

    ruling("OR-01", "OWN-36 I3s: shared-window replacement retirement", [0], lanes=["RECERT-FIX"],
           owner=["kvnloo/cua#36"],
           evidence=[st_owner(0),
                     gate("RECERT-FIX", ["kvnloo/cua#36 same-process two-window row", "gates", "0 cross-session mutations on F'"])],
           stop="The owner rules on I3s, or a native ownership candidate changes shared-window replacement.")
    ruling("OR-02", "B-02 H_E endpoint re-proof bound check (security policy)", [1], lanes=["B-02", "B-08"],
           owner=["kvnloo/cua#73", "kvnloo/cua#10"],
           evidence=[E("B-02 fill endpoint verdict {v}; saving {s} ms",
                       v=Q("B-02", ["browser", "measured", "classes", "fill", "E", "verdict"]),
                       s=Q("B-02", ["browser", "measured", "classes", "fill", "E", "saving_median_ms"], 1)),
                     E("On B7 (B-08 Part E, fill C arm) endpoint revalidation is {m} ms, verdict {v}",
                       m=Q("B-08", ["part_E", "classes", "fill", "C", "corr:below_gate_as_irreducible", "components", 3,
                                    "mean_ms"], 2),
                       v=Q("B-08", ["part_E", "classes", "fill", "C", "corr:below_gate_as_irreducible", "components", 3,
                                    "verdict"]))],
           stop="The owner rules on the bound check, or a security review changes the re-proof contract.")
    ruling("OR-03", "B-01 H_T: insert_text focus settle", [2], lanes=["B-01R"], owner=["kvnloo/cua#10"],
           evidence=[E("Verdict {v}", v=Q("B-01R", ["hypotheses", "H_T", "verdict"]))],
           stop="The owner rules, or the insert_text settle constant changes upstream.")
    ruling("OR-04", "N-01R H_C: native cursor reveal (text entry)", [4], lanes=["N-04"], owner=["kvnloo/cua#10"],
           evidence=[E("Reveal work removed on R'n text, BASE to best: {w} ms",
                       w=Q("N-04", ["e2", "text", "work_deleted_BASE_minus_best_ms", "reveal"], 1))],
           stop="The owner rules on reveal policy, or the reveal default changes upstream.")
    ruling("OR-06", "OWN-09R timeout semantics: bounded coordinator wait vs leaked-closure guards", [6], blocked=[9],
           lanes=["OWN-09R"], owner=["kvnloo/cua#9", "kvnloo/cua#84"],
           evidence=[st_owner(6), E("OWN-09R disposition {d}; failing rows {f}",
                                    d=Q("OWN-09R", ["disposition", "disposition"]),
                                    f=Q("OWN-09R", ["disposition", "failing_rows"]))],
           stop="The owner chooses a timeout semantics, or the kvnloo/cua#84 head moves.")
    ruling("OR-07", "OWN-09R / kvnloo/cua#9 R8: implement MCP notifications/cancelled or keep it ignored", [7], blocked=[9],
           lanes=["OWN-09R"], owner=["kvnloo/cua#9", "kvnloo/cua#84"],
           evidence=[E("R8 status on the revision: {s}; notifications in flight ignored {i}",
                       s=Q("OWN-09R", ["row_status", "P", "R8", "status"]),
                       i=Q("OWN-09R", ["matrix", "P|R8|sdk/notification_in_flight", "IGNORED"]))],
           stop="The owner rules on R8, or upstream implements notifications/cancelled.")
    ruling("OR-08", "trycua/cua PR 4336 timing fields emitted unconditionally vs env-gated wording", [8], lanes=["OWN-75R"],
           owner=["kvnloo/cua#75"],
           evidence=[st_owner(8), E("REAL trials verified {v} of {t}", v=Q("OWN-75R", ["real_analysis", "trials_verified"]),
                                    t=Q("OWN-75R", ["real_analysis", "trials"]))],
           stop="The owner rules, or the PR head moves from 8391cf802.")
    ruling("OR-09", "OWN-16W: JSON null refusal and the analyzer-vs-PREREG reading", [9, 21], blocked=[10],
           lanes=["RECERT-FIX"], owner=["kvnloo/cua#16"],
           evidence=[gate("RECERT-FIX", ["OWN-16W", "gates", "X11 F'' string_false refused 42/42"]),
                     E("Recertification verdict {v}", v=Q("RECERT-FIX", ["OWN-16W", "verdict"])), st_owner(21)],
           stop="The owner rules on null and on the gate reading, or selector parsing changes upstream.")
    ruling("OR-10", "R2-09 T3: install WebKitGTK (or use the flatpak runtime), or accept BLOCKED", [10], blocked=[6],
           lanes=["R2-09"], owner=["kvnloo/cua#93"],
           evidence=[st_blocked(6), E("R2-09 Chromium background S0 saving on checkbox {s} ms",
                                      s=Q("R2-09", ["paired_vs_base", "M/checkbox/B-S0", "T_base_minus_arm_median"], 1))],
           stop="The owner rules; a WebKitGTK row then runs or is recorded BLOCKED.")
    ruling("OR-11", "TypeSafe budget allocation for the remaining reached requests (live R' recertification, live toggle/modal "
                    "S, kvnloo/cua#78 R1/R4, native live arms) or a cap raise", [11, 17, 22, 30], blocked=[0, 1, 3],
           pending=["R2-07g"], owner=["kvnloo/cua#73"],
           evidence=[E("Loop budget ({p}): cap {c} requests reaching the provider; used {u} ({a} attempts); remaining {r}",
                       p=ST("provider_budget", "provider"), c=ST("provider_budget", "cap_requests"),
                       u=ST("provider_budget", "used_requests_reached_provider"),
                       a=ST("provider_budget", "used_attempts"), r=ST("provider_budget", "remaining_reached")),
                     st_owner(30)],
           stop="The owner raises the cap or accepts the BLOCKED live rows; R2-07g's spend changes the remaining figure.",
           note="Budget figures re-read from the state extract (re-derived from STATE by the verifier). R2-07g may spend "
                "part of the remainder in wave 7.")
    ruling("OR-12", "RECERT-FIX wave-4 cross-lane pkill ruling", [12], blocked=[15], owner=["kvnloo/cua#73"],
           evidence=[st_owner(12), st_blocked(15)],
           stop="The owner records the ruling (record-keeping only; the third attempt ran without pkill).")
    ruling("OR-14", "OWN-20G: reply-delay R1 row in place of the XGrabServer row; settle overshoot as IRREDUCIBLE coverage", [14],
           lanes=["OWN-20G"], owner=["kvnloo/cua#20"],
           evidence=[E("R1 reply-delay gate {r}; XGrabServer row gate {g}",
                       r=Q("OWN-20G", ["r1", "reply", "gate_G_20_of_20"]), g=Q("OWN-20G", ["r1", "grab", "gate_G_20_of_20"]))],
           stop="The owner rules, or Q06 supersedes OWN-20G for posting.")
    ruling("OR-15", "Browser per-process cold first snapshot: B-06 amendment reading (moot since B-08)", [15, 18],
           blocked=[16], lanes=["B-06", "B-08"], owner=["kvnloo/cua#10", "kvnloo/cua#73"],
           evidence=[E("B-06 primary verdict fill {p}; amended fill {a} (D {d} ms {ci})",
                       p=Q("B-06", ["classes", "fill", "verdict"]),
                       a=Q("B-06", ["block_x_amendment_1", "classes", "fill", "verdict"]),
                       d=Q("B-06", ["block_x_amendment_1", "classes", "fill", "D_C_minus_Wa", "median"], 1),
                       ci=Q("B-06", ["block_x_amendment_1", "classes", "fill", "D_C_minus_Wa", "ci"], 1)),
                     E("B-08 pre-registered verdicts: fill {f}, toggle {t}, modal {m}",
                       f=Q("B-08", ["classes", "fill", "verdict"]), t=Q("B-08", ["classes", "toggle", "verdict"]),
                       m=Q("B-08", ["classes", "modal", "verdict"]))],
           missing=["The owner closes the two B-06 owner items as moot (STATE still lists them as pending)."],
           stop="The owner closes the items, or B-08's reading is overturned by a later pre-registered run.")
    ruling("OR-16", "OWN-09R strict PREREG reading of the head-core unit row (Deviation 6)", [19], blocked=[10],
           lanes=["RECERT-FIX"], owner=["kvnloo/cua#9", "kvnloo/cua#84"],
           evidence=[E("Strict PREREG reading {s}; recertification verdict {v}",
                       s=Q("RECERT-FIX", ["OWN-09R (kvnloo/cua#84 revision)", "strict_prereg_reading", "verdict"]),
                       v=Q("RECERT-FIX", ["OWN-09R (kvnloo/cua#84 revision)", "verdict"]))],
           stop="The owner accepts the re-run rule or records the unit row as REVISE.")
    ruling("OR-17", "OWN-20P: marked-twin R1 substitution (superseded by OWN-20Q R1m) and A's trigger set", [20],
           lanes=["OWN-20P", "OWN-20Q"], owner=["kvnloo/cua#20"],
           evidence=[E("OWN-20Q mark-free R1m: G0 verified restores {g} of {n}; gate {k}",
                       g=Q("OWN-20Q", ["r1m", "G0_verified_restore"]), n=Q("OWN-20Q", ["r1m", "n", "G0"]),
                       k=Q("OWN-20Q", ["r1m", "gate"])),
                     E("A2 trigger rows: r3s gate {s}; r3n gate {r}",
                       s=Q("OWN-20Q", ["a2", "r3s_gate"]), r=Q("OWN-20Q", ["a2", "r3n_gate"]))],
           stop="The owner rules on the trigger set; the R1 half is already superseded by R1m.")
    ruling("OR-18", "Driver telemetry on by default in lane sessions (set it off in the shared session wrapper)", [24],
           owner=["kvnloo/cua#73"], evidence=[st_owner(24)],
           stop="The shared session wrapper sets telemetry off, or the owner accepts the default.")
    ruling("OR-19", "Fail-closed guard that rejects code-executing commands outside the hostless wrapper", [], blocked=[14],
           owner=["kvnloo/cua#73"], evidence=[st_blocked(14)],
           stop="The owner or orchestrator installs the guard, or rules it unnecessary.")
    ruling("OR-20", "kvnloo/cua#78 S1 backend row (adapter not local; only TypeSafe permitted)", [], blocked=[3],
           lanes=["OWN-78L"], owner=["kvnloo/cua#78"],
           evidence=[E("OWN-78L records the row as {b}", b=Q("OWN-78L", ["blocked", "S1_backend_row"]))],
           stop="The owner provides an adapter or permits another provider, or accepts BLOCKED.")
    ruling("OR-21", "Native T definition: may native whole-task T exclude provider decisions (scripted chooser), or fund live native arms",
           [], blocked=[2], owner=["kvnloo/cua#10"], evidence=[st_blocked(2)],
           stop="The owner accepts scripted-chooser native T or funds live native arms.")
    ruling("OR-22", "R2-07e: accept the n7_presat forced-fallback substitution for the spec's rename fallback", [25],
           blocked=[5], lanes=["R2-07e"], pending=["R2-07g"], owner=["kvnloo/cua#93", "kvnloo/cua#10"],
           evidence=[E("Modal forced fallback (kind {k}): outcome {o}, verified {v}, decisions {d}; modal disposition {m}",
                       k=Q("R2-07e", ["part_L", "modal", "LF", "kind"]), o=Q("R2-07e", ["part_L", "modal", "LF", "outcome"]),
                       v=Q("R2-07e", ["part_L", "modal", "LF", "verified"]),
                       d=Q("R2-07e", ["part_L", "modal", "LF", "decisions"]),
                       m=Q("R2-07e", ["disposition", "per_class", "modal", "lineage"]))],
           stop="The owner accepts or rejects the substitution; modal REVISE holds either way until a fallback verifies.")
    ruling("OR-23", "B-08: browser per-process cold excess is OWNER_DECISION (process/session reuse kept outside T)", [26],
           blocked=[13], lanes=["B-08"], owner=["kvnloo/cua#10", "kvnloo/cua#73"],
           evidence=[E("D = C - Wa (median T_j ms): fill {f} {fc}, toggle {t} {tc}, modal {m} {mc}; verdicts {fv} / {tv} / {mv}",
                       f=Q("B-08", ["classes", "fill", "D_C_minus_Wa", "median"], 2),
                       fc=Q("B-08", ["classes", "fill", "D_C_minus_Wa", "ci"], 2),
                       t=Q("B-08", ["classes", "toggle", "D_C_minus_Wa", "median"], 2),
                       tc=Q("B-08", ["classes", "toggle", "D_C_minus_Wa", "ci"], 2),
                       m=Q("B-08", ["classes", "modal", "D_C_minus_Wa", "median"], 2),
                       mc=Q("B-08", ["classes", "modal", "D_C_minus_Wa", "ci"], 2),
                       fv=Q("B-08", ["classes", "fill", "verdict"]), tv=Q("B-08", ["classes", "toggle", "verdict"]),
                       mv=Q("B-08", ["classes", "modal", "verdict"]))],
           stop="The owner rules on process or session reuse (a product policy outside T).")
    ruling("OR-24", "FIX-03 F4: accept IRREDUCIBLE-with-honest-unknown, and approve the effect=unknown follow-up", [27],
           lanes=["FIX-03"], pending=["FIX-04"], owner=["kvnloo/cua#36", "kvnloo/cua#73"],
           evidence=[E("F5: success receipts {s} of {n}; the change still reached the server in {g} cells; verdict {v}",
                       s=Q("FIX-03", ["part_a", "A1", "F5", "success_receipts"]), n=Q("FIX-03", ["part_a", "A1", "F5", "n"]),
                       g=Q("FIX-03", ["part_a", "A1", "F5", "gen0_events_cells"]),
                       v=Q("FIX-03", ["F4", "verdict"], file="dispositions.json"))],
           stop="The owner rules; FIX-04's candidate then either lands the effect=unknown mapping or is rejected.")
    ruling("OR-25", "OWN-20Q A2: a second persistent session-bus connection for an org.a11y.Bus name-owner watch", [28],
           blocked=[11], lanes=["OWN-20Q"], owner=["kvnloo/cua#20"],
           evidence=[E("r3n gate {g} (GQ passes {p} of {n}); r3n positive control {c}",
                       g=Q("OWN-20Q", ["a2", "r3n_gate"]), p=Q("OWN-20Q", ["a2", "r3n", "GQ", "pass"]),
                       n=Q("OWN-20Q", ["a2", "r3n", "GQ", "n"]), c=Q("OWN-20Q", ["a2", "r3n_positive_control"]))],
           stop="The owner allows or rejects the second connection; the trigger is then built or recorded as not built.")
    ruling("OR-26", "Published-fork privacy: the PUB-03 owner-ruling draft (lease-guarded replace) for OWN-20G, N-03 a3, N-04, "
                    "R2-10 (r1c) and R2-10R a3", [29], blocked=[12], lanes=["PUB-03"], pending=["PUB-04"],
           owner=["kvnloo/cua#73"],
           evidence=[st_owner(29), E("PUB-03 disposition: {d}", d=ST("dispositions", "PUB-03", "disposition_head"))],
           stop="The owner rules for each branch; Publish then runs only the ruled sequence.",
           held=[("exp/own-20g-guard-final-diff-r1c-20261003", "cb18ebfbdfa41b733b8c68c1971760ab39f392f4"),
                 ("exp/n-03-native-closure-axfg-r1c-20261003", "a2f7a93efa6689f201b7d4e4e8f53a37749bca2c"),
                 ("exp/n-04-native-composition-rprime-r1c-20261003", "32299f857c80683e1ebbe9e5602316f1a77a9635"),
                 ("exp/r2-10-composition-r1c-20261003", "eaca68df9d7f4757028ba787f2e2fa82c92bafe7")])

    # ----------------------------------------------------------- published-fork privacy candidates
    def priv(id_, title, delta, published, held, owner_refs, lanes, evidence, pending=(), missing=None, note=""):
        cand = None
        if held:
            cand = {"branch": held[0], "sha": held[1], "commits": [], "note": "held locally, not pushed (owner ruling)"}
        add(id=id_, title=title, delta=delta, owner=["kvnloo/cua#73"],
            sha={"candidate": cand, "packets": [{"lane": l} for l in lanes]},
            evidence=evidence, missing=missing or ["The owner's ruling (replace, delete and re-push, or accept)."],
            action="owner ruling, then a privacy rewrite on the fork", dependency=["owner ruling OR-26"],
            stop="The owner rules; Publish replaces only with a lease on the exact published SHA and checks ls-remote "
                 "before any delete.",
            review_note=note or "Published head re-read on origin; held candidate confirmed absent from origin.",
            gate_in=dict(lanes=list(lanes), published=[published], not_published=[held] if held else [],
                         drift=None, owner=list(owner_refs), blocked=[12], pending=list(pending), prereq=[], prs=[]))

    priv("PRIV-A", "Published exp/r2-10-composition-20261002 carries an encoded private-name list (candidate r1c eaca68df9)",
         "Replace the published R2-10 branch history with the clean rewrite r1c, or delete and re-push, or accept.",
         ("exp/r2-10-composition-20261002", "030f6bdbf811e124e11daa2de0569bffb993b66d"),
         ("exp/r2-10-composition-r1c-20261003", "eaca68df9d7f4757028ba787f2e2fa82c92bafe7"),
         [13, 23, 29], ["PUB-02", "R2-10"],
         [E("The R2-10 summary blob is identical at the published head and at r1c: {same}",
            same={"value": True, "check": {"op": "same_blob", "a": ["030f6bdbf811e124e11daa2de0569bffb993b66d",
                                                                    "docs/experiments/r2-10-composition-2026-10-02/r2-10-summary.json"],
                                            "b": ["eaca68df9d7f4757028ba787f2e2fa82c92bafe7",
                                                  "docs/experiments/r2-10-composition-2026-10-02/r2-10-summary.json"]}}),
          st_owner(13)])
    priv("PRIV-B", "Published exp/own-20g-guard-final-diff-a2-20261003 carries the local user name in raw output (candidate cb18ebfbd)",
         "Replace the published OWN-20G branch with the PUB-03 rewrite, or delete and re-push, or accept.",
         ("exp/own-20g-guard-final-diff-a2-20261003", "ce7544cc064cecfd9ba4702466a1d0f24b1799b6"),
         ("exp/own-20g-guard-final-diff-r1c-20261003", "cb18ebfbdfa41b733b8c68c1971760ab39f392f4"),
         [23, 29], ["OWN-20G", "PUB-03"],
         [E("PUB-03 disposition: {d}", d=ST("dispositions", "PUB-03", "disposition_head")), st_owner(23)])
    priv("PRIV-C", "Published exp/n-03-native-closure-axfg-a3-20261003 carries tmp session-bus paths (candidate a2f7a93ef)",
         "Replace the published N-03 branch with the PUB-03 rewrite, or delete and re-push, or accept.",
         ("exp/n-03-native-closure-axfg-a3-20261003", "6b70ec9024cc3921f7637bba2ffabcc93e29fc77"),
         ("exp/n-03-native-closure-axfg-r1c-20261003", "a2f7a93efa6689f201b7d4e4e8f53a37749bca2c"),
         [29], ["N-03", "PUB-03"],
         [E("PUB-03 disposition: {d}", d=ST("dispositions", "PUB-03", "disposition_head")), st_blocked(12)])
    priv("PRIV-D", "Published exp/n-04-native-composition-rprime-20261003 carries tmp session-bus paths (candidate 32299f857)",
         "Replace the published N-04 branch with the PUB-03 rewrite, or delete and re-push, or accept.",
         ("exp/n-04-native-composition-rprime-20261003", "9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2"),
         ("exp/n-04-native-composition-rprime-r1c-20261003", "32299f857c80683e1ebbe9e5602316f1a77a9635"),
         [29], ["N-04", "PUB-03"],
         [E("PUB-03 disposition: {d}", d=ST("dispositions", "PUB-03", "disposition_head")), st_blocked(12)])
    priv("PRIV-E", "Published exp/r2-10r-recert-a3-20261003 carries tmp session-bus paths (PUB-03 finding; PUB-04 pending)",
         "Build a clean rewrite of the published R2-10R a3 head and replace it, or delete and re-push, or accept.",
         ("exp/r2-10r-recert-a3-20261003", "d22eeb2ecf8a679d1425c21120a599775aa0817d"), None,
         [29], ["R2-10R", "PUB-03"],
         [E("PUB-03 disposition: {d}", d=ST("dispositions", "PUB-03", "disposition_head")), st_owner(29)],
         pending=["PUB-04"],
         missing=["A clean rewrite candidate (PUB-04 is building it in wave 7).", "The owner's ruling."],
         note="New entry for the PUB-03 R2-10R a3 finding; published head re-read on origin; no candidate exists yet.")
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


def published_refs(g):
    """(branch, sha, expect) for every ref the entry cites: expect 'present' or 'absent' (held candidates)."""
    out = []
    seen = set()
    for br, sha in g["published"]:
        out.append((br, sha, "present"))
        seen.add(br)
    for br, sha in g.get("not_published", []):
        if br not in seen:
            out.append((br, sha, "absent"))
            seen.add(br)
    for l in g["lanes"]:
        br, sha, _d, _f = QP[l]
        if br not in seen and l not in HELD_LANES:   # a held candidate is cited only where an entry names it
            out.append((br, sha, "present"))
            seen.add(br)
    return out


def review_for(it, heads, gh, ext):
    """The fresh review record: reviewer, date, every SHA checked (origin + gh reads) and the outcome."""
    g = it["gate_in"]
    checked = []
    for i in g["owner"]:
        checked.append({"what": "owner_decisions_pending[%d]" % i, "cited": None,
                        "head": ext["owner_decisions_pending"][i][:90], "ok": True})
    for i in g["blocked"]:
        checked.append({"what": "blocked_items_w6[%d]" % i, "cited": None,
                        "head": ext["blocked_items_w6"][i][:90], "ok": True})
    for br, sha, expect in published_refs(g):
        full = C.full_sha(sha)
        ls = heads.get("refs/heads/" + br)
        ghv = gh.get("fork_branches", {}).get(br, "not read")
        ok = (ls is None and ghv is None) if expect == "absent" else (ls == full and ghv == full)
        checked.append({"what": "fork branch " + br, "cited": full, "expect": expect, "ls_remote": ls, "gh": ghv, "ok": ok})
    for p in it["sha"].get("packets", []):
        br, sha, _d, _f = QP[p["lane"]]
        checked.append({"what": "packet %s commit" % p["lane"], "cited": sha, "exists": C.sha_exists(sha),
                        "ok": C.sha_exists(sha)})
    prs = {(x["repo"], x["number"]): x for x in gh.get("prs", [])}
    for repo, num in g["prs"]:
        x = prs.get((repo, num), {})
        checked.append({"what": "%s PR %d head" % (repo, num), "cited": PR_PINS[(repo, num)], "gh": x.get("head_sha"),
                        "state": x.get("state"), "ok": x.get("head_sha") == PR_PINS[(repo, num)] and x.get("state") == "open"})
    if g["drift"]:
        um = gh.get("upstream_main", {}).get("sha")
        checked.append({"what": "upstream main (drift pin)", "cited": MAIN_PIN, "gh": um, "ok": um == MAIN_PIN})
    ok = all(c["ok"] for c in checked) and bool(it.get("review_note"))
    return {"reviewer": LANE_ID, "date_utc": (gh.get("read_utc") or ["", ""])[1],
            "shas_checked": checked,
            "evidence_check": "every completed-evidence pointer re-read at its packet SHA; missing evidence re-checked "
                              "against the accepted packets through wave 6",
            "note": it.get("review_note", ""),
            "outcome": "consistent" if ok else "inconsistent"}


def gates_for(it, ext, heads, prheads, review):
    g = it["gate_in"]
    acc_all = set(x for v in ext["accepted_by_wave"].values() for x in v)
    lanes_ok = all(l in acc_all for l in g["lanes"])
    out = {}
    out["accepted_packet"] = {"value": bool(g["lanes"]) and lanes_ok,
                              "basis": "lanes %s accepted in STATE (accepted_by_wave)" % ", ".join(g["lanes"]) if g["lanes"]
                              else "no packet backs this entry"}
    pub = []
    for br, sha, expect in published_refs(g):
        full = C.full_sha(sha)
        got = heads.get("refs/heads/" + br)
        ok = (got is None) if expect == "absent" else (got == full)
        pub.append({"branch": br, "sha": full, "origin": got, "expect": expect, "ok": ok})
    held = [p for p in pub if p["expect"] == "absent"]
    out["published_on_origin"] = {
        "value": bool(pub) and all(p["ok"] for p in pub) and not held, "refs": pub, "held": bool(held),
        "basis": ("candidate held for the owner ruling: not on origin by design, so the entry is not published"
                  if held else "git ls-remote origin") if pub else "nothing to publish for this entry"}
    if g["drift"]:
        d = drift_check(g["drift"])
        out["recertified_or_drift_free"] = dict(d, basis="libs/cua-driver drift from the certified base to upstream main "
                                                         "(pin): no overlap with the claim and only non-Linux allowlisted paths")
    else:
        out["recertified_or_drift_free"] = {"value": True, "basis": "not applicable: no libs/cua-driver claim"}
    odp = ext["owner_decisions_pending"]
    blk = ext["blocked_items_w6"]
    owner_blk = [i for i in g["blocked"] if C.owner_type(blk[i])]
    out["no_pending_owner_decision"] = {
        "value": not g["owner"] and not owner_blk,
        "owner_decisions_pending": [{"index": i, "head": odp[i][:90]} for i in g["owner"]],
        "blocked_items_owner": [{"index": i, "head": blk[i][:90]} for i in owner_blk],
        "blocked_items_other": [{"index": i, "head": blk[i][:90]} for i in g["blocked"] if i not in owner_blk],
        "basis": "STATE owner_decisions_pending / owner-type blocked_items_w6 entries cited by index"}
    out["no_pending_lane"] = {"value": not g["pending"],
                              "lanes": [{"lane": l, "branch": PENDING_W7[l], "scope": PENDING_W7_SCOPE[l]} for l in g["pending"]],
                              "basis": "wave-7 lanes still running (planner assignment)"}
    out["prerequisites_met"] = {"value": not g.get("prereq"), "missing": list(g.get("prereq", [])),
                                "basis": "non-owner prerequisites the entry's action needs before posting"}
    prs = []
    for repo, num in g["prs"]:
        pin = PR_PINS[(repo, num)]
        got = prheads.get((repo, num))
        prs.append({"repo": repo, "number": num, "pinned": pin, "live": got, "ok": got == pin})
    out["pr_head_unchanged"] = {"value": all(p["ok"] for p in prs), "prs": prs,
                                "basis": "git ls-remote refs/pull/N/head (and gh, in the review)" if prs else "no live PR for this entry"}
    out["fresh_review_done"] = {"value": review["outcome"] == "consistent",
                                "basis": "review by %s on %s: %s" % (review["reviewer"], review["date_utc"], review["outcome"])}
    out["READY_NOW"] = all(out[k]["value"] for k in GATE_ORDER)
    return out


def render_evidence(e):
    vals = {}
    for k, p in e["n"].items():
        x = p["value"]
        nd = p.get("from", {}).get("round") if isinstance(p, dict) and "from" in p else None
        if isinstance(x, str):
            vals[k] = C.fork_refs(x)
        elif isinstance(x, dict):
            vals[k] = json.dumps(x, sort_keys=True)
        else:
            vals[k] = C.fmt(x, nd)
    return e["t"].format(**vals)


def all_branches(its):
    out = set()
    for it in its:
        for br, _sha, _e in published_refs(it["gate_in"]):
            out.add(br)
    return sorted(out)


def build():
    if not os.path.exists(EXTRACT):
        raise SystemExit("run make_state_extract.py first")
    ext = json.load(open(EXTRACT))
    if os.environ.get("CUA_LOOP_STATE"):
        fresh = MSE.state_extract()
        if fresh != ext:
            raise SystemExit("inputs/state-extract.json is not current: run make_state_extract.py")
    _EXT["ext"] = ext
    gh = json.load(open(GH_READS)) if os.path.exists(GH_READS) else {}
    its = items()
    branches = all_branches(its)
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
    since_prev = [x for x in C.git("diff", "--name-only", PREV_PIN, MAIN_PIN, "--", "libs/cua-driver").stdout.splitlines() if x]
    upstream_main_live = up.get("refs/heads/main")
    post_pin = []
    if upstream_main_live and C.sha_exists(upstream_main_live):
        post_pin = [x for x in C.git("diff", "--name-only", MAIN_PIN, upstream_main_live, "--", "libs/cua-driver").stdout.splitlines() if x]
    with open(os.path.join(RAW, "drift.json"), "w") as f:
        json.dump({"pin": MAIN_PIN, "since": "0f1955d2f1ee2b01b40775aa53ea2af0b5544218", "libs_cua_driver_files": drift_main,
                   "non_allowlisted": [x for x in drift_main if not DRIFT_ALLOW.search(x)],
                   "previous_pin": PREV_PIN, "since_previous_pin": since_prev,
                   "since_previous_pin_non_allowlisted": [x for x in since_prev if not DRIFT_ALLOW.search(x)],
                   "upstream_main_live": upstream_main_live,
                   "post_pin_libs_cua_driver_files": post_pin}, f, indent=1)
        f.write("\n")
    out_items = []
    for it in its:
        review = review_for(it, heads, gh, ext)
        gates = gates_for(it, ext, heads, prheads, review)
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
            "review": review,
            "ready_now": gates,
        })
    doc = {
        "schema": "cua-rfc-74-posting-queue/v2",
        "lane": LANE_ID,
        "format": "delta -> canonical owner -> exact SHA -> completed evidence -> missing evidence -> action type -> "
                  "dependency -> stop condition",
        "pinned_main": MAIN_PIN,
        "previous_pin": PREV_PIN,
        "ready_now_rule": "READY NOW = " + " AND ".join(GATE_ORDER),
        "pending_w7": PENDING_W7,
        "pending_w7_scope": PENDING_W7_SCOPE,
        "pr_pins": [{"repo": r, "number": n, "pinned": s} for (r, n), s in PR_PINS.items()],
        "pr_recorded": [{"repo": r, "number": n} for (r, n) in PR_RECORDED],
        "state_extract": os.path.relpath(EXTRACT, HERE),
        "gh_reads": os.path.relpath(GH_READS, HERE),
        "items": out_items,
        "ready_now_count": sum(1 for i in out_items if i["ready_now"]["READY_NOW"]),
    }
    doc["headline"] = headline(doc)
    return doc


# --------------------------------------------------------------------------------- rendering

GATE_ORDER = ["accepted_packet", "published_on_origin", "recertified_or_drift_free", "no_pending_owner_decision",
              "no_pending_lane", "prerequisites_met", "pr_head_unchanged", "fresh_review_done"]
GATE_SHORT = ["packet", "origin", "drift", "owner", "w7", "prereq", "PR", "review"]


def failing(it):
    return [k for k in GATE_ORDER if not it["ready_now"][k]["value"]]


def headline(doc):
    """Counts computed from the gates (the verifier recomputes them)."""
    by_gate = {k: sum(1 for it in doc["items"] if not it["ready_now"][k]["value"]) for k in GATE_ORDER}
    single = {}
    for it in doc["items"]:
        f = failing(it)
        if len(f) == 1:
            single.setdefault(f[0], []).append(it["id"])
    reviewed = sum(1 for it in doc["items"] if it["review"]["outcome"] == "consistent")
    return {"items": len(doc["items"]), "ready_now": doc["ready_now_count"], "reviewed_consistent": reviewed,
            "failing_by_gate": by_gate, "failing_exactly_one_gate": single,
            "pending_w7_items": sorted(it["id"] for it in doc["items"] if not it["ready_now"]["no_pending_lane"]["value"]),
            "owner_gated_items": sorted(it["id"] for it in doc["items"]
                                        if not it["ready_now"]["no_pending_owner_decision"]["value"])}


def yn(b):
    return "yes" if b else "**no**"


def why_text(g):
    why = []
    for k in GATE_ORDER:
        if g[k]["value"]:
            continue
        if k == "no_pending_owner_decision":
            why.append("owner: decision pending (%s)" % ", ".join(
                ["owner_decisions_pending[%d]" % x["index"] for x in g[k]["owner_decisions_pending"]] +
                ["blocked_items_w6[%d]" % x["index"] for x in g[k]["blocked_items_owner"]]))
        elif k == "no_pending_lane":
            why.append("w7: " + ", ".join("pending wave 7 %s" % x["lane"] for x in g[k]["lanes"]))
        elif k == "recertified_or_drift_free":
            why.append("drift: not drift-free against upstream main `%s` (%d non-allowlisted drift paths, %d overlapping "
                       "the claim)" % (MAIN_PIN[:9], len(g[k].get("drift_non_allowlisted", [])),
                                       len(g[k].get("intersection", []))))
        elif k == "published_on_origin":
            if g[k].get("held"):
                why.append("origin: candidate held for the owner ruling (not on origin by design)")
            else:
                why.append("origin: not published at the cited SHA" if g[k]["refs"] else "origin: nothing published")
        elif k == "accepted_packet":
            why.append("packet: no accepted packet")
        elif k == "prerequisites_met":
            why.append("prereq: " + "; ".join(g[k]["missing"]))
        elif k == "pr_head_unchanged":
            why.append("PR: live PR head moved")
        elif k == "fresh_review_done":
            why.append("review: fresh review inconsistent")
    return why


def render(doc):
    L = [BEGIN, ""]
    h = doc["headline"]
    L.append("Format: `%s`. READY NOW = all eight gates true. Drift pin: upstream main `%s` (live at the review)." % (
        doc["format"], doc["pinned_main"][:9]))
    L.append("")
    L.append("**READY NOW: %d of %d entries.** Fresh review recorded on %d of %d entries (outcome consistent)." % (
        h["ready_now"], h["items"], h["reviewed_consistent"], h["items"]))
    L.append("")
    L.append("- Entries failing each gate: " + ", ".join("%s %d" % (s, h["failing_by_gate"][k])
                                                        for k, s in zip(GATE_ORDER, GATE_SHORT)) + ".")
    one = h["failing_exactly_one_gate"]
    L.append("- Entries failing exactly one gate: " + ("; ".join("%s: %s" % (GATE_SHORT[GATE_ORDER.index(k)], ", ".join(v))
                                                                 for k, v in sorted(one.items())) if one else "none") + ".")
    L.append("- Pending a wave-7 lane: %s." % (", ".join(h["pending_w7_items"]) or "none"))
    L.append("- Behind an owner decision: %s." % (", ".join(h["owner_gated_items"]) or "none"))
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
        rv = it["review"]
        shas = [c for c in rv["shas_checked"] if c.get("cited")]
        st_refs = [c["what"] for c in rv["shas_checked"] if not c.get("cited")]
        L.append("- **review** -> %s, %s: %s; %s%s. %s" % (
            rv["reviewer"], rv["date_utc"], rv["outcome"],
            ("%d SHAs checked (%s)" % (len(shas), ", ".join("%s `%s`" % (c["what"], c["cited"][:9]) for c in shas)))
            if shas else "no SHA to check",
            ("; STATE entries re-read: " + ", ".join(st_refs)) if st_refs else "", rv["note"]))
        why = why_text(g)
        L.append("- **READY NOW: %s.** %s" % ("YES" if g["READY_NOW"] else "NO",
                                              ("Failing gates: " + "; ".join(why) + ".") if why else "All eight gates pass."))
        L.append("")
    L.append(END)
    return "\n".join(L)


def assemble_gh(path):
    """raw/gh-reads.json from the JSON lines collect_gh_reads.sh printed (read-only gh reads)."""
    out = {"tool": "gh api (read-only; collect_gh_reads.sh)", "read_utc": ["", ""], "prs": [], "upstream_main": {},
           "fork_branches": {}}
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        k = r.pop("kind")
        if k == "read_start":
            out["read_utc"][0] = r["utc"]
        elif k == "read_end":
            out["read_utc"][1] = r["utc"]
        elif k == "pr":
            out["prs"].append(r)
        elif k == "upstream_main":
            out["upstream_main"] = r
        elif k == "branch":
            out["fork_branches"][r["branch"]] = r["sha"]
    os.makedirs(RAW, exist_ok=True)
    with open(GH_READS, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print("gh-reads.json written: %d PRs, %d branches" % (len(out["prs"]), len(out["fork_branches"])))


def main():
    if "--assemble-gh" in sys.argv:
        assemble_gh(sys.argv[sys.argv.index("--assemble-gh") + 1])
        return
    if "--list-branches" in sys.argv:
        ext = json.load(open(EXTRACT))
        _EXT["ext"] = ext
        for b in all_branches(items()):
            print(b)
        return
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
    print("queue.json written: %d items, READY NOW %d, reviewed %d" % (
        len(doc["items"]), doc["ready_now_count"], doc["headline"]["reviewed_consistent"]))


if __name__ == "__main__":
    main()
