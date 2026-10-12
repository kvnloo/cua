# Explicit destroy after local reconnect — final qualification, 2026-10-12

Canonical owner: dot/ayo, https://github.com/kvnloo/cua/issues/136, claimed before implementation. Pinned base: `a329fcf435191655a8dc8271c0df9ea824c2b564`. Exact tested candidate: `325b38bf2771cba7ef955955f56371e99fba6eca`; executable source equals `1f858bfaed6d140183aa5f8ae06cf7b888d62aad`, production fix `2d5fa18645a758db37ca2d8759fd6a06324348a7`. Final publication adds this receipt only and keeps executable package/test source unchanged. The tracker gives the publication SHA separately.

## Problem, requirement and bounded fix

Native local named reconnect retains a native handle in EnvTransport but no runtime metadata. Instance destroy therefore disconnected without requesting deletion. The actual lifecycle guide (docs/content/docs/cua-sdk/guides/lifecycle.mdx:59), destroy docstring and merged #1249 distinguish explicit deletion from disconnect/context preservation. #1249 preserved explicit delete with snapshot warning; automatic ephemeral suspend behavior remains separate.

The23-line production addition stores the exact native handle only during named local reconnect when cached metadata confirms local location and matching name. A fallback after existing cleanup calls that bound handle's delete() only when runtime/runtime-info remain absent and placement is still local. Name, generic EnvTransport and _ephemeral alone do not grant deletion authority. Fleet/released claims, cloud/direct connections and runtime owners keep precedence. Ordinary disconnect errors do not skip explicit cleanup; cancellation still propagates. Snapshot warning and runtime stop/suspend policies are untouched. There is no lifecycle registry or native/backend change.

## Final matched evidence

| Check | Result |
| --- | --- |
| Original base + identical final separated fixture | 5 FAIL / 15 PASS |
| Exact candidate + identical final separated fixture | 20 PASS |
| Applicable adjacent scope | 11 PASS / 1 native GuestDisplay case DESELECTED |
| Ruff lint/format and committed diff whitespace | PASS |
| Independent xhigh matched base/candidate | 5 FAIL / 15 PASS → 20 PASS |
| Independent xhigh adjacent | 11 PASS / 1 DESELECTED |

Final overlay SHA256 is `b36044b0dc0d1e97309d2c6d4b2bd87cc0fe7faaa9c021b03f1acd57f2e109cc`; base and candidate test bytes are identical. Base production is unmodified in its own isolated evidence worktree. Five baseline failures cover explicit destroy, destroy after disconnect, cleanup after disconnect failure, attempted delete/error logging and explicit snapshot deletion. All15negative/preservation/precedence controls pass on the base. Final20cases use genuine Sandbox.connect, Sandbox, EnvTransport and RuntimeInfo, with distinct inert manager.delete(name) and bound handle.delete() methods. They only record calls and toggle an in-memory flag. sandbox_state loading/deletion is an in-memory dictionary seam; saving/updating refuses persistence.

Controls cover disconnect and connect-context preservation; class-level local manager deletion; direct URLs; manual handle/name/_ephemeral lookalikes; legacy state without a native handle; cloud/mismatched/unavailable handle metadata; runtime stop/delete dispatch; cloud, Fleet and released-claim precedence; ordinary disconnect failure versus cancellation; deletion error best effort; and explicit destruction with snapshots.

## Safe runner preparation and exclusions

All original guard functions and refusal assignments remain unchanged (AST/assignment comparison against the historical packet was checked). The harness refuses cua/cua.* imports, native SDK access, socket connect/connect_ex/sendto and os.unlink/remove. Owning fixtures additionally refuse directory removal, SDK aliases and telemetry, and assert the native SDK is not imported. These are real package imports with denied native access, not import stubs or extracted production functions. No VM/container, CUA native library execution, guest RPC, external network, persistent-state or filesystem deletion was executed by these final runs.

Pytest's supported --capture=sys uses in-memory capture instead of fd TemporaryFile capture. All basetemp paths are freshly verified absent, including symlink checks. The existing environment-isolation fixture remains active. A supported pytest fixture hook uses the public mktemp(..., numbered=False) method with unique names during that fixture's preparation; it avoids the numbered helper's unlink/current-symlink bookkeeping. No deletion guard is relaxed, and no unlink is retried. No existing directory is cleared or reused.

