# kvnloo/cua#74: posting queue (round 2, wave-7 refresh and fresh review, staged)

Lane DOC-10-74b, wave 7 of the CUA RFC loop. This is the kvnloo/cua#74 deliverable for kvnloo/cua#73 end condition
E5(c). It refreshes DOC-10-74 (wave 6, `a3e3cb86e`) and records the first fresh review of every entry. It is staged on
the fork branch `docs/accounting-10-queue-74-r2-20261003`. Nothing has been posted, and nothing here goes to
trycua/cua: upstream items are written as plain text ("trycua/cua PR 4316").

## Format

Every surviving delta is one entry in kvnloo/cua#74's own format:

`delta -> canonical owner -> exact SHA -> completed evidence -> missing evidence -> action type -> dependency -> stop condition`

- **Evidence numbers.** Each completed-evidence line is a template whose numbers are filled from pointers into an
  accepted packet at an exact commit, or into the committed STATE extract. Gate lines quote the packet's own gate key.
  `queue.json` holds the pointers, and `verify_artifacts.py` re-reads them and fails on any bare number in free text.
- **Owner decisions.** Every owner decision pending in the loop STATE is covered by an entry; rulings are their own
  entries with action type "owner ruling" (OR-xx). Every entry, rulings included, has real completed evidence and a
  real stop condition.
- **What changed in this refresh.** The wave-6 packets (B-08, R2-07e, OWN-78L, FIX-03, OWN-20Q, PUB-03) are folded in:
  new entries Q24 (FIX-03 side index), Q25 (the effect=unknown follow-up), Q26 (OWN-20Q dialog fix), OR-22 to OR-26
  (the wave-6 owner items) and PRIV-C to PRIV-E (the PUB-03 privacy findings, including R2-10R a3); FIX-03 F4's
  honest-unknown result goes into Q03 and OR-24, and OWN-78L's KEEP on F into Q13.

## READY NOW gate

Each entry has eight explicit booleans. READY NOW = all eight true. Nothing is forced: an entry behind an owner
decision or a running wave-7 lane stays NOT READY and names the exact gate.

| Gate | Source of truth (recomputed by the verifier) |
|---|---|
| packet | Every lane the entry cites is in the loop STATE's accepted lists (`inputs/state-extract.json`, with the STATE sha256) |
| origin | Every cited branch is on origin at the cited SHA (read-only `git ls-remote https://github.com/kvnloo/cua.git`). An entry whose candidate is a held privacy rewrite is not published by design, so this gate is false for it |
| drift | Recertified on, or free of drift against, the live upstream main read with gh at the review (`9a2b1d99e`, see `raw/gh-reads.json`). Every libs/cua-driver path changed from the entry's certified base to that main must be outside the entry's changed files and must be one of the non-Linux allowlisted paths (platform-macos, platform-windows, the macOS Skills doc, the AppKit / WinUI3 / WPF e2e tests and fixtures, `tests/fixtures/shared/scenarios.json`). Main now also changes Linux and core paths (the X11 overlay and the core verify_state expectation, trycua/cua PR 4529 and PR 4531, plus release version files), so every entry with a libs/cua-driver claim fails this gate until it is recertified; `raw/drift.json` lists the files |
| owner | No pending owner decision cited for the entry (STATE `owner_decisions_pending` and the owner-type `blocked_items_w6`, by index; an item marked RESOLVED never counts) |
| w7 | No wave-7 lane still running for the entry: "pending wave 7 <id>" for B-09, R2-07f, R2-07g, FIX-04, FRESH-07 or PUB-04 |
| prereq | No unmet non-owner prerequisite, such as "reviewed product diff missing" for a default-behaviour change, a missing form-scope fix, or logs that must be committed first |
| PR | Where a live PR exists, its head is unchanged (read-only `git ls-remote refs/pull/N/head`, and gh in the review): trycua/cua PR 4316 `a0bca7440`, PR 4336 `8391cf802`, PR 4394 `039257811`; kvnloo/cua#84 `566b9c732`, kvnloo/cua#105 `98a45e6c5`, kvnloo/cua#106 `c45845797` |
| review | A fresh review is recorded on the entry: reviewer (this lane), date, every SHA checked (cited branch heads against ls-remote and gh, packet commits, PR heads and states from gh, the drift pin) and the STATE entries it re-read, with outcome "consistent" |

## Fresh review

`collect_gh_reads.sh` made the read-only gh reads (trycua/cua PRs 4316, 4336, 4394 open at their pins; PRs 4529 and
4531 merged into main after the tested sources; kvnloo/cua#84, kvnloo/cua#105, kvnloo/cua#106 open at their pins;
upstream main; every cited fork branch head). For every entry the reviewer re-read each completed-evidence pointer at
its packet SHA, re-checked the missing evidence against the accepted packets through wave 6, and recorded the result
in the entry's `review` field. Held privacy candidates were confirmed absent from origin. The headline counts below
are computed from the gates, and the verifier recomputes them.

This lane attempted no TypeSafe request and none reached the provider. Verify with
`python3 docs/rfc/74-posting-queue/verify_artifacts.py` under the hostless wrapper, with `CUA_LOOP_STATE` set.

<!-- BEGIN GENERATED: make_queue.py -->

Format: `delta -> canonical owner -> exact SHA -> completed evidence -> missing evidence -> action type -> dependency -> stop condition`. READY NOW = all eight gates true. Drift pin: upstream main `9a2b1d99e` (live at the review).

**READY NOW: 0 of 55 entries.** Fresh review recorded on 55 of 55 entries (outcome consistent).

- Entries failing each gate: packet 5, origin 11, drift 21, owner 46, w7 17, prereq 5, PR 0, review 0.
- Entries failing exactly one gate: owner: Q20, Q21, Q22, Q23, OR-01, OR-02, OR-03, OR-04, OR-06, OR-07, OR-08, OR-09, OR-10, OR-14, OR-15, OR-16, OR-17, OR-20, OR-23, OR-25; drift: Q09, Q10.
- Pending a wave-7 lane: OR-11, OR-22, OR-24, OR-26, PRIV-E, Q01, Q02, Q03, Q06, Q07, Q15, Q16, Q18, Q19, Q24, Q25, Q26.
- Behind an owner decision: OR-01, OR-02, OR-03, OR-04, OR-06, OR-07, OR-08, OR-09, OR-10, OR-11, OR-12, OR-14, OR-15, OR-16, OR-17, OR-18, OR-19, OR-20, OR-21, OR-22, OR-23, OR-24, OR-25, OR-26, PRIV-A, PRIV-B, PRIV-C, PRIV-D, PRIV-E, Q03, Q04, Q05, Q07, Q08, Q12, Q13, Q15, Q16, Q17, Q18, Q19, Q20, Q21, Q22, Q23, Q25.

