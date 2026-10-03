# kvnloo/cua#74: posting queue (round 2, staged)

Lane DOC-10-74, wave 6 of the CUA RFC loop. This is the kvnloo/cua#74 deliverable for kvnloo/cua#73 end condition
E5(c). It is staged on the fork branch `docs/accounting-10-queue-74-20261003`. Nothing has been posted, and nothing
here goes to trycua/cua: upstream items are written as plain text ("trycua/cua PR 4316").

## Format

Every surviving delta is one entry in kvnloo/cua#74's own format:

`delta -> canonical owner -> exact SHA -> completed evidence -> missing evidence -> action type -> dependency -> stop condition`

- **Evidence numbers.** Each completed-evidence line is a template whose numbers are filled from pointers into an
  accepted packet at an exact commit. Gate lines quote the packet's own gate key. `queue.json` holds the pointers,
  and `verify_artifacts.py` re-reads them and fails on any bare number in free text.
- **Owner decisions.** Every owner decision pending in the loop STATE is its own entry with action type
  "owner ruling" (OR-xx). The verifier checks that each pending decision is covered by at least one entry.

## READY NOW gate

Each entry has seven explicit booleans. READY NOW = all seven true.

| Gate | Source of truth (recomputed by the verifier) |
|---|---|
| packet | Every lane the entry cites is in the loop STATE's accepted lists (`inputs/state-extract.json`, with the STATE sha256) |
| origin | Every cited branch is on origin at the cited SHA (read-only `git ls-remote https://github.com/kvnloo/cua.git`) |
| drift | Recertified on, or free of drift against, pinned trycua/cua main `5de1a3799`. Every libs/cua-driver path changed from the entry's certified base to the pin must be outside the entry's changed files, and must be one of the non-Linux allowlisted paths (platform-macos, platform-windows, the macOS Skills doc, the AppKit e2e test and fixture, `tests/fixtures/shared/scenarios.json`). The drift since 0f1955d2f is recomputed with read-only git in `raw/drift.json` |
| owner | No pending owner decision cited for the entry (STATE `owner_decisions_pending` and the owner-type `blocked_items_w5`, by index) |
| w6 | No wave-6 lane still running for the entry (B-08, FIX-03, OWN-20Q, OWN-78L, R2-07e, PUB-03, DOC-3963) |
| PR | Where a live PR exists, its head is unchanged (read-only `git ls-remote refs/pull/N/head`): trycua/cua PR 4316 `a0bca7440`, PR 4336 `8391cf802`, PR 4394 `039257811`; kvnloo/cua#84 `566b9c732`, kvnloo/cua#105 `98a45e6c5`, kvnloo/cua#106 `c45845797` |
| review | A fresh reviewer has reviewed this entry against the pinned main. This is false for every entry: the DOC-10-74 verifier review is the first such review, and the wave-7 refresh records its outcome |

Upstream main moved past the pin during the lane, to the 0.33.0 release version bump and a Windows input fix. The
gates still use the pin, as the task specifies; `raw/drift.json` lists the post-pin files for the wave-7 refresh.

This lane attempted no TypeSafe request and none reached the provider. Verify with
`python3 docs/rfc/74-posting-queue/verify_artifacts.py` under the hostless wrapper.

<!-- BEGIN GENERATED: make_queue.py -->

Format: `delta -> canonical owner -> exact SHA -> completed evidence -> missing evidence -> action type -> dependency -> stop condition`. READY NOW = all seven gates true. Pinned main `5de1a3799`.

**READY NOW: 0 of 44 entries.**

