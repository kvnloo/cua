## Round-2 wave 6: posting queue staged (DOC-10-74), 2026-10-03

The full kvnloo/cua#74 queue is staged on the fork at [`docs/rfc/74-posting-queue/`](https://github.com/kvnloo/cua/blob/docs/accounting-10-queue-74-20261003/docs/rfc/74-posting-queue/README.md) (branch `docs/accounting-10-queue-74-20261003` @ `a3e3cb86e`). Nothing is posted, and nothing goes to trycua/cua.

Each entry uses this issue's format:

`delta -> canonical owner -> exact SHA -> completed evidence -> missing evidence -> action type -> dependency -> stop condition`

Each entry also has seven READY NOW booleans, recomputed by `verify_artifacts.py` from their sources:
- **packet:** an accepted packet exists.
- **origin:** the branch is on origin at the cited SHA.
- **drift:** the entry is recertified on, or free of drift against, pinned trycua/cua main `5de1a3799`.
- **owner:** no owner decision is pending.
- **w6:** no wave-6 lane is pending.
- **PR:** the live PR head is unchanged.
- **review:** a fresh review is done.

**READY NOW: 0 of 44 entries.** Every entry fails at least the fresh-review gate; the review of this queue is the first one.

| ID | Entry | Action type | Failing gates |
|---|---|---|---|
| Q01 | FIX-01 detached-node refusal (dom_event route) + refused-is-refused runner rule | fork candidate review, then a reviewed upstream PR proposal (not posted; upstream owner named at that time) | review |
| Q02 | FIX-02 F1-F3: native token ownership, runtime generation, runner re-dispatch scope | fork candidate review, then a reviewed upstream PR proposal (not posted) | w6, review |
| Q03 | FIX-02 F4: browser_set_input_files detached-input refusal (FIX-03 PENDING) | hold (REVISE); fork candidate after FIX-03 | w6, review |
| Q04 | kvnloo/cua#84 revision (OWN-09R): cancel before admission, guard ownership | hold; revision staged on the fork for the kvnloo/cua#84 owner | owner, review |
| Q05 | OWN-16W fix dd205d17b: refuse non-boolean modality selectors | hold; fork candidate after the owner rulings | owner, review |
| Q06 | OWN-20P G: focus-guard final read on deadline exit, ported to clean main | fork candidate review after OWN-20Q | owner, w6, review |
| Q07 | OWN-20P A: in-process AT-SPI bus-restart reconnect (OWN-20Q PENDING) | fork candidate review after OWN-20Q | owner, w6, review |
| Q08 | OWN-20G guard a30cbbc3b (superseded by the OWN-20P G port; privacy rewrite PUB-03 PENDING) | privacy rewrite candidate (owner ruling) - no posting; the product delta moves to Q06 | owner, w6, review |
| Q09 | BUG-01 A: foreground trusted click receipt labelled background (fix 2533db6d5 + 49a3adf0f) | fork fix branch for owner review; upstream routing decided by the kvnloo/cua#38 owner (not posted) | drift, review |
| Q10 | BUG-01 B: CDP sessions accumulate (attach per call, never detach) | evidence note only (no fix) | drift, review |
| Q11 | OWN-105 runner reconcile (kvnloo/cua#105 gaps G1-G3 + pre-write rule) | fork branch + kvnloo/cua#105 comment (fork only) | drift, review |
| Q12 | trycua/cua PR 4336 native timing parity (OWN-75R) | evidence comment for the trycua/cua PR 4336 owner (drafted on the fork; not posted upstream) | drift, owner, review |
| Q13 | OWN-78A candidate F for trycua/cua PR 4394 (restore form + page + outline) (OWN-78L PENDING) | hold; evidence comment for kvnloo/cua#78 after OWN-78L (fork only) | drift, owner, w6, review |
| Q14 | B-02 H_V browser admission tools-list cache | product-change proposal (default behaviour change; needs a reviewed product diff first) | review |
| Q15 | N-04 V native admission tools-list cache | product-change proposal (with Q14; one admission cache for both paths) | w6, review |
| Q16 | Post-DoAction sleep deletion scope (N-01R / R2-09 / N-03) | product-change proposal, scoped to the measured routes (default behaviour change) | owner, review |
| Q17 | R2-03 guarded completion = trycua/cua PR 4316 | evidence comment for the trycua/cua PR 4316 owner, including the wrong-target finding (drafted on the fork; not posted upstream) | drift, review |
| Q18 | R2-07b fill compiled replay (re-qualified by FIX-01) | research evidence for the trycua/cua issue 3963 rewrite draft (DOC-3963); no upstream posting | drift, owner, w6, review |
| Q19 | R2-07c/d/e toggle and modal compiled replay (R2-07e PENDING) | hold (research evidence; excluded from the composed toggle / modal configuration) | drift, owner, w6, review |
| Q20 | R2-08 API route per task (owner ruling) | owner ruling | owner, review |
| Q21 | B-01 fast feedback glide / glide-off policy (owner ruling) | owner ruling | owner, review |
| Q22 | B-01 H_C / N-02 HC caller-compiled output validators | client-side change proposal for the jev-use runners (after the HCL ruling) | owner, review |
| Q23 | HCL lazy per-schema validators (owner ruling) | owner ruling | owner, review |
| OR-01 | OWN-36 I3s: shared-window replacement retirement | owner ruling | owner, review |
| OR-02 | B-02 H_E endpoint re-proof bound check (security policy) | owner ruling | owner, review |
| OR-03 | B-01 H_T: 100 ms insert_text focus settle | owner ruling | owner, review |
| OR-04 | N-01R H_C: native cursor reveal (text entry) | owner ruling | owner, review |
| OR-06 | OWN-09R timeout semantics: bounded coordinator wait vs leaked-closure guards | owner ruling | owner, review |
| OR-07 | OWN-09R / kvnloo/cua#9 R8: implement MCP notifications/cancelled or keep it ignored | owner ruling | owner, review |
| OR-08 | trycua/cua PR 4336 timing fields emitted unconditionally vs env-gated wording | owner ruling | owner, review |
| OR-09 | OWN-16W: JSON null refusal and the analyzer-vs-PREREG reading | owner ruling | owner, review |
| OR-10 | R2-09 T3: install WebKitGTK (or use the flatpak runtime), or accept BLOCKED | owner ruling | owner, review |
| OR-11 | TypeSafe budget allocation for the remaining reached requests (live R' recertification, live toggle/modal, kvnloo/cua#78 R1/R4, native live arms) or a cap raise | owner ruling | packet, origin, owner, review |
| OR-12 | RECERT-FIX wave-4 cross-lane pkill ruling | owner ruling | packet, origin, owner, review |
| OR-14 | OWN-20G: reply-delay R1 row in place of the XGrabServer row; settle overshoot as IRREDUCIBLE coverage | owner ruling | owner, review |
| OR-15 | Browser per-process cold first snapshot: accept B-06's post-hoc amendment reading or fund a fresh run (B-08 PENDING) | owner ruling | owner, w6, review |
| OR-16 | OWN-09R strict PREREG reading of the head-core unit row (Deviation 6) | owner ruling | owner, review |
| OR-17 | OWN-20P: marked-twin R1 substitution and A's trigger set | owner ruling | owner, w6, review |
| OR-18 | Driver telemetry on by default in lane sessions (set it off in the shared session wrapper) | owner ruling | packet, origin, owner, review |
| OR-19 | Fail-closed guard that rejects code-executing commands outside the hostless wrapper | owner ruling | packet, origin, owner, review |
| OR-20 | kvnloo/cua#78 S1 backend row (adapter not local; only TypeSafe permitted) | owner ruling | owner, review |
| OR-21 | Native T definition: may native whole-task T exclude provider decisions (scripted chooser), or fund live native arms | owner ruling | packet, origin, owner, review |
| PRIV-A | Published fork branch exp/r2-10-composition-20261002 carries an encoded private-name list (PUB-02 r1c) | owner ruling, then a privacy rewrite on the fork | owner, review |
| PRIV-B | Published fork branch exp/own-20g-guard-final-diff-a2-20261003 carries the local user name in raw output (PUB-03 PENDING) | owner ruling, then a privacy rewrite on the fork | owner, w6, review |

Notes:
- Upstream main moved past the pin during the lane, to the 0.33.0 release version bump and a Windows input fix. The wave-7 refresh re-runs the gates.
- 0 provider requests. Verify with `python3 docs/rfc/74-posting-queue/verify_artifacts.py`.