| ID | Entry | Action type | packet | origin | drift | owner | w7 | prereq | PR | review | READY NOW |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Q01 | FIX-01 detached-node refusal (dom_event route) + refused-is-refused runner rule | fork candidate review, then a reviewed upstream PR proposal (not posted; upstream owner named at that time) | yes | yes | **no** | yes | **no** | yes | yes | yes | **no** |
| Q02 | FIX-02 F1-F3 + FIX-03 side-index fix: native token ownership, runtime generation, re-dispatch scope | fork candidate review (F5 line), then a reviewed upstream PR proposal (not posted) | yes | yes | **no** | yes | **no** | yes | yes | yes | **no** |
| Q03 | FIX-02 F4 + FIX-03 F5: set_input_files on a detached input (honest receipt, effect can land) | hold (REVISE); fork candidate after the owner ruling and FIX-04 | yes | yes | **no** | **no** | **no** | yes | yes | yes | **no** |
| Q04 | kvnloo/cua#84 revision (OWN-09R): cancel before admission, guard ownership | hold; revision staged on the fork for the kvnloo/cua#84 owner | yes | yes | **no** | **no** | yes | yes | yes | yes | **no** |
| Q05 | OWN-16W fix dd205d17b: refuse non-boolean modality selectors | hold; fork candidate after the owner rulings | yes | yes | **no** | **no** | yes | yes | yes | yes | **no** |
| Q06 | OWN-20P G: focus-guard final read on deadline exit (R1 now mark-free, OWN-20Q) | fork candidate review (with Q26) | yes | yes | **no** | yes | **no** | yes | yes | yes | **no** |
| Q07 | OWN-20P A + OWN-20Q A2: in-process AT-SPI bus-restart reconnect and its triggers | fork candidate review after the owner rulings | yes | yes | **no** | **no** | **no** | yes | yes | yes | **no** |
| Q08 | OWN-20G guard a30cbbc3b (superseded by the G port; privacy candidate cb18ebfbd held) | privacy rewrite on the fork after the owner ruling - no posting; the product delta moves to Q06 | yes | **no** | **no** | **no** | yes | yes | yes | yes | **no** |
| Q09 | BUG-01 A: foreground trusted click receipt labelled background (fix 2533db6d5 + 49a3adf0f) | fork fix branch for owner review; upstream routing decided by the kvnloo/cua#38 owner (not posted) | yes | yes | **no** | yes | yes | yes | yes | yes | **no** |
| Q10 | BUG-01 B: CDP sessions accumulate (attach per call, never detach) | evidence note only (no fix) | yes | yes | **no** | yes | yes | yes | yes | yes | **no** |
| Q11 | OWN-105 runner reconcile (kvnloo/cua#105 gaps G1-G3 + pre-write rule) | fork branch + kvnloo/cua#105 comment (fork only) | yes | yes | **no** | yes | yes | **no** | yes | yes | **no** |
| Q12 | trycua/cua PR 4336 native timing parity (OWN-75R) | evidence comment for the trycua/cua PR 4336 owner (drafted on the fork; not posted upstream) | yes | yes | **no** | **no** | yes | yes | yes | yes | **no** |
| Q13 | Fork fix candidate F for trycua/cua PR 4394 (restore form + page + outline): KEEP (OWN-78L) | evidence comment for kvnloo/cua#78 (fork only); upstream routing by the PR 4394 owner | yes | yes | **no** | **no** | yes | yes | yes | yes | **no** |
| Q14 | B-02 H_V browser admission tools-list cache | product-change proposal (default behaviour change; needs a reviewed product diff first) | yes | yes | **no** | yes | yes | **no** | yes | yes | **no** |
| Q15 | N-04 V native admission tools-list cache | product-change proposal (with Q14; one admission cache for both paths) | yes | yes | **no** | **no** | **no** | **no** | yes | yes | **no** |
| Q16 | Post-DoAction sleep deletion scope (N-01R / R2-09 / N-03) | product-change proposal, scoped to the measured routes (default behaviour change) | yes | yes | **no** | **no** | **no** | **no** | yes | yes | **no** |
| Q17 | R2-03 guarded completion = trycua/cua PR 4316 | evidence comment for the trycua/cua PR 4316 owner, including the wrong-target finding (drafted on the fork; not posted upstream) | yes | yes | **no** | **no** | yes | **no** | yes | yes | **no** |
| Q18 | R2-07b fill compiled replay (re-qualified by FIX-01) | research evidence for the trycua/cua issue 3963 rewrite draft (DOC-3963); no upstream posting | yes | yes | **no** | **no** | **no** | yes | yes | yes | **no** |
| Q19 | R2-07c/d/e toggle and modal compiled replay (toggle KEEP, modal REVISE) | research evidence (compiled replay in the composed toggle configuration; excluded for modal) | yes | yes | **no** | **no** | **no** | yes | yes | yes | **no** |
| Q20 | R2-08 API route per task (owner ruling) | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| Q21 | B-01 fast feedback glide / glide-off policy (owner ruling) | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| Q22 | B-01 H_C / N-02 HC caller-compiled output validators | client-side change proposal for the jev-use runners (after the HCL ruling) | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| Q23 | HCL lazy per-schema validators (owner ruling) | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| Q24 | FIX-03 side-index session check 2237cf9c6 (kvnloo/cua#36 native ownership) | fork candidate review together with Q02 (the kvnloo/cua#36 candidate is the F5 line) | yes | yes | **no** | yes | **no** | yes | yes | yes | **no** |
| Q25 | effect=unknown for delivery=unknown refusals (FIX-03 follow-up; FIX-04 pending) | fork fix candidate (FIX-04), then review | yes | yes | yes | **no** | **no** | yes | yes | yes | **no** |
| Q26 | OWN-20Q same_app_dialog fix 4ac191a7c (kvnloo/cua#20) | fork candidate review (with Q06) | yes | yes | **no** | yes | **no** | yes | yes | yes | **no** |
| OR-01 | OWN-36 I3s: shared-window replacement retirement | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-02 | B-02 H_E endpoint re-proof bound check (security policy) | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-03 | B-01 H_T: insert_text focus settle | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-04 | N-01R H_C: native cursor reveal (text entry) | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-06 | OWN-09R timeout semantics: bounded coordinator wait vs leaked-closure guards | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-07 | OWN-09R / kvnloo/cua#9 R8: implement MCP notifications/cancelled or keep it ignored | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-08 | trycua/cua PR 4336 timing fields emitted unconditionally vs env-gated wording | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-09 | OWN-16W: JSON null refusal and the analyzer-vs-PREREG reading | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-10 | R2-09 T3: install WebKitGTK (or use the flatpak runtime), or accept BLOCKED | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-11 | TypeSafe budget allocation for the remaining reached requests (live R' recertification, live toggle/modal S, kvnloo/cua#78 R1/R4, native live arms) or a cap raise | owner ruling | **no** | **no** | yes | **no** | **no** | yes | yes | yes | **no** |
| OR-12 | RECERT-FIX wave-4 cross-lane pkill ruling | owner ruling | **no** | **no** | yes | **no** | yes | yes | yes | yes | **no** |
| OR-14 | OWN-20G: reply-delay R1 row in place of the XGrabServer row; settle overshoot as IRREDUCIBLE coverage | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-15 | Browser per-process cold first snapshot: B-06 amendment reading (moot since B-08) | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-16 | OWN-09R strict PREREG reading of the head-core unit row (Deviation 6) | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-17 | OWN-20P: marked-twin R1 substitution (superseded by OWN-20Q R1m) and A's trigger set | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-18 | Driver telemetry on by default in lane sessions (set it off in the shared session wrapper) | owner ruling | **no** | **no** | yes | **no** | yes | yes | yes | yes | **no** |
| OR-19 | Fail-closed guard that rejects code-executing commands outside the hostless wrapper | owner ruling | **no** | **no** | yes | **no** | yes | yes | yes | yes | **no** |
| OR-20 | kvnloo/cua#78 S1 backend row (adapter not local; only TypeSafe permitted) | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-21 | Native T definition: may native whole-task T exclude provider decisions (scripted chooser), or fund live native arms | owner ruling | **no** | **no** | yes | **no** | yes | yes | yes | yes | **no** |
| OR-22 | R2-07e: accept the n7_presat forced-fallback substitution for the spec's rename fallback | owner ruling | yes | yes | yes | **no** | **no** | yes | yes | yes | **no** |
| OR-23 | B-08: browser per-process cold excess is OWNER_DECISION (process/session reuse kept outside T) | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-24 | FIX-03 F4: accept IRREDUCIBLE-with-honest-unknown, and approve the effect=unknown follow-up | owner ruling | yes | yes | yes | **no** | **no** | yes | yes | yes | **no** |
| OR-25 | OWN-20Q A2: a second persistent session-bus connection for an org.a11y.Bus name-owner watch | owner ruling | yes | yes | yes | **no** | yes | yes | yes | yes | **no** |
| OR-26 | Published-fork privacy: the PUB-03 owner-ruling draft (lease-guarded replace) for OWN-20G, N-03 a3, N-04, R2-10 (r1c) and R2-10R a3 | owner ruling | yes | **no** | yes | **no** | **no** | yes | yes | yes | **no** |
| PRIV-A | Published exp/r2-10-composition-20261002 carries an encoded private-name list (candidate r1c eaca68df9) | owner ruling, then a privacy rewrite on the fork | yes | **no** | yes | **no** | yes | yes | yes | yes | **no** |
| PRIV-B | Published exp/own-20g-guard-final-diff-a2-20261003 carries the local user name in raw output (candidate cb18ebfbd) | owner ruling, then a privacy rewrite on the fork | yes | **no** | yes | **no** | yes | yes | yes | yes | **no** |
| PRIV-C | Published exp/n-03-native-closure-axfg-a3-20261003 carries tmp session-bus paths (candidate a2f7a93ef) | owner ruling, then a privacy rewrite on the fork | yes | **no** | yes | **no** | yes | yes | yes | yes | **no** |
| PRIV-D | Published exp/n-04-native-composition-rprime-20261003 carries tmp session-bus paths (candidate 32299f857) | owner ruling, then a privacy rewrite on the fork | yes | **no** | yes | **no** | yes | yes | yes | yes | **no** |
| PRIV-E | Published exp/r2-10r-recert-a3-20261003 carries tmp session-bus paths (PUB-03 finding; PUB-04 pending) | owner ruling, then a privacy rewrite on the fork | yes | yes | yes | **no** | **no** | yes | yes | yes | **no** |

### Q01. FIX-01 detached-node refusal (dom_event route) + refused-is-refused runner rule

- **delta** -> Driver refuses dom_event browser_click / browser_pointer / browser_download on a detached ref node (isConnected checked inside the dispatching callFunctionOn; browser_ref_stale, effect refused); jev-use runners treat refused as refused and never re-dispatch an unverified accepted mutation.
- **canonical owner** -> kvnloo/cua#73 (stale-dispatch invariant); kvnloo/cua#93 (R2-07 gap); kvnloo/cua#105 (runner rule)
- **exact SHA** -> candidate `exp/r2-10r-control-a2-20261003` @ `8a2362770` commits `a4cda75bd`, `8a2362770` (FIX-01 Part A + Part B rebased on 0f1955d2f (the R2-10R control binary source); original commits 8cfa8c1db + 6eb9319fe on the FIX-01 packet branch); packet FIX-01 `exp/fix-01-detached-node-refusal-20261002` @ `4a301d32a`; packet R2-10R `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec`; packet FIX-03 `exp/fix-03-file-input-toctou-session-routing-20261003` @ `e300edbd3`
- **completed evidence** -> N4a re-render on the FIX-01 fixed tree: first click refused 20 of 20 (browser_ref_stale), then rebound and verified 20; unfixed tree accepted 20 of 20; old-node page events on the fixed tree 0; Recertified on 0f1955d2f inside R2-10R: N4a controls passed 15 of 15; Runner: re-dispatches after an unverified accepted mutation on the fixed runner 0; on the old runner, cells with a re-dispatch 10; FIX-03 (wave 6): a refusal issued after the assignment carries delivery unknown (20 of 20 on F5) while the change still reached the server in 20 cells; this is the receipt the runner rule must not treat as refused
- **missing evidence** -> The runner rule must honour delivery=unknown / retryable=false refusals as unknown (no re-dispatch, reconcile first); FIX-04 is building and measuring that in wave 7. The trusted-input route keeps a residual re-render window between send and landing (FIX-01 follow-up; characterised under a shared lock only). Recertification on upstream main 9a2b1d99e (drift gate).
- **action type** -> fork candidate review, then a reviewed upstream PR proposal (not posted; upstream owner named at that time)
- **dependency** -> FIX-04 (wave 7); FIX-02 F3 (retry scope) travels with Part B; drift-free or recertified on upstream main 9a2b1d99e
- **stop condition** -> Any false refusal on a connected node, a refused dispatch whose effect landed reported as refused, or a re-dispatch after a delivery=unknown refusal.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 8 SHAs checked (fork branch exp/r2-10r-control-a2-20261003 `8a2362770`, fork branch exp/fix-01-detached-node-refusal-20261002 `4a301d32a`, fork branch exp/r2-10r-recert-a3-20261003 `d22eeb2ec`, fork branch exp/fix-03-file-input-toctou-session-routing-20261003 `e300edbd3`, packet FIX-01 commit `4a301d32a`, packet R2-10R commit `d22eeb2ec`, packet FIX-03 commit `e300edbd3`, upstream main (drift pin) `9a2b1d99e`). FIX-01 and R2-10R pointers re-read at their packet SHAs; candidate head re-read on origin. The FIX-03 receipt evidence (delivery unknown with a landed effect) is new since wave 6 and makes the runner half depend on FIX-04; missing evidence updated accordingly.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 0 overlapping the claim); w7: pending wave 7 FIX-04.

### Q02. FIX-02 F1-F3 + FIX-03 side-index fix: native token ownership, runtime generation, re-dispatch scope

- **delta** -> F1 binds native element tokens to the publishing session; F2 starts snapshot ids at a random per-process base (runtime generation); F3 lets jev-use runners re-dispatch only after pre-dispatch refusals. The kvnloo/cua#36 candidate must also carry FIX-03's 2237cf9c6 (element-addressed writes and focus use the token's own window snapshot), because F' alone lets a valid token write into another session's window.
- **canonical owner** -> kvnloo/cua#36; kvnloo/cua#105 (F3 runner rule)
- **exact SHA** -> candidate `exp/fix-03-file-input-toctou-session-routing-20261003` @ `e300edbd3` commits `8e0e8aea0`, `205a4ecb2`, `cdffb3213`, `2237cf9c6` (F5 line: F1-F3 rebased on 0f1955d2f (RECERT-FIX F') plus the FIX-03 commits; the head also carries FIX-03's measurement-only seam 5a1e209ab (env-gated, default off)); packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`; packet FIX-02 `exp/fix-02-token-ownership-retry-scope-20261002` @ `cea02cb74`; packet FIX-03 `exp/fix-03-file-input-toctou-session-routing-20261003` @ `e300edbd3`
- **completed evidence** -> I2 F' 40/40: yes; I2d F' 40/40: yes; I5p F' 20/20: yes; I5pt F' 10/10: yes; 0 blind re-dispatches on F': yes; 0 cross-session mutations on F': yes; Recertification verdicts: F1 RECERT_PASS, F2 RECERT_PASS, F3 RECERT_PASS; FIX-03 side index: cross-session mutations on F' 40, on F5 0; F5 own-window gates WS yes, WK yes; W2dX discriminating yes
- **missing evidence** -> Native AT-SPI fallbacks still index the whole application walk by pid when the cached object is missing (FIX-03 remaining limit; E4 residue). The runner F3 rule against delivery=unknown / retryable=false refusals (FIX-04, wave 7). Freshness of the X11 rows against upstream main 9a2b1d99e (FRESH-07, wave 7).
- **action type** -> fork candidate review (F5 line), then a reviewed upstream PR proposal (not posted)
- **dependency** -> FIX-04 (wave 7); FRESH-07 (wave 7); drift-free or recertified on upstream main 9a2b1d99e
- **stop condition** -> Upstream main changes snapshot_store.rs or the Linux token path; any cross-session mutation on the fixed tree.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 7 SHAs checked (fork branch exp/fix-03-file-input-toctou-session-routing-20261003 `e300edbd3`, fork branch exp/fix-recert-a3-20261003 `939580fc6`, fork branch exp/fix-02-token-ownership-retry-scope-20261002 `cea02cb74`, packet RECERT-FIX commit `939580fc6`, packet FIX-02 commit `cea02cb74`, packet FIX-03 commit `e300edbd3`, upstream main (drift pin) `9a2b1d99e`). RECERT-FIX gate keys re-read; the wave-6 FIX-03 finding (F' cross-session hole, fixed in F5) moves the candidate from exp/fix-02r-a3-20261003 to the FIX-03 head, which contains F1-F3 (ancestry checked) and 2237cf9c6. The recording-lookup and W2c/W2d gaps listed in wave 6 are closed by FIX-03 and removed.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 0 overlapping the claim); w7: pending wave 7 FIX-04, pending wave 7 FRESH-07.

### Q03. FIX-02 F4 + FIX-03 F5: set_input_files on a detached input (honest receipt, effect can land)

- **delta** -> Refuse browser_set_input_files on a file input detached before the call (F4) and never report success for a node detached after the check (F5, post-assignment isConnected check).
- **canonical owner** -> kvnloo/cua#36
- **exact SHA** -> candidate `exp/fix-03-file-input-toctou-session-routing-20261003` @ `e300edbd3` commits `a357d061d`, `b235fabef` (F4 rebased on 0f1955d2f plus F5 b235fabef); packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`; packet FIX-02 `exp/fix-02-token-ownership-retry-scope-20261002` @ `cea02cb74`; packet FIX-03 `exp/fix-03-file-input-toctou-session-routing-20261003` @ `e300edbd3`
- **completed evidence** -> F4 F' 20/20 (narrower claim; TOCTOU not covered): yes; FIX-03 A1 (seam-forced race): F5 success receipts 0 of 20; refused with delivery unknown 20; the change event still reached the server in 20 cells; F'S positive control success receipts 20; Disposition REVISE (IRREDUCIBLE-with-honest-unknown)
- **missing evidence** -> The refusal is mapped to effect=refused although the effect can land: it must become effect=unknown (FIX-04, wave 7). Owner acceptance of IRREDUCIBLE-with-honest-unknown (CDP cannot make the check and the assignment atomic).
- **action type** -> hold (REVISE); fork candidate after the owner ruling and FIX-04
- **dependency** -> owner ruling OR-24; FIX-04 (wave 7)
- **stop condition** -> Any success receipt for a detached node on the fixed tree, or a delivery=unknown refusal still reported as effect=refused after FIX-04.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 7 SHAs checked (fork branch exp/fix-03-file-input-toctou-session-routing-20261003 `e300edbd3`, fork branch exp/fix-recert-a3-20261003 `939580fc6`, fork branch exp/fix-02-token-ownership-retry-scope-20261002 `cea02cb74`, packet RECERT-FIX commit `939580fc6`, packet FIX-02 commit `cea02cb74`, packet FIX-03 commit `e300edbd3`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[27]. Wave-6 FIX-03 replaces the pending marker: F5 measured; F4 stays REVISE with an honest-unknown boundary. Candidate moved to the FIX-03 head (a357d061d and b235fabef are ancestors).
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 0 overlapping the claim); owner: decision pending (owner_decisions_pending[27]); w7: pending wave 7 FIX-04.

### Q04. kvnloo/cua#84 revision (OWN-09R): cancel before admission, guard ownership

- **delta** -> Revised kvnloo/cua#84: cancellation checked before admission, admission holds owned by the operation, Linux spawn_blocking sites converted to spawn_blocking_owned.
- **canonical owner** -> kvnloo/cua#9; kvnloo/cua#84
- **exact SHA** -> candidate `exp/own-09r2-a3-20261003` @ `ba611b51a` (kvnloo/cua#84 head plus the OWN-09R revision commits, rebased on 0f1955d2f; kvnloo/cua#84 itself is not modified); packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`; packet OWN-09R `exp/own-09r-84-revision-20261002` @ `0c2896a53`
- **completed evidence** -> P_R1D_pass_40: yes; P_R6_pass_80: yes; M_R1D_fail_40: yes; Recertification verdict RECERT_PASS; strict PREREG reading REVISE
- **missing evidence** -> Owner call on the timeout path: guards held by a leaked closure after a foreground timeout vs a bounded coordinator wait with a structured refusal. Owner call on R8 (MCP notifications/cancelled is ignored on both arms). Owner call on the strict unit-row reading (Deviation 6 re-run rule). R3 on macOS (held-input oracle): BLOCKED, hardware.
- **action type** -> hold; revision staged on the fork for the kvnloo/cua#84 owner
- **dependency** -> owner rulings OR-06, OR-07 and OR-16; kvnloo/cua#84 head unchanged
- **stop condition** -> Upstream main changes the coordinator / barrier path, or kvnloo/cua#84 head moves.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 7 SHAs checked (fork branch exp/own-09r2-a3-20261003 `ba611b51a`, fork branch exp/own-09r-84-revision-20261002 `0c2896a53`, fork branch exp/fix-recert-a3-20261003 `939580fc6`, packet RECERT-FIX commit `939580fc6`, packet OWN-09R commit `0c2896a53`, kvnloo/cua PR 84 head `566b9c732`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[6], owner_decisions_pending[7], owner_decisions_pending[19], blocked_items_w6[9], blocked_items_w6[10]. Gate keys re-read; kvnloo/cua#84 head re-read with gh (open, unchanged). No wave-6 lane touched it.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 0 overlapping the claim); owner: decision pending (owner_decisions_pending[6], owner_decisions_pending[7], owner_decisions_pending[19], blocked_items_w6[9], blocked_items_w6[10]).

### Q05. OWN-16W fix dd205d17b: refuse non-boolean modality selectors

- **delta** -> get_window_state refuses non-boolean include_screenshot / modality selectors with invalid_arguments before any producer runs (Linux).
- **canonical owner** -> kvnloo/cua#16
- **exact SHA** -> candidate `exp/own-16w2-a3-20261003` @ `7e31eae59` (dd205d17b rebased on 0f1955d2f); packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`; packet OWN-16W `exp/own-16w-sway-modality-20261002` @ `1b9819157`
- **completed evidence** -> X11 F'' string_false refused 42/42: yes; X11 U'' accepts 42/42 (both string rows): yes; S-W F'' rows meet the wave-3 gates: yes; Recertification verdict RECERT_PASS
- **missing evidence** -> Owner call: the fix also refuses JSON null (formerly the default). Owner call: accept the PREREG F'' gate where the wave-3 analyzer prints REVISE. macOS and Windows parity: BLOCKED (hardware); the macOS get_window_state file changed again on main (trycua/cua PR 4531).
- **action type** -> hold; fork candidate after the owner rulings
- **dependency** -> owner ruling OR-09
- **stop condition** -> Upstream main changes get_window_state selector parsing on Linux.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 6 SHAs checked (fork branch exp/own-16w2-a3-20261003 `7e31eae59`, fork branch exp/fix-recert-a3-20261003 `939580fc6`, fork branch exp/own-16w-sway-modality-20261002 `1b9819157`, packet RECERT-FIX commit `939580fc6`, packet OWN-16W commit `1b9819157`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[9], owner_decisions_pending[21]. Gate keys re-read. Upstream main now also changes platform-macos get_window_state (allowlisted, non-Linux); the Linux claim is unaffected, but the drift gate fails on other Linux/core paths.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 0 overlapping the claim); owner: decision pending (owner_decisions_pending[9], owner_decisions_pending[21]).

### Q06. OWN-20P G: focus-guard final read on deadline exit (R1 now mark-free, OWN-20Q)

- **delta** -> focus_guard: a final focus read when the settle watch ends on its deadline after a read that began before it (restores a focus steal the watch would otherwise miss silently).
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> candidate `exp/own-20q-a11y-triggers-dialog-markfree-20261003` @ `44116546d` commits `a761f1f1f` (G port a761f1f1f (clean main cb685fad7) under the OWN-20Q head); packet OWN-20P `exp/own-20p-guard-port-a11y-20261003` @ `64081dded`; packet OWN-20Q `exp/own-20q-a11y-triggers-dialog-markfree-20261003` @ `44116546d`
- **completed evidence** -> Mark-free R1m on product binaries (OWN-20Q): unguarded U0 silent misses 40 of 40; guarded G0 verified restores 40 of 40; false restores 0; Product G on the normal path (OWN-20P): verified 40 of 40; failures plus false restores 0
- **missing evidence** -> Hyprland/Wayland focus rows: BLOCKED (real seat). Freshness against upstream main 9a2b1d99e, whose X11 overlay change may interact with focus (FRESH-07).
- **action type** -> fork candidate review (with Q26)
- **dependency** -> FRESH-07 (wave 7); drift-free or recertified on upstream main 9a2b1d99e
- **stop condition** -> The port changes quiet-path behaviour, or any false restore on the normal path.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 5 SHAs checked (fork branch exp/own-20q-a11y-triggers-dialog-markfree-20261003 `44116546d`, fork branch exp/own-20p-guard-port-a11y-20261003 `64081dded`, packet OWN-20P commit `64081dded`, packet OWN-20Q commit `44116546d`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: blocked_items_w6[7]. OWN-20Q R1m replaces the marked-twin substitution (STATE blocked_items_w6 notes it superseded), so the R1 half of that owner decision no longer gates this entry; A's trigger set stays with Q07.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 0 overlapping the claim); w7: pending wave 7 FRESH-07.

### Q07. OWN-20P A + OWN-20Q A2: in-process AT-SPI bus-restart reconnect and its triggers

- **delta** -> The Driver reconnects to a restarted accessibility bus in-process (stream end, plus NoReply with a Peer.Ping probe from 31318e374); the org.a11y.Bus name-owner trigger is not built.
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> candidate `exp/own-20q-a11y-triggers-dialog-markfree-20261003` @ `44116546d` commits `064d2e4ad`, `31318e374` (A 064d2e4ad plus the A2 trigger 31318e374); packet OWN-20P `exp/own-20p-guard-port-a11y-20261003` @ `64081dded`; packet OWN-20Q `exp/own-20q-a11y-triggers-dialog-markfree-20261003` @ `44116546d`
- **completed evidence** -> R3 bus restart (OWN-20P): liveness GA 20 of the pre-registered twenty (yes); safety GA 20; OWN-20Q A2: real restarts live where killed 23 of 23; stale mutations 0; r3s gate yes; name-owner row r3n gate no (GQ passes 0 of 20)
- **missing evidence** -> The name-owner trigger needs a second persistent session-bus connection: owner/design decision. Owner call: is the trigger set (stream end + NoReply/Peer.Ping) enough. Hyprland/Wayland: BLOCKED (seat).
- **action type** -> fork candidate review after the owner rulings
- **dependency** -> owner rulings OR-17 and OR-25; FRESH-07 (wave 7)
- **stop condition** -> Any stale mutation after a reconnect, or reconnect breaks the quiet path.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 5 SHAs checked (fork branch exp/own-20q-a11y-triggers-dialog-markfree-20261003 `44116546d`, fork branch exp/own-20p-guard-port-a11y-20261003 `64081dded`, packet OWN-20P commit `64081dded`, packet OWN-20Q commit `44116546d`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[20], owner_decisions_pending[28], blocked_items_w6[7], blocked_items_w6[11]. OWN-20Q A2 measured (REVISE on r3n). r3s is cited with its boundary (GA passes trivially) and r3_carry with the real-restart view, as the wave-6 verifier asked.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 0 overlapping the claim); owner: decision pending (owner_decisions_pending[20], owner_decisions_pending[28], blocked_items_w6[11]); w7: pending wave 7 FRESH-07.

### Q08. OWN-20G guard a30cbbc3b (superseded by the G port; privacy candidate cb18ebfbd held)

- **delta** -> The original focus-guard final-read diff, tested on 0f1955d2f plus measurement picks.
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> candidate `exp/own-20g-guard-final-diff-r1c-20261003` @ `cb18ebfbd` commits `a30cbbc3b` (PUB-03 privacy candidate of the published a2 head ce7544cc0, held for the owner ruling; a30cbbc3b does not apply to clean main and is superseded by a761f1f1f (Q06)); packet OWN-20G `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc0`; packet PUB-03 `exp/own-20g-guard-final-diff-r1c-20261003` @ `cb18ebfbd`
- **completed evidence** -> R1 reply-delay row: gate (G restores every trial) yes; specified XGrabServer row gate no; R3 bus restart: safety gate yes; in-process liveness gate no
- **missing evidence** -> The owner's privacy ruling on the published a2 head (replace with cb18ebfbd, delete and re-push, or accept). Owner calls: the reply-delay row in place of the XGrabServer row, and the settle-overshoot IRREDUCIBLE judgement.
- **action type** -> privacy rewrite on the fork after the owner ruling - no posting; the product delta moves to Q06
- **dependency** -> owner rulings PRIV-B, OR-14 and OR-26
- **stop condition** -> Superseded once Q06 is accepted for posting.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 5 SHAs checked (fork branch exp/own-20g-guard-final-diff-a2-20261003 `ce7544cc0`, fork branch exp/own-20g-guard-final-diff-r1c-20261003 `cb18ebfbd`, packet OWN-20G commit `ce7544cc0`, packet PUB-03 commit `cb18ebfbd`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[14], owner_decisions_pending[23], owner_decisions_pending[29], blocked_items_w6[12]. PUB-03 built and verified the candidate (accepted wave 6); it is held, so the origin gate is false by design. Evidence pointers re-read at the OWN-20G packet SHA.
- **READY NOW: NO.** Failing gates: origin: candidate held for the owner ruling (not on origin by design); drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 0 overlapping the claim); owner: decision pending (owner_decisions_pending[14], owner_decisions_pending[23], owner_decisions_pending[29], blocked_items_w6[12]).

### Q09. BUG-01 A: foreground trusted click receipt labelled background (fix 2533db6d5 + 49a3adf0f)

- **delta** -> The click receipt reports delivery=foreground only when the executed branch activates the window. The fix is the pair 2533db6d5 + 49a3adf0f; neither commit is cited alone (d86b3b1d1 and the superseded fix binary are not cited).
- **canonical owner** -> kvnloo/cua#38 (upstream compatibility: trycua/cua 4009, plain text)
- **exact SHA** -> candidate `exp/bug-01-delivery-cdp-sessions-20261002` @ `097b4f097` commits `2533db6d5`, `49a3adf0f` (fix pair on base c4d0c6625); packet BUG-01 `exp/bug-01-delivery-cdp-sessions-20261002` @ `097b4f097`
- **completed evidence** -> Baseline trusted-foreground arm: mislabelled background 20 of 20; fixed: delivery foreground 20; Only the delivery mode changed between baseline and the fix pair: yes
- **missing evidence** -> Recertification on upstream main 9a2b1d99e (Linux/core paths changed on main since c4d0c6625). Windows, macOS and embedded labels are UNIT-only.
- **action type** -> fork fix branch for owner review; upstream routing decided by the kvnloo/cua#38 owner (not posted)
- **dependency** -> recertification on current main
- **stop condition** -> The producer branch structure changes upstream, or any other receipt field changes.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 3 SHAs checked (fork branch exp/bug-01-delivery-cdp-sessions-20261002 `097b4f097`, packet BUG-01 commit `097b4f097`, upstream main (drift pin) `9a2b1d99e`). Pointers re-read; unchanged since wave 6. Recertification is the only open gate besides drift.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (30 non-allowlisted drift paths, 0 overlapping the claim).

### Q10. BUG-01 B: CDP sessions accumulate (attach per call, never detach)

- **delta** -> Each browser call attaches one CDP session and never detaches it; the post-navigation event burst scales with the session count. Accumulation only - no fix and no cost on a no-op page.
- **canonical owner** -> trycua/cua 4052 (plain text; evidence owner)
- **exact SHA** -> packet BUG-01 `exp/bug-01-delivery-cdp-sessions-20261002` @ `097b4f097`
- **completed evidence** -> Live CDP sessions at the end of each long run: [304.0, 304.0, 304.0]
- **missing evidence** -> A cost on a non-trivial page (none measured).
- **action type** -> evidence note only (no fix)
- **dependency** -> drift-free on upstream main 9a2b1d99e for the browser paths
- **stop condition** -> Upstream changes CDP session lifetime.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 3 SHAs checked (fork branch exp/bug-01-delivery-cdp-sessions-20261002 `097b4f097`, packet BUG-01 commit `097b4f097`, upstream main (drift pin) `9a2b1d99e`). Pointer re-read; unchanged since wave 6.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (30 non-allowlisted drift paths, 0 overlapping the claim).

### Q11. OWN-105 runner reconcile (kvnloo/cua#105 gaps G1-G3 + pre-write rule)

- **delta** -> Python and TS jev-use runners reconcile an ambiguous mutation receipt before any second dispatch (no new service).
- **canonical owner** -> kvnloo/cua#105
- **exact SHA** -> candidate `exp/own-105-runner-reconcile-20261002` @ `b97daa4ba` (on base 345ff6d9d); packet OWN-105 `exp/own-105-runner-reconcile-20261002` @ `b97daa4ba`
- **completed evidence** -> Fixed runners: trials 148; duplicates 0; receipts present 148; second dispatches 0; Gate verdict KEEP; unfixed base reproduces the gap: yes
- **missing evidence** -> Red/green counts live only in gitignored logs: force-add them before posting. TS R6 is emulated-state evidence (Python R6 carries the gate alone). Recertification on current main (Linux/core paths changed since 345ff6d9d).
- **action type** -> fork branch + kvnloo/cua#105 comment (fork only)
- **dependency** -> red/green logs committed; kvnloo/cua#105 head unchanged
- **stop condition** -> kvnloo/cua#105 head moves, or any duplicate mutation on a fixed runner.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 4 SHAs checked (fork branch exp/own-105-runner-reconcile-20261002 `b97daa4ba`, packet OWN-105 commit `b97daa4ba`, kvnloo/cua PR 105 head `98a45e6c5`, upstream main (drift pin) `9a2b1d99e`). Pointers re-read; kvnloo/cua#105 head re-read with gh (open, unchanged). The red/green-log prerequisite was a missing-evidence line in wave 6 and is now an explicit gate input.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (30 non-allowlisted drift paths, 0 overlapping the claim); prereq: red/green counts committed (they live only in gitignored logs).

### Q12. trycua/cua PR 4336 native timing parity (OWN-75R)

- **delta** -> trycua/cua PR 4336 adds native timing fields to the jev-use runners with no cross-language field mismatch and no behaviour change versus its base.
- **canonical owner** -> kvnloo/cua#75; upstream trycua/cua PR 4336 (plain text)
- **exact SHA** -> candidate `exp/own-75r-timing-parity-4336-r1b-20261003` @ `efe36d1a1` (r1b = publish fixes on the accepted packet e02621fdc; PR head 8391cf802); packet OWN-75R `exp/own-75r-timing-parity-4336-20261002` @ `e02621fdc`
- **completed evidence** -> REAL trials verified 160 of 160; non-loopback refusals by the net guard 0
- **missing evidence** -> Owner call: the PR emits the timing fields unconditionally (log-only) vs the env-gated / default-off wording. kvnloo/cua#75 body still cites an older head (d301a076c). Recertification against current main (the PR base predates many Linux/core changes).
- **action type** -> evidence comment for the trycua/cua PR 4336 owner (drafted on the fork; not posted upstream)
- **dependency** -> owner ruling OR-08; PR head unchanged
- **stop condition** -> The PR head moves from 8391cf802.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 5 SHAs checked (fork branch exp/own-75r-timing-parity-4336-r1b-20261003 `efe36d1a1`, fork branch exp/own-75r-timing-parity-4336-20261002 `e02621fdc`, packet OWN-75R commit `e02621fdc`, trycua/cua PR 4336 head `8391cf802`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[8]. Pointers re-read; trycua/cua PR 4336 re-read with gh (open, head unchanged).
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (181 non-allowlisted drift paths, 0 overlapping the claim); owner: decision pending (owner_decisions_pending[8]).

### Q13. Fork fix candidate F for trycua/cua PR 4394 (restore form + page + outline): KEEP (OWN-78L)

- **delta** -> Restore the form, page and outline context in the PR 4394 browser request so the live provider stops abstaining at step one.
- **canonical owner** -> kvnloo/cua#78; upstream trycua/cua PR 4394 (plain text)
- **exact SHA** -> candidate `exp/own-78l-r1-lite-f-20261003` @ `d9edde70e` commits `61eec0909` (fix candidate F head 61eec0909); packet OWN-78A `exp/own-78a-abstain-isolation-4394-20261003` @ `6f6c67955`; packet OWN-78L `exp/own-78l-r1-lite-f-20261003` @ `d9edde70e`
- **completed evidence** -> Live TypeSafe step-one isolation: PR abstained 5/5; PR plus form correct 1/5; F correct 5/5; pre-PR correct 5/5; R1-lite on F (OWN-78L, live TypeSafe): verified 3 of 3; backend == responder 3; replays or restarts 0; disposition KEEP
- **missing evidence** -> Full-n live R1 / R4: BLOCKED (paid budget). S1 backend row: BLOCKED (owner decision; adapter not local). The remaining A2-vs-A3 gap (question key, instructions, goal / history placement, visual): BLOCKED (budget). The step-one margin is thin and n is small: KEEP is a gate result, not a rate.
- **action type** -> evidence comment for kvnloo/cua#78 (fork only); upstream routing by the PR 4394 owner
- **dependency** -> owner rulings OR-11 and OR-20 (blocked rows); PR head unchanged
- **stop condition** -> The trycua/cua PR 4394 head moves from 039257811.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 6 SHAs checked (fork branch exp/own-78l-r1-lite-f-20261003 `d9edde70e`, fork branch exp/own-78a-abstain-isolation-4394-20261003 `6f6c67955`, packet OWN-78A commit `6f6c67955`, packet OWN-78L commit `d9edde70e`, trycua/cua PR 4394 head `039257811`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[22], owner_decisions_pending[30], blocked_items_w6[3]. OWN-78L closes R1-lite (KEEP on F). Candidate moved to the OWN-78L head (61eec0909 is an ancestor). PR 4394 re-read with gh (open, head unchanged).
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (181 non-allowlisted drift paths, 0 overlapping the claim); owner: decision pending (owner_decisions_pending[22], owner_decisions_pending[30], blocked_items_w6[3]).

### Q14. B-02 H_V browser admission tools-list cache

- **delta** -> Cache the validated tools/list at MCP admission instead of re-validating it per call (browser).
- **canonical owner** -> kvnloo/cua#93; kvnloo/cua#10
- **exact SHA** -> candidate `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec` commits `770a715ed` (measurement-only env-gated knob (B-02) carried in R'; no product diff exists yet); packet B-02 `exp/b-02-browser-driver-sites-20261002` @ `b282ff389`; packet R2-10R `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec`
- **completed evidence** -> B-02 fill: verdict DELETED (KEEP); admission component saving 24.3 ms; B-02 toggle verdict DELETED (KEEP); modal verdict NOT_MATERIAL (saving not shown on T_oracle); On R' inside COMP: admission work removed per fill trial 8.7 ms
- **missing evidence** -> A reviewed product (non-env-gated) diff with unit tests; the knob is measurement-only. Modal is NOT_MATERIAL on the B-02 binary.
- **action type** -> product-change proposal (default behaviour change; needs a reviewed product diff first)
- **dependency** -> a reviewed product diff; drift-free or recertified on upstream main 9a2b1d99e
- **stop condition** -> A product diff changes the tools/list envelope bytes.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 5 SHAs checked (fork branch exp/b-02-browser-driver-sites-20261002 `b282ff389`, fork branch exp/r2-10r-recert-a3-20261003 `d22eeb2ec`, packet B-02 commit `b282ff389`, packet R2-10R commit `d22eeb2ec`, upstream main (drift pin) `9a2b1d99e`). Pointers re-read. The wave-6 gate row did not record the missing product diff; it is now the prerequisite gate. The candidate branch is the published R2-10R a3 head, whose privacy rewrite (PUB-04) changes no number.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 1 overlapping the claim); prereq: reviewed product diff missing.

### Q15. N-04 V native admission tools-list cache

- **delta** -> The same admission tools-list cache on the native GTK3 path.
- **canonical owner** -> kvnloo/cua#93; kvnloo/cua#10
- **exact SHA** -> candidate `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5` (measurement-only knob on R'n; PUB-03 privacy candidate 32299f857 is held); packet N-04 `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5`; packet N-03 `exp/n-03-native-closure-axfg-a3-20261003` @ `6b70ec902`
- **completed evidence** -> N-04 verdict DELETED; T saved checkbox 2.94 ms [2.02, 3.46], text 3.04 ms [2.01, 3.91]; Admission work deleted: checkbox 2.84 ms, text 4.35 ms; Replicated on N3 (N-03): checkbox verdict DELETED, text verdict DELETED
- **missing evidence** -> A reviewed product (non-env-gated) diff with unit tests; the knob is measurement-only. Freshness of the native rows against upstream main 9a2b1d99e (FRESH-07).
- **action type** -> product-change proposal (with Q14; one admission cache for both paths)
- **dependency** -> a reviewed product diff; owner ruling OR-26 (the published N-04 head); FRESH-07 (wave 7)
- **stop condition** -> A product diff changes the tools/list envelope bytes.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 5 SHAs checked (fork branch exp/n-04-native-composition-rprime-20261003 `9d7d8d7a5`, fork branch exp/n-03-native-closure-axfg-a3-20261003 `6b70ec902`, packet N-04 commit `9d7d8d7a5`, packet N-03 commit `6b70ec902`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[29], blocked_items_w6[12]. Pointers re-read. PUB-03 built the N-04 privacy candidate (held), so the wave-6 PUB-03 dependency becomes the owner privacy ruling.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 1 overlapping the claim); owner: decision pending (owner_decisions_pending[29], blocked_items_w6[12]); w7: pending wave 7 FRESH-07; prereq: reviewed product diff missing.

### Q16. Post-DoAction sleep deletion scope (N-01R / R2-09 / N-03)

- **delta** -> Delete the fixed post-DoAction sleep on the measured routes: GTK3 AT-SPI background (N-01R), Chromium AT-SPI background (R2-09, qualified by the focus-change condition) and GTK3 X11 ax_fg at the default config (N-03).
- **canonical owner** -> kvnloo/cua#93; kvnloo/cua#10; kvnloo/cua#20 (settle watch)
- **exact SHA** -> candidate `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec` commits `8f4f8b542` (measurement-only N-01R knob carried in R'; no product diff yet); packet N-01R `exp/n-01r-native-wait-ab-20261002` @ `3bb4a7fc7`; packet R2-09 `exp/r2-09-native-event-wake-20261002` @ `3539e34ae`; packet N-03 `exp/n-03-native-closure-axfg-a3-20261003` @ `6b70ec902`; packet N-04 `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5`
- **completed evidence** -> N-01R GTK3 background: checkbox verdict DELETED (saving 60.6 ms), text verdict DELETED (saving 42.3 ms); R2-09 Chromium background: S0 saves 69.8 ms [53.1, 102.2] on checkbox; N-03 X11 ax_fg: verdict DELETED; click wrapper saved 51.35 ms [48.86, 53.72]; On R'n the sleep is gone from the best arm: post-action sleep work deleted 51.14 ms (checkbox)
- **missing evidence** -> WebKitGTK targets: NOT_RUN (owner decision on installing WebKitGTK). Hyprland foreground route: BLOCKED (real seat). A reviewed product diff: the deletion is measured through an env-gated knob only. Freshness against upstream main 9a2b1d99e (X11 overlay change; FRESH-07).
- **action type** -> product-change proposal, scoped to the measured routes (default behaviour change)
- **dependency** -> owner ruling OR-10; a reviewed product diff; FRESH-07 (wave 7)
- **stop condition** -> A focus-steal control misses silently with the sleep removed, or a new route lacks the settle watch.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 10 SHAs checked (fork branch exp/n-01r-native-wait-ab-20261002 `3bb4a7fc7`, fork branch exp/r2-09-native-event-wake-r1b-20261003 `ffb4919a7`, fork branch exp/n-03-native-closure-axfg-a3-20261003 `6b70ec902`, fork branch exp/r2-09-native-event-wake-20261002 `3539e34ae`, fork branch exp/n-04-native-composition-rprime-20261003 `9d7d8d7a5`, packet N-01R commit `3bb4a7fc7`, packet R2-09 commit `3539e34ae`, packet N-03 commit `6b70ec902`, packet N-04 commit `9d7d8d7a5`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[10], blocked_items_w6[6], blocked_items_w6[7]. Pointers re-read; no wave-6 lane changed these numbers. FRESH-07 decides whether the X11 rows ran with a mapped idle overlay.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 1 overlapping the claim); owner: decision pending (owner_decisions_pending[10], blocked_items_w6[6]); w7: pending wave 7 FRESH-07; prereq: reviewed product diff missing.

### Q17. R2-03 guarded completion = trycua/cua PR 4316

- **delta** -> trycua/cua PR 4316 completes a guarded fill->submit without the second provider decision.
- **canonical owner** -> kvnloo/cua#10; kvnloo/cua#87; upstream trycua/cua PR 4316 (plain text)
- **exact SHA** -> candidate `exp/r2-03-guarded-live-20261001` @ `6bab214ab` (tested PR head a0bca7440); packet R2-03 `exp/r2-03-guarded-live-20261001` @ `6bab214ab`
- **completed evidence** -> Live TypeSafe: provider requests baseline 80, guarded 40; paired verified-time difference -211.8 ms [-251.8, -192.1]; Disposition KEEP
- **missing evidence** -> kvnloo/cua#107 D (other track, exp/i107-d-20261002 at 6d1c60926): the guard accepted a Submit relocated into another form and submitted to a decoy (missing form-scope fact). Wrong-target breach; blocks promotion. Guarded completion binds nothing on toggle / modal (no saving there). Recertification of the live claim on current main (live layer on R' is BLOCKED by budget).
- **action type** -> evidence comment for the trycua/cua PR 4316 owner, including the wrong-target finding (drafted on the fork; not posted upstream)
- **dependency** -> a form-scope fix for the decoy case; PR head unchanged
- **stop condition** -> The PR head moves from a0bca7440, or any wrong-target submit.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 5 SHAs checked (fork branch exp/r2-03-guarded-live-20261001 `6bab214ab`, fork branch exp/i107-d-20261002 `6d1c60926`, packet R2-03 commit `6bab214ab`, trycua/cua PR 4316 head `a0bca7440`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: blocked_items_w6[0]. Pointers re-read; trycua/cua PR 4316 re-read with gh (open, head unchanged). The wrong-target finding is an explicit prerequisite gate now.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (30 non-allowlisted drift paths, 0 overlapping the claim); owner: decision pending (blocked_items_w6[0]); prereq: form-scope fix for the decoy wrong-target case missing (kvnloo/cua#107 D).

### Q18. R2-07b fill compiled replay (re-qualified by FIX-01)

- **delta** -> A compiled fresh-bound fill->submit routine replays without provider decisions on warm runs, with fresh authority before each replayed mutation and bounded fallback.
- **canonical owner** -> kvnloo/cua#93 (R2-07); kvnloo/cua#10
- **exact SHA** -> candidate `exp/r2-10-composition-20261002` @ `030f6bdbf` (measured inside R2-10's fill COMP arm on R; the R2-07 packet itself stays KILL); packet R2-10 `exp/r2-10-composition-20261002` @ `030f6bdbf`; packet FIX-01 `exp/fix-01-detached-node-refusal-20261002` @ `4a301d32a`; packet B-08 `exp/b-08-per-process-cold-b7-20261003` @ `49ae94590`
- **completed evidence** -> Live fill on R: provider requests per trial BASE 2 -> COMP 0.033; provider work removed 484.8 ms per trial; Live fill amortized S (all invocations incl. training) 42.16 [34.68, 48.46]; B-08 on B7: the compiled routine's verify poll is unstamped and filed under runner (10.23 ms, UNTESTED)
- **missing evidence** -> Live recertification on R' (0f1955d2f): BLOCKED (paid budget). The verify poll inside the routine has no verdict (B-09 is stamping it in wave 7). A product shape: no routine framework or route miner is proposed (parked by kvnloo/cua#74); this stays research evidence.
- **action type** -> research evidence for the trycua/cua issue 3963 rewrite draft (DOC-3963); no upstream posting
- **dependency** -> owner ruling OR-11 (budget); B-09 and R2-07f (wave 7)
- **stop condition** -> Any blind replay of a may-have-landed effect, or a fallback that skips fresh authority.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 7 SHAs checked (fork branch exp/r2-10-composition-20261002 `030f6bdbf`, fork branch exp/fix-01-detached-node-refusal-20261002 `4a301d32a`, fork branch exp/b-08-per-process-cold-b7-20261003 `49ae94590`, packet R2-10 commit `030f6bdbf`, packet FIX-01 commit `4a301d32a`, packet B-08 commit `49ae94590`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[22], owner_decisions_pending[30], blocked_items_w6[0]. Pointers re-read. DOC-3963 is accepted (wave 6), so that dependency is gone; B-08 found the unstamped verify poll, which B-09 measures.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (23 non-allowlisted drift paths, 0 overlapping the claim); owner: decision pending (owner_decisions_pending[22], owner_decisions_pending[30], blocked_items_w6[0]); w7: pending wave 7 B-09, pending wave 7 R2-07f.

### Q19. R2-07c/d/e toggle and modal compiled replay (toggle KEEP, modal REVISE)

- **delta** -> The compiled fresh-bound routine for toggle->confirm and modal->act; R2-07e admits it into the composed toggle configuration (live provider decision DELETED on warm invocations) and keeps it out of modal.
- **canonical owner** -> kvnloo/cua#93 (R2-07); kvnloo/cua#10
- **exact SHA** -> candidate `exp/r2-07e-modal-gate-phase-l-20261003` @ `67b99ddc6` (tested on R (12b9045a); no Driver change); packet R2-07c `exp/r2-07c-toggle-modal-compiled-a2-20261003` @ `7f46edd16`; packet R2-07d `exp/r2-07d-quiet-timing-phase-l-20261003` @ `79f6dd299`; packet R2-07e `exp/r2-07e-modal-gate-phase-l-20261003` @ `67b99ddc6`
- **completed evidence** -> Modal non-regression, second look (R2-07e Part Q, CR - COMP at the alpha-adjusted level): -0.5 ms [-1.4, 0.5]; gate yes; first look (R2-07d) 0.6 ms [-1.4, 2.4], gate no; Toggle non-regression (R2-07d Phase S): 0.5 ms [-1.3, 0.8], gate yes; Phase L live (R2-07e): toggle verdict DELETED (warm valid 29, warm provider requests 0); modal verdict REVISE (forced fallback outcome budget_exhausted); Correctness (R2-07c): accepted mutations all fresh, non-fresh attempts refused (10 attempts)
- **missing evidence** -> Modal: the verdict-bearing forced fallback did not verify; R2-07g re-runs it (wave 7), and the n7_presat substitution for the spec's rename fallback needs an owner ruling. Toggle non-regression was not re-confirmed in R2-07e's window (descriptive block only). Paired live BASE vs COMP+CR S: BLOCKED (paid budget).
- **action type** -> research evidence (compiled replay in the composed toggle configuration; excluded for modal)
- **dependency** -> R2-07f and R2-07g (wave 7); owner rulings OR-22 and OR-11
- **stop condition** -> The modal forced fallback fails again, a gated toggle block fails non-regression, or any E4 violation.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 7 SHAs checked (fork branch exp/r2-07e-modal-gate-phase-l-20261003 `67b99ddc6`, fork branch exp/r2-07d-quiet-timing-phase-l-20261003 `79f6dd299`, fork branch exp/r2-07c-toggle-modal-compiled-a2-20261003 `7f46edd16`, packet R2-07c commit `7f46edd16`, packet R2-07d commit `79f6dd299`, packet R2-07e commit `67b99ddc6`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: owner_decisions_pending[17], owner_decisions_pending[22], owner_decisions_pending[25], owner_decisions_pending[30], blocked_items_w6[1], blocked_items_w6[4], blocked_items_w6[5]. R2-07e (wave 6) replaces the pending marker. The modal second look uses the alpha-adjusted gate and is reported beside the first look, not pooled. The candidate moves to the R2-07e head.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (23 non-allowlisted drift paths, 0 overlapping the claim); owner: decision pending (owner_decisions_pending[17], owner_decisions_pending[22], owner_decisions_pending[25], owner_decisions_pending[30], blocked_items_w6[5]); w7: pending wave 7 R2-07f, pending wave 7 R2-07g.

### Q20. R2-08 API route per task (owner ruling)

- **delta** -> Use the fixture's existing POST /submit route instead of the GUI route when per-task equivalence and authorization evidence exist.
- **canonical owner** -> kvnloo/cua#93 (R2-08); kvnloo/cua#10
- **exact SHA** -> packet R2-08 `exp/r2-08-cross-surface-20261002` @ `afba150d5`
- **completed evidence** -> Equivalence on the base fixture: 20 of 20 rounds; disposition KEEP
- **missing evidence** -> Per-task equivalence and authorization evidence for any real task; the measured route is a fixture route.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> An API route is proposed as a default.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/r2-08-cross-surface-20261002 `afba150d5`, packet R2-08 commit `afba150d5`); STATE entries re-read: owner_decisions_pending[5], blocked_items_w6[13]. Pointers re-read; its owner decision is still pending in STATE.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[5], blocked_items_w6[13]).

### Q21. B-01 fast feedback glide / glide-off policy (owner ruling)

- **delta** -> Shorten the awaited agent-cursor glide (fast glide) or turn feedback off; the glide is most of default browser BASE T.
- **canonical owner** -> kvnloo/cua#10; kvnloo/cua#93 (R2-01)
- **exact SHA** -> packet B-01R `exp/b-01r-browser-critpath-textfix-20261002` @ `0cd63f786`; packet R2-10 `exp/r2-10-composition-20261002` @ `030f6bdbf`
- **completed evidence** -> Fast glide (H_V) fill: verdict KEEP; share of the feedback-off saving recovered 0.987; KEEP-only composition on R (glide left on): fill S 1.01
- **missing evidence** -> A product decision on visual-feedback policy; the knob is measurement-only.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> Visual feedback becomes a user-facing contract.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 4 SHAs checked (fork branch exp/b-01r-browser-critpath-textfix-20261002 `0cd63f786`, fork branch exp/r2-10-composition-20261002 `030f6bdbf`, packet B-01R commit `0cd63f786`, packet R2-10 commit `030f6bdbf`); STATE entries re-read: owner_decisions_pending[3], blocked_items_w6[13]. Pointers re-read; its owner decision is still pending in STATE.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[3], blocked_items_w6[13]).

### Q22. B-01 H_C / N-02 HC caller-compiled output validators

- **delta** -> The caller compiles output-schema validators once instead of validating each result from scratch (client side).
- **canonical owner** -> kvnloo/cua#10; kvnloo/cua#93
- **exact SHA** -> packet B-01R `exp/b-01r-browser-critpath-textfix-20261002` @ `0cd63f786`; packet N-02 `exp/n-02-native-transport-20261002` @ `9846ac803`
- **completed evidence** -> Browser H_C toggle verdict KEEP; Native HC checkbox verdict DELETED (saving 21.3 ms); text verdict DELETED (saving 25.9 ms)
- **missing evidence** -> Eager compilation costs time per session; the lazy form (HCL) is an owner decision on session shape (Q23).
- **action type** -> client-side change proposal for the jev-use runners (after the HCL ruling)
- **dependency** -> owner ruling Q23 (HCL)
- **stop condition** -> Any validation outcome differs from the uncompiled validator.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 4 SHAs checked (fork branch exp/n-02-native-transport-20261002 `9846ac803`, fork branch exp/b-01r-browser-critpath-textfix-20261002 `0cd63f786`, packet B-01R commit `0cd63f786`, packet N-02 commit `9846ac803`); STATE entries re-read: owner_decisions_pending[16]. Pointers re-read; no wave-6 lane touched this entry.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[16]).

### Q23. HCL lazy per-schema validators (owner ruling)

- **delta** -> Compile each output validator lazily on first use: about zero at one task per session, a saving per multi-task session.
- **canonical owner** -> kvnloo/cua#10
- **exact SHA** -> packet N-04 `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5`; packet N-03 `exp/n-03-native-closure-axfg-a3-20261003` @ `6b70ec902`
- **completed evidence** -> N-04 checkbox: at one task -0.04 ms; per five-task session 82.22 ms; verdict OWNER_DECISION
- **missing evidence** -> The expected session shape (tasks per session) - an owner decision.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner sets the expected session shape, or a later packet measures HCL on a different session shape.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 4 SHAs checked (fork branch exp/n-04-native-composition-rprime-20261003 `9d7d8d7a5`, fork branch exp/n-03-native-closure-axfg-a3-20261003 `6b70ec902`, packet N-04 commit `9d7d8d7a5`, packet N-03 commit `6b70ec902`); STATE entries re-read: owner_decisions_pending[16], blocked_items_w6[13]. Pointers re-read; its owner decision is still pending in STATE.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[16], blocked_items_w6[13]).

### Q24. FIX-03 side-index session check 2237cf9c6 (kvnloo/cua#36 native ownership)

- **delta** -> Element-addressed text writes and focus use the token's own window snapshot instead of the (pid, xid) side index, so a session's valid token cannot write into, or focus, another session's window.
- **canonical owner** -> kvnloo/cua#36
- **exact SHA** -> candidate `exp/fix-03-file-input-toctou-session-routing-20261003` @ `e300edbd3` commits `2237cf9c6`, `37d17e0b3` (side-index scoping (Linux call sites) plus the recording-lookup session test); packet FIX-03 `exp/fix-03-file-input-toctou-session-routing-20261003` @ `e300edbd3`
- **completed evidence** -> Cross-session mutations through the side index: F' 40, F5 0, unfixed U' 60; F5 rows: WS gate yes, WK gate yes, WR gate yes; W2dX unfixed lands 20, F5 refuses 20; Routing verdict KEEP; routing fix needed no
- **missing evidence** -> Native AT-SPI pid-wide fallbacks still index the whole application walk by pid (E4 residue). The FIX-03 packet verifier fix and the fallback pin (FIX-04, wave 7). Freshness of the X11 rows against upstream main 9a2b1d99e (FRESH-07).
- **action type** -> fork candidate review together with Q02 (the kvnloo/cua#36 candidate is the F5 line)
- **dependency** -> FIX-04 (wave 7); FRESH-07 (wave 7); drift-free or recertified on upstream main 9a2b1d99e
- **stop condition** -> Any cross-session mutation on the F5 line or later.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 3 SHAs checked (fork branch exp/fix-03-file-input-toctou-session-routing-20261003 `e300edbd3`, packet FIX-03 commit `e300edbd3`, upstream main (drift pin) `9a2b1d99e`). New entry from the wave-6 FIX-03 packet (accepted); all pointers re-read at e300edbd3; candidate head re-read on origin.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 0 overlapping the claim); w7: pending wave 7 FIX-04, pending wave 7 FRESH-07.

### Q25. effect=unknown for delivery=unknown refusals (FIX-03 follow-up; FIX-04 pending)

- **delta** -> Map a refusal issued after the effect may have landed (delivery=unknown, retryable=false) to effect=unknown instead of effect=refused, and keep the runner from re-dispatching it before reconciliation.
- **canonical owner** -> kvnloo/cua#36; kvnloo/cua#105 (runner rule); kvnloo/cua#73 (E4: a possibly landed effect stays unknown)
- **exact SHA** -> packet FIX-03 `exp/fix-03-file-input-toctou-session-routing-20261003` @ `e300edbd3`
- **completed evidence** -> F5 refusals with delivery unknown 20 of 20, while the change still reached the server in 20 cells; strict E4 count on F5 20 (the seam-forced residue), 0 without it
- **missing evidence** -> A fix candidate with red/green tests and a REAL re-run (FIX-04 is building it in wave 7).
- **action type** -> fork fix candidate (FIX-04), then review
- **dependency** -> FIX-04 (wave 7); owner ruling OR-24
- **stop condition** -> Any possibly landed effect reported as refused, or any re-dispatch after a delivery=unknown refusal.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/fix-03-file-input-toctou-session-routing-20261003 `e300edbd3`, packet FIX-03 commit `e300edbd3`); STATE entries re-read: owner_decisions_pending[27]. New entry for the wave-6 E4 residue (a); evidence re-read at e300edbd3. No candidate exists yet.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[27]); w7: pending wave 7 FIX-04.

### Q26. OWN-20Q same_app_dialog fix 4ac191a7c (kvnloo/cua#20)

- **delta** -> The focus guard no longer treats a steal by the application's own dialog as same-app noise when it is a real steal, and leaves the app's own dialog focused when it should be.
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> candidate `exp/own-20q-a11y-triggers-dialog-markfree-20261003` @ `44116546d` commits `4ac191a7c` (focus_guard.rs (GQ source)); packet OWN-20Q `exp/own-20q-a11y-triggers-dialog-markfree-20261003` @ `44116546d`
- **completed evidence** -> GA misclassified 20 of 20; GQ verified restores 20 of 20; the app's own dialog stays focused 10 of 10 with false restores 0; Normal path with GQ: verified 40; false restores 0; spurious reconnects 0
- **missing evidence** -> Hyprland/Wayland: BLOCKED (seat). Freshness against upstream main 9a2b1d99e (FRESH-07).
- **action type** -> fork candidate review (with Q06)
- **dependency** -> FRESH-07 (wave 7); drift-free or recertified on upstream main 9a2b1d99e
- **stop condition** -> The app's own dialog loses focus to a restore, or any false restore on the normal path.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 3 SHAs checked (fork branch exp/own-20q-a11y-triggers-dialog-markfree-20261003 `44116546d`, packet OWN-20Q commit `44116546d`, upstream main (drift pin) `9a2b1d99e`); STATE entries re-read: blocked_items_w6[7]. New entry from the wave-6 OWN-20Q packet; pointers re-read at 44116546d.
- **READY NOW: NO.** Failing gates: drift: not drift-free against upstream main `9a2b1d99e` (16 non-allowlisted drift paths, 0 overlapping the claim); w7: pending wave 7 FRESH-07.

### OR-01. OWN-36 I3s: shared-window replacement retirement

- **delta** -> OWN-36 I3s: shared-window replacement retirement
- **canonical owner** -> kvnloo/cua#36
- **exact SHA** -> packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`
- **completed evidence** -> STATE records the pending decision: OWN-36 I3s shared-window replacement retirement (FIX-02 leaves it unchanged).; 0 cross-session mutations on F': yes
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules on I3s, or a native ownership candidate changes shared-window replacement.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/fix-recert-a3-20261003 `939580fc6`, packet RECERT-FIX commit `939580fc6`); STATE entries re-read: owner_decisions_pending[0]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[0]).

### OR-02. B-02 H_E endpoint re-proof bound check (security policy)

- **delta** -> B-02 H_E endpoint re-proof bound check (security policy)
- **canonical owner** -> kvnloo/cua#73; kvnloo/cua#10
- **exact SHA** -> packet B-02 `exp/b-02-browser-driver-sites-20261002` @ `b282ff389`; packet B-08 `exp/b-08-per-process-cold-b7-20261003` @ `49ae94590`
- **completed evidence** -> B-02 fill endpoint verdict OWNER_DECISION; saving 21.9 ms; On B7 (B-08 Part E, fill C arm) endpoint revalidation is 20.41 ms, verdict OWNER_DECISION
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules on the bound check, or a security review changes the re-proof contract.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 4 SHAs checked (fork branch exp/b-02-browser-driver-sites-20261002 `b282ff389`, fork branch exp/b-08-per-process-cold-b7-20261003 `49ae94590`, packet B-02 commit `b282ff389`, packet B-08 commit `49ae94590`); STATE entries re-read: owner_decisions_pending[1]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[1]).

### OR-03. B-01 H_T: insert_text focus settle

- **delta** -> B-01 H_T: insert_text focus settle
- **canonical owner** -> kvnloo/cua#10
- **exact SHA** -> packet B-01R `exp/b-01r-browser-critpath-textfix-20261002` @ `0cd63f786`
- **completed evidence** -> Verdict OWNER_DECISION
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules, or the insert_text settle constant changes upstream.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/b-01r-browser-critpath-textfix-20261002 `0cd63f786`, packet B-01R commit `0cd63f786`); STATE entries re-read: owner_decisions_pending[2]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[2]).

