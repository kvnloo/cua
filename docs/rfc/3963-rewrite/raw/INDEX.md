# raw/: logs of the r3 draft (DOC-3963c)

Every run is under the loop's hostless wrapper. Every log is masked: `<tmp>` is the lane's temp directory, `<clone>` the clone that holds the objects and `<export>` the export directory. Each log ends with the exit code. Evidence class: SOURCE.

## Diagnosis of the r2 draft against the wave-7 STATE (step 1)

| File | What |
|---|---|
| `DIAGNOSIS.md` | the 20 FAILs of the r2 verifier against the wave-7 STATE: cause and r3 fix for each |
| `r2-at-wave7-state-verify-export.log` | r2 `verify_artifacts.py --state` from a clean export of e83d9ebc6: FAIL=20 |
| `r2-at-wave7-state-verify-worktree.log` | the same from the r2 worktree: FAIL=19 (failure 20 appears only in an export) |
| `r2-at-wave7-state-generate-check.log` | r2 `generate.py --check` from the export: 5 stale files |

## r3 from a clean export (`git archive` of the content commit c56bfa497)

| File | Expected | Result |
|---|---|---|
| `r3-export-generate-check.log` | up to date | up to date, exit 0 |
| `r3-export-verify-default.log` | FAIL=0 | FAIL=0, FLAG=2 (FRESH-07 branch not on the fork; upstream main moved from a9baa8d10 to fe6d89d80 after generation, one commit, no `libs/cua-driver` file), exit 0 |
| `r3-export-verify-state.log` | FAIL=0 | FAIL=0, DIFF=3 (N-03, BUG-01, OWN-75, each with its reason), FLAG=2, exit 0 |

## Negative controls (each on a temp copy; the export is restored after each)

| Control | File(s) | Expected | Result |
|---|---|---|---|
| (a) delete one STATE disposition key (PUB-04) | `r3-neg-a1-coverage-deleted-key-generate.log`, `r3-neg-a1-coverage-deleted-key-verify.log` | generator fails the coverage gate; verifier FAILs coverage | generator exit 2 (coverage); verifier FAIL=5 incl. coverage, exit 1 |
| (a') add a STATE disposition key with no row (NEW-99) | `r3-neg-a2-coverage-new-key-generate.log` | coverage gate fails | exit 2: "maps to 0 primary rows" |
| (b) shift the budget by one (cap still adds up, the ledger does not) | `r3-neg-b1-budget-ledger-generate.log`, `r3-neg-b1-budget-ledger-verify.log` | budget gate fails; verifier flags the budget | generator exit 2 (ledger); verifier FAIL=10 incl. budget, exit 1 |
| (b') remaining no longer adds up to the cap | `r3-neg-b2-budget-cap-verify.log` | verifier flags the budget | FAIL=9 incl. budget "used + remaining != cap", exit 1 |
| (c) plant an absolute local path in the README | `r3-neg-c-privacy-planted-path-verify.log`, `r3-neg-c-privacy-restored-verify.log` | privacy FAIL; PASS after restore | FAIL=1 (privacy, offset only, the path is not echoed), exit 1; restored FAIL=0, exit 0 |
| (d) plant a hand-written wave string in a row template | `r3-neg-d-wave-text-generate.log`, `r3-neg-d-wave-text-restored-generate.log` | wave-text gate fails; up to date after restore | exit 2; restored exit 0 |
| (e) a newer upstream_main pin appears in STATE | `r3-neg-e-pin-newer-state-pin-verify.log` | pin FAIL | FAIL=3 incl. pin, exit 1 |
