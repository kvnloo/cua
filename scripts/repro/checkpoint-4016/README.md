# Checkpoint #4016: real save/load red–green evidence

Optional evidence and candidate for the existing PR by @shobhitagnihotri69, not a competing PR or an upstream source change.

## Executed result

Source: `072ceb73f9ce32e65b5280438040b59cb4da2794`.

- Baseline: **18 passed, 2 failed**, no skips or fixture errors.
- Candidate: **20 passed**, no failures, skips or fixture errors.
- The 20 cases are all **11 original tests unchanged**, plus **9 new save/load tests**.
- Both baseline failures are actual state-signature mismatches when loading through the returned canonical weights/config paths with stale same-stem siblings present. Directory loading still works.

These tests execute the complete checkpoint module with real CPU tensors and actual safetensors files. They do not mock path resolution, tensor I/O, or integrity checks.

## Narrower candidate

Prefer the canonical partner **when it exists**, otherwise retain the original legacy-only same-stem behavior. This differs from the earlier review suggestion to always reserve canonical basenames: the tested alternative preserves both historical-only pairs while making canonical directory output win when both naming schemes coexist.

`candidate.patch` modifies two resolver conditions only. Serialization, integrity checking, tensor data, and exception handling are unchanged. This is an optional compatibility choice for the existing owner, not a claim that the public ambiguity policy is already approved.

New cases cover clean canonical paths, custom filenames, unrelated siblings, both historical-only pairs, canonical directory access with stale siblings, repeated saves, and both failing returned-path variants.

## Exact evidence scope

Executed on Linux x86_64 with Python 3.13.5, torch 2.10.0+cpu, safetensors 0.7.0 and pytest 9.0.2.

The source and upstream test bytes were verified against Git blob IDs:

- checkpoint.py: `0f4f7effe9226683e18df6ebb558148c77df2a86`
- original test_checkpoint.py: `80c7fbebe2124e571a69b1ef6d21367e19aaf268`
- candidate checkpoint.py: `ce6fb00b5e8b92f84533c6904e374038ad100e8c`

The module is staged as an isolated `cua_s1` namespace so unrelated package initialization is not part of this experiment. This is **not** the full Cua-S1/project suite, a package-installation test, or validation under the repository lockfile. Those integration checks remain required before landing. No contributor branch was modified.

## Reproduce

From a checkout containing the pinned source commit and these evidence files, with Python, torch, safetensors and pytest installed:

```sh
proof="$(mktemp -d)"
pin=072ceb73f9ce32e65b5280438040b59cb4da2794
git show "$pin:libs/cua-s1/python/src/cua_s1/checkpoint.py" > "$proof/checkpoint_baseline.py"
git show "$pin:libs/cua-s1/python/tests/test_checkpoint.py" > "$proof/test_checkpoint_upstream.py"
cp scripts/repro/checkpoint-4016/run_evidence.py "$proof/"
cp scripts/repro/checkpoint-4016/test_checkpoint_locator_regressions.py "$proof/"
python "$proof/run_evidence.py"
printf 'Evidence: %s\n' "$proof"
```

The wrapper succeeds only when baseline reproduces the two specified failures and candidate passes all 20 tests. Its success is not a claim the baseline is fixed. It writes each variant's raw pytest log, JUnit XML, module hashes, environment versions, structured results and generated patch in the temporary directory.

No source file in the checkout is changed by this recipe. The original author's existing tests and contribution remain intact.