### OR-04. N-01R H_C: native cursor reveal (text entry)

- **delta** -> N-01R H_C: native cursor reveal (text entry)
- **canonical owner** -> kvnloo/cua#10
- **exact SHA** -> packet N-04 `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5`
- **completed evidence** -> Reveal work removed on R'n text, BASE to best: 1410.6 ms
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules on reveal policy, or the reveal default changes upstream.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/n-04-native-composition-rprime-20261003 `9d7d8d7a5`, packet N-04 commit `9d7d8d7a5`); STATE entries re-read: owner_decisions_pending[4]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[4]).

### OR-06. OWN-09R timeout semantics: bounded coordinator wait vs leaked-closure guards

- **delta** -> OWN-09R timeout semantics: bounded coordinator wait vs leaked-closure guards
- **canonical owner** -> kvnloo/cua#9; kvnloo/cua#84
- **exact SHA** -> packet OWN-09R `exp/own-09r-84-revision-20261002` @ `0c2896a53`
- **completed evidence** -> STATE records the pending decision: OWN-09R timeout semantics: guards held by a leaked closure after foreground_timeout (unbounded next-action wait) vs a bounded coordinator wait with a structured refusal.; OWN-09R disposition KEEP; failing rows []
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner chooses a timeout semantics, or the kvnloo/cua#84 head moves.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/own-09r-84-revision-20261002 `0c2896a53`, packet OWN-09R commit `0c2896a53`); STATE entries re-read: owner_decisions_pending[6], blocked_items_w6[9]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[6], blocked_items_w6[9]).

