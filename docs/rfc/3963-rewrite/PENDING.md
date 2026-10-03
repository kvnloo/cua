# PENDING: rows of the trycua/cua issue 3963 rewrite draft that can still move

This is section 11 of the draft. Every other row of `dispositions.json` is terminal for this draft.

A later wave may change only:
- the rows listed here;
- the rows whose `pending` field in `dispositions.json` is non-empty (verify_artifacts.py checks that every such row appears below).

If an accepted wave-6 packet moves a row, update all of these together:
- that row;
- the README section that quotes it;
- `claims.json`;
- this file.

Do not touch any other row.

## Wave-6 lanes (not accepted; no evidence cited)

| Lane | Branch (planned) | Rows it can move | What will change |
|---|---|---|---|
| B-08 | exp/b-08-per-process-cold-b7-20261003 | B-08, B-06, README sections 1 and 10 (browser E2) | The per-process part of the browser cold first snapshot gets a pre-registered verdict on B-07's binary. If it is IRREDUCIBLE or OWNER_DECISION, the fill/toggle untested shares fall from the R' lower bounds (36.70 / 34.93%) to B-07's 1.6 / 0.6% view. If it is UNTESTED or DELETED, they stay or move by the measured size. |
| R2-07e | exp/r2-07e-modal-gate-phase-l-20261003 | R2-07e, R2-07d, R2-10-LIVE-CR, delta D2 | A new pre-registered modal timing gate. A pass would let the compiled routine into the composed toggle/modal configuration and allow Phase L within its cap. A fail keeps the routine excluded. |
| OWN-78L | exp/own-78l-r1-lite-f-20261003 | OWN-78L, OWN-78A, delta D11 | R1-lite on candidate F (at most 6 reached). It can confirm or weaken F as the fix for the PR 4394 abstain. Full-n R1/R4 stays BLOCKED (budget). |
| OWN-20Q | exp/own-20q-a11y-triggers-dialog-markfree-20261003 | OWN-20Q, OWN-20P, delta D9 | The reconnect's NoReply / name-owner triggers, the same_app_dialog misclassification, and a mark-free stall so R1 can run on a product binary. |
| FIX-03 | exp/fix-03-file-input-toctou-session-routing-20261003 | FIX-03, FIX-02-F4, delta D6 | The file-input check inside the DOM.setFileInputFiles path (TOCTOU) and session routing. It can turn F4 from REVISE into KEEP. |
| PUB-03 | (publish-hygiene lane; several replacement branches) | PUB-03; branch@SHA cells of R2-10, OWN-20G (and N-03/N-04 if their replacements are adopted) | Privacy-clean replacement heads for published branches with private-class findings. The claims and numbers do not change; only the cited branch and SHA may. |

The sibling deliverable DOC-10-74 (kvnloo/cua#10 table and kvnloo/cua#74 queue) is staged in parallel. If it changes a number quoted in section 10, section 10 follows it.

## Owner rulings (each can move the named rows)

| Ruling | Rows / sections | What will change |
|---|---|---|
| Browser feedback glide default | R2-01, R2-10, sections 1, 6 and 10 | Whether S ≈ 45 (glide off) or 1.01 (KEEP-only) is the product number |
| H_E endpoint re-proof bound | B-02, section 6 | Whether about 22 ms per task is deletable |
| Native cursor reveal | N-01R, N-04, section 6 | Whether native text S is 5.941 or 1.030 |
| H_T insert_text focus settle | B-01, section 6 | Whether about 100 ms per fill is deletable |
| HCL session shape | N-03, N-04, delta D15 | Whether lazy validators are a default |
| R2-08 API route | R2-08 | Whether an equivalent, authorized route may be used per task |
| Per-process reuse (B-06 amended reading) | B-06, B-08, section 1 | Browser fill/toggle E2 |
| I3s shared-window replacement | OWN-36, delta D5 | Retirement rule for a shared window |
| OWN-09R bounded coordinator wait | OWN-09R, delta D7 | KEEP stays, or the row turns REVISE until the wait is bounded |
| R8 notifications/cancelled | OWN-09-R8, delta D7 | BLOCKED row resolves |
| OWN-09R strict unit-row reading | OWN-09R, RECERT-FIX | Unit row REVISE vs pass under the re-run rule |
| trycua/cua PR 4336 unconditional fields | OWN-75R, delta D12 | Accepted as is or gated |
| dd205d17b JSON-null refusal | OWN-16W, delta D8 | Accepted as is or narrowed |
| OWN-20P marked-twin R1 substitution; OWN-16W analyzer reading | OWN-20P, OWN-16W | Evidence reading only |
| WebKitGTK | R2-09-T3, delta D14 scope | BLOCKED row runs or stays BLOCKED |
| Driver telemetry default in sessions | section 2 (invariant 2 exception) | Exception removed if set off |
| Provider budget | R2-10-LIVE-RECERT, R2-10-NATIVE-LIVE, R2-10-LIVE-CR, OWN-78-R1R4, OWN-78-S1 | Rows run or stay BLOCKED |
| Native T definition | R2-10-NATIVE-LIVE, section 1 | Whether native T may exclude provider decisions |
| Published-branch privacy findings | R2-10, OWN-20G (branch cells only) | Cited branch/SHA |

## Rows with a non-empty `pending` field

R2-07d, R2-07e, R2-09-T3, R2-10, R2-10-LIVE-RECERT, R2-10-NATIVE-LIVE, R2-10-LIVE-CR, B-06, B-08, FIX-02-F4, FIX-03, OWN-09R, OWN-09-R8, OWN-16W, OWN-20G, OWN-20P, OWN-20Q, OWN-36, OWN-75R, OWN-78A, OWN-78L, OWN-78-S1, OWN-78-R1R4, PUB-03.
