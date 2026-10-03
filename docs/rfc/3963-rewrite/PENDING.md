# PENDING: rows of the trycua/cua issue 3963 rewrite draft that can still move

This is section 11 of the draft. Every row of `dispositions.json` whose `pending` field is empty is terminal for this draft.

**No row is PENDING.** The six wave-6 lanes (B-08, R2-07e, OWN-78L, OWN-20Q, FIX-03, PUB-03) are accepted and folded into the rows; they are no longer listed here.

A later wave may change only the rows in the moving-rows table below. If an accepted packet moves a row, regenerate (`generate.py --state <STATE.json>`) and update, together:
- that row's entry in `rows.spec.json` (claim template and number pointers);
- the README section that quotes it;
- the curated entries of `claims.json` for that prose;
- this file.

Do not touch any other row.

## Wave-7 lanes in flight (OPEN; no result cited)

Each lane below is scheduled but not accepted. The rows it touches say `OPEN: scheduled wave 7 <lane>`; none of them quotes a wave-7 result. The scope column is the planner follow-up the lane comes from (STATE `followups_ranked`), not a finding.
<!-- gen:wave7-lanes -->
| Lane | Scope (planner follow-up) | Rows marked OPEN |
|---|---|---|
| B-09 | browser fill E2: a terminal verdict for the compiled routine's unstamped verify poll (runner component) on B7 | B-08 |
| R2-07f | R2-07e follow-ups: quiet-window toggle non-regression re-confirmation; modal forced fallback or LN toggle within the remaining budget (shared scope with R2-07g) | R2-07e, R2-07e-MODAL |
| R2-07g | R2-07e follow-ups (shared scope with R2-07f) | R2-07e, R2-07e-MODAL |
| FIX-04 | E4 residue for kvnloo/cua#105 and kvnloo/cua#36: runner handling of delivery=unknown refusals, effect=unknown mapping, native AT-SPI pid-wide fallbacks | FIX-02, FIX-03, FIX-03-SIDE |
| FRESH-07 | freshness against upstream main 9a2b1d99e: overlay.rs (trycua/cua PR 4529) and expectation.rs (trycua/cua PR 4531) against the surviving X11 native and focus rows | N-04, FIX-03-SIDE, OWN-16W, OWN-20P, OWN-20Q, OWN-20Q-DLG, OWN-20Q-A2 |
| PUB-04 | privacy-clean replacement candidate for the published R2-10R a3 head (PUB-03 finding) | R2-10R |
<!-- /gen:wave7-lanes -->
The sibling deliverable that refreshes the kvnloo/cua#10 accounting and the kvnloo/cua#74 queue is also in flight. If it changes a number quoted in section 10, section 10 follows it.

## Moving rows (generated)