### OR-07. OWN-09R / kvnloo/cua#9 R8: implement MCP notifications/cancelled or keep it ignored

- **delta** -> OWN-09R / kvnloo/cua#9 R8: implement MCP notifications/cancelled or keep it ignored
- **canonical owner** -> kvnloo/cua#9; kvnloo/cua#84
- **exact SHA** -> packet OWN-09R `exp/own-09r-84-revision-20261002` @ `0c2896a53`
- **completed evidence** -> R8 status on the revision: OWNER_DECISION; notifications in flight ignored 40
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules on R8, or upstream implements notifications/cancelled.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/own-09r-84-revision-20261002 `0c2896a53`, packet OWN-09R commit `0c2896a53`); STATE entries re-read: owner_decisions_pending[7], blocked_items_w6[9]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[7], blocked_items_w6[9]).

### OR-08. trycua/cua PR 4336 timing fields emitted unconditionally vs env-gated wording

- **delta** -> trycua/cua PR 4336 timing fields emitted unconditionally vs env-gated wording
- **canonical owner** -> kvnloo/cua#75
- **exact SHA** -> packet OWN-75R `exp/own-75r-timing-parity-4336-20261002` @ `e02621fdc`
- **completed evidence** -> STATE records the pending decision: OWN-75R: trycua/cua PR 4336 timing fields emitted unconditionally (log-only) vs the env-gated/default-off wording.; REAL trials verified 160 of 160
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules, or the PR head moves from 8391cf802.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/own-75r-timing-parity-4336-20261002 `e02621fdc`, packet OWN-75R commit `e02621fdc`); STATE entries re-read: owner_decisions_pending[8]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[8]).

