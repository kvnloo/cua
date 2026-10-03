# Fresh-review checklist: trycua/cua issue 3963 rewrite draft

This list is for a reviewer who did not write the draft.

Run `verify_artifacts.py` first, under the loop's hostless wrapper, with `--state` pointing at the loop STATE.json and `CUA_PRIVACY_NAMES_FILE` set. Every check below is in addition to it: the script proves that cited text exists, not that it is the right text.

## A. Machine checks (expect 0 FAIL)

- [ ] **SHAs:** every row SHA and every backticked SHA in the markdown resolves in the main clone.
- [ ] **Origin heads:** every row branch head on origin equals the cited SHA (read-only `git ls-remote`). UNPUBLISHED rows are flagged; this draft expects only OWN-75 (a hard-stop record).
- [ ] **STATE diffs:** every difference from STATE.json carries a reason. Expected diffs: N-03, BUG-01, OWN-75. Re-read each reason and decide whether you agree.
- [ ] **Claims:** every claim in `claims.json` is found verbatim in its packet at its SHA, and its text is in README.md.
- [ ] **Autolinks:** no upstream autolink patterns and no at-mentions.
- [ ] **Privacy:** the scan is clean on every commit of the branch, including any encoded names.

## B. Claims to spot-check against the packets (open the README at the cited SHA)

1. **North-star table (section 1).** Recompute nothing. Confirm that each S and CI is the packet's own number, and that the source/binary column matches the packet's provenance.
   - R2-10 `030f6bdbf`: live fill 45.11, toggle 5.95, modal 5.73; scripted 45.61 / 47.01 / 46.56.
   - R2-10R `d22eeb2ec`: scripted 45.65 / 46.82 / 44.86.
   - N-04 `9d7d8d7a5`: 1.196 / 5.941, and S0 1.180 / 1.030.
2. **KEEP-only S 1.01** (R2-10). Confirm it is COMP_K on the scripted layer, and that the draft never presents ≈45 as a product number without the owner-decision qualifier.
3. **No cross-binary arithmetic.** Check that no sentence adds, subtracts or divides numbers from different lanes. Watch especially:
   - section 6, the H_E row: R2-10 and B-02 are quoted side by side, each with its own binary;
   - section 10.
4. **E2 statements (section 1).**
   - Native 1.19% / 1.65% (N-04).
   - Browser 1.6 / 0.6 / 0.6% (B-07) versus the lower bounds 36.70 / 34.93% (B-06 primary). Confirm the draft says which one holds under which reading.
5. **Owner-decision sizes (section 6).** Check these four against the packets:
   - glide 3000.5 / 2406.2 ms (R2-10);
   - HCL 82.22 / 73.69 ms (N-04);
   - R2-08 174.4 ms;
   - B-06 10.0 [8.0, 12.0] / 4.0 [3.9, 6.0].
6. **Every KILL in section 7** cites the KILLing packet. None of them is described as "deferred".
7. **BLOCKED rows** each name one blocker class: hardware, owner decision or budget. None says "not attempted".
8. **PENDING rows** cite no evidence (sha and packet are null).

## C. Invariant coverage (section 2)

For each invariant, confirm that at least one cited packet shows it holds with a discriminating control. Also confirm that no surviving delta in section 5 violates it.

- [ ] **No new service.** The deltas are refusals, bindings, bounds or measurement knobs inside an existing owner. There is no new tool, field or process.
- [ ] **Env-gated, default-off.** Knob names are `CUA_DRIVER_EXP_*`. The two exceptions (trycua/cua PR 4336 fields, Driver telemetry) are listed as owner decisions, not hidden.
- [ ] **Events are hints.** R2-02, R2-09 and OWN-20 are cited. No delta uses event absence as authority.
- [ ] **Passive state never mints authority.** FIX-02 F1/F2 and RECERT-FIX: fixed 0 vs unfixed 100 cross-session mutations.
- [ ] **Possibly landed means unknown.** R2-05, OWN-105, FIX-01 Part B, FIX-02 F3 and R2-07c G5. D4 states the gap for native refusal codes.
- [ ] **Durable identity only.** The D2 routine rebinds fresh refs; F2 is the generation binding. No delta persists a ref, token, capture or epoch.

## D. Owner mapping (section 3)

- [ ] **Item types.** Each upstream item is written as plain text with the right kind (issue or PR). Spot-check with a read-only `gh` call, for example:
  - trycua/cua PR 3873 is a merged PR;
  - trycua/cua issue 3796 is an issue.
- [ ] **"None named" rows (D3, D6, D8, D9, D13)** do not invent an owner and are not framed as requests for a new RFC.
- [ ] **Fork owners** match the kvnloo/cua#73 and kvnloo/cua#74 tables.
- [ ] **Closed-issue fit.** Nothing contradicts the maintainer decision on trycua/cua issue 3963: one PR per mechanism, recipe-local and opt-in, deleted services stay deleted.

## E. Moving rows

- [ ] **PENDING.md coverage.** PENDING.md names every wave-6 lane (B-08, R2-07e, OWN-78L, OWN-20Q, FIX-03, PUB-03) and every owner ruling.
- [ ] **No pre-emption.** No terminal row depends on a PENDING result.

## F. Publication hygiene

- [ ] **Text.** No absolute paths, host name, user name or secrets. No upstream autolink form (owner/repo plus a hash and number, a bare hash-number meaning an upstream item, or a link into the upstream repository), and no at-mention.
- [ ] **Commits.** The branch has only this lane's commits on top of `5de1a3799`, each with the required author and trailer.
