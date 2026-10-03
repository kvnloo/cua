## Round-2 wave 6: final whole-task accounting staged (DOC-10-74), 2026-10-03

The final kvnloo/cua#10 table is staged on the fork at [`docs/rfc/10-final-accounting/`](https://github.com/kvnloo/cua/blob/docs/accounting-10-queue-74-20261003/docs/rfc/10-final-accounting/README.md) (branch `docs/accounting-10-queue-74-20261003` @ `a3e3cb86e`). Nothing is posted upstream. The companion kvnloo/cua#74 queue is in [`docs/rfc/74-posting-queue/`](https://github.com/kvnloo/cua/blob/docs/accounting-10-queue-74-20261003/docs/rfc/74-posting-queue/README.md).

Rules:
- One row per source (binary). No number is added or ratioed across rows.
- Every number is a pointer into an accepted packet at an exact commit, and `verify_artifacts.py` re-reads it with `git show`.
- Work deleted is reported separately from wall-clock saved.
- T is the median T_oracle.

### Rows with a BASE arm (S = median BASE / median best)

| Task | Row (source) | BASE T ms | Best T ms | S [CI] | KEEP-only S | Floor | Untested A / B |
|---|---|---|---|---|---|---|---|
| browser fill | R2-10 (R) live | 3647.2 | 80.9 | 45.11 [42.43, 51.90] | NOT_MEASURED | 1.95 | 13.97% / 36.47% |
| browser fill | R2-10 (R) scripted | 3187.6 | 69.9 | 45.61 [44.35, 46.98] | 1.01 | 1.84 | 15.17% / 39.12% |
| browser fill | R2-10R (R') scripted | 3189.9 | 69.9 | 45.65 [44.39, 48.36] | 1.01 | 1.90 | 15.18% / 36.70% |
| browser toggle | R2-10 (R) live | 2928.3 | 491.8 | 5.95 [5.70, 6.25] | NOT_MEASURED | 22.51 | 90.37% / 92.73% |
| browser toggle | R2-10 (R) scripted | 2507.4 | 53.3 | 47.01 [45.36, 48.54] | 1.01 | 2.59 | 16.44% / 36.04% |
| browser toggle | R2-10R (R') scripted | 2503.4 | 53.5 | 46.82 [45.21, 48.69] | 1.01 | 2.72 | 16.65% / 34.93% |
| browser modal | R2-10 (R) live | 2930.2 | 511.0 | 5.73 [5.41, 6.00] | NOT_MEASURED | 23.37 | 90.89% / 90.89% |
| browser modal | R2-10 (R) scripted | 2483.6 | 53.3 | 46.56 [45.56, 47.69] | 1.01 | 2.59 | 16.43% / 16.43% |
| browser modal | R2-10R (R') scripted | 2491.4 | 55.5 | 44.86 [43.56, 46.81] | 1.01 | 2.64 | 16.21% / 16.21% |
| native checkbox | R2-10 (R) scripted | 334.9 | 283.0 | 1.18 [1.18, 1.18] | 1.18 | 1.04 | 4.14% / n/a |
| native checkbox | R2-10R (R') scripted | 334.3 | 283.0 | 1.18 [1.18, 1.18] | 1.18 | 1.04 | 3.94% / n/a |
| native checkbox | N-04 (R'n) scripted | 334.9 | 280.0 | 1.196 [1.189, 1.198] | 1.180 | 1.036 | 1.19% / 2.23% |
| native text | R2-10 (R) scripted | 1760.9 | 300.9 | 5.85 [5.81, 5.88] | 1.03 | 1.10 | 7.53% / n/a |
| native text | R2-10R (R') scripted | 1761.3 | 298.9 | 5.89 [5.87, 5.90] | 1.03 | 1.10 | 6.89% / n/a |
| native text | N-04 (R'n) scripted | 1764.1 | 296.9 | 5.941 [5.938, 5.957] | 1.030 | 1.089 | 1.65% / 2.62% |

The rows without a BASE arm (B-06, B-07, B-05, R2-07d, N-03) carry component verdicts, cold-excess sizes and untested shares. They are listed in the table.

### Owner-decision dependency

Most of the browser speedup is owner decisions: feedback glide, the H_T settle and the H_E endpoint re-proof.

| Path | Source | KEEP-only S |
|---|---|---|
| Browser fill | R | 1.01 (amortized ratio of means 0.98) |
| Browser toggle / modal | R | 1.01 / 1.01 |
| Native checkbox / text | R'n | 1.180 / 1.030 |

### Live-layer gaps

- **R' live layer (R2-10 recertification with TypeSafe on 0f1955d2f): BLOCKED.** paid budget: the loop's remaining TypeSafe budget does not cover a live recertification (kvnloo/cua#74 OR-11; figures in the queue's state extract)
- **live toggle/modal provider decisions (the largest live COMP component in R2-10): UNTESTED.** BLOCKED by budget; modal also needs a passing non-regression gate (R2-07d modal FAIL)
- **R2-07e (new pre-registered modal gate + Phase L): PENDING.** wave-6 lane running; refresh in wave 7
- **native live arms (native T including provider decisions): BLOCKED.** owner decision (may native T exclude provider decisions?) or paid budget

### Pending rows (wave 7 refresh)

- **B-08:** per-process cold first snapshot on B7 (exp/b-08-per-process-cold-b7-20261003); decides the browser cold-excess verdict on the B7 source
- **R2-07e:** new pre-registered modal gate + Phase L (exp/r2-07e-modal-gate-phase-l-20261003)
- **PUB-03:** privacy rewrites of published N-03 / N-04 / OWN-20G heads (r1c branches); numbers unchanged by design

PreAct and SkillDroid are listed as references only, with every difference in benchmark and scope.

0 provider requests. Verify with `python3 docs/rfc/10-final-accounting/verify_artifacts.py` under the hostless wrapper.