### OR-09. OWN-16W: JSON null refusal and the analyzer-vs-PREREG reading

- **delta** -> OWN-16W: JSON null refusal and the analyzer-vs-PREREG reading
- **canonical owner** -> kvnloo/cua#16
- **exact SHA** -> packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`
- **completed evidence** -> X11 F'' string_false refused 42/42: yes; Recertification verdict RECERT_PASS; STATE records the pending decision: W5 OWN-16W: accept the PREREG F'' gate reading where the wave-3 analyzer prints REVISE (U'' positive control 41/42 by GetState attribution).
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules on null and on the gate reading, or selector parsing changes upstream.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/fix-recert-a3-20261003 `939580fc6`, packet RECERT-FIX commit `939580fc6`); STATE entries re-read: owner_decisions_pending[9], owner_decisions_pending[21], blocked_items_w6[10]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[9], owner_decisions_pending[21], blocked_items_w6[10]).

### OR-10. R2-09 T3: install WebKitGTK (or use the flatpak runtime), or accept BLOCKED

- **delta** -> R2-09 T3: install WebKitGTK (or use the flatpak runtime), or accept BLOCKED
- **canonical owner** -> kvnloo/cua#93
- **exact SHA** -> packet R2-09 `exp/r2-09-native-event-wake-20261002` @ `3539e34ae`
- **completed evidence** -> STATE records the blocker: R2-09 T3 WebKitGTK MiniBrowser row: BLOCKED, owner decision (no host package; flatpak GNOME 50 runtime only).; R2-09 Chromium background S0 saving on checkbox 69.8 ms
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules; a WebKitGTK row then runs or is recorded BLOCKED.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/r2-09-native-event-wake-20261002 `3539e34ae`, packet R2-09 commit `3539e34ae`); STATE entries re-read: owner_decisions_pending[10], blocked_items_w6[6]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[10], blocked_items_w6[6]).

### OR-11. TypeSafe budget allocation for the remaining reached requests (live R' recertification, live toggle/modal S, kvnloo/cua#78 R1/R4, native live arms) or a cap raise

- **delta** -> TypeSafe budget allocation for the remaining reached requests (live R' recertification, live toggle/modal S, kvnloo/cua#78 R1/R4, native live arms) or a cap raise
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> none (ruling only)
- **completed evidence** -> Loop budget (TypeSafe): cap 600 requests reaching the provider; used 583 (679 attempts); remaining 17; STATE records the pending decision: W6 budget: 17 reached remain. Candidates: R2-07e modal forced-fallback re-run (n >= 3, <= ~12 reached) or LN toggle (4). Everything else live needs a cap raise.
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner raises the cap or accepts the BLOCKED live rows; R2-07g's spend changes the remaining figure.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; no SHA to check; STATE entries re-read: owner_decisions_pending[11], owner_decisions_pending[17], owner_decisions_pending[22], owner_decisions_pending[30], blocked_items_w6[0], blocked_items_w6[1], blocked_items_w6[3]. Budget figures re-read from the state extract (re-derived from STATE by the verifier). R2-07g may spend part of the remainder in wave 7.
- **READY NOW: NO.** Failing gates: packet: no accepted packet; origin: nothing published; owner: decision pending (owner_decisions_pending[11], owner_decisions_pending[17], owner_decisions_pending[22], owner_decisions_pending[30], blocked_items_w6[0], blocked_items_w6[3]); w7: pending wave 7 R2-07g.

### OR-12. RECERT-FIX wave-4 cross-lane pkill ruling

- **delta** -> RECERT-FIX wave-4 cross-lane pkill ruling
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> none (ruling only)
- **completed evidence** -> STATE records the pending decision: W4 RECERT-FIX lane hard stop: ruling on the cross-lane pkill (not a hard_rule_breach class under the loop's definitions) before RECERT-FIX attempt 3.; STATE records the blocker: W4 RECERT-FIX attempt-2 cross-lane pkill ruling: BLOCKED, owner decision (record-keeping only; attempt 3 ran clean).
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner records the ruling (record-keeping only; the third attempt ran without pkill).
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; no SHA to check; STATE entries re-read: owner_decisions_pending[12], blocked_items_w6[15]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: packet: no accepted packet; origin: nothing published; owner: decision pending (owner_decisions_pending[12], blocked_items_w6[15]).

### OR-14. OWN-20G: reply-delay R1 row in place of the XGrabServer row; settle overshoot as IRREDUCIBLE coverage

- **delta** -> OWN-20G: reply-delay R1 row in place of the XGrabServer row; settle overshoot as IRREDUCIBLE coverage
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> packet OWN-20G `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc0`
- **completed evidence** -> R1 reply-delay gate yes; XGrabServer row gate no
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules, or Q06 supersedes OWN-20G for posting.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/own-20g-guard-final-diff-a2-20261003 `ce7544cc0`, packet OWN-20G commit `ce7544cc0`); STATE entries re-read: owner_decisions_pending[14]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[14]).

### OR-15. Browser per-process cold first snapshot: B-06 amendment reading (moot since B-08)

- **delta** -> Browser per-process cold first snapshot: B-06 amendment reading (moot since B-08)
- **canonical owner** -> kvnloo/cua#10; kvnloo/cua#73
- **exact SHA** -> packet B-06 `exp/b-06-per-process-cold-snapshot-20261003` @ `31bc98a95`; packet B-08 `exp/b-08-per-process-cold-b7-20261003` @ `49ae94590`
- **completed evidence** -> B-06 primary verdict fill UNDECIDED; amended fill OWNER_DECISION (D 10.0 ms [8.0, 12.0]); B-08 pre-registered verdicts: fill OWNER_DECISION, toggle OWNER_DECISION, modal OWNER_DECISION
- **missing evidence** -> The owner closes the two B-06 owner items as moot (STATE still lists them as pending).
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner closes the items, or B-08's reading is overturned by a later pre-registered run.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 4 SHAs checked (fork branch exp/b-06-per-process-cold-snapshot-20261003 `31bc98a95`, fork branch exp/b-08-per-process-cold-b7-20261003 `49ae94590`, packet B-06 commit `31bc98a95`, packet B-08 commit `49ae94590`); STATE entries re-read: owner_decisions_pending[15], owner_decisions_pending[18], blocked_items_w6[16]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[15], owner_decisions_pending[18]).

### OR-16. OWN-09R strict PREREG reading of the head-core unit row (Deviation 6)

- **delta** -> OWN-09R strict PREREG reading of the head-core unit row (Deviation 6)
- **canonical owner** -> kvnloo/cua#9; kvnloo/cua#84
- **exact SHA** -> packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`
- **completed evidence** -> Strict PREREG reading REVISE; recertification verdict RECERT_PASS
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner accepts the re-run rule or records the unit row as REVISE.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/fix-recert-a3-20261003 `939580fc6`, packet RECERT-FIX commit `939580fc6`); STATE entries re-read: owner_decisions_pending[19], blocked_items_w6[10]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[19], blocked_items_w6[10]).

