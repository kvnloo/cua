# Fresh-review checklist: trycua/cua issue 3963 rewrite draft

This list is for a reviewer who did not write the draft.

Run `verify_artifacts.py` first, under the loop's hostless wrapper, from a clean clone, once without and once with `--state` pointing at the loop STATE.json, with `CUA_PRIVACY_NAMES_FILE` set and `--all-commits`. Every check below is in addition to it: the script proves that cited text exists where its pointer says, not that it is the right text.

## A. Machine checks (expect 0 FAIL in both modes)

- [ ] **Regeneration (`--state`):** `generate.py --check` reproduces `dispositions.json`, the generated claims, the README table and head notes, the budget line, the wave-7 lane table and the moving-rows table from the given STATE.json byte for byte.
- [ ] **SHAs:** every row SHA, packet README and backticked SHA in the markdown resolves. In a clone without the cited ref, the verifier fetches it read-only by the ref recorded in `provenance.json` `sha_refs` (fork branches, the census ref, upstream main and PR heads). A ref that is not published (a held candidate) shows as `NEED`, never as a bare FAIL.
- [ ] **Census ref:** the census SHA is resolved, fetched from the fork ref `research/rfc3963-dependency-census-20260925`, or reported as `NEED` with the exact command.
- [ ] **Origin heads:** every row branch head on the fork equals the cited SHA (read-only `git ls-remote`). UNPUBLISHED rows are flagged; this draft expects OWN-75 (a hard-stop record) and PUB-03 (held candidate).
- [ ] **STATE diffs:** every difference from STATE.json carries a reason. Expected diffs: N-03, BUG-01, OWN-75. Re-read each reason and decide whether you agree. The head notes under the table (R2-10R a3 vs a2, B-01 via B-01R) are generated from STATE; check that you agree with each reason.
- [ ] **Number pointers:** no row template in `rows.spec.json` carries a bare number; every generated number is on the recorded line of its packet file (or at its JSON path), at the row's SHA, and appears in that row of the README table.
- [ ] **Curated claims:** each prose claim's needle is on its recorded packet line (and next to its anchor where one is given), and its text is in the README section it names.
- [ ] **No pre-emption:** no row is PENDING; every row that mentions a wave-7 lane says `OPEN: scheduled wave 7 <lane>`; every README line that names a wave-7 lane is marked OPEN or scheduled.
- [ ] **Freshness:** the README freshness table lists trycua/cua PR 4529 and PR 4531 with "disposition pending: FRESH-07 (wave 7)", and the upstream head in provenance.json is 41 commits past 0f1955d2f.
- [ ] **Autolinks:** no upstream autolink patterns and no at-mentions in any file of the draft.
- [ ] **Privacy:** the scan is clean on every file in the directory and on every commit of the branch, including any encoded names.

## B. Claims to spot-check against the packets (open the file at the cited SHA)

1. **North-star table (section 1).** Recompute nothing. Confirm that each S and CI is the packet's own number, and that the source/binary column matches the packet's provenance.
   - R2-10 `030f6bdbf`: live fill 45.11, toggle 5.95, modal 5.73; scripted 45.61 / 47.01 / 46.56.
   - R2-10R `d22eeb2ec`: scripted 45.65 / 46.82 / 44.86.
   - R2-07e `67b99ddc6`: warm toggle 29/29 with 0 decisions; no paired live S is claimed.
   - B-08 `49ae94590`: one-binary untested shares 0.4% / 0.4% / 16.9% (C arm, below-gate as IRREDUCIBLE).
   - N-04 `9d7d8d7a5`: 1.196 / 5.941, and S0 1.180 / 1.030.
2. **KEEP-only S 1.01** (R2-10). Confirm it is COMP_K on the scripted layer, and that the draft never presents ≈45 as a product number without the owner-decision qualifier.
3. **No cross-binary arithmetic.** Check that no sentence adds, subtracts or divides numbers from different lanes. Watch especially:
   - section 6, the H_E row: R2-10 and B-02 are quoted side by side, each with its own binary;
   - section 10 (R2-10, R2-07e, B-08 and N-04 each on their own line).
4. **E2 statements (section 1).**
   - Native 1.19% / 1.65% (N-04).
   - Browser scripted on B7 (B-08): toggle and modal met, fill not met; fill's remainder is the runner component, marked `OPEN: scheduled wave 7 B-09`.
   - Browser live: fill and warm toggle decisions deleted; modal without a terminal verdict.
