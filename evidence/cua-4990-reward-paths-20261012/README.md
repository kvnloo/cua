# CUA #4990 reward-path evidence (downstream writeback)

Al-aminI owns the implementation in https://github.com/trycua/cua/pull/4990.
Head: `86ee66d9587344efd47226b18df3294dcd4b0dc0`.
Base: `29823dd6b556cb893cdc5fdbeb687eb18d1c8f54`.

Controlled `[1,0,0]` loaded through decorated task modules and existing `cli_env` / `FakeSDK` fixture: public `cb.interact` prints envelope reward **1.0**; real `runner.run_episode` prints **0.3333333333333333**, equal to `EpisodeResult.reward` and the documented arithmetic mean. Both parser round-trips agree with their envelopes. Scalar `0.75` and `[0.75]` emit 0.75 in both paths. Each case made/released two fake SDK claims. No actual imports were stubbed or helper implementations extracted; only existing SDK seam and stdin were faked.

Base runs use the same harness: no envelopes on either path, episode reward already averages to 1/3. `reward_of` and evaluate_task mean documentation are unchanged by this PR. The added interactive `coerce_reward` chooses the first recoverable list item. Thus episode averaging is inherited; the conflicting interactive machine-readable envelope is introduced by #4990. Do not conflate with #4930 or claim a unified-runner regression. Current production sources do not call parse_reward/try_parse_reward outside their definitions; the typed runner reward is unaffected. This demonstrates an inconsistent new envelope and public-helper round-trip, not changed in-process scoring, success thresholds, CLI scoring, or release behavior.

## Results

- Head: 59 PASS (28 existing reward tests, 28 existing runner/display tests, 3 evidence cases); 34 existing datetime deprecation warnings, 11.31s.
- Base: 31 PASS (28 existing runner/display tests, 3 evidence cases); 34 warnings, 11.28s. No reward.py/test_reward.py exists on base.
- Head documented-mean assertion: 1 FAIL (`multi`), 2 PASS (`scalar`, `single`), 0.84s. This is the desired defect-detection assertion, not a fix acceptance result.
- Initial runs preserved: head 54 PASS/5 FAIL, base 26 PASS/5 FAIL. Two failures were missing declared dotenv/httpx imports; three were an erroneous harness disconnected assertion. Corrected harness uses existing fake context release counters, with no production edits.

Python 3.12.14; pytest 9.1.1; pytest-asyncio 1.4.0; datasets 5.1.0; Pillow 12.3.0; python-dotenv 1.2.4; httpx 0.28.1. Full versions and official-wheel resolver plans included. Setup completed in 150.55 seconds; venv 406793419 bytes (~388 MiB), initial wheel download plan 101566829 bytes. No native compilation or OS/GPU/model/browser/driver installation.

## Scope and state

Hermetic Python package-path evidence with simulated SDK/file/screenshot behavior. No desktop/native/hosted CI, supported platform E2E, agent/model, CLI-executable installation, or release certification. Core programmatic `interact` is distinct from CLI `cb interact`; this finding targets the former. Episode run uses dump mode to skip solver and retains real task setup/evaluation/tracing paths. Production blobs untouched; only evidence and test files are new. Separate head/base worktree branches were used during testing. A later, separate evidence-only writeback branch contains this portable receipt; product tested SHAs are distinct from its publication commit.

Repository guidance and requested ledgers read; local bounded claim made before coding. Public downstream issue inventory (126 items) found no #4990 mirror. No overlapping #4990 claim was found in refreshed ledger bodies/comments. The GitHub search endpoint returned 422; the explicit full downstream inventory succeeded. The pre-test claim was local only, not a globally visible registry reservation. Canonical fork work item https://github.com/kvnloo/cua/issues/127 was created at 2026-10-12T04:18:56Z after execution and independent review; this writeback does not backdate a public claim. Kevin subsequently authorized the downstream evidence-only commit/push. Upstream publication remains pending a separately authorized owner handoff. Existing unrelated holds unchanged.

The initial broad discovery hit permission denial on unrelated `/tmp/codex-daemon-1000`. Work stopped until explicit scoped continuation; directory never retried, no alternate route or permission changes. All resumed discovery stayed within known /workspace paths and public repository metadata.

See commands.sh for exact successful test commands, resolver/install logs for setup commands/results, provenance.json and source-diff.patch for source scope, and critic.md for independent review when available.

## Portable paths and chronology

All host path prefixes in actual logs, source identity JSON, and command receipts are replaced with aliases: `${HEAD_WORKTREE}`, `${BASE_WORKTREE}`, `${VENV_ROOT}`, `${TEST_OUTPUT_ROOT}`; set them to your own absolute paths. The remaining suffixes identify the exact source modules and commands used. Logs otherwise preserve observed numbers, failures, durations and warnings; ANSI color codes removed. Sandbox `/tmp/evaluation` is an in-memory fixture path, not a host directory. `reproduce.sh` accepts your own worktree, venv and output paths and copies the supplemental test into its intended package test location. The commit itself adds only this evidence directory. No virtualenv, cache, binary archive, production file, or unrelated file is included.

Refresh before writeback: 2026-10-12T04:18:07Z, head/base/Al-aminI unchanged, reviews0/inline0; full fork issue inventory126, authenticated #4990 search empty, requested ledger comments show no overlapping #4990 claim. Remote target branch checked free. No test reruns were needed because only evidence presentation changed after the independently reviewed execution. Ownership is released upon verified push and public receipt readback; this is completed LIMITED evidence, not an implementation reservation.
