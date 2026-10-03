# Offline lazy validators: MODIFY

The bounded offline experiment preserves acceptance on the covered corpus and reduces repeated schema checking, but does not establish a cold one-task win. Cold means a new validator session inside a warm Python process: checks/constructors are included, interpreter/import/driver startup and native transport are excluded. Production invalidation and concurrency remain unproven. No CUA production code is changed.

Credit: Kevin Rajan's N-02 native-transport experiment supplied the historical schemas/results; its provenance attributes the caller-compiled mechanism to Kevin Rajan's B-01 H_C. This is an isolated first-use-cache adaptation, with no ownership/exclusivity claim.

## Results

Twelve randomized blocks, seed 20261003, 396 timed sessions with no drops. Session-total p50 milliseconds:

| Workload | Standard | Eager | Lazy |
|---|---:|---:|---:|
| Single result | 5.550 | 30.563 | 5.445 |
| First five-call trial | 29.929 | 30.634 | 30.439 |
| First six-call trial | 35.005 | 30.946 | 30.777 |
| Ten five-call trials | 298.176 | 39.698 | 39.410 |
| 88 recorded results | 513.341 | 47.195 | 46.740 |

The first five-call task uses all five distinct schemas (six tool schemas, click/set_value identical). Lazy defers these checks rather than deleting them, and fails the preregistered <= standard cold-task condition. Small lazy-versus-eager differences do not establish superiority. Eager/lazy both eliminate redundant metaschema checks on repeated calls. Checking unused schemas is avoided on sparse sessions. N-02's historical 107.5 ms preparation and this environment's approximately 30 ms are not a replicated improvement. No whole-task/native transport gain is established.

Correctness: original 3,131 rows, zero acceptance disagreements; independently reproduced exactly. A separately reviewed 1,784-row supplement covers first/repeated cross-tool substitutions and first-invalid/repeated use, also zero disagreements. Original cross-tool cases ran once, a documented deviation from the preregistration's repeated-use intent. Counts are separate and timings were never rerun. 64/88 added-property mutants are valid under the original permissive schemas and are correctly accepted. Cross-tool schemas may legitimately accept identical/permissive results. Schema validation is not semantic task verification.

## Scope and limits

All arms preserve full schemas, dialect selection and references; cache keys are complete canonical JSON. Validators use validator_for/check_schema and best_match(iter_errors). Registry is fixed per session by contract, and schemas are deep-copied on creation, but dictionaries/resource contents are not deeply frozen. Updates require a new session. No integration invalidation/concurrency guarantee exists.

Known-tool accept/reject equivalence is not error-message or MCP tools/list-refresh equivalence. Unknown tools fail closed in this kernel. Registered relative/local recursive refs and unresolved refs are tested. Actual MCP cross-check covers recorded known-tool content, not its remote retrieval policy. Installed versions: jsonschema 4.26.0, referencing 0.37.0, MCP 1.29.0; N-02 used MCP 1.30.0.

Timers include schema snapshot/setup, first-use/eager checks and constructors, canonical keys, validation. They exclude file reads, module imports, JSON decoding, MCP/driver startup, tools/list, subprocess/network/UI/transport and real task success. Twelve observations per cell make nearest-rank p95 the maximum, not a stable population-tail estimate. The process was coordinated without concurrent worker benchmarks, not guaranteed an exclusive machine.

## Reproduction inputs are not included

This branch contains code, preregistration, aggregate timing summaries and public source identities only. It does NOT contain captured UI/window/process/interaction data, raw comparison rows, full evidence archive, or a complete self-contained reproduction packet. Obtain the already published historical inputs separately if authorized:

- [N-02 packet](https://github.com/kvnloo/cua/tree/9846ac8033a8b5e952b0d44f39858625375d54e1/docs/experiments/n-02-native-transport-2026-10-02)
- [Output schemas](https://github.com/kvnloo/cua/blob/9846ac8033a8b5e952b0d44f39858625375d54e1/docs/experiments/n-02-native-transport-2026-10-02/raw/n02-e01/output-schemas.json), Git blob 5f1aa20fea98d7c971c4280e5aaab5bc73c01345
- [Recorded gzip corpus](https://github.com/kvnloo/cua/blob/9846ac8033a8b5e952b0d44f39858625375d54e1/docs/experiments/n-02-native-transport-2026-10-02/raw/n02-e01/hc-corpus.jsonl.gz), Git blob ad78ea40aa456ae87125cc552e3f7bb99e1754e8
- [Original mutation helper](https://github.com/kvnloo/cua/blob/9846ac8033a8b5e952b0d44f39858625375d54e1/docs/experiments/n-02-native-transport-2026-10-02/hc_equivalence.py), included unchanged for mutation generation.

Put schemas at inputs/output-schemas.json. Decompress corpus with Python gzip or equivalent to inputs/hc-corpus.jsonl. Verify the Git blob identities before use (Git hashes blob-header + original bytes). The measured schema materialization had one extra trailing newline; parsed JSON was independently verified identical to original.

Using already installed dependencies, run `python run.py --correctness-only`, `python supplemental.py`, or `python run.py` for a fresh bounded timing run. These commands use local supplied inputs and make no network/UI calls. Running writes new output and does not recreate the historical timing environment. No toolchain installation is necessary when dependencies are already available.

Independent review reproduced original and supplemental correctness exactly and recalculated every timing aggregate/order. This publication intentionally retains only aggregate evidence; no claim of raw evidence completeness is made.