5. **Owner-decision sizes (section 6).** Check these against the packets:
   - glide 3000.5 / 2406.2 ms (R2-10);
   - HCL 82.22 / 73.69 ms (N-04);
   - R2-08 174.4 ms;
   - B-08 10.58 [9.50, 11.41] / 3.05 [2.62, 5.38] / 4.56 [2.98, 5.92] ms.
6. **Wave-6 folds.** For each, compare the row with the packet and with STATE:
   - B-08 KEEP: per-process OWNER_DECISION, lineage terminal; B-06 no longer moving.
   - R2-07e: toggle KEEP (compiled replay in the composed toggle configuration), modal REVISE (forced fallback not verified).
   - OWN-78L: kvnloo/cua#78 REVISE → KEEP on candidate F `61eec0909`; n = 3 is stated as a gate, not a rate.
   - FIX-03: F4 REVISE (IRREDUCIBLE with an honest unknown); side-index fix `2237cf9c6` KEEP; the kvnloo/cua#36 candidate is F5, not F'.
   - OWN-20Q: R1m KEEP, DLG KEEP, A2 REVISE (r3n not built).
   - PUB-03 KEEP; DOC-3963 and DOC-10-74 are listed as process rows.
7. **Every KILL in section 7** cites the KILLing packet. None of them is described as "deferred".
8. **BLOCKED rows** each name one blocker class: hardware, owner decision or budget. None says "not attempted". Budget rows read the remaining budget from STATE.

## C. Invariant coverage (section 2)

For each invariant, confirm that at least one cited packet shows it holds with a discriminating control. Also confirm that no surviving delta in section 5 violates it.

- [ ] **No new service.** The deltas are refusals, bindings, bounds or measurement knobs inside an existing owner. There is no new tool, field or process. The r3n trigger, which would need a second persistent bus connection, is an owner decision and is not built.
- [ ] **Env-gated, default-off.** Knob names are `CUA_DRIVER_EXP_*`. The two exceptions (trycua/cua PR 4336 fields, Driver telemetry) are listed as owner decisions, not hidden.
- [ ] **Events are hints.** R2-02, R2-09 and OWN-20 are cited. No delta uses event absence as authority.
- [ ] **Passive state never mints authority.** FIX-02 F1/F2 and RECERT-FIX: fixed 0 vs unfixed 100 cross-session mutations; FIX-03-SIDE: the side index is window-scoped on F5.
- [ ] **Possibly landed effects stay unknown.** The F5 effect-mapping gap (refused although landed) is stated openly and is `OPEN: scheduled wave 7 FIX-04`, not presented as closed.
- [ ] **Durable identity only.** The D2 routine rebinds fresh refs; F2 is the generation binding. No delta persists a ref, token, capture or epoch.

## D. Owner mapping (section 3)

- [ ] **Item types.** Each upstream item is written as plain text with the right kind (issue or PR). Spot-check with a read-only `gh` call, for example:
  - trycua/cua PR 3873 is a merged PR;
  - trycua/cua issue 3796 is an issue;
  - trycua/cua PR 4529 and PR 4531 are merged PRs.
- [ ] **"None named" rows (D3, D6, D8, D9, D13)** do not invent an owner and are not framed as requests for a new RFC.
- [ ] **Fork owners** match the kvnloo/cua#73 and kvnloo/cua#74 tables.
- [ ] **Closed-issue fit.** Nothing contradicts the maintainer decision on trycua/cua issue 3963: one PR per mechanism, recipe-local and opt-in, deleted services stay deleted.

## E. Moving rows

- [ ] **PENDING.md coverage.** PENDING.md names every wave-7 lane in flight (B-09, R2-07f, R2-07g, FIX-04, FRESH-07, PUB-04) and every owner ruling, and lists no wave-6 lane as pending.
- [ ] **No pre-emption.** No terminal row depends on a wave-7 result; the OPEN rows quote only accepted packets.

## F. Publication hygiene

- [ ] **Text.** No absolute paths, host name, user name, tmp bus paths or secrets. No upstream autolink form (owner/repo plus a hash and number, a bare hash-number meaning an upstream item, or a link into the upstream repository), and no at-mention.
- [ ] **Commits.** The branch has only DOC-3963's commit and this lane's commits on top of `5de1a3799`, each with the required author and trailer.
- [ ] **Logs.** The verifier logs in `raw/` hold no absolute path and no planted private name (the negative-control output reports entry numbers, not names).