### OR-17. OWN-20P: marked-twin R1 substitution (superseded by OWN-20Q R1m) and A's trigger set

- **delta** -> OWN-20P: marked-twin R1 substitution (superseded by OWN-20Q R1m) and A's trigger set
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> packet OWN-20P `exp/own-20p-guard-port-a11y-20261003` @ `64081dded`; packet OWN-20Q `exp/own-20q-a11y-triggers-dialog-markfree-20261003` @ `44116546d`
- **completed evidence** -> OWN-20Q mark-free R1m: G0 verified restores 40 of 40; gate yes; A2 trigger rows: r3s gate yes; r3n gate no
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules on the trigger set; the R1 half is already superseded by R1m.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 4 SHAs checked (fork branch exp/own-20p-guard-port-a11y-20261003 `64081dded`, fork branch exp/own-20q-a11y-triggers-dialog-markfree-20261003 `44116546d`, packet OWN-20P commit `64081dded`, packet OWN-20Q commit `44116546d`); STATE entries re-read: owner_decisions_pending[20]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[20]).

### OR-18. Driver telemetry on by default in lane sessions (set it off in the shared session wrapper)

- **delta** -> Driver telemetry on by default in lane sessions (set it off in the shared session wrapper)
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> none (ruling only)
- **completed evidence** -> STATE records the pending decision: W5 Driver telemetry default-on in lane sessions (OWN-78A verifier; most lanes since wave 1): set CUA_DRIVER_RS_TELEMETRY_ENABLED=false in the shared session wrapper.
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The shared session wrapper sets telemetry off, or the owner accepts the default.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; no SHA to check; STATE entries re-read: owner_decisions_pending[24]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: packet: no accepted packet; origin: nothing published; owner: decision pending (owner_decisions_pending[24]).

