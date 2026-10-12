# Local reconnect explicit destroy — HOLD / unpushed, 2026-10-12

Canonical claim: https://github.com/kvnloo/cua/issues/136, owner dot/ayo. Pinned base `a329fcf435191655a8dc8271c0df9ea824c2b564`. Local production/test candidate `2d5fa18645a758db37ca2d8759fd6a06324348a7`; test-only provenance correction `1f858bfaed6d140183aa5f8ae06cf7b888d62aad`. This packet is local only. No fork/upstream branch push or runtime acceptance is claimed.

## Requirement and reproduced behavior

The maintained lifecycle guide (docs/content/docs/cua-sdk/guides/lifecycle.mdx:59) says destroy deletes the sandbox held by the caller. Sandbox.destroy's docstring agrees. Merged upstream #1249 (`03a1415db060d6d726742aeeab5ca53413242c82`) deliberately preserves explicit deletion with snapshot warning and separate automatic suspend behavior. Sandbox.disconnect and connect-context exit explicitly preserve the sandbox.

Native local named reconnect retains its native handle inside genuine EnvTransport but sets no Python runtime/runtime-info fields. Existing destroy therefore disconnects and makes no local deletion request. No deletion-on-drop rescue was inferred or executed.

Corrected RED uses actual Sandbox.connect with local=True, Sandbox, EnvTransport and RuntimeInfo construction, replacing only state/native manager/handle seams with inert recordings. No Sandbox/import stub or extracted production helper. Fake deletion only appends a call and toggles an in-memory flag; state removal is an in-memory dict operation. No guest RPC or actual sandbox deletion is executed.

## Recorded execution and limits

| Attempt | Result and scope |
| --- | --- |
| Initial 16-case baseline | 5 FAIL / 11 PASS; one bad manual EnvTransport constructor is setup failure, not behavioral RED |
| Corrected identical 16-case baseline | 4 FAIL / 12 PASS |
| Fixed identical 16-case fixture | 16 PASS |
| Expanded 20-case fixture before manager/handle split | 20 PASS; no identical expanded baseline rerun |
| Guarded adjacent pytest harness | BLOCKED before collection: tempfile startup probe attempted os.unlink; deliberate refusal guard stopped it; zero adjacent tests ran |
| Final distinct manager/handle fixture | NOT EXECUTED after the stopped guarded run |
| Final lint/format and source whitespace | PASS |
| Independent exact-code rerun | NOT EXECUTED; publication gate remains blocked |

The owning module overrides the suite manifest fixture that normally loads the native SDK. During test bodies, native access/import, socket connects/sendto and filesystem unlink/remove/rmdir are guarded; telemetry is disabled. The test bodies assert cua was not imported. These fixture guards activate after pytest startup, so the direct owning runs do NOT establish a whole-process zero filesystem-deletion guarantee. Framework initialization may perform its own temporary-file probe before fixture setup. Do not claim the stronger guarantee or desktop/native acceptance.

A separate adjacent harness refused native imports/accessors, network and file deletion before pytest startup. Its first run stopped when tempfile._get_default_tempdir attempted unlink. The guard was not relaxed and the stopped harness was not retried through another route. This is our deliberate test-boundary refusal, not a sandbox/automatic-approval permission denial. No deletion occurred at that guarded action. The failed harness and traceback are retained. The adjacent agentless GuestDisplay case directly imports cua and is excluded from any permissible future scope; it was never reached by the stopped run.

The independent xhigh critic additionally identified that the original RecordingLocal object doubled as both manager and native handle, weakening signature/provenance assertions. A local test-only correction separates RecordingHandle.delete() from RecordingLocal.delete(name), with distinct handle_delete/manager_delete events. Production code is unchanged. The corrected fixture has not been rerun and receives no inherited green claim. Required independent exact-code execution and applicable adjacent execution remain outstanding; no validated push may proceed yet.

## Narrow local correction

Only23production lines are added to sandbox.py: a private handle slot; bind it only during local named reconnect when an actual attached native handle reports local location and matching name; after existing cleanup dispatch, use its delete() only with no runtime metadata and still-local placement. Unknown metadata remains unbound. Fleet claims (including already released), cloud transports, direct URLs and runtime owners keep precedence. Name, generic EnvTransport and _ephemeral alone grant no deletion authority. Existing exception/cancellation semantics, snapshots, adapters and automatic exit remain unchanged by the production diff.

Prior test bodies cover ordinary disconnect/context preservation, class-level local delete, direct URL and manual handle lookalikes, cloud/mismatched/unavailable metadata, runtime stop/delete precedence, cloud/Fleet claim precedence, disconnect failure independence, delete-error best effort and explicit snapshots. The expanded historical fixture adds disconnect-then-destroy, legacy non-native state, released Fleet claim and cancellation controls. The native manager/handle calls remain simulated effects, not provider or filesystem deletion evidence.

## Provenance and remaining gate

Observed final upstream main moved to `6984010502583a8fb5c667e76063a65b5a6a0a67`. Source comparison of sandbox.py, EnvTransport, NativeRuntime and existing cleanup tests against the pinned base passed; the update concerns CLI/Spaces host features. This is static applicability only, not a new-head test execution.

Existing Python3.12.14/Ruff0.17.0 reused with no installs/sync. Exact commands, versions, source hashes, sanitized logs and independent source-review receipt accompany this local packet. Logs have root/address/whitespace sanitation; commands intentionally preserve exact execution paths.

Dillon DuPont / ddupont808 authored the maintained reconnect/SDK implementation (`9166817485ae53f3966935c13878a8196d79a399`), original Sandbox (`7d1fa31fb6ed1d5565fad6eef756044be76061e4`) and merged #1249 semantics. Existing cleanup resilience also credits r33drichards (`da9098b21ccb9694230b7c347914d3013556c45f`). Official pinned GitHub blame is recorded, with existing history retained. No external contribution was cherry-picked, no human coauthor/DCO/CLA/signoff fabricated; new commits identify OpenAI Codex.

Current repository instructions, selected-item skill, canonical factory AGENTS/control-plane/HITL/registry and #74/#14/#77 were refreshed. Bounded symptom searches found no competing reconnect-destroy repair. #4468/#4763/#3989/#4338/#4062 ownership is excluded. No dashboard/other branch edit, real VM/container, native-library test execution, guest network, credential operation, cleanup, blocked-action retry, force/main push or upstream write was performed. Publication is held specifically because independent exact-code and adjacent execution gates are unmet under the guarded test constraint.

The baseline production SHA is pinned; the initial uncommitted 16-case overlay hash was not captured separately. Source hashes cover the immutable base, historical 20-case code and final unexecuted fixture. No unrecorded exact-overlay hash is invented.
