# Diagnosis: the r2 draft against the wave-7 STATE

Inputs: the r2 draft at docs/rfc3963-rewrite-draft-r2-20261003 @ e83d9ebc6 (DOC-3963b), the loop STATE.json after the wave-7 synthesis (sha256 `971c4d00ca3641cecf9db3c997e5410a5e6182e1c5669b7a079f3114f00fd4dd`, the STATE this revision is generated from), and the r2 `verify_artifacts.py --state`, run under the hostless wrapper.

- From a clean export (`git archive` of e83d9ebc6, `--repo` pointing at the clone): **FAIL=20** (`r2-at-wave7-state-verify-export.log`). This is the count the planner reported.
- From the r2 worktree: FAIL=19 (`r2-at-wave7-state-verify-worktree.log`). Failure 20 below appears only in an export.
- The r2 `generate.py --check` from the same export reports 5 stale files (`r2-at-wave7-state-generate-check.log`).

Evidence class: SOURCE on every row.

| # | Check | Failure (r2 verifier text, shortened) | Cause | Fixed in r3 by | Class |
|---|---|---|---|---|---|
| 1 | claims | G-R2-10-LIVE-RECERT-budget.remaining: STATE 1, cited 17 | the draft was generated from the wave-6 STATE (583 reached / 17 remaining); wave 7 used 16 (R2-07g), so STATE now has 599 / 1 | regeneration from the wave-7 STATE; budget gate checks used + remaining = cap and the ledger sums (61 entries: 599 reached, 695 attempts) | SOURCE |
| 2 | claims | G-R2-10-LIVE-CR-budget.remaining: STATE 1, cited 17 | same | same | SOURCE |
| 3 | claims | G-OWN-78-R1R4-budget.remaining: STATE 1, cited 17 | same | same | SOURCE |
| 4 | claims | G-OWN-78-A2A3-budget.remaining: STATE 1, cited 17 | same | same | SOURCE |
| 5 | claims | S01 used reached: STATE 599, cited 583 | same | same | SOURCE |
| 6 | claims | S03 remaining: STATE 1, cited 17 | same | same | SOURCE |
| 7 | claims | S04 attempts: STATE 695, cited 679 | same | same | SOURCE |
| 8 | regen | dispositions.json differs from regeneration | the budget numbers in four blocked rows changed | regeneration; `REGEN-DIFF.md` lists the rows | SOURCE |
| 9 | regen | claims.json differs from regeneration | the generated budget claims changed | regeneration | SOURCE |
| 10 | regen | README.md differs from regeneration | the table cells and the budget line changed | regeneration | SOURCE |
| 11 | regen | PENDING.md differs from regeneration | the moving-rows table and the budget line changed | regeneration | SOURCE |
| 12 | state | STATE row B-09 has no draft row | wave-7 lane accepted after r2 was generated | new row B-09 (BLOCKED, shared infrastructure, not terminal); coverage gate in the generator | SOURCE |
| 13 | state | STATE row R2-07f has no draft row | same | new row R2-07f (BLOCKED, shared infrastructure, not terminal) | SOURCE |
| 14 | state | STATE row R2-07g has no draft row | same | new rows R2-07g (toggle REVISE, +2.2 ms bound; LN refused) and R2-07g-MODAL (REVISE; live decision component OWNER_DECISION, conditional on n7_presat) | SOURCE |
| 15 | state | STATE row FIX-04 has no draft row | same | new rows FIX-04 (A, B, D KEEP) and FIX-04-CT (CT KEEP, F6c pending an owner ruling) | SOURCE |
| 16 | state | STATE row FRESH-07 has no draft row | same | new row FRESH-07 (PARTIAL, three kvnloo/cua#20 RECERT_FAILs; timing rows BLOCKED on shared infrastructure) | SOURCE |
| 17 | state | STATE row DOC-3963b has no draft row | same | new row DOC-3963b (staged deliverable; final regeneration DEFERRED to wave 9) | SOURCE |
| 18 | state | STATE row DOC-10-74b has no draft row | same | new row DOC-10-74b (staged deliverable; refresh DEFERRED to wave 9) | SOURCE |
| 19 | state | STATE row PUB-04 has no draft row | same | new row PUB-04 (held candidate; not posted before the privacy ruling) | SOURCE |
| 20 | regen (export only) | provenance.json sha_refs differ | r2 `generate.py` resolves the draft's own history from `HEAD` of the repository it is given; in an export that is the clone's HEAD, not the draft branch | `--head <branch SHA>` on both `generate.py` and `verify_artifacts.py` | SOURCE |

Staleness that the r2 verifier does not count as FAIL, because it expected it:

| Item | r2 state | Fixed in r3 by | Class |
|---|---|---|---|
| 13 rows marked `OPEN` for wave 7 (R2-07e, R2-07e-MODAL, R2-10R, B-08, N-04, FIX-02, FIX-03, FIX-03-SIDE, OWN-16W, OWN-20P, OWN-20Q, OWN-20Q-DLG, OWN-20Q-A2) | hand-written in `rows.spec.json` and the README prose | every wave-7 lane is folded in. Pending marks are generated from `pending-plan.json` (wave-8 lanes), and a wave-text gate rejects hand-written schedule strings in templates | SOURCE |
| Upstream drift | README cited `9a2b1d99e` with "disposition pending: FRESH-07 (wave 7)" | the pin is the newest STATE pin (`upstream_main_w7` = `5845488f2`); live main `a9baa8d10` is read with `git ls-remote` at generation; the freshness statuses come from FRESH-07 in STATE | SOURCE |
| Dependency graph | open-lane nodes for wave-7 lanes | wave-8 lane nodes, plus edges for the kvnloo/cua#20 overlay fix (D9) and the native residue (D5) | SOURCE |
