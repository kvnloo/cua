# PENDING: rows of the trycua/cua issue 3963 rewrite draft that can still move

This is section 11 of the draft. Every row of `dispositions.json` whose `pending` field is empty is terminal for this draft.

**No row has the disposition PENDING.** The eight wave-7 lanes (B-09, R2-07f, R2-07g, FIX-04, FRESH-07, PUB-04, DOC-3963b, DOC-10-74b) are accepted and folded into the rows; B-09 and R2-07f as BLOCKED (shared infrastructure, not terminal) and FRESH-07 as PARTIAL.

The marks in the Pending cells are generated:
- "PENDING: wave-8 lane <id>" comes from `pending-plan.json`. It names a lane in flight that touches the row; the row cites no result of that lane.
- "DEFERRED: wave-9 ..." comes from the same file and names a planned later step.

After the wave-8 results, regenerate with the planner's plan for the next wave:

    python3 docs/rfc/3963-rewrite/generate.py --state <STATE.json> --pending-plan <plan> --upstream-live <sha>

If an accepted packet moves a row, update, together:
- that row's entry in `rows.spec.json` (claim template and number pointers), or add a row (the coverage gate fails until every new STATE key has one);
- the README section that quotes it;
- the curated entries of `claims.json` for that prose.

`REGEN-DIFF.md` then lists every row that changed. Do not touch any other row.

## Wave-8 lanes in flight (PENDING; no result cited)

Each lane below is planned but not accepted. The scope column is planner input (`pending-plan.json`), not a finding.
<!-- gen:wave-lanes -->
| Lane | Scope (planner input, pending-plan.json) | Rows marked PENDING |
|---|---|---|
| B-09R | resume of B-09's pre-registered fill verify-poll run on binary B7 in an EXCLUSIVE quiet-lane window (PREREG unchanged) | B-08, B-09 |
| R2-07fR | resume of R2-07f's committed plan: one-binary scripted toggle/modal S and decomposition on binary B7 | R2-07g, R2-07f |
| FIX-20O | kvnloo/cua#20 overlay fork fix: keep the Driver's own overlay window out of the focus guard's popup list, then re-run OWN-20P R1, OWN-20Q R1m and DLG on current upstream main | OWN-20P, OWN-20Q, OWN-20Q-DLG, FRESH-07 |
| FRESH-07R | FRESH-07 packet repair (raw-log redaction) and timing recertification on current upstream main: R2-10R scripted and native, N-04, N-03 | R2-10R, N-03, N-04, FRESH-07 |
| FIX-05 | kvnloo/cua#36 native index residue: replay F6 onto current upstream main and close the remaining pid-wide index fallbacks (perform_action, scroll_element, set_value) | FIX-03-SIDE, FIX-04 |
| INFRA-08 | quiet-lane lock hygiene: close-on-exec lock fd, waiter reaping and a starvation alarm, so the BLOCKED timing lanes get EXCLUSIVE windows | none: shared infrastructure for the B-09R, R2-07fR and FRESH-07R resumes; it moves no row by itself |
| DOC-3963c | this draft: generator gates (coverage, budget, pin, plan) and the wave-7 refresh; staged only | none: this revision; the final regeneration is deferred below |
<!-- /gen:wave-lanes -->
## Deferred (generated)
<!-- gen:deferred -->
| Item | Wave | Rows marked DEFERRED |
|---|---|---|
| final regeneration of this draft from the wave-8 STATE, then a fresh review | wave-9 | DOC-3963b |
| refresh of the kvnloo/cua#10 accounting and the kvnloo/cua#74 queue from the wave-8 STATE | wave-9 | DOC-10-74b |
<!-- /gen:deferred -->
## Moving rows (generated)

