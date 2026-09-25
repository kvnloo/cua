# Whole-task timing: fork-only experiment

Refs trycua/cua#4052 and #3963. This is an unselected measurement experiment,
not an accepted public contract or a competing upstream implementation. Both
tracked runners and both active upstream branches remain unchanged.

## Reproduce

From this directory, with Python and the repository's TypeScript dependency
available:

```sh
python instrument.py
python -m unittest -v
node instrument_ts.cjs
node test_task_timing_ts.cjs
```

For a globally installed TypeScript compiler, set `NODE_PATH=$(npm root -g)`
for the two Node commands. No provider key, network, desktop, or SDK installation
is needed for these controlled tests. Node 22.16.0 and TypeScript 5.8.3 were used
locally; the generated timer also passes strict typechecking with Node types.

Each generator refuses drift from the exact #4052 runner. Python Git blob:
`003bdf23d41e7fa71a74583bb760d576503e908f`; TypeScript Git blob:
`dbb26b67143b425b21d26ebb257e1e76f7cc25c3`. The common source candidate is
`5d3a55419194172b31f92cf2aa36b0b603ecac2a`.

Generated baseline and instrumented copies are ignored local files. Python
also writes `runner-timing.patch`; TypeScript's printed copy is directly
comparable to `baseline-ts.ts`. The original runners are never edited.

## Two facts, not one success flag

Schema version 2 retains the cleanup-inclusive `task_root` and adds:

- `terminal_observation`: the first existing fixture classification that is
  `verified` or `refuted`, with a same-clock `at_ms` and explicit source.
- `post_terminal_observation_ms`: elapsed time after that classification until
  root end, or null when no terminal fixture observation was obtained.

These are passive marks at the three existing classification sites. They add
no fixture read, model request, action, retry, or completion policy. An
`unknown`, abstention, dry run, or ordinary runner return does not invent a
verified observation. Refutation is terminal but is not success.

A successful fixture check followed by a cleanup exception now retains BOTH
facts: `terminal_observation.verdict: verified`, and the original unknown
runner outcome plus cleanup error. It does not swallow or relabel that error.

The mark records when the existing fixture result was classified, not the
exact instant the application changed or presented a frame. The tail includes
remaining logging, bookkeeping and cleanup; it is not labeled pure cleanup.
No claims are made about independent native fixture validity by these tests.

## Timing scope and accounting

The root covers run entry through existing context/client cleanup and closes
before extra timing records are flushed. Imports, CLI parsing, process exit,
and the extra flush are outside it. Overhead measurements therefore need an
EXTERNAL interval around the complete runner call, including the flush.

`setup_ms` is a boundary, not another duration to add to child spans. Use the
union of intervals for coverage. Keep residual time visible. Clock identifiers
are task-local; matching schema does not make timestamps from different
processes or languages subtractable.

At most 512 spans are buffered; drops are explicit. Timing output failure must
not replace the existing return or exception, but can leave incomplete data.
Missing roots, dropped spans, incomplete streams and mismatched identities
must not pass an accounting gate. Process-kill durability is not implemented.

The TypeScript async wrappers add promise boundaries and incur overhead. The
controlled checks establish call/outcome parity in their scenarios, not native
scheduling equivalence, cancellation-race equivalence, or zero observer effect.
Python and TypeScript retain their existing error/cancellation behavior rather
than forcing both languages into a new policy.

## Executed checks

- Eleven Python unittest methods, including 15 baseline/treatment scenarios,
  plus terminal-observation and cleanup-error controls.
- Twenty TypeScript baseline/treatment scenarios: normal and delayed success,
  refutation, abstention, reobserve, dry run, setup/observation/provider/action/
  verifier failures, abort-like action failure, cleanup error/delay,
  second-provider failure after progress, optional-visual success/failure and
  a controlled asynchronous provider.
- TypeScript additionally tests four timing-sink failure cases, explicit
  buffer overflow, original exception identity, no exception payload, and
  single-use finalization. Both generators reject changed baseline bytes.
- Fake-clock records match between languages after removing task/clock IDs.
- Four broken variants are detected: missing terminal marks in either
  language, missing Python verification spans and missing TypeScript waits.

The runner control flow is real; MCP, providers, fixture reads and desktop
behavior are controlled substitutes. No native Driver, live provider,
full-example dependency typecheck, or whole-task >90% promotion is claimed.
Local controlled overhead probes are diagnostics, not a native speedup.

## Remaining gate

Resolve the metric-boundary question in trycua/cua#4052 before selecting an
upstream follow-up. Then use an exact-candidate native fixture, interleaved
baseline/treatment, independently observed outcomes, all failure/abstention
rows, and an external timer that includes telemetry output. Retain explicit
residual time and verify both languages. Do not inherit #3961's earlier
browser certification for this different experiment.

AI-assisted implementation and review. No product latency improvement claimed.