The adjacent scope is five TestDestroyResilience cases, four pure agentless cases and two port-forwarding cases. The native-importing test_the_native_guest_display_never_prints_its_password is excluded via the collection expression and counted as deselected, never as passed. Native mock-server/Fleet fixtures and the broader SDK/live suites remain outside this task.

The fake deletion events demonstrate Python ownership and dispatch only, not real native/provider deletion, stop/suspend behavior, filesystem removal, desktop input or hosted CI acceptance. The native SDK remains unloaded. This bounded Python behavior is qualified; real backend lifecycle acceptance remains untested by design.

## Preserved historical attempts

Earlier local packet evidence/cua-local-reconnect-destroy-20261012 is retained as an explicitly historical HOLD checkpoint. Its original corrected16-case baseline4FAIL12PASS and intermediate20PASS with a conflated manager/handle are not final qualification. The initial16-case5FAIL11PASS also contained one invalid EnvTransport constructor; that setup failure is excluded from behavioral RED.

The first fully guarded adjacent runner stopped before collection at tempfile's new probe-file unlink; this was a self-imposed assertion, not a platform permission denial. After the user's diagnosis/authorization, --capture=sys avoided that probe. The first capture=sys attempt then reported20setupERRORS at the numbered fixture's unconditional unlink of absent cua-homecurrent. Both refusals remain preserved; no actual unlink occurred at those blocked actions. The non-numbered preparation avoids that bookkeeping operation while keeping all guards.

One path-form --deselect failed to match pytest's node ID: the native GuestDisplay import was selected and refused by the import guard, yielding1guardFAIL/11PASS with no native SDK loaded. That attempt is retained as wrong-deselection-guard-block.log. The corrected collection expression excludes the prohibited case before execution and produces11PASS/1DESELECTED. No prohibited operation is hidden or retried.

## Provenance, attribution and publication

The existing Python3.12.14 environment was reused: pytest9.1.1, pytest-asyncio1.4.0, Ruff0.17.0. No installs/sync, native build, OS dependency, credential operation or cleanup. Complete versions, source hashes, identical-overlay/harness hashes and exact commands accompany this packet. Logs are sanitized for roots/volatile addresses/trailing output whitespace; commands retain explicit execution paths.

Observed current main `6984010502583a8fb5c667e76063a65b5a6a0a67` has the same relevant Sandbox/EnvTransport/NativeRuntime/cleanup-test source as pinned a329. This is static applicability, not later-main execution. Fresh final ownership/main/remote checks precede a normal fork-only push; remote SHA and the append-only done result on #136 are read back.

Dillon DuPont / ddupont808 authored the original Sandbox (`7d1fa31fb6ed1d5565fad6eef756044be76061e4`), maintained SDK reconnect (`9166817485ae53f3966935c13878a8196d79a399`) and #1249 semantics (`03a1415db060d6d726742aeeab5ca53413242c82`). Existing cleanup resilience also retains r33drichards credit (`da9098b21ccb9694230b7c347914d3013556c45f`). Official pinned GitHub blame is recorded. No external patch was cherry-picked or replaced; new commits identify OpenAI Codex, with no human coauthor/DCO/CLA/signoff claim.

Current repo instructions/selected-item skill and factory AGENTS/control-plane/HITL/registry/#74/#14/#77 were read. Bounded searches found no competing explicit reconnect-destroy owner. #4468/#4763/#3989/#4338/#4062 remain excluded. No shared dashboard rewrite, other-branch edit, upstream write, default/force push, credential recovery, canceled-upload action or destructive cleanup. Upstream publication remains with Hermes.

The independent critic caught an initial dependency census generated with the host Python rather than the explicit test venv. Final environment-source.json was regenerated using the exact test interpreter and records pytest9.1.1, pytest-asyncio1.4.0, anyio4.15.1 and Ruff0.17.0. The historical HOLD packet metadata is not used as the final environment inventory.

Final independent verdict: bounded PASS; required independent exact-code rerun gate is resolved. No executable package/test change followed final qualification. Old HOLD material remains historical and is superseded for current qualification by this receipt.
