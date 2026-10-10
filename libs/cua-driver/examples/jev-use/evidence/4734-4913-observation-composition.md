# Fork-only observation composition gate

This downstream evidence is stacked on kvnloo/cua PR #117, exact parent
`e8fed42004c96490bd443a44a850bec255f3580f`, whose base is upstream #4734
`32ca35a6c03a646d712390b39a9a67fab1831b98`.

Credit: f-trycua implemented upstream #4913's complete observation request and
pre-0.35 compatibility fallback. Andrew9603 reported #4374; IRONICBo identified
the application-owned progress evidence boundary. Their existing history and
production changes are retained; this delta adds tests and this evidence only.

## Boundary and frozen input

The mirrored Python/TypeScript regression calls the actual native `observe`
function and feeds its result to eligible native control construction. Both
synthetic Driver implementations return the same fixture, except the simulated
0.35 lean default omits `elements` and `elements_complete` unless requested
with `full_output: true`. The Increment candidate must remain available.

Input: `fixtures/native/appkit-window-state-initial-v1.json`.
SHA-256: `f252866be077f1694386503723619a1f626287dff67af7c8652eda2b0edb2967`.
This is a frozen synthetic accessibility observation, not a running app oracle.

## Local checks (2026-10-10 UTC)

From `libs/cua-driver/examples/jev-use`:

- `uv sync --frozen`: installed the locked official dependencies (35 packages).
- `uv run --frozen python -m unittest python.tests.test_run_native_observe -v`:
  5 passed, covering full output, lean-default candidate preservation, legacy
  unknown-argument fallback, permission-denial/no-retry, and retained arguments.
- `uv run --frozen python -m unittest discover -s python/tests -v`:
  243 tests, success; one skipped because optional `cua-s1` is not installed.
- `npm ci --ignore-scripts`: installed 103 locked packages without install scripts.
- `npm test`: 118 passed, no failures or skips.
- `npm run typecheck`: passed.

Default user-home caches were read-only; writable isolated temporary caches
were used, with no dependency pin or global configuration changes.

Existing Python and mirrored TypeScript no-progress unit tests cover stale and
refused recovery followed by dispatch remaining bounded, plus candidate-change
reset. These are guard tests, not real native runner fault injection.

## Limits

No live desktop E2E claim is made. The earlier environment preflight found
AF_UNIX daemon binding refused (EPERM), unavailable D-Bus launcher, and no GUI.
This gate did not rebuild Driver or bypass those restrictions. `verify_native.py`
GTK3 control tasks do not certify the complete stale/refusal fault matrix.
Cross-platform native behavior still needs the supported desktop runners.

At refresh, PR #117 remained draft/open at the exact parent above with no
comments, workflow runs, or commit statuses. Local tests do not replace CI.
When #4734 rebases on main, retain the merged #4913 production behavior rather
than cherry-picking it a second time; carry only appropriate regression tests.

## RED to GREEN and final focused replay

The exact #4734 native observation function was temporarily substituted in
this isolated worktree; the fixture and new assertions were unchanged. Python's
new candidate regression failed with an empty control set; the TypeScript
regression failed with Increment missing. Both exited 1. Restoring the exact
PR #117 production files made both assertions pass. TypeScript's baseline
needed only an `observe` export to expose the same test seam; its implementation
was otherwise unchanged.

Final focused replay: Python observation plus guard tests 14 passed;
TypeScript observation plus guard tests 13 passed. Production files are
byte-identical to `e8fed420`; no production mutation is retained.

Independent source review recommends promotion only of this unit-interface
evidence and holds desktop/E2E certification. It also identified an inherited
landing-readiness issue: the #117 adaptation commit credits f-trycua in prose
but lacks the contributor trailer required for material adaptations by
CONTRIBUTING.md. This downstream test-only branch does not rewrite its owner
commit; attribution must be resolved by the owner before upstream landing.
