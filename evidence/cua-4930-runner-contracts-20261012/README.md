# CUA #4930 independent runner evidence

Implementation owner: hippoley. Independent evidence contributor: ayo, prepared with OpenAI Codex. Canonical downstream record: https://github.com/kvnloo/cua/issues/126. Owner's focused-review request: https://github.com/trycua/cua/pull/4930#issuecomment-6116439838.

Tested head: `cc7326d6ffd71fcf9a157e4498924ab47431d467`.
Tested PR base: `7cc4bd0bfc3ce1a3246ae47fe02948dc9f64f010`.
This evidence commit is based on the tested head and adds only a supplemental test and this packet. Its publication SHA is distinct from both product SHAs.

| Suite | Head | Base |
| --- | --- | --- |
| Revision's existing test_run_benchmark.py | 36 passed, exit 0 | 14 passed, exit 0 |
| Identical supplemental suite | 2 failed, exit 1 | 2 failed, exit 1 |

Both findings are inherited contract gaps, not regressions introduced by #4930 and not RED-to-GREEN repair evidence:

1. `[1.0, 0.0, 0.0]` returns reward 1.0 and success. `evaluate_task` documents the component mean, which is 1/3 and below the runner's success threshold.
2. A genuine Environment completes two `step()` calls inside an injected solver, then the solver raises. The runner returns steps=0, while the Environment counter is 2. The original error and zero reward are preserved, and the fake-backed session closes.

The malformed trailing-component observation is explicitly withdrawn: hippoley repaired validation of every component, and the author's four malformed-tail cases pass. Preserve this repair credit and production ownership.

## Execution and reproduction

Python 3.12.14; pytest 9.1.1; pytest-asyncio 1.4.0; datasets 5.1.0; Pillow 12.3.0. Full installed versions, relevant original source SHA256/Git blob hashes and exact UTC setup times are in `environment-provenance.json`. Wheel-only installation completed in about 96 seconds; no compilation or native SDK build. Dependency setup and test artifacts remained below the 1 GiB setup cap; the separate publication Git repository subsequently materialized about 198 MiB of public repository objects. `pip check` reported no broken installed requirements; cua-bench itself was imported from the genuine exact source snapshot using PYTHONPATH, so this is not an installed-distribution metadata certification.

`commands.txt` preserves the actual test invocations with the original machine root replaced by `$EVIDENCE_ROOT`. Choose any writable reproduction directory for that variable. Reconstruct `source/` and `base-source/` from the two exact public archive URLs recorded there. Install the hash-pinned `locked-requirements.txt` in an isolated Python 3.12 environment using official PyPI, then copy the supplemental test from this evidence commit into `libs/cua-bench/cua_bench/tests/` in each snapshot before running it. No shipped helper is extracted or substituted.

The supported component entry point is pytest from `libs/cua-bench`, as documented in TESTING.md and `.github/workflows/ci-py-bench.yml`. CI uses `uv sync --frozen --extra dev` and the full offline suite; this bounded independent run used authorized official wheels and selected only the exact runner file, not a frozen uv reproduction or full CI certification.

The four logs are raw pytest output with only machine roots and volatile object addresses sanitized. Original outcomes, assertion failures, test counts and timings are retained. `packet-sha256.json` records payload hashes before README creation; it does not hash itself or this README. No environments, caches, private generated task state or credentials are included.

## Independent review and limits

An independent xhigh critic reviewed source, all four logs, fixture boundaries and contracts without rerunning tests or querying GitHub. The critic independently recalculated all six original source/test SHA256 and Git blob hashes, confirmed the common package trees differ only in runners.py and the author's test file, and confirmed both supplemental failures reach their intended behavioral assertions. See `critic-receipt.txt`.

The tests use genuine imports, task loading and Environment. The shared `_fake_sandboxes` fixture replaces the sandbox SDK; the oracle test additionally injects a controlled solver callable on the genuine Environment. This is source/unit evidence with a fake sandbox, not desktop, VM, Docker, native SDK, hosted CI, deployment or full cleanup certification. No production fix, competing implementation, upstream post, main push, force push or human signoff is included.

Before publication, origin head/base and hippoley ownership were rechecked, #126 contained only the bounded claim, and no equivalent review appeared in the origin conversation/submitted reviews. Requested reviewer ddupont808 retains their review role. The PR is open and ready for review at that refresh; hosted CI approval and maintainer acceptance remain separate gates.
