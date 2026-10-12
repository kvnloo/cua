# CUA #4929 action cancellation receipts — 2026-10-12

Evidence-only owner: ayo, with OpenAI Codex. All production implementation and original author credit remain with hippoley. Canonical bounded claim/work item: [kvnloo/cua#131](https://github.com/kvnloo/cua/issues/131). Tested candidate: `b90c58e627dd7cdc71eb6de5b7cfbbe14c502f9b`, from `hippoley/cua` branch `fix/cua-bench-validate-parallelism-20261009`. Exact PR base: `7cc4bd0bfc3ce1a3246ae47fe02948dc9f64f010`.

This concerns the new batch action-evidence adapter and offline receipt consumer, not #4930 reward/step-count paths. The [maintainer's request for smaller topic PRs](https://github.com/trycua/cua/pull/4929#issuecomment-6095204273) remains authoritative; this packet proposes no competing production patch or merge readiness for the broad draft. Existing #126/#127/#129 receipts remain separate and unchanged.

## Executed results

| Head-only execution | Result |
| --- | --- |
| Owner test_evidence_contract.py + test_verify_execution.py | 17 PASS, exit 0 |
| Independent cancellation/controls/offline-verifier probe | 4 FAIL / 4 PASS, exit 1 |

Two failures are cancellation recording expectations (execute_action and click_element); two are offline acceptance expectations for those generated receipts. All normal-return and RuntimeError controls pass. This is head-only RED evidence of a gap in the new adapter. **The adapter, verifier and shared contract files are absent on the exact base. No base implementation, passing baseline, regression comparison or RED-to-GREEN repair is fabricated.**

## Actual recording and downstream consumption

The probe imports genuine EvidenceSession, ClickAction and verify_execution from the exact candidate. Only the desktop boundary is fake: screenshot returns constant synthetic bytes, and, in cancellation cases, the action sets an entered asyncio.Event then awaits an unreleased Event before incrementing a mutation counter. One task cancellation is delivered after entered; awaiting it raises CancelledError, the task reports cancelled and the mutation count is zero.

Both adapter boundaries nevertheless produce one actual executed-actions.jsonl row with `execution_status: returned` and `error_type: null`. Cancellation bypasses their `except Exception` assignments on Python3.12, while the finally block still observes and records. Normal returns are recorded as returned with one fake mutation; RuntimeError propagates, records failed/RuntimeError and leaves zero mutations. No shipped functions, imports or results are substituted or extracted.

The probe separately feeds the actual unmodified cancellation row to genuine verify_execution, using the owner's make_receipts fixture for structurally valid **synthetic** positive oracle/cleanup artifacts. The adapter removes the provisional fixture action file at construction and writes its own actual output; the tests parse that output and the verifier reads that exact file. The verifier reports actions/oracle/cleanup checks true, failed_action_count0 and run_accepted true. It counts only rows marked failed. This is downstream offline acceptance of a misclassified producer receipt, **not an independent verifier fault or a live cancelled-task success demonstration**.

Two actual JSONL artifacts from the separate verifier cases are included byte-for-byte: `actual-cancelled-execute_action.jsonl` and `actual-cancelled-click_element.jsonl`. Their SHA256 values are recorded in environment-source-hashes.json and the packet manifest. Complete actual events/reports for cancellations and controls are also in probe.log. The positive oracle/cleanup values are fixture artifacts, never human attestations or evidence of real VM/process cleanup.

## Requirement and bound

The adapter describes a desktop action-evidence boundary. A propagated CancelledError is not a returned awaited action. The proposed failed/CancelledError expectation follows the existing failed/error_type receipt vocabulary and ordinary exception control; it does not add a cancellation status or repair policy. This experiment measures one cancellation delivered while the controlled operation is pending, not cancellation before execution, repeated cancellation, cancellation during screenshot/record I/O, uncertain remote effects or missing-stream completeness.

In the ordinary batch solver, cancellation that propagates out of agent.perform_task is not caught by its `except Exception`; the oracle phase follows that await and is skipped. That is source inspection, not a solver lifecycle experiment. An agent swallowing cancellation or external artifact assembly is outside this probe. No live false success, physical action delivery, native observation, actual cleanup or end-to-end benchmark execution is claimed.

## Provenance, reproduction and review

Reused the approved official PyPI wheel environment, Python3.12.14; preflight imported datasets5.1.0, Pillow12.3.0 and Jinja2 3.1.6. Full installed versions and seven source SHA256/Git-blob hashes are in environment-source-hashes.json. Genuine worktree imports use PYTHONPATH; no installs, OS packages, SDK compilation, package/helper extraction or sys.modules package substitutes. Root AGENTS.md is absent on the historical candidate; current canonical factory AGENTS/registry/control-plane/HITL and relevant downstream records were refreshed, and the candidate CONTRIBUTING.md was read.

Exact invocations and base-absence metadata command are in commands.txt. Run from libs/cua-bench with fresh temp directories. Owner fixtures and the supplemental test remain in their package test namespace. Logs retain assertions, IDs, errors, result counts and timings; machine paths are replaced with HEAD_WORKTREE/RESULTS_ROOT/ENV_ROOT and volatile object addresses are redacted. No environments, caches, private generated task state or credentials are published. Synthetic actual action rows contain no machine-private paths. The manifest excludes itself.

Independent xhigh critic scope and verdict are in critic-receipt.txt. Origin metadata/comments, owner-topic PRs and canonical factory/project claims were checked. An additional broad alias issue search timed out with HTTP504; it was not retried, and the overlap check remains bounded. No origin action, default/force push, competing patch, destructive cleanup, credential recovery, fake human attestation or retry of denied/cancelled actions. Unrelated holds remain untouched. Publication SHA is distinct from the tested product SHA; hosted approval, smaller-topic routing and maintainer acceptance remain separate gates.
