# CUA #4930 exact-head requalification — 2026-10-12

Production owner: hippoley. Independent evidence contributor: ayo, with OpenAI Codex. Canonical record: [fork #126](https://github.com/kvnloo/cua/issues/126). [Bounded claim](https://github.com/kvnloo/cua/issues/126#issuecomment-6119955619) was recorded after refreshing origin comments, #126/#74, factory #14/AGENTS and known claims; no equivalent active qualification was found. No implementation scope was claimed.

Tested current head: `a612deae0d16da95d3bfcb8c45ea610fd9b0e3f5`.
Prior-head comparison product: `cc7326d6ffd71fcf9a157e4498924ab47431d467`.
Original PR base remains `7cc4bd0bfc3ce1a3246ae47fe02948dc9f64f010`; it was **not rerun in this dated receipt**.

The [original immutable ae8dd2ca receipt](https://github.com/kvnloo/cua/blob/ae8dd2cadfd3dc3bc47c1eab27315ff2a381c012/evidence/cua-4930-runner-contracts-20261012/README.md) remains unchanged. Its original own-revision counts were cc7326d6 36 PASS and PR base 14 PASS, plus 2 inherited-probe failures on each. Publication SHAs are distinct from tested product SHAs.

## Actual results

| This dated execution | Current a612deae | Prior cc7326d6 product |
| --- | --- | --- |
| Current owner's 49-test runner suite | 49 PASS, exit 0 | 36 PASS / 13 FAIL, exit 1, with current test-file overlay |
| Identical two inherited probes | 2 FAIL, exit 1 | 2 FAIL, exit 1 |

All 13 prior-head owner failures are the newly added argument-validation, discovery-failure, discovery-close and discovery-cleanup-failure cases. The expanded tests are copied onto the prior-head worktree without modifying production source. Those 13 cases demonstrate the owner's new tested behavior; their failed prior-head controls are different from cc7326d6's historical unexpanded 36-test suite.

The two remaining observations remain inherited, not introduced regressions and not RED-to-GREEN repair claims:

- `[1.0, 0.0, 0.0]` returns reward 1.0 and success, despite the documented component mean of 1/3. The probe verifies no error and one completed step before asserting the mean.
- A genuine Environment completes two steps in a controlled oracle solver, then raises. The runner reports zero steps. Both revisions preserve the original error, zero reward and failed outcome, and close the fake-backed session; these preconditions are asserted before the failing result-step assertion.

Malformed trailing-component finding remains explicitly withdrawn: hippoley repaired validation, and the owner's repaired cases pass. The current/prior runner diff affects only run_benchmark. Identical run_single_task AST hashes independently retain the inherited-path applicability distinction. No newly introduced cleanup or validation defect was established by this bounded execution; no additional competing repair was implemented.

## Environment, provenance and reproduction

Reused the existing official PyPI wheel environment: Python 3.12.14, pytest 9.1.1, pytest-asyncio 1.4.0, datasets 5.1.0, Pillow 12.3.0. No installs, synchronization or SDK builds. Genuine current cua-bench source imports via PYTHONPATH succeeded before the test run. Project dependency declarations are unchanged (Git blob `dfaf1eda0e3fe399b6aa3164a3b1d393fb12a563`). Full installed dependency versions and current/overlaid-baseline source SHA256/Git blob hashes are in `environment-source-hashes.json`.

`commands.txt` records exact invocations, isolated worktree creation, test overlay and exit results. Set HEAD_WORKTREE, BASELINE_WORKTREE, ENV_ROOT and RESULTS_ROOT to writable locations. The unchanged supplemental file is included at `libs/cua-bench/cua_bench/tests/test_independent_4930.py` in this evidence commit; copy it into both product worktrees. Use fresh basetemp locations. The log roots are replaced by these portable variables; volatile object addresses are redacted. Assertions, source excerpts, test IDs/counts and timing output are preserved in all four logs.

The entry point is component pytest from `libs/cua-bench`. The environment uses official prebuilt CUA dependency wheels, not the monorepo uv path-dependency/frozen CI graph. Source imports and passing tests do not certify installed snapshot distribution metadata or hosted CI. No virtual environments, caches, credentials, generated task state or machine-private paths are published.

## Scope and review limits

This is genuine runner/Environment execution using the existing fake sandbox SDK. The inherited oracle probe injects a controlled task solver callable. The owner's new discovery cases additionally use discovery-environment/fake runner seams. No real desktop, VM, Docker, native SDK build, deployment, full cleanup or universal argument-validation certification is claimed.

In particular, the owner's close-before-execution test checks an assertion inside fake_run but does not inspect the returned BenchmarkResult; run_benchmark gathers exceptions into failure results. Its final assertion proves a close call, and source inspection establishes current ordering, but a future after-execution-close mutation could evade this test. This is a coverage limit, not a reproduced current-head cleanup regression. No mutation result is claimed.

Independent xhigh critic scope and outcome are recorded in `critic-receipt.txt`. No upstream comments/PRs, competing production fix, default-branch push, force push, destructive cleanup or human signoff. hippoley retains production ownership and all repair credit; maintainer review and hosted approval remain separate gates.