<!-- moving-rows:start -->
| Row | Disposition | What can still move it |
|---|---|---|
| R2-07e-MODAL | REVISE | Owner ruling on the n7_presat substitution for the spec's rename fallback (see R2-07g-MODAL). |
| R2-07g | REVISE | PENDING: wave-8 lane R2-07fR (toggle non-regression re-confirmation on B7). No wave-8 result is cited. Also: owner ruling on the toggle bound: accept non-inferiority at the measured upper bound, or require a larger-n quiet re-run against the gate. |
| R2-07g-MODAL | REVISE | Owner rulings on the n7_presat substitution and on the live modal admission policy. |
| R2-09-T3 | BLOCKED | Owner ruling on WebKitGTK. |
| R2-10 | KEEP | Published branch carries an encoded private-name list; owner privacy ruling on the held replacement (PUB-02 B, still held after PUB-03). Numbers do not move. |
| R2-10R | KEEP | PENDING: wave-8 lane FRESH-07R (scripted and native rows). No wave-8 result is cited. Also: owner privacy ruling on the held PUB-04 candidate: only the cited branch and SHA may change, not the claims or numbers. |
| R2-10-LIVE-RECERT | BLOCKED | Owner ruling on the provider budget. |
| R2-10-NATIVE-LIVE | BLOCKED | Owner ruling on native T / budget. |
| R2-10-LIVE-CR | BLOCKED | Owner ruling on the provider budget. |
| B-08 | KEEP | PENDING: wave-8 lane B-09R (fill untested share only; the per-process verdict is terminal). No wave-8 result is cited. |
| B-09 | BLOCKED | PENDING: wave-8 lane B-09R (measured run). No wave-8 result is cited. |
| R2-07f | BLOCKED | PENDING: wave-8 lane R2-07fR. No wave-8 result is cited. |
| N-03 | KEEP | PENDING: wave-8 lane FRESH-07R. No wave-8 result is cited. Also: published raw output carries session-bus paths; owner privacy ruling on the held PUB-03 candidate. Numbers do not move. |
| N-04 | KEEP | PENDING: wave-8 lane FRESH-07R. No wave-8 result is cited. Also: published raw output carries session-bus paths; owner privacy ruling on the held PUB-03 candidate (numbers do not move). |
| FIX-03-SIDE | KEEP | PENDING: wave-8 lane FIX-05 (native AT-SPI index fallbacks). No wave-8 result is cited. |
| FIX-04 | KEEP | PENDING: wave-8 lane FIX-05 (native residue). No wave-8 result is cited. |
| FIX-04-CT | KEEP | Owner/reviewer ruling on F6c as a change of default native behaviour. |
| OWN-09R | KEEP | Owner rulings on the bounded coordinator wait, R8 and the strict unit-row reading can turn this into REVISE before any proposal. |
| OWN-09-R8 | BLOCKED | Owner ruling on R8. |
| OWN-16W | KEEP | Owner ruling on dd205d17b refusing JSON null. |
| OWN-20G | KEEP | Published raw output carries the local user name; owner privacy ruling on the held PUB-03 candidate. Numbers do not move. |
| OWN-20P | KEEP | PENDING: wave-8 lane FIX-20O (R1 on current main). No wave-8 result is cited. |
| OWN-20Q | KEEP | PENDING: wave-8 lane FIX-20O (R1m on current main). No wave-8 result is cited. |
| OWN-20Q-DLG | KEEP | PENDING: wave-8 lane FIX-20O (DLG on current main). No wave-8 result is cited. |
| OWN-20Q-A2 | REVISE | Owner/design ruling on r3n (OWN-20Q-R3N). |
| OWN-20Q-R3N | BLOCKED | Owner/design ruling on r3n. |
| OWN-36 | REVISE | Owner ruling on I3s shared-window replacement. |
| OWN-75 | SUPERSEDED | Do not post this row before the owner privacy ruling. |
| OWN-75R | KEEP | Owner ruling on the unconditional (log-only) timing fields. |
| OWN-78-S1 | BLOCKED | Owner ruling on another provider or budget. |
| OWN-78-R1R4 | BLOCKED | Owner ruling on the provider budget. |
| OWN-78-A2A3 | BLOCKED | Owner ruling on the provider budget. |
| PUB-03 | KEEP | Owner privacy ruling (replace or keep the published heads). Do not post this row before that ruling. |
| FRESH-07 | PARTIAL | PENDING: wave-8 lanes FIX-20O (the kvnloo/cua#20 RECERT_FAIL rows), FRESH-07R (packet repair and timing rows). No wave-8 result is cited. Also: the branch is not on the fork: its gzipped raw logs carry the local user name and need redaction before a push. |
| PUB-04 | KEEP | Owner privacy ruling. Do not post this row before that ruling. |
| DOC-3963b | KEEP | DEFERRED: wave-9 final regeneration of this draft from the wave-8 STATE, then a fresh review. |
| DOC-10-74b | KEEP | DEFERRED: wave-9 refresh of the kvnloo/cua#10 accounting and the kvnloo/cua#74 queue from the wave-8 STATE. |
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
| n7_presat substitution and live modal admission | R2-07e-MODAL, R2-07g-MODAL, delta D2 | Whether the substituted forced fallback stands for the spec's rename fallback, and whether a compiled modal routine whose live fallback fails is admitted (the live modal decision component is then OWNER_DECISION) |
| Toggle compiled-replay non-regression bound | R2-07g, delta D2 | Whether non-inferiority at +2.2 ms replaces the +2.0 ms gate, or a larger-n quiet re-run is required |
| FIX-04 F6c default native behaviour | FIX-04-CT, delta D5 | Whether refusing a token whose window has closed becomes the default |
| FIX-03 F4 honest unknown | FIX-03, delta D6 | Whether IRREDUCIBLE with an honest unknown is the accepted bound |
| Provider budget | R2-10-LIVE-RECERT, R2-10-LIVE-CR, R2-10-NATIVE-LIVE, OWN-78-R1R4, OWN-78-A2A3, OWN-78-S1 | Live rows that do not fit the remaining budget |
| Native T definition | R2-10-NATIVE-LIVE, section 1 | Whether native T may exclude provider decisions |
| Published-fork privacy replacements | R2-10, R2-10R, N-03, N-04, OWN-20G, PUB-03, PUB-04, OWN-75 | Only the cited branch and SHA; the claims and numbers do not move. The PUB-03, PUB-04 and OWN-75 rows are not posted before this ruling |

Provider budget at generation time: <!-- gen:budget -->599 of 600 reached used, 1 remain (695 attempts)<!-- /gen:budget -->.