### OR-19. Fail-closed guard that rejects code-executing commands outside the hostless wrapper

- **delta** -> Fail-closed guard that rejects code-executing commands outside the hostless wrapper
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> none (ruling only)
- **completed evidence** -> STATE records the blocker: Fail-closed guard against plain-shell code execution (near misses recur in every wave-6 lane and verifier): BLOCKED, owner/orchestrator action on the user's shell/tool configuration, which no lane may make.
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner or orchestrator installs the guard, or rules it unnecessary.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; no SHA to check; STATE entries re-read: blocked_items_w6[14]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: packet: no accepted packet; origin: nothing published; owner: decision pending (blocked_items_w6[14]).

### OR-20. kvnloo/cua#78 S1 backend row (adapter not local; only TypeSafe permitted)

- **delta** -> kvnloo/cua#78 S1 backend row (adapter not local; only TypeSafe permitted)
- **canonical owner** -> kvnloo/cua#78
- **exact SHA** -> packet OWN-78L `exp/own-78l-r1-lite-f-20261003` @ `d9edde70e`
- **completed evidence** -> OWN-78L records the row as BLOCKED (adapter not local; non-TypeSafe providers not permitted)
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner provides an adapter or permits another provider, or accepts BLOCKED.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/own-78l-r1-lite-f-20261003 `d9edde70e`, packet OWN-78L commit `d9edde70e`); STATE entries re-read: blocked_items_w6[3]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (blocked_items_w6[3]).

### OR-21. Native T definition: may native whole-task T exclude provider decisions (scripted chooser), or fund live native arms

- **delta** -> Native T definition: may native whole-task T exclude provider decisions (scripted chooser), or fund live native arms
- **canonical owner** -> kvnloo/cua#10
- **exact SHA** -> none (ruling only)
- **completed evidence** -> STATE records the blocker: Native live-provider arms / native T definition: BLOCKED, owner decision (rule that native T may exclude provider decisions; native E2/E3 met on scripted-chooser T only) or owner funds >= 120 reached.
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner accepts scripted-chooser native T or funds live native arms.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; no SHA to check; STATE entries re-read: blocked_items_w6[2]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: packet: no accepted packet; origin: nothing published; owner: decision pending (blocked_items_w6[2]).

### OR-22. R2-07e: accept the n7_presat forced-fallback substitution for the spec's rename fallback

- **delta** -> R2-07e: accept the n7_presat forced-fallback substitution for the spec's rename fallback
- **canonical owner** -> kvnloo/cua#93; kvnloo/cua#10
- **exact SHA** -> packet R2-07e `exp/r2-07e-modal-gate-phase-l-20261003` @ `67b99ddc6`
- **completed evidence** -> Modal forced fallback (kind n7): outcome budget_exhausted, verified no, decisions 4; modal disposition REVISE
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner accepts or rejects the substitution; modal REVISE holds either way until a fallback verifies.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/r2-07e-modal-gate-phase-l-20261003 `67b99ddc6`, packet R2-07e commit `67b99ddc6`); STATE entries re-read: owner_decisions_pending[25], blocked_items_w6[5]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[25], blocked_items_w6[5]); w7: pending wave 7 R2-07g.

### OR-23. B-08: browser per-process cold excess is OWNER_DECISION (process/session reuse kept outside T)

- **delta** -> B-08: browser per-process cold excess is OWNER_DECISION (process/session reuse kept outside T)
- **canonical owner** -> kvnloo/cua#10; kvnloo/cua#73
- **exact SHA** -> packet B-08 `exp/b-08-per-process-cold-b7-20261003` @ `49ae94590`
- **completed evidence** -> D = C - Wa (median T_j ms): fill 10.58 [9.50, 11.41], toggle 3.05 [2.62, 5.38], modal 4.56 [2.98, 5.92]; verdicts OWNER_DECISION / OWNER_DECISION / OWNER_DECISION
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules on process or session reuse (a product policy outside T).
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/b-08-per-process-cold-b7-20261003 `49ae94590`, packet B-08 commit `49ae94590`); STATE entries re-read: owner_decisions_pending[26], blocked_items_w6[13]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[26], blocked_items_w6[13]).

### OR-24. FIX-03 F4: accept IRREDUCIBLE-with-honest-unknown, and approve the effect=unknown follow-up

- **delta** -> FIX-03 F4: accept IRREDUCIBLE-with-honest-unknown, and approve the effect=unknown follow-up
- **canonical owner** -> kvnloo/cua#36; kvnloo/cua#73
- **exact SHA** -> packet FIX-03 `exp/fix-03-file-input-toctou-session-routing-20261003` @ `e300edbd3`
- **completed evidence** -> F5: success receipts 0 of 20; the change still reached the server in 20 cells; verdict REVISE (IRREDUCIBLE-with-honest-unknown)
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules; FIX-04's candidate then either lands the effect=unknown mapping or is rejected.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/fix-03-file-input-toctou-session-routing-20261003 `e300edbd3`, packet FIX-03 commit `e300edbd3`); STATE entries re-read: owner_decisions_pending[27]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[27]); w7: pending wave 7 FIX-04.

### OR-25. OWN-20Q A2: a second persistent session-bus connection for an org.a11y.Bus name-owner watch

- **delta** -> OWN-20Q A2: a second persistent session-bus connection for an org.a11y.Bus name-owner watch
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> packet OWN-20Q `exp/own-20q-a11y-triggers-dialog-markfree-20261003` @ `44116546d`
- **completed evidence** -> r3n gate no (GQ passes 0 of 20); r3n positive control yes
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner allows or rejects the second connection; the trigger is then built or recorded as not built.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 2 SHAs checked (fork branch exp/own-20q-a11y-triggers-dialog-markfree-20261003 `44116546d`, packet OWN-20Q commit `44116546d`); STATE entries re-read: owner_decisions_pending[28], blocked_items_w6[11]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[28], blocked_items_w6[11]).

### OR-26. Published-fork privacy: the PUB-03 owner-ruling draft (lease-guarded replace) for OWN-20G, N-03 a3, N-04, R2-10 (r1c) and R2-10R a3