<!-- moving-rows:start -->
| Row | Disposition | What can still move it |
|---|---|---|
| R2-07e | KEEP | OPEN: scheduled wave 7 R2-07f, R2-07g. No wave-7 result is cited. |
| R2-07e-MODAL | REVISE | OPEN: scheduled wave 7 R2-07f, R2-07g. No wave-7 result is cited. Also: owner/planner ruling on the n7_presat substitution for the spec's rename fallback. |
| R2-09-T3 | BLOCKED | Owner ruling on WebKitGTK. |
| R2-10 | KEEP | Published branch carries an encoded private-name list; owner privacy ruling on the held replacement (PUB-02 B, still held after PUB-03). Numbers do not move. |
| R2-10R | KEEP | OPEN: scheduled wave 7 PUB-04. No wave-7 result is cited; the claims and numbers do not depend on it, only the cited branch and SHA may change. |
| R2-10-LIVE-RECERT | BLOCKED | Owner ruling on the provider budget. |
| R2-10-NATIVE-LIVE | BLOCKED | Owner ruling on native T / budget. |
| R2-10-LIVE-CR | BLOCKED | Owner ruling on the provider budget. |
| B-08 | KEEP | OPEN: scheduled wave 7 B-09 (fill share only; the per-process verdict is terminal). No wave-7 result is cited. |
| N-03 | KEEP | Published raw output carries session-bus paths; owner privacy ruling on the held PUB-03 candidate. Numbers do not move. |
| N-04 | KEEP | OPEN: scheduled wave 7 FRESH-07. No wave-7 result is cited. Also: published raw output carries session-bus paths; owner privacy ruling on the held PUB-03 candidate (numbers do not move). |
| FIX-02 | KEEP | OPEN: scheduled wave 7 FIX-04 (runner F3 rule against delivery=unknown refusals). No wave-7 result is cited. |
| FIX-03 | REVISE | OPEN: scheduled wave 7 FIX-04 (effect=unknown for delivery=unknown refusals). No wave-7 result is cited. |
| FIX-03-SIDE | KEEP | OPEN: scheduled wave 7 FIX-04 (native AT-SPI pid-wide fallbacks), FRESH-07 (X11 rows). No wave-7 result is cited. |
| OWN-09R | KEEP | Owner rulings on the bounded coordinator wait, R8 and the strict unit-row reading can turn this into REVISE before any proposal. |
| OWN-09-R8 | BLOCKED | Owner ruling on R8. |
| OWN-16W | KEEP | OPEN: scheduled wave 7 FRESH-07 (X11 string row). No wave-7 result is cited. Also: owner ruling on dd205d17b refusing JSON null. |
| OWN-20G | KEEP | Published raw output carries the local user name; owner privacy ruling on the held PUB-03 candidate. Numbers do not move. |
| OWN-20P | KEEP | OPEN: scheduled wave 7 FRESH-07. No wave-7 result is cited. |
| OWN-20Q | KEEP | OPEN: scheduled wave 7 FRESH-07. No wave-7 result is cited. |
| OWN-20Q-DLG | KEEP | OPEN: scheduled wave 7 FRESH-07. No wave-7 result is cited. |
| OWN-20Q-A2 | REVISE | OPEN: scheduled wave 7 FRESH-07. No wave-7 result is cited. Also: owner/design ruling on r3n (OWN-20Q-R3N). |
| OWN-20Q-R3N | BLOCKED | Owner/design ruling on r3n. |
| OWN-36 | REVISE | Owner ruling on I3s shared-window replacement. |
| OWN-75R | KEEP | Owner ruling on the unconditional (log-only) timing fields. |
| OWN-78-S1 | BLOCKED | Owner ruling on another provider or budget. |
| OWN-78-R1R4 | BLOCKED | Owner ruling on the provider budget. |
| OWN-78-A2A3 | BLOCKED | Owner ruling on the provider budget. |
| PUB-03 | KEEP | Owner privacy ruling (replace or keep the published heads). |
| DOC-10-74 | KEEP | A sibling wave-7 deliverable refreshes it; if it changes a number quoted in section 10, section 10 follows it. |
<!-- moving-rows:end -->

## Owner rulings (each can move the named rows)

| Ruling | Rows / sections | What will change |
|---|---|---|
| Browser feedback glide default | R2-01, R2-10, sections 1, 6 and 10 | Whether S ≈ 45 (glide off) or 1.01 (KEEP-only) is the product number |
| H_E endpoint re-proof bound | B-02, section 6 | Whether about 22 ms per task is deletable |
| Native cursor reveal | N-01R, N-04, section 6 | Whether native text S is 5.941 or 1.030 |
| H_T insert_text focus settle | B-01, section 6 | Whether about 100 ms per fill is deletable |
| HCL session shape | N-03, N-04, delta D15 | Whether lazy validators are a default |
| R2-08 API route | R2-08 | Whether an equivalent, authorized route may be used per task |
| Browser per-process cold excess (process reuse) | B-08, section 6 | Whether process or session reuse with the warm-up outside T is the product shape |
| I3s shared-window replacement | OWN-36, delta D5 | Whether a shared window's tokens retire on replacement |
| OWN-09R bounded wait, R8 and the strict unit-row reading | OWN-09R, OWN-09-R8, delta D7 | Whether OWN-09R stays KEEP before any proposal |
| a11y bus name-owner trigger (r3n) | OWN-20Q-A2, OWN-20Q-R3N, delta D9 | Whether the trigger is built or NoReply + Peer.Ping stays the claim |
| trycua/cua PR 4336 unconditional fields | OWN-75R, delta D12 | Accept, or gate behind an env var |
| dd205d17b refusing JSON null | OWN-16W, delta D8 | Third-party clients sending null |
| WebKitGTK | R2-09-T3 | Install it, use the flatpak runtime, or keep BLOCKED |
| R2-07e n7_presat substitution | R2-07e-MODAL | Whether the substituted forced fallback stands for the spec's rename fallback |
| Provider budget | R2-10-LIVE-RECERT, R2-10-LIVE-CR, R2-10-NATIVE-LIVE, OWN-78-R1R4, OWN-78-A2A3, OWN-78-S1 | Live rows that do not fit the remaining budget |
| Native T definition | R2-10-NATIVE-LIVE, section 1 | Whether native T may exclude provider decisions |
| Published-fork privacy replacements | R2-10, N-03, N-04, OWN-20G, PUB-03 (and R2-10R through PUB-04) | Only the cited branch and SHA; the claims and numbers do not move |

Provider budget at generation time: <!-- gen:budget -->583 of 600 reached used, 17 remain (679 attempts)<!-- /gen:budget -->.
