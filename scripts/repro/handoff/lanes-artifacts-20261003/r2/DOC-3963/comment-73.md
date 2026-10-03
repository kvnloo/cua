## trycua/cua issue 3963 rewrite draft staged on the fork (wave 6, 2026-10-03)

The E5 rewrite draft is staged on the fork. It has not been posted anywhere else.

- **Branch:** [`docs/rfc3963-rewrite-draft-20261003`](https://github.com/kvnloo/cua/tree/docs/rfc3963-rewrite-draft-20261003/docs/rfc/3963-rewrite) @ `088fe745a`
- **Base:** upstream main `5de1a3799`
- **Location:** `docs/rfc/3963-rewrite/`

**What it is.** A replacement for the current-state note on the closed trycua/cua issue 3963. It is written as deltas against current CUA, not as a new target architecture. It follows the maintainer decision on that issue: one owner PR per mechanism, recipe-local and opt-in, and the deleted services stay deleted.

**What it contains:**
- north-star T and the measured composition results;
- the six invariants;
- an existing-owner map for 15 surviving deltas;
- a dispositions table with 70 rows, as KEEP / REVISE / KILL / BLOCKED, plus PENDING for wave 6;
- the remaining deltas with their gates;
- the owner-decision list with measured sizes;
- non-goals, including every KILLed mechanism;
- the kvnloo/cua#74 READY NOW gates;
- a dependency graph;
- an accounting summary that points to kvnloo/cua#10.

**Moving rows.** PENDING.md lists every row a later wave can still change:
- the wave-6 lanes B-08, R2-07e, OWN-78L, OWN-20Q, FIX-03 and PUB-03;
- each owner ruling.

No other row should change.

**Machine checks.** `verify_artifacts.py` (stdlib only, run under the loop's hostless wrapper) reports 0 FAIL. It checks that:
- every cited SHA resolves, and every cited branch head equals origin;
- every disposition matches the loop state, with 3 differences listed with reasons;
- all 65 cited numbers are found verbatim in their packet at their SHA;
- there are no upstream autolink forms;
- the privacy scan of every commit is clean.

The one flag is OWN-75, a hard-stop record that was never pushed and is listed as SUPERSEDED by OWN-75R.

**Headline, unchanged from wave 5.** Most of the measured whole-task S comes from owner decisions:
- browser feedback glide: S about 45 with it off, 1.01 KEEP-only (R2-10);
- native cursor reveal: text S 5.941, 1.030 KEEP-only (N-04).

No delta is READY NOW for upstream. Each one waits on an owner decision, a staged review, a rebase check or a PENDING lane.

**Next.** A fresh reviewer works through REVIEW-CHECKLIST.md. After that the branch is published.

0 provider requests. Nothing was posted upstream.