| ID | Entry | Action type | packet | origin | drift | owner | w6 | PR | review | READY NOW |
|---|---|---|---|---|---|---|---|---|---|---|
| Q01 | FIX-01 detached-node refusal (dom_event route) + refused-is-refused runner rule | fork candidate review, then a reviewed upstream PR proposal (not posted; upstream owner named at that time) | yes | yes | yes | yes | yes | yes | **no** | **no** |
| Q02 | FIX-02 F1-F3: native token ownership, runtime generation, runner re-dispatch scope | fork candidate review, then a reviewed upstream PR proposal (not posted) | yes | yes | yes | yes | **no** | yes | **no** | **no** |
| Q03 | FIX-02 F4: browser_set_input_files detached-input refusal (FIX-03 PENDING) | hold (REVISE); fork candidate after FIX-03 | yes | yes | yes | yes | **no** | yes | **no** | **no** |
| Q04 | kvnloo/cua#84 revision (OWN-09R): cancel before admission, guard ownership | hold; revision staged on the fork for the kvnloo/cua#84 owner | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| Q05 | OWN-16W fix dd205d17b: refuse non-boolean modality selectors | hold; fork candidate after the owner rulings | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| Q06 | OWN-20P G: focus-guard final read on deadline exit, ported to clean main | fork candidate review after OWN-20Q | yes | yes | yes | **no** | **no** | yes | **no** | **no** |
| Q07 | OWN-20P A: in-process AT-SPI bus-restart reconnect (OWN-20Q PENDING) | fork candidate review after OWN-20Q | yes | yes | yes | **no** | **no** | yes | **no** | **no** |
| Q08 | OWN-20G guard a30cbbc3b (superseded by the OWN-20P G port; privacy rewrite PUB-03 PENDING) | privacy rewrite candidate (owner ruling) - no posting; the product delta moves to Q06 | yes | yes | yes | **no** | **no** | yes | **no** | **no** |
| Q09 | BUG-01 A: foreground trusted click receipt labelled background (fix 2533db6d5 + 49a3adf0f) | fork fix branch for owner review; upstream routing decided by the kvnloo/cua#38 owner (not posted) | yes | yes | **no** | yes | yes | yes | **no** | **no** |
| Q10 | BUG-01 B: CDP sessions accumulate (attach per call, never detach) | evidence note only (no fix) | yes | yes | **no** | yes | yes | yes | **no** | **no** |
| Q11 | OWN-105 runner reconcile (kvnloo/cua#105 gaps G1-G3 + pre-write rule) | fork branch + kvnloo/cua#105 comment (fork only) | yes | yes | **no** | yes | yes | yes | **no** | **no** |
| Q12 | trycua/cua PR 4336 native timing parity (OWN-75R) | evidence comment for the trycua/cua PR 4336 owner (drafted on the fork; not posted upstream) | yes | yes | **no** | **no** | yes | yes | **no** | **no** |
| Q13 | OWN-78A candidate F for trycua/cua PR 4394 (restore form + page + outline) (OWN-78L PENDING) | hold; evidence comment for kvnloo/cua#78 after OWN-78L (fork only) | yes | yes | **no** | **no** | **no** | yes | **no** | **no** |
| Q14 | B-02 H_V browser admission tools-list cache | product-change proposal (default behaviour change; needs a reviewed product diff first) | yes | yes | yes | yes | yes | yes | **no** | **no** |
| Q15 | N-04 V native admission tools-list cache | product-change proposal (with Q14; one admission cache for both paths) | yes | yes | yes | yes | **no** | yes | **no** | **no** |
| Q16 | Post-DoAction sleep deletion scope (N-01R / R2-09 / N-03) | product-change proposal, scoped to the measured routes (default behaviour change) | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| Q17 | R2-03 guarded completion = trycua/cua PR 4316 | evidence comment for the trycua/cua PR 4316 owner, including the wrong-target finding (drafted on the fork; not posted upstream) | yes | yes | **no** | yes | yes | yes | **no** | **no** |
| Q18 | R2-07b fill compiled replay (re-qualified by FIX-01) | research evidence for the trycua/cua issue 3963 rewrite draft (DOC-3963); no upstream posting | yes | yes | **no** | **no** | **no** | yes | **no** | **no** |
| Q19 | R2-07c/d/e toggle and modal compiled replay (R2-07e PENDING) | hold (research evidence; excluded from the composed toggle / modal configuration) | yes | yes | **no** | **no** | **no** | yes | **no** | **no** |
| Q20 | R2-08 API route per task (owner ruling) | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| Q21 | B-01 fast feedback glide / glide-off policy (owner ruling) | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| Q22 | B-01 H_C / N-02 HC caller-compiled output validators | client-side change proposal for the jev-use runners (after the HCL ruling) | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| Q23 | HCL lazy per-schema validators (owner ruling) | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-01 | OWN-36 I3s: shared-window replacement retirement | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-02 | B-02 H_E endpoint re-proof bound check (security policy) | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-03 | B-01 H_T: 100 ms insert_text focus settle | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-04 | N-01R H_C: native cursor reveal (text entry) | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-06 | OWN-09R timeout semantics: bounded coordinator wait vs leaked-closure guards | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-07 | OWN-09R / kvnloo/cua#9 R8: implement MCP notifications/cancelled or keep it ignored | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-08 | trycua/cua PR 4336 timing fields emitted unconditionally vs env-gated wording | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-09 | OWN-16W: JSON null refusal and the analyzer-vs-PREREG reading | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-10 | R2-09 T3: install WebKitGTK (or use the flatpak runtime), or accept BLOCKED | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-11 | TypeSafe budget allocation for the remaining reached requests (live R' recertification, live toggle/modal, kvnloo/cua#78 R1/R4, native live arms) or a cap raise | owner ruling | **no** | **no** | yes | **no** | yes | yes | **no** | **no** |
| OR-12 | RECERT-FIX wave-4 cross-lane pkill ruling | owner ruling | **no** | **no** | yes | **no** | yes | yes | **no** | **no** |
| OR-14 | OWN-20G: reply-delay R1 row in place of the XGrabServer row; settle overshoot as IRREDUCIBLE coverage | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-15 | Browser per-process cold first snapshot: accept B-06's post-hoc amendment reading or fund a fresh run (B-08 PENDING) | owner ruling | yes | yes | yes | **no** | **no** | yes | **no** | **no** |
| OR-16 | OWN-09R strict PREREG reading of the head-core unit row (Deviation 6) | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-17 | OWN-20P: marked-twin R1 substitution and A's trigger set | owner ruling | yes | yes | yes | **no** | **no** | yes | **no** | **no** |
| OR-18 | Driver telemetry on by default in lane sessions (set it off in the shared session wrapper) | owner ruling | **no** | **no** | yes | **no** | yes | yes | **no** | **no** |
| OR-19 | Fail-closed guard that rejects code-executing commands outside the hostless wrapper | owner ruling | **no** | **no** | yes | **no** | yes | yes | **no** | **no** |
| OR-20 | kvnloo/cua#78 S1 backend row (adapter not local; only TypeSafe permitted) | owner ruling | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| OR-21 | Native T definition: may native whole-task T exclude provider decisions (scripted chooser), or fund live native arms | owner ruling | **no** | **no** | yes | **no** | yes | yes | **no** | **no** |
| PRIV-A | Published fork branch exp/r2-10-composition-20261002 carries an encoded private-name list (PUB-02 r1c) | owner ruling, then a privacy rewrite on the fork | yes | yes | yes | **no** | yes | yes | **no** | **no** |
| PRIV-B | Published fork branch exp/own-20g-guard-final-diff-a2-20261003 carries the local user name in raw output (PUB-03 PENDING) | owner ruling, then a privacy rewrite on the fork | yes | yes | yes | **no** | **no** | yes | **no** | **no** |

### Q01. FIX-01 detached-node refusal (dom_event route) + refused-is-refused runner rule

- **delta** -> Driver refuses dom_event browser_click / browser_pointer / browser_download on a detached ref node (isConnected checked inside the dispatching callFunctionOn; browser_ref_stale, effect refused); jev-use runners treat refused as refused and never re-dispatch an unverified accepted mutation.
- **canonical owner** -> kvnloo/cua#73 (stale-dispatch invariant); kvnloo/cua#93 (R2-07 gap); kvnloo/cua#105 (runner rule)
- **exact SHA** -> candidate `exp/r2-10r-control-a2-20261003` @ `8a2362770` commits `a4cda75bd`, `8a2362770` (FIX-01 Part A + Part B rebased on 0f1955d2f (the R2-10R control binary source); original commits 8cfa8c1db + 6eb9319fe on the FIX-01 packet branch); packet FIX-01 `exp/fix-01-detached-node-refusal-20261002` @ `4a301d32a`; packet R2-10R `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec`
- **completed evidence** -> N4a re-render on the FIX-01 fixed tree: first click refused 20 of 20 (browser_ref_stale), then rebound and verified 20; unfixed tree accepted 20 of 20; old-node page events on the fixed tree 0; Recertified on 0f1955d2f inside R2-10R: N4a controls passed 15 of 15; Runner: re-dispatches after an unverified accepted mutation on the fixed runner 0; on the old runner, cells with a re-dispatch 10
- **missing evidence** -> The trusted-input route keeps a residual re-render window between send and landing (FIX-01 follow-up; characterised under a shared lock only). kvnloo/cua#107 D (other track) found the same detached-node acceptance on its unfixed binary (DC05b); no re-run of that cell on a fixed tree.
- **action type** -> fork candidate review, then a reviewed upstream PR proposal (not posted; upstream owner named at that time)
- **dependency** -> fresh review of this entry; FIX-02 F3 (retry scope) travels with Part B
- **stop condition** -> Any false refusal on a connected node, or a refused dispatch whose effect landed.
- **READY NOW: NO.** Failing: fresh review not done.

### Q02. FIX-02 F1-F3: native token ownership, runtime generation, runner re-dispatch scope

- **delta** -> F1 binds native element tokens to the publishing session; F2 starts snapshot ids at a random per-process base (runtime generation); F3 lets jev-use runners re-dispatch only after pre-dispatch refusals.
- **canonical owner** -> kvnloo/cua#36; kvnloo/cua#105 (F3 runner rule)
- **exact SHA** -> candidate `exp/fix-02r-a3-20261003` @ `df4f1edf5` commits `8e0e8aea0`, `205a4ecb2`, `cdffb3213` (F1-F3 rebased on 0f1955d2f (on top of the FIX-01 picks)); packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`; packet FIX-02 `exp/fix-02-token-ownership-retry-scope-20261002` @ `cea02cb74`
- **completed evidence** -> I2 F' 40/40: yes; I2d F' 40/40: yes; I5p F' 20/20: yes; I5pt F' 10/10: yes; 0 blind re-dispatches on F': yes; 0 cross-session mutations on F': yes; Recertification verdicts: F1 RECERT_PASS, F2 RECERT_PASS, F3 RECERT_PASS
- **missing evidence** -> A dedicated recording-lookup test (the F1 recording.rs session check has no session-published test). Session checks on window_for_snapshot and the (pid, xid) side index (non-authority routing) - FIX-03 is running. Discriminating unfixed rows for W2c / W2d (the unfixed tree also refuses them).
- **action type** -> fork candidate review, then a reviewed upstream PR proposal (not posted)
- **dependency** -> FIX-03 (wave 6) session-routing result; fresh review of this entry
- **stop condition** -> Upstream main changes snapshot_store.rs or the Linux token path; any cross-session mutation on the fixed tree.
- **READY NOW: NO.** Failing: wave-6 lane pending (FIX-03); fresh review not done.

### Q03. FIX-02 F4: browser_set_input_files detached-input refusal (FIX-03 PENDING)

- **delta** -> Refuse browser_set_input_files on a file input that is detached before the call.
- **canonical owner** -> kvnloo/cua#36
- **exact SHA** -> candidate `exp/fix-02r-a3-20261003` @ `df4f1edf5` commits `a357d061d` (F4 rebased on 0f1955d2f); packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`; packet FIX-02 `exp/fix-02-token-ownership-retry-scope-20261002` @ `cea02cb74`
- **completed evidence** -> F4 F' 20/20 (narrower claim; TOCTOU not covered): yes; Disposition REVISE (recertification verdict RECERT_PASS)
- **missing evidence** -> The check is a separate call before DOM.setFileInputFiles: a re-render inside the check-to-set window is not covered (TOCTOU). FIX-03 is measuring an in-call check.
- **action type** -> hold (REVISE); fork candidate after FIX-03
- **dependency** -> FIX-03 (wave 6)
- **stop condition** -> FIX-03 cannot close the window inside the call path, or any old-node event on the fixed tree.
- **READY NOW: NO.** Failing: wave-6 lane pending (FIX-03); fresh review not done.

### Q04. kvnloo/cua#84 revision (OWN-09R): cancel before admission, guard ownership

- **delta** -> Revised kvnloo/cua#84: cancellation checked before admission, admission holds owned by the operation, Linux spawn_blocking sites converted to spawn_blocking_owned.
- **canonical owner** -> kvnloo/cua#9; kvnloo/cua#84
- **exact SHA** -> candidate `exp/own-09r2-a3-20261003` @ `ba611b51a` (kvnloo/cua#84 head plus the OWN-09R revision commits, rebased on 0f1955d2f; kvnloo/cua#84 itself is not modified); packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`; packet OWN-09R `exp/own-09r-84-revision-20261002` @ `0c2896a53`
- **completed evidence** -> P_R1D_pass_40: yes; P_R6_pass_80: yes; M_R1D_fail_40: yes; Recertification verdict RECERT_PASS; strict PREREG reading REVISE
- **missing evidence** -> Owner call on the timeout path: guards held by a leaked closure after a foreground timeout vs a bounded coordinator wait with a structured refusal. Owner call on R8 (MCP notifications/cancelled is ignored on both arms). Owner call on the strict unit-row reading (Deviation 6 re-run rule). R3 on macOS (held-input oracle): BLOCKED, hardware.
- **action type** -> hold; revision staged on the fork for the kvnloo/cua#84 owner
- **dependency** -> owner rulings OR-06, OR-07 and OR-16; fresh review of this entry
- **stop condition** -> Upstream main changes the coordinator / barrier path, or kvnloo/cua#84 head moves.
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[6], owner_decisions_pending[7], owner_decisions_pending[19]); fresh review not done.

### Q05. OWN-16W fix dd205d17b: refuse non-boolean modality selectors

- **delta** -> get_window_state refuses non-boolean include_screenshot / modality selectors with invalid_arguments before any producer runs (Linux).
- **canonical owner** -> kvnloo/cua#16
- **exact SHA** -> candidate `exp/own-16w2-a3-20261003` @ `7e31eae59` (dd205d17b rebased on 0f1955d2f); packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`; packet OWN-16W `exp/own-16w-sway-modality-20261002` @ `1b9819157`
- **completed evidence** -> X11 F'' string_false refused 42/42: yes; X11 U'' accepts 42/42 (both string rows): yes; S-W F'' rows meet the wave-3 gates: yes; Recertification verdict RECERT_PASS
- **missing evidence** -> Owner call: the fix also refuses JSON null (formerly the default). Owner call: accept the PREREG F'' gate where the wave-3 analyzer prints REVISE. macOS and Windows parity: BLOCKED (hardware); the Windows get_window_state file has also drifted on main.
- **action type** -> hold; fork candidate after the owner rulings
- **dependency** -> owner ruling OR-09; fresh review of this entry
- **stop condition** -> Upstream main changes get_window_state selector parsing on Linux.
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[9], owner_decisions_pending[21]); fresh review not done.

### Q06. OWN-20P G: focus-guard final read on deadline exit, ported to clean main

- **delta** -> focus_guard: a final focus read when the settle watch ends on its deadline after a read that began before it (restores a focus steal the watch would otherwise miss silently).
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> candidate `exp/own-20p-guard-port-a11y-20261003` @ `64081dded` commits `a761f1f1f` (G port commit a761f1f1f on clean main cb685fad7); packet OWN-20P `exp/own-20p-guard-port-a11y-20261003` @ `64081dded`
- **completed evidence** -> R1 stall row on the marked twins: G restored 40 of 40; U missed 40 of 40 silently; Product G on the normal path: verified 40 of 40; failures plus false restores 0
- **missing evidence** -> R1 on a product binary: needs a mark-free stall method (OWN-20Q is running). Owner acceptance of the marked-twin substitution (R1 ran with the post-action-sleep knob at zero). The same_app_dialog misclassification is not fixed by G (OWN-20Q is running).
- **action type** -> fork candidate review after OWN-20Q
- **dependency** -> OWN-20Q (wave 6); owner ruling OR-17; fresh review of this entry
- **stop condition** -> The port changes quiet-path behaviour, or any false restore on the normal path.
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[20]); wave-6 lane pending (OWN-20Q); fresh review not done.

### Q07. OWN-20P A: in-process AT-SPI bus-restart reconnect (OWN-20Q PENDING)

- **delta** -> The Driver reconnects to a restarted accessibility bus in-process (today a fresh Driver process is needed).
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> candidate `exp/own-20p-guard-port-a11y-20261003` @ `64081dded` commits `064d2e4ad` (A commit 064d2e4ad on the G port); packet OWN-20P `exp/own-20p-guard-port-a11y-20261003` @ `64081dded`
- **completed evidence** -> R3 bus restart: liveness GA 20 of the pre-registered twenty (yes); G0 passes 1; safety GA 20, G0 20; R3 gate yes
- **missing evidence** -> Reconnect triggers only on event-stream end: NoReply and org.a11y.Bus name-owner change are not implemented (OWN-20Q is running). Owner call: is the current trigger set enough.
- **action type** -> fork candidate review after OWN-20Q
- **dependency** -> OWN-20Q (wave 6); owner ruling OR-17; fresh review of this entry
- **stop condition** -> Any stale mutation after a reconnect, or reconnect breaks the quiet path.
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[20]); wave-6 lane pending (OWN-20Q); fresh review not done.

### Q08. OWN-20G guard a30cbbc3b (superseded by the OWN-20P G port; privacy rewrite PUB-03 PENDING)

- **delta** -> The original focus-guard final-read diff, tested on 0f1955d2f plus measurement picks.
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> candidate `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc0` commits `a30cbbc3b` (a30cbbc3b does not apply to clean main; superseded by a761f1f1f (Q06)); packet OWN-20G `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc0`
- **completed evidence** -> R1 reply-delay row: gate (G restores every trial) yes; specified XGrabServer row gate no; R3 bus restart: safety gate yes; in-process liveness gate no
- **missing evidence** -> The published branch carries the local user name in raw xhost output (privacy); PUB-03 is preparing a rewrite candidate. Owner calls: the reply-delay row in place of the XGrabServer row, and the settle-overshoot IRREDUCIBLE judgement.
- **action type** -> privacy rewrite candidate (owner ruling) - no posting; the product delta moves to Q06
- **dependency** -> PUB-03 (wave 6); owner rulings PRIV-B and OR-14
- **stop condition** -> Superseded once Q06 is accepted for posting.
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[14], owner_decisions_pending[23], blocked_items_w5[13]); wave-6 lane pending (PUB-03); fresh review not done.

### Q09. BUG-01 A: foreground trusted click receipt labelled background (fix 2533db6d5 + 49a3adf0f)

- **delta** -> The click receipt reports delivery=foreground only when the executed branch activates the window. The fix is the pair 2533db6d5 + 49a3adf0f; neither commit is cited alone (d86b3b1d1 and the superseded fix binary are not cited).
- **canonical owner** -> kvnloo/cua#38 (upstream compatibility: trycua/cua 4009, plain text)
- **exact SHA** -> candidate `exp/bug-01-delivery-cdp-sessions-20261002` @ `097b4f097` commits `2533db6d5`, `49a3adf0f` (fix pair on base c4d0c6625); packet BUG-01 `exp/bug-01-delivery-cdp-sessions-20261002` @ `097b4f097`
- **completed evidence** -> Baseline trusted-foreground arm: mislabelled background 20 of 20; fixed: delivery foreground 20; Only the delivery mode changed between baseline and the fix pair: yes
- **missing evidence** -> Recertification on 0f1955d2f or later (Linux/core paths changed on main since c4d0c6625). Windows, macOS and embedded labels are UNIT-only.
- **action type** -> fork fix branch for owner review; upstream routing decided by the kvnloo/cua#38 owner (not posted)
- **dependency** -> recertification on current main; fresh review of this entry
- **stop condition** -> The producer branch structure changes upstream, or any other receipt field changes.
- **READY NOW: NO.** Failing: not recertified on pinned main (14 non-allowlisted drift paths, 0 overlapping the claim); fresh review not done.

### Q10. BUG-01 B: CDP sessions accumulate (attach per call, never detach)

- **delta** -> Each browser call attaches one CDP session and never detaches it; the post-navigation event burst scales with the session count. Accumulation only - no fix and no cost on a no-op page.
- **canonical owner** -> trycua/cua 4052 (plain text; evidence owner)
- **exact SHA** -> packet BUG-01 `exp/bug-01-delivery-cdp-sessions-20261002` @ `097b4f097`
- **completed evidence** -> Live CDP sessions at the end of each long run: [304.0, 304.0, 304.0]
- **missing evidence** -> A cost on a non-trivial page (none measured).
- **action type** -> evidence note only (no fix)
- **dependency** -> fresh review of this entry
- **stop condition** -> Upstream changes CDP session lifetime.
- **READY NOW: NO.** Failing: not recertified on pinned main (14 non-allowlisted drift paths, 0 overlapping the claim); fresh review not done.

### Q11. OWN-105 runner reconcile (kvnloo/cua#105 gaps G1-G3 + pre-write rule)

- **delta** -> Python and TS jev-use runners reconcile an ambiguous mutation receipt before any second dispatch (no new service).
- **canonical owner** -> kvnloo/cua#105
- **exact SHA** -> candidate `exp/own-105-runner-reconcile-20261002` @ `b97daa4ba` (on base 345ff6d9d); packet OWN-105 `exp/own-105-runner-reconcile-20261002` @ `b97daa4ba`
- **completed evidence** -> Fixed runners: trials 148; duplicates 0; receipts present 148; second dispatches 0; Gate verdict KEEP; unfixed base reproduces the gap: yes
- **missing evidence** -> Red/green counts live only in gitignored logs: force-add them before posting. TS R6 is emulated-state evidence (Python R6 carries the gate alone). Recertification on current main (Linux/core paths changed since 345ff6d9d).
- **action type** -> fork branch + kvnloo/cua#105 comment (fork only)
- **dependency** -> fresh review of this entry; kvnloo/cua#105 head unchanged
- **stop condition** -> kvnloo/cua#105 head moves, or any duplicate mutation on a fixed runner.
- **READY NOW: NO.** Failing: not recertified on pinned main (25 non-allowlisted drift paths, 0 overlapping the claim); fresh review not done.

### Q12. trycua/cua PR 4336 native timing parity (OWN-75R)

- **delta** -> trycua/cua PR 4336 adds native timing fields to the jev-use runners with no cross-language field mismatch and no behaviour change versus its base.
- **canonical owner** -> kvnloo/cua#75; upstream trycua/cua PR 4336 (plain text)
- **exact SHA** -> candidate `exp/own-75r-timing-parity-4336-r1b-20261003` @ `efe36d1a1` (r1b = publish fixes on the accepted packet e02621fdc; PR head 8391cf802); packet OWN-75R `exp/own-75r-timing-parity-4336-20261002` @ `e02621fdc`
- **completed evidence** -> REAL trials verified 160 of 160; non-loopback refusals by the net guard 0
- **missing evidence** -> Owner call: the PR emits the timing fields unconditionally (log-only) vs the env-gated / default-off wording. kvnloo/cua#75 body still cites an older head (d301a076c). Recertification against current main (the PR base predates many Linux/core changes).
- **action type** -> evidence comment for the trycua/cua PR 4336 owner (drafted on the fork; not posted upstream)
- **dependency** -> owner ruling OR-08; PR head unchanged; fresh review of this entry
- **stop condition** -> The PR head moves from 8391cf802.
- **READY NOW: NO.** Failing: not recertified on pinned main (177 non-allowlisted drift paths, 0 overlapping the claim); owner decision pending (owner_decisions_pending[8]); fresh review not done.

### Q13. OWN-78A candidate F for trycua/cua PR 4394 (restore form + page + outline) (OWN-78L PENDING)

- **delta** -> Restore the form, page and outline context in the PR 4394 browser request so the live provider stops abstaining at step one.
- **canonical owner** -> kvnloo/cua#78; upstream trycua/cua PR 4394 (plain text)
- **exact SHA** -> candidate `exp/own-78a-abstain-isolation-4394-20261003` @ `6f6c67955` commits `61eec0909` (fix candidate F head 61eec0909); packet OWN-78A `exp/own-78a-abstain-isolation-4394-20261003` @ `6f6c67955`
- **completed evidence** -> Live TypeSafe step-one isolation: PR abstained 5/5; PR plus form correct 1/5; F correct 5/5; pre-PR correct 5/5; Attribution PAGE_OUTLINE_ALSO_NEEDED; disposition REVISE
- **missing evidence** -> R1-lite on F (OWN-78L is running). Full-n live R1 / R4: BLOCKED (paid budget). S1 backend row: BLOCKED (owner decision; adapter not local). The remaining A2-vs-A3 gap (question key, instructions, goal / history placement, visual): BLOCKED (budget).
- **action type** -> hold; evidence comment for kvnloo/cua#78 after OWN-78L (fork only)
- **dependency** -> OWN-78L (wave 6); owner rulings OR-11 and OR-20; PR head unchanged
- **stop condition** -> The trycua/cua PR 4394 head moves from 039257811.
- **READY NOW: NO.** Failing: not recertified on pinned main (177 non-allowlisted drift paths, 0 overlapping the claim); owner decision pending (owner_decisions_pending[22], blocked_items_w5[4]); wave-6 lane pending (OWN-78L); fresh review not done.

### Q14. B-02 H_V browser admission tools-list cache

- **delta** -> Cache the validated tools/list at MCP admission instead of re-validating it per call (browser).
- **canonical owner** -> kvnloo/cua#93; kvnloo/cua#10
- **exact SHA** -> candidate `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec` commits `770a715ed` (measurement-only env-gated knob (B-02) carried in R'; no product diff exists yet); packet B-02 `exp/b-02-browser-driver-sites-20261002` @ `b282ff389`; packet R2-10R `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec`
- **completed evidence** -> B-02 fill: verdict DELETED (KEEP); admission component saving 24.3 ms; B-02 toggle verdict DELETED (KEEP); modal verdict NOT_MATERIAL (saving not shown on T_oracle); On R' inside COMP: admission work removed per fill trial 8.7 ms
- **missing evidence** -> A product (non-env-gated) diff with unit tests; the knob is measurement-only. Modal is NOT_MATERIAL on the B-02 binary.
- **action type** -> product-change proposal (default behaviour change; needs a reviewed product diff first)
- **dependency** -> a reviewed product diff; fresh review of this entry
- **stop condition** -> A product diff changes the tools/list envelope bytes.
- **READY NOW: NO.** Failing: fresh review not done.

### Q15. N-04 V native admission tools-list cache

- **delta** -> The same admission tools-list cache on the native GTK3 path.
- **canonical owner** -> kvnloo/cua#93; kvnloo/cua#10
- **exact SHA** -> candidate `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5` (measurement-only knob on R'n; PUB-03 is preparing a privacy rewrite (r1c) of this branch); packet N-04 `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5`; packet N-03 `exp/n-03-native-closure-axfg-a3-20261003` @ `6b70ec902`
- **completed evidence** -> N-04 verdict DELETED; T saved checkbox 2.94 ms [2.02, 3.46], text 3.04 ms [2.01, 3.91]; Admission work deleted: checkbox 2.84 ms, text 4.35 ms; Replicated on N3 (N-03): checkbox verdict DELETED, text verdict DELETED
- **missing evidence** -> A product (non-env-gated) diff with unit tests; the knob is measurement-only.
- **action type** -> product-change proposal (with Q14; one admission cache for both paths)
- **dependency** -> PUB-03 (wave 6) r1c publication head; a reviewed product diff; fresh review of this entry
- **stop condition** -> A product diff changes the tools/list envelope bytes.
- **READY NOW: NO.** Failing: wave-6 lane pending (PUB-03); fresh review not done.

### Q16. Post-DoAction sleep deletion scope (N-01R / R2-09 / N-03)

- **delta** -> Delete the fixed post-DoAction sleep on the measured routes: GTK3 AT-SPI background (N-01R), Chromium AT-SPI background (R2-09, qualified by the focus-change condition) and GTK3 X11 ax_fg at the default config (N-03).
- **canonical owner** -> kvnloo/cua#93; kvnloo/cua#10; kvnloo/cua#20 (settle watch)
- **exact SHA** -> candidate `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec` commits `8f4f8b542` (measurement-only N-01R knob carried in R'; no product diff yet); packet N-01R `exp/n-01r-native-wait-ab-20261002` @ `3bb4a7fc7`; packet R2-09 `exp/r2-09-native-event-wake-20261002` @ `3539e34ae`; packet N-03 `exp/n-03-native-closure-axfg-a3-20261003` @ `6b70ec902`; packet N-04 `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5`
- **completed evidence** -> N-01R GTK3 background: checkbox verdict DELETED (saving 60.6 ms), text verdict DELETED (saving 42.3 ms); R2-09 Chromium background: S0 saves 69.8 ms [53.1, 102.2] on checkbox; N-03 X11 ax_fg: verdict DELETED; click wrapper saved 51.35 ms [48.86, 53.72]; On R'n the sleep is gone from the best arm: post-action sleep work deleted 51.14 ms (checkbox)
- **missing evidence** -> WebKitGTK targets: NOT_RUN (owner decision on installing WebKitGTK). Hyprland foreground route: BLOCKED (real seat). A product diff: the deletion is measured through an env-gated knob only.
- **action type** -> product-change proposal, scoped to the measured routes (default behaviour change)
- **dependency** -> owner ruling OR-10; a reviewed product diff; fresh review of this entry
- **stop condition** -> A focus-steal control misses silently with the sleep removed, or a new route lacks the settle watch.
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[10]); fresh review not done.

### Q17. R2-03 guarded completion = trycua/cua PR 4316

- **delta** -> trycua/cua PR 4316 completes a guarded fill->submit without the second provider decision.
- **canonical owner** -> kvnloo/cua#10; kvnloo/cua#87; upstream trycua/cua PR 4316 (plain text)
- **exact SHA** -> candidate `exp/r2-03-guarded-live-20261001` @ `6bab214ab` (tested PR head a0bca7440); packet R2-03 `exp/r2-03-guarded-live-20261001` @ `6bab214ab`
- **completed evidence** -> Live TypeSafe: provider requests baseline 80, guarded 40; paired verified-time difference -211.8 ms [-251.8, -192.1]; Disposition KEEP
- **missing evidence** -> kvnloo/cua#107 D (other track, exp/i107-d-20261002 at 6d1c60926): the guard accepted a Submit relocated into another form and submitted to a decoy (missing form-scope fact). Wrong-target breach; blocks promotion. Guarded completion binds nothing on toggle / modal (no saving there). Recertification of the live claim on current main (live layer on R' is BLOCKED by budget).
- **action type** -> evidence comment for the trycua/cua PR 4316 owner, including the wrong-target finding (drafted on the fork; not posted upstream)
- **dependency** -> a form-scope fix for the decoy case; PR head unchanged; fresh review of this entry
- **stop condition** -> The PR head moves from a0bca7440, or any wrong-target submit.
- **READY NOW: NO.** Failing: not recertified on pinned main (25 non-allowlisted drift paths, 0 overlapping the claim); fresh review not done.

### Q18. R2-07b fill compiled replay (re-qualified by FIX-01)

- **delta** -> A compiled fresh-bound fill->submit routine replays without provider decisions on warm runs, with fresh authority before each replayed mutation and bounded fallback.
- **canonical owner** -> kvnloo/cua#93 (R2-07); kvnloo/cua#10
- **exact SHA** -> candidate `exp/r2-10-composition-20261002` @ `030f6bdbf` (measured inside R2-10's fill COMP arm on R; the R2-07 packet itself stays KILL); packet R2-10 `exp/r2-10-composition-20261002` @ `030f6bdbf`; packet FIX-01 `exp/fix-01-detached-node-refusal-20261002` @ `4a301d32a`
- **completed evidence** -> Live fill on R: provider requests per trial BASE 2 -> COMP 0.033; provider work removed 484.8 ms per trial; Live fill amortized S (all invocations incl. training) 42.16 [34.68, 48.46]
- **missing evidence** -> Live recertification on R' (0f1955d2f): BLOCKED (paid budget). A product shape: no routine framework or route miner is proposed (parked by kvnloo/cua#74); this stays research evidence.
- **action type** -> research evidence for the trycua/cua issue 3963 rewrite draft (DOC-3963); no upstream posting
- **dependency** -> owner ruling OR-11 (budget); DOC-3963 (wave 6)
- **stop condition** -> Any blind replay of a may-have-landed effect, or a fallback that skips fresh authority.
- **READY NOW: NO.** Failing: not recertified on pinned main (7 non-allowlisted drift paths, 0 overlapping the claim); owner decision pending (owner_decisions_pending[22]); wave-6 lane pending (DOC-3963); fresh review not done.

### Q19. R2-07c/d/e toggle and modal compiled replay (R2-07e PENDING)

- **delta** -> The compiled fresh-bound routine for toggle->confirm and modal->act.
- **canonical owner** -> kvnloo/cua#93 (R2-07); kvnloo/cua#10
- **exact SHA** -> candidate `exp/r2-07d-quiet-timing-phase-l-20261003` @ `79f6dd299` (tested on R (12b9045a); no Driver change); packet R2-07c `exp/r2-07c-toggle-modal-compiled-a2-20261003` @ `7f46edd16`; packet R2-07d `exp/r2-07d-quiet-timing-phase-l-20261003` @ `79f6dd299`
- **completed evidence** -> Quiet-window non-regression (CR - COMP): toggle 0.5 ms [-1.3, 0.8] gate yes; modal 0.6 ms [-1.4, 2.4] gate no; Correctness (R2-07c): accepted mutations all fresh, non-fresh attempts refused (10 attempts); Phase L status: NOT_RUN (pre-registered precondition: Phase S passes in both classes)
- **missing evidence** -> A passing modal gate (R2-07e is running a new pre-registered block). Live Phase L (provider decisions are most of live toggle / modal T): NOT_RUN; paid budget.
- **action type** -> hold (research evidence; excluded from the composed toggle / modal configuration)
- **dependency** -> R2-07e (wave 6); owner ruling OR-11 (budget)
- **stop condition** -> The modal gate fails again, or any E4 violation.
- **READY NOW: NO.** Failing: not recertified on pinned main (7 non-allowlisted drift paths, 0 overlapping the claim); owner decision pending (owner_decisions_pending[17], owner_decisions_pending[22]); wave-6 lane pending (R2-07e); fresh review not done.

### Q20. R2-08 API route per task (owner ruling)

- **delta** -> Use the fixture's existing POST /submit route instead of the GUI route when per-task equivalence and authorization evidence exist.
- **canonical owner** -> kvnloo/cua#93 (R2-08); kvnloo/cua#10
- **exact SHA** -> packet R2-08 `exp/r2-08-cross-surface-20261002` @ `afba150d5`
- **completed evidence** -> Equivalence on the base fixture: 20 of 20 rounds; disposition KEEP
- **missing evidence** -> Per-task equivalence and authorization evidence for any real task; the measured route is a fixture route.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> An API route is proposed as a default.
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[5]); fresh review not done.

### Q21. B-01 fast feedback glide / glide-off policy (owner ruling)

- **delta** -> Shorten the awaited agent-cursor glide (fast glide) or turn feedback off; the glide is most of default browser BASE T.
- **canonical owner** -> kvnloo/cua#10; kvnloo/cua#93 (R2-01)
- **exact SHA** -> packet B-01R `exp/b-01r-browser-critpath-textfix-20261002` @ `0cd63f786`; packet R2-10 `exp/r2-10-composition-20261002` @ `030f6bdbf`
- **completed evidence** -> Fast glide (H_V) fill: verdict KEEP; share of the feedback-off saving recovered 0.987; KEEP-only composition on R (glide left on): fill S 1.01
- **missing evidence** -> A product decision on visual-feedback policy; the knob is measurement-only.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> Visual feedback becomes a user-facing contract.
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[3]); fresh review not done.

### Q22. B-01 H_C / N-02 HC caller-compiled output validators

- **delta** -> The caller compiles output-schema validators once instead of validating each result from scratch (client side).
- **canonical owner** -> kvnloo/cua#10; kvnloo/cua#93
- **exact SHA** -> packet B-01R `exp/b-01r-browser-critpath-textfix-20261002` @ `0cd63f786`; packet N-02 `exp/n-02-native-transport-20261002` @ `9846ac803`
- **completed evidence** -> Browser H_C toggle verdict KEEP; Native HC checkbox verdict DELETED (saving 21.3 ms); text verdict DELETED (saving 25.9 ms)
- **missing evidence** -> Eager compilation costs time per session; the lazy form (HCL) is an owner decision on session shape (Q23).
- **action type** -> client-side change proposal for the jev-use runners (after the HCL ruling)
- **dependency** -> owner ruling Q23 (HCL); fresh review of this entry
- **stop condition** -> Any validation outcome differs from the uncompiled validator.
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[16]); fresh review not done.

### Q23. HCL lazy per-schema validators (owner ruling)

- **delta** -> Compile each output validator lazily on first use: about zero at one task per session, a saving per multi-task session.
- **canonical owner** -> kvnloo/cua#10
- **exact SHA** -> packet N-04 `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5`; packet N-03 `exp/n-03-native-closure-axfg-a3-20261003` @ `6b70ec902`
- **completed evidence** -> N-04 checkbox: at one task -0.04 ms; per five-task session 82.22 ms; verdict OWNER_DECISION
- **missing evidence** -> The expected session shape (tasks per session) - an owner decision.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[16]); fresh review not done.

### OR-01. OWN-36 I3s: shared-window replacement retirement

- **delta** -> OWN-36 I3s: shared-window replacement retirement
- **canonical owner** -> kvnloo/cua#36
- **exact SHA** -> packet OWN-36 `exp/own-36-session-isolation-native-20261002` @ `ff77554f4`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[0]); fresh review not done.

### OR-02. B-02 H_E endpoint re-proof bound check (security policy)

- **delta** -> B-02 H_E endpoint re-proof bound check (security policy)
- **canonical owner** -> kvnloo/cua#73; kvnloo/cua#10
- **exact SHA** -> packet B-02 `exp/b-02-browser-driver-sites-20261002` @ `b282ff389`
- **completed evidence** -> B-02 fill endpoint verdict OWNER_DECISION; saving 21.9 ms
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[1]); fresh review not done.

### OR-03. B-01 H_T: 100 ms insert_text focus settle

- **delta** -> B-01 H_T: 100 ms insert_text focus settle
- **canonical owner** -> kvnloo/cua#10
- **exact SHA** -> packet B-01R `exp/b-01r-browser-critpath-textfix-20261002` @ `0cd63f786`
- **completed evidence** -> Verdict OWNER_DECISION
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[2]); fresh review not done.

### OR-04. N-01R H_C: native cursor reveal (text entry)

- **delta** -> N-01R H_C: native cursor reveal (text entry)
- **canonical owner** -> kvnloo/cua#10
- **exact SHA** -> packet N-04 `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5`
- **completed evidence** -> Reveal work removed on R'n text, BASE to best: 1410.6 ms
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[4]); fresh review not done.

### OR-06. OWN-09R timeout semantics: bounded coordinator wait vs leaked-closure guards

- **delta** -> OWN-09R timeout semantics: bounded coordinator wait vs leaked-closure guards
- **canonical owner** -> kvnloo/cua#9; kvnloo/cua#84
- **exact SHA** -> packet OWN-09R `exp/own-09r-84-revision-20261002` @ `0c2896a53`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[6]); fresh review not done.

### OR-07. OWN-09R / kvnloo/cua#9 R8: implement MCP notifications/cancelled or keep it ignored

- **delta** -> OWN-09R / kvnloo/cua#9 R8: implement MCP notifications/cancelled or keep it ignored
- **canonical owner** -> kvnloo/cua#9; kvnloo/cua#84
- **exact SHA** -> packet OWN-09R `exp/own-09r-84-revision-20261002` @ `0c2896a53`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[7]); fresh review not done.

### OR-08. trycua/cua PR 4336 timing fields emitted unconditionally vs env-gated wording

- **delta** -> trycua/cua PR 4336 timing fields emitted unconditionally vs env-gated wording
- **canonical owner** -> kvnloo/cua#75
- **exact SHA** -> packet OWN-75R `exp/own-75r-timing-parity-4336-20261002` @ `e02621fdc`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[8]); fresh review not done.

### OR-09. OWN-16W: JSON null refusal and the analyzer-vs-PREREG reading

- **delta** -> OWN-16W: JSON null refusal and the analyzer-vs-PREREG reading
- **canonical owner** -> kvnloo/cua#16
- **exact SHA** -> packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[9], owner_decisions_pending[21]); fresh review not done.

### OR-10. R2-09 T3: install WebKitGTK (or use the flatpak runtime), or accept BLOCKED

- **delta** -> R2-09 T3: install WebKitGTK (or use the flatpak runtime), or accept BLOCKED
- **canonical owner** -> kvnloo/cua#93
- **exact SHA** -> packet R2-09 `exp/r2-09-native-event-wake-20261002` @ `3539e34ae`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[10], blocked_items_w5[8]); fresh review not done.

### OR-11. TypeSafe budget allocation for the remaining reached requests (live R' recertification, live toggle/modal, kvnloo/cua#78 R1/R4, native live arms) or a cap raise

- **delta** -> TypeSafe budget allocation for the remaining reached requests (live R' recertification, live toggle/modal, kvnloo/cua#78 R1/R4, native live arms) or a cap raise
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> none (ruling only)
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: no accepted packet; nothing published; owner decision pending (owner_decisions_pending[11], owner_decisions_pending[17], owner_decisions_pending[22]); fresh review not done.

### OR-12. RECERT-FIX wave-4 cross-lane pkill ruling

- **delta** -> RECERT-FIX wave-4 cross-lane pkill ruling
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> none (ruling only)
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: no accepted packet; nothing published; owner decision pending (owner_decisions_pending[12], blocked_items_w5[14]); fresh review not done.

### OR-14. OWN-20G: reply-delay R1 row in place of the XGrabServer row; settle overshoot as IRREDUCIBLE coverage

- **delta** -> OWN-20G: reply-delay R1 row in place of the XGrabServer row; settle overshoot as IRREDUCIBLE coverage
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> packet OWN-20G `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc0`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[14]); fresh review not done.

### OR-15. Browser per-process cold first snapshot: accept B-06's post-hoc amendment reading or fund a fresh run (B-08 PENDING)

- **delta** -> Browser per-process cold first snapshot: accept B-06's post-hoc amendment reading or fund a fresh run (B-08 PENDING)
- **canonical owner** -> kvnloo/cua#10; kvnloo/cua#73
- **exact SHA** -> packet B-06 `exp/b-06-per-process-cold-snapshot-20261003` @ `31bc98a95`
- **completed evidence** -> B-06 primary verdict fill UNDECIDED; amended fill OWNER_DECISION (D 10.0 ms [8.0, 12.0])
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[15], owner_decisions_pending[18], blocked_items_w5[11]); wave-6 lane pending (B-08); fresh review not done.

### OR-16. OWN-09R strict PREREG reading of the head-core unit row (Deviation 6)

- **delta** -> OWN-09R strict PREREG reading of the head-core unit row (Deviation 6)
- **canonical owner** -> kvnloo/cua#9; kvnloo/cua#84
- **exact SHA** -> packet RECERT-FIX `exp/fix-recert-a3-20261003` @ `939580fc6`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[19]); fresh review not done.

### OR-17. OWN-20P: marked-twin R1 substitution and A's trigger set

- **delta** -> OWN-20P: marked-twin R1 substitution and A's trigger set
- **canonical owner** -> kvnloo/cua#20
- **exact SHA** -> packet OWN-20P `exp/own-20p-guard-port-a11y-20261003` @ `64081dded`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[20]); wave-6 lane pending (OWN-20Q); fresh review not done.

### OR-18. Driver telemetry on by default in lane sessions (set it off in the shared session wrapper)

- **delta** -> Driver telemetry on by default in lane sessions (set it off in the shared session wrapper)
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> none (ruling only)
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: no accepted packet; nothing published; owner decision pending (owner_decisions_pending[24]); fresh review not done.

### OR-19. Fail-closed guard that rejects code-executing commands outside the hostless wrapper

- **delta** -> Fail-closed guard that rejects code-executing commands outside the hostless wrapper
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> none (ruling only)
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: no accepted packet; nothing published; owner decision pending (blocked_items_w5[15]); fresh review not done.

### OR-20. kvnloo/cua#78 S1 backend row (adapter not local; only TypeSafe permitted)

- **delta** -> kvnloo/cua#78 S1 backend row (adapter not local; only TypeSafe permitted)
- **canonical owner** -> kvnloo/cua#78
- **exact SHA** -> packet OWN-78A `exp/own-78a-abstain-isolation-4394-20261003` @ `6f6c67955`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (blocked_items_w5[4]); fresh review not done.

### OR-21. Native T definition: may native whole-task T exclude provider decisions (scripted chooser), or fund live native arms

- **delta** -> Native T definition: may native whole-task T exclude provider decisions (scripted chooser), or fund live native arms
- **canonical owner** -> kvnloo/cua#10
- **exact SHA** -> none (ruling only)
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> The owner's ruling.
- **action type** -> owner ruling
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: no accepted packet; nothing published; owner decision pending (blocked_items_w5[3]); fresh review not done.

### PRIV-A. Published fork branch exp/r2-10-composition-20261002 carries an encoded private-name list (PUB-02 r1c)

- **delta** -> Replace the published R2-10 branch history with the clean rewrite r1c, or delete and re-push, or accept.
- **canonical owner** -> kvnloo/cua#73
- **exact SHA** -> candidate `exp/r2-10-composition-r1c-20261003` @ `eaca68df9` (held locally, not pushed (PUB-02 B)); packet PUB-02 `docs/packet-template-privacy-20261003` @ `c4342323b`; packet R2-10 `exp/r2-10-composition-20261002` @ `030f6bdbf`
- **completed evidence** -> The R2-10 summary blob is identical at the published head and at r1c: yes
- **missing evidence** -> The owner's ruling (force-replace, delete and re-push, or accept).
- **action type** -> owner ruling, then a privacy rewrite on the fork
- **dependency** -> owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[13], owner_decisions_pending[23], blocked_items_w5[13]); fresh review not done.

### PRIV-B. Published fork branch exp/own-20g-guard-final-diff-a2-20261003 carries the local user name in raw output (PUB-03 PENDING)

- **delta** -> Replace the published OWN-20G branch with a scrubbed rewrite, or delete and re-push, or accept.
- **canonical owner** -> kvnloo/cua#73; kvnloo/cua#20
- **exact SHA** -> packet OWN-20G `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc0`
- **completed evidence** -> none beyond the cited packet
- **missing evidence** -> A rewrite candidate (PUB-03 is preparing r1c). The owner's ruling.
- **action type** -> owner ruling, then a privacy rewrite on the fork
- **dependency** -> PUB-03 (wave 6); owner
- **stop condition** -> —
- **READY NOW: NO.** Failing: owner decision pending (owner_decisions_pending[23], blocked_items_w5[13]); wave-6 lane pending (PUB-03); fresh review not done.

<!-- END GENERATED: make_queue.py -->