- **delta** -> Published-fork privacy: the PUB-03 owner-ruling draft (lease-guarded replace) for OWN-20G, N-03 a3, N-04, R2-10 (r1c) and R2-10R a3
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> packet PUB-03 `exp/own-20g-guard-final-diff-r1c-20261003` @ `cb18ebfbd`
- **completed evidence** -> STATE records the pending decision: W6 privacy: the PUB-03 owner-ruling draft (artifacts/r2/PUB-03/OWNER-RULING-DRAFT.md) recommends lease-guarded replace for OWN-20G, N-03 a3, N-04 and R2-10 (r1c); rule R2-10R a3 (tmp session-bus x25) together with N-03/N-04 (same class). Confirm exp/portable-evidence-v0 is not a loop branch.; PUB-03 disposition: KEEP (publish-gate fix). Three held clean candidates that differ from the published heads only by redaction, manifest entries and a PRIVACY-REWRITE.md note; held for the owner ruling. NEW published finding: origin exp/r2-10r-recert-a3-20261003 @ d22eeb2ec carries 25 tmp session-bus paths (first in 8be812d0c, raw/logs/*.log); candidate exp/r2-10r-recert-r1c-20261003 proposed, not built.
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> The owner rules for each branch; Publish then runs only the ruled sequence.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 5 SHAs checked (fork branch exp/own-20g-guard-final-diff-r1c-20261003 `cb18ebfbd`, fork branch exp/n-03-native-closure-axfg-r1c-20261003 `a2f7a93ef`, fork branch exp/n-04-native-composition-rprime-r1c-20261003 `32299f857`, fork branch exp/r2-10-composition-r1c-20261003 `eaca68df9`, packet PUB-03 commit `cb18ebfbd`); STATE entries re-read: owner_decisions_pending[29], blocked_items_w6[12]. Owner item(s) re-read in the state extract; cited evidence re-read.
- **READY NOW: NO.** Failing gates: origin: candidate held for the owner ruling (not on origin by design); owner: decision pending (owner_decisions_pending[29], blocked_items_w6[12]); w7: pending wave 7 PUB-04.

### PRIV-A. Published exp/r2-10-composition-20261002 carries an encoded private-name list (candidate r1c eaca68df9)

- **delta** -> Replace the published R2-10 branch history with the clean rewrite r1c, or delete and re-push, or accept.
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> candidate `exp/r2-10-composition-r1c-20261003` @ `eaca68df9` (held locally, not pushed (owner ruling)); packet PUB-02 `docs/packet-template-privacy-20261003` @ `c4342323b`; packet R2-10 `exp/r2-10-composition-20261002` @ `030f6bdbf`
- **completed evidence** -> The R2-10 summary blob is identical at the published head and at r1c: yes; STATE records the pending decision: W4 privacy: hex-encoded host name in verify_artifacts.py on fork branch exp/r2-10-composition-20261002 (pushed wave 3): rewrite/force-push or delete-and-repush the fork branch, or accept. Unpublished copies (R2-10R, R2-10 r1b) are rewritten/fixed before Publish regardless.
- **missing evidence** -> The owner's ruling (replace, delete and re-push, or accept).
- **action type** -> owner ruling, then a privacy rewrite on the fork
- **dependency** -> owner ruling OR-26
- **stop condition** -> The owner rules; Publish replaces only with a lease on the exact published SHA and checks ls-remote before any delete.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 5 SHAs checked (fork branch exp/r2-10-composition-20261002 `030f6bdbf`, fork branch exp/r2-10-composition-r1c-20261003 `eaca68df9`, fork branch docs/packet-template-privacy-20261003 `c4342323b`, packet PUB-02 commit `c4342323b`, packet R2-10 commit `030f6bdbf`); STATE entries re-read: owner_decisions_pending[13], owner_decisions_pending[23], owner_decisions_pending[29], blocked_items_w6[12]. Published head re-read on origin; held candidate confirmed absent from origin.
- **READY NOW: NO.** Failing gates: origin: candidate held for the owner ruling (not on origin by design); owner: decision pending (owner_decisions_pending[13], owner_decisions_pending[23], owner_decisions_pending[29], blocked_items_w6[12]).

### PRIV-B. Published exp/own-20g-guard-final-diff-a2-20261003 carries the local user name in raw output (candidate cb18ebfbd)

- **delta** -> Replace the published OWN-20G branch with the PUB-03 rewrite, or delete and re-push, or accept.
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> candidate `exp/own-20g-guard-final-diff-r1c-20261003` @ `cb18ebfbd` (held locally, not pushed (owner ruling)); packet OWN-20G `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc0`; packet PUB-03 `exp/own-20g-guard-final-diff-r1c-20261003` @ `cb18ebfbd`
- **completed evidence** -> PUB-03 disposition: KEEP (publish-gate fix). Three held clean candidates that differ from the published heads only by redaction, manifest entries and a PRIVACY-REWRITE.md note; held for the owner ruling. NEW published finding: origin exp/r2-10r-recert-a3-20261003 @ d22eeb2ec carries 25 tmp session-bus paths (first in 8be812d0c, raw/logs/*.log); candidate exp/r2-10r-recert-r1c-20261003 proposed, not built.; STATE records the pending decision: W5 privacy: ruling on origin exp/r2-10-composition-20261002 (030f6bdbf) with PUB-02 r1c eaca68df9 as candidate, and on origin exp/own-20g-guard-final-diff-a2-20261003 (ce7544cc0, user name in raw x10).
- **missing evidence** -> The owner's ruling (replace, delete and re-push, or accept).
- **action type** -> owner ruling, then a privacy rewrite on the fork
- **dependency** -> owner ruling OR-26
- **stop condition** -> The owner rules; Publish replaces only with a lease on the exact published SHA and checks ls-remote before any delete.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 4 SHAs checked (fork branch exp/own-20g-guard-final-diff-a2-20261003 `ce7544cc0`, fork branch exp/own-20g-guard-final-diff-r1c-20261003 `cb18ebfbd`, packet OWN-20G commit `ce7544cc0`, packet PUB-03 commit `cb18ebfbd`); STATE entries re-read: owner_decisions_pending[23], owner_decisions_pending[29], blocked_items_w6[12]. Published head re-read on origin; held candidate confirmed absent from origin.
- **READY NOW: NO.** Failing gates: origin: candidate held for the owner ruling (not on origin by design); owner: decision pending (owner_decisions_pending[23], owner_decisions_pending[29], blocked_items_w6[12]).

### PRIV-C. Published exp/n-03-native-closure-axfg-a3-20261003 carries tmp session-bus paths (candidate a2f7a93ef)

- **delta** -> Replace the published N-03 branch with the PUB-03 rewrite, or delete and re-push, or accept.
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> candidate `exp/n-03-native-closure-axfg-r1c-20261003` @ `a2f7a93ef` (held locally, not pushed (owner ruling)); packet N-03 `exp/n-03-native-closure-axfg-a3-20261003` @ `6b70ec902`; packet PUB-03 `exp/own-20g-guard-final-diff-r1c-20261003` @ `cb18ebfbd`
- **completed evidence** -> PUB-03 disposition: KEEP (publish-gate fix). Three held clean candidates that differ from the published heads only by redaction, manifest entries and a PRIVACY-REWRITE.md note; held for the owner ruling. NEW published finding: origin exp/r2-10r-recert-a3-20261003 @ d22eeb2ec carries 25 tmp session-bus paths (first in 8be812d0c, raw/logs/*.log); candidate exp/r2-10r-recert-r1c-20261003 proposed, not built.; STATE records the blocker: Published-fork privacy replacements: BLOCKED, owner decision before Publish deletes or re-pushes anything. origin exp/r2-10-composition-20261002 @ 030f6bdbf (candidate r1c eaca68df9); exp/own-20g-guard-final-diff-a2-20261003 @ ce7544cc0 (candidate cb18ebfbd); exp/n-03-native-closure-axfg-a3-20261003 @ 6b70ec902 (candidate a2f7a93ef); exp/n-04-native-composition-rprime-20261003 @ 9d7d8d7a5 (candidate 32299f857); NEW exp/r2-10r-recert-a3-20261003 @ d22eeb2ec (25 tmp session-bus paths; candidate r1c not built).
- **missing evidence** -> The owner's ruling (replace, delete and re-push, or accept).
- **action type** -> owner ruling, then a privacy rewrite on the fork
- **dependency** -> owner ruling OR-26
- **stop condition** -> The owner rules; Publish replaces only with a lease on the exact published SHA and checks ls-remote before any delete.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 4 SHAs checked (fork branch exp/n-03-native-closure-axfg-a3-20261003 `6b70ec902`, fork branch exp/n-03-native-closure-axfg-r1c-20261003 `a2f7a93ef`, packet N-03 commit `6b70ec902`, packet PUB-03 commit `cb18ebfbd`); STATE entries re-read: owner_decisions_pending[29], blocked_items_w6[12]. Published head re-read on origin; held candidate confirmed absent from origin.
- **READY NOW: NO.** Failing gates: origin: candidate held for the owner ruling (not on origin by design); owner: decision pending (owner_decisions_pending[29], blocked_items_w6[12]).

### PRIV-D. Published exp/n-04-native-composition-rprime-20261003 carries tmp session-bus paths (candidate 32299f857)

- **delta** -> Replace the published N-04 branch with the PUB-03 rewrite, or delete and re-push, or accept.
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> candidate `exp/n-04-native-composition-rprime-r1c-20261003` @ `32299f857` (held locally, not pushed (owner ruling)); packet N-04 `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5`; packet PUB-03 `exp/own-20g-guard-final-diff-r1c-20261003` @ `cb18ebfbd`
- **completed evidence** -> PUB-03 disposition: KEEP (publish-gate fix). Three held clean candidates that differ from the published heads only by redaction, manifest entries and a PRIVACY-REWRITE.md note; held for the owner ruling. NEW published finding: origin exp/r2-10r-recert-a3-20261003 @ d22eeb2ec carries 25 tmp session-bus paths (first in 8be812d0c, raw/logs/*.log); candidate exp/r2-10r-recert-r1c-20261003 proposed, not built.; STATE records the blocker: Published-fork privacy replacements: BLOCKED, owner decision before Publish deletes or re-pushes anything. origin exp/r2-10-composition-20261002 @ 030f6bdbf (candidate r1c eaca68df9); exp/own-20g-guard-final-diff-a2-20261003 @ ce7544cc0 (candidate cb18ebfbd); exp/n-03-native-closure-axfg-a3-20261003 @ 6b70ec902 (candidate a2f7a93ef); exp/n-04-native-composition-rprime-20261003 @ 9d7d8d7a5 (candidate 32299f857); NEW exp/r2-10r-recert-a3-20261003 @ d22eeb2ec (25 tmp session-bus paths; candidate r1c not built).
- **missing evidence** -> The owner's ruling (replace, delete and re-push, or accept).
- **action type** -> owner ruling, then a privacy rewrite on the fork
- **dependency** -> owner ruling OR-26
- **stop condition** -> The owner rules; Publish replaces only with a lease on the exact published SHA and checks ls-remote before any delete.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 4 SHAs checked (fork branch exp/n-04-native-composition-rprime-20261003 `9d7d8d7a5`, fork branch exp/n-04-native-composition-rprime-r1c-20261003 `32299f857`, packet N-04 commit `9d7d8d7a5`, packet PUB-03 commit `cb18ebfbd`); STATE entries re-read: owner_decisions_pending[29], blocked_items_w6[12]. Published head re-read on origin; held candidate confirmed absent from origin.
- **READY NOW: NO.** Failing gates: origin: candidate held for the owner ruling (not on origin by design); owner: decision pending (owner_decisions_pending[29], blocked_items_w6[12]).

### PRIV-E. Published exp/r2-10r-recert-a3-20261003 carries tmp session-bus paths (PUB-03 finding; PUB-04 pending)

- **delta** -> Build a clean rewrite of the published R2-10R a3 head and replace it, or delete and re-push, or accept.
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> packet R2-10R `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec`; packet PUB-03 `exp/own-20g-guard-final-diff-r1c-20261003` @ `cb18ebfbd`
- **completed evidence** -> PUB-03 disposition: KEEP (publish-gate fix). Three held clean candidates that differ from the published heads only by redaction, manifest entries and a PRIVACY-REWRITE.md note; held for the owner ruling. NEW published finding: origin exp/r2-10r-recert-a3-20261003 @ d22eeb2ec carries 25 tmp session-bus paths (first in 8be812d0c, raw/logs/*.log); candidate exp/r2-10r-recert-r1c-20261003 proposed, not built.; STATE records the pending decision: W6 privacy: the PUB-03 owner-ruling draft (artifacts/r2/PUB-03/OWNER-RULING-DRAFT.md) recommends lease-guarded replace for OWN-20G, N-03 a3, N-04 and R2-10 (r1c); rule R2-10R a3 (tmp session-bus x25) together with N-03/N-04 (same class). Confirm exp/portable-evidence-v0 is not a loop branch.
- **missing evidence** -> A clean rewrite candidate (PUB-04 is building it in wave 7). The owner's ruling.
- **action type** -> owner ruling, then a privacy rewrite on the fork
- **dependency** -> owner ruling OR-26
- **stop condition** -> The owner rules; Publish replaces only with a lease on the exact published SHA and checks ls-remote before any delete.
- **review** -> DOC-10-74b (wave 7), 2026-10-03T16:15:27Z: consistent; 3 SHAs checked (fork branch exp/r2-10r-recert-a3-20261003 `d22eeb2ec`, packet R2-10R commit `d22eeb2ec`, packet PUB-03 commit `cb18ebfbd`); STATE entries re-read: owner_decisions_pending[29], blocked_items_w6[12]. New entry for the PUB-03 R2-10R a3 finding; published head re-read on origin; no candidate exists yet.
- **READY NOW: NO.** Failing gates: owner: decision pending (owner_decisions_pending[29], blocked_items_w6[12]); w7: pending wave 7 PUB-04.

<!-- END GENERATED: make_queue.py -->
