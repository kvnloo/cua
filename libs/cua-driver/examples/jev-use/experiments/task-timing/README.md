# Whole-task timing: fork-only Python experiment

Refs trycua/cua#4052, #3963. This is an unselected measurement experiment, not
an upstream runtime change. It deliberately leaves the active #4052 and #3961
branches, their runners, and all Driver contracts unchanged.

## Reproduce

From this directory on the experiment branch:

```sh
python instrument.py
python -m unittest -v
```

The generator requires the exact #4052 runner Git blob
`003bdf23d41e7fa71a74583bb760d576503e908f`, from candidate
`5d3a55419194172b31f92cf2aa36b0b603ecac2a`. It refuses drift, even with
`python -O`, and creates only local `baseline.py`, `run.py`, and a reviewable
`runner-timing.patch`. It does not edit the tracked runner.

Only the standard library is needed for these controlled tests. MCP, the
provider, candidate builder and fixture are substituted at their boundaries;
the real baseline and generated runner control flow is executed. This is not
native Driver, browser, cloud-provider, or model-quality qualification.

## What is measured

The generated runner buffers explicit same-clock intervals for 17 statement
regions: setup operations, semantic and optional visual observation, candidate
construction, provider decisions, choice validation, actions, fixture checks
and the existing verification sleeps. It adds no Driver/provider calls, retry,
shorter wait, authorization change, or action-selection policy.

One `task_root` closes after the existing session/transport cleanup, before the
extra timing records are flushed. It covers entry to `run`, including fixture
reset and session setup; imports, CLI parsing and process exit are outside it.
`setup_ms` marks successful navigation before the task loop, or stays null when
setup fails. It is not an overlapping duration to sum with child spans.

The recipe return is recorded as `outcome_source:
recipe_return_not_independent_oracle`. Verification calls are timed, but an
independent success oracle remains a separate requirement. A phase exception
records its class, never its message, arguments, screenshot or typed contents.
Existing recipe logs are not changed or made more private by this addition.

At most 512 spans are buffered. Overflow is explicit in `dropped_spans`.
A timing-sink failure cannot replace the original return, exception, or
cancellation; it can leave incomplete telemetry. Missing roots, dropped spans,
foreign task/clock identities, and incomplete streams must reject a coverage
claim, not count as success. Process kill or interpreter failure is not covered.

Union intervals instead of summing parent/child durations. Report residual time
explicitly; startup/context management, cleanup and local bookkeeping can remain
unattributed. Neither the whole-task >90% gate nor instrumentation overhead has
been qualified on a native run. Do not mix these rows with old decision-only
records or advertise a latency improvement from this experiment.

## Executed local validation

Six unittest methods pass, including 15 baseline/treatment scenario comparisons:
verified, refuted, empty candidates, provider abstention, explicit abstention,
reobserve, dry run, action/observation/provider/verification/reset failures,
action cancellation, cleanup failure and delayed verification. Calls/arguments,
state, oracle reads, sleeps, cleanup order, return/error and legacy non-timing
events match. Separate checks cover timing-sink failure, cleanup-before-root,
exact fake-clock intervals, no recorded payload, buffer overflow and task IDs.

Three deliberately broken generated copies were detected: missing root,
missing verification spans and missing wait spans. None is committed. These are
sensitivity checks, not additional native tests. This Python-only result does
not qualify TypeScript parity, real optional-visual behavior, live provider
behavior or a later rebased candidate.

## Next decision

Should completed-task latency end at independent task verification, with cleanup
reported separately, while a second root records total runner lifetime? This
prototype deliberately labels its current cleanup-inclusive boundary instead
of calling it time-to-goal. Resolve that metric boundary before porting it to
both runners and interleaving real baseline/treatment trials.

AI-assisted implementation and review. No production change or native timing
speedup is claimed.
