# Lume checkpoint timestamp qualification

Source and fixture qualification, 2026-10-14 UTC. The qualification used no implementation claim, production edit, guest, real Lume server, or external-service mutation. This separate downstream evidence branch publishes the reviewed packet only; it does not change Grok's branch or authorize origin action.

## Disposition

**LIMITED evidence; owner-controlled implementation.** The current-origin Python behavior is independently reproduced. This confirms the known premise of existing Grok work rather than exposing a free implementation leaf. Preserve the origin assignee ddupont808, reporter methanoya, and Grok's existing branch.

- Origin issue: https://github.com/trycua/cua/issues/4954
- Maintainer requirement: https://github.com/trycua/cua/issues/4954#issuecomment-6118633790 says the timestamp should come from the checkpoint, not the call time, and assigns triage.
- Existing carrier: `grok/cua/4954-checkpoint-created-at`, live verified tip `8e0214e0251f9a727d70b751aec61a190b017811`.
- Existing regression commit: `5d70e096381cd872c94323f9a8b00f52dfbbc637`; original base `e321277644369e179798f07cfdad07499ded63e9`.
- Prior tracking: https://github.com/kvnloo/oss-factory/issues/64 and https://github.com/kvnloo/oss-factory/issues/64#issuecomment-6112999215 already record this exact branch as Grok-owned, WAIT. No writes were made there.

The branch's current implementation omits `created_at` for listing and existing-base reuse, leaving the Python dataclass default 0.0. Its two tests require 0.0. This is an existing candidate choice, not an independently documented unknown-time contract. Do not upgrade it to adoption-ready based only on these tests. The classification remains LIMITED, with fixture evidence only. The existing implementation carrier and its WAIT disposition remain unchanged.

## Revisions and frozen artifacts

- Tested origin: `6dea13a3f1e7a9f26444f7835ebcc53c967ca616`.
- Latest origin main at final refresh: `3f70341ee1e42c5b32e22c1ce1483ceeba0a5831`. The one-commit delta changes only `libs/cua-driver/rust/crates/cua-driver/src/main.rs` (logging). All 19 frozen source/policy/test-seam blobs remain identical. See `source-current-main.json`. No test execution is claimed on the newer commit.
- Current fork main: `6e74bfadd82790312f0ab46ae7ed48027f8aca56`.
- Factory control/registry/HITL: `fa0cea339ce9df68b100d2c6e8f6390ba718a670`.
- Origin checkout: `<origin-worktree>`, detached and production source unchanged.
- `source-origin/`: 19 exact origin files, with full Git blob IDs and SHA-256 hashes in `source-manifest.json`.
- `grok-source/`: exact owner `lume.py` and regression file retrieved at the owner tip.
- `observe.py`, `guards.py`, `observed.raw.log`: rerunnable current-origin characterization and raw stdout/stderr. The saved-file run is the authoritative repeatable artifact; the exploratory stdin run is excluded.
- `metadata.json`: current repository and overlap metadata. The existing-carrier discovery in this README supersedes the initial keyword-search-only absence of a mirror; no absence-of-work conclusion is valid.

`commands.sh` provides the executed guard/environment/pytest configuration with portable worktree arguments; its portable replay was also verified with the same results. Existing owner tests were independently rerun, unchanged: 2 expected assertion failures on tested origin, 2 passes on Grok's exact tip. Raw logs are `grok-tests-origin.raw.log` and `grok-tests-grok.raw.log`. These tests impose the owner's 0.0 choice; their pass does not settle the semantic decision. The isolated runs bypass repository conftest/native fixtures intentionally and load the real Python package from the selected clean worktree. Both runs have one pytest warning because the explicitly loaded guard module was already imported; this is not a test failure. Python 3.12.14, pytest 9.1.1, httpx 0.28.1. No full package suite, SDK tests, CI, macOS, or live-server acceptance is claimed.

## What is actually established

1. **Listing misreport, executed Python.** On unchanged fake VM rows, `LumeRuntime.list_checkpoints()` yields 100.0 for both prefixed entries, then 200.0 on the second call under injected clocks. An ordinary VM is filtered out. The code calls the clock separately for each entry, so exact equality of real-clock values within a list is not guaranteed; the defect is retrieval-time stamping.
2. **Existing-base reuse, executed Python.** `ensure_base()` returns 300.0 then 400.0 for the same pre-existing stopped VM, and likewise for suspended. Both paths perform only mocked GETs. This is `ensure_base()` reuse, not a `checkpoint()` reuse path.
3. **Fresh creation paths, source only in this packet.** Python `ensure_base()` after pull and `checkpoint()` after clone/restart stamp the client completion clock. No fresh pull, clone, or restart was executed. Do not claim these values are authoritative server creation instants.
4. **Rust sibling, source only.** `cua-vmm/src/lume/mod.rs:795-800` returns `CheckpointInfo::now` for an existing non-pulling base, even after touching an ownership record. This resembles the reuse problem, but no Rust build/test or runtime reproduction was performed, and no separate implementation claim is made.

## Timestamp contract and metadata coverage

The Python `CheckpointInfo` dataclass (`runtime/base.py:16-22`) has `created_at: float = 0.0`, with only a general metadata docstring. The abstract `list_checkpoints()` has no further contract. No explicit documented interpretation of 0.0 as unknown was found in the inspected Python component or Lume reference. None would change the declared type; using it cannot be inferred as an approved fix.

The strongest independent requirement evidence is the maintainer's issue comment: checkpoint time, not call time. The issue author proposes 0.0, None, or backend metadata as alternatives. Those alternatives are not a recorded maintainer selection.

Lume's GET list/get handlers serialize `VMDetails`. Its fields and CodingKeys, and `VMConfig`, carry no creation timestamp. The Rust HTTP `VmDetails` mirror also has none. The generated public HTTP reference describes list/get endpoints but no creation-time response field. Session start and transient provisioning timestamps in `VMDirectory` are different events; substituting them would invent semantics.

There **is** narrower SDK ownership metadata: `cua-vmm/src/lume/owned.rs:29-39` declares `OwnedVm.created_at` as Unix creation seconds, stored in the SDK's owned-VM records. `mark()` sets the client clock. Rust pulls mark before the pull and again after successful completion (`mod.rs:820,843`); Rust forks mark after clone (`mod.rs:1526`). Touch updates last-used metadata, not the recorded created_at. This is not a universal Lume-server creation timestamp. Directly created/imported VMs and the Python direct-HTTP `ensure_base`/`fork`/`checkpoint` paths are not guaranteed to have these SDK ownership records.

The Python list path goes through `NativeRuntime.list()` (`native.py:322-336`) and the SDK's SandboxInfo. Neither exposes a created_at field on this listing path. Reading filesystem mtimes would not fix the contract: the owned-record mtime explicitly means last use. A mapping to ownership metadata would require coverage/provenance and API decisions, not a blind field substitution.

RFC #4956 explicitly places Lume migration outside its pilot and says #4954 is independent. It is not approval for a new backend timestamp contract.

## Current ownership and overlap

Bounded origin/fork searches for `4954`, `LumeRuntime`, `checkpoint`, `created_at`, owner PRs and branch names found no open PR directly carrying this timestamp fix. Origin issue timeline links RFC #4956 and factory #64, and records assignment to ddupont808 on October 12. Factory #64 is how the existing Grok branch was recovered; initial issue/PR keyword search alone was insufficient.

Adjacent live work that must be preserved:
- Origin #4468, ddupont808, head `297249b266c24453bb4c08d5a0e5f74b53f8c286`: ownership/cleanup, touching `cua-vmm/src/lume/mod.rs` and `owned.rs`.
- Origin #5095, nick-inkeep, head `aa2e3429261bdd1d7976a7533f3d5c791aa7294c`: owned GHCR preparation, touching Lume controller/HTTP pull paths.
- Origin #4538, head `581042ec2b905d58cbfc9f1df625e695b7fb6597`: VMDetails printer only; JSON unchanged per PR description.
- Origin #4664 and #4672 are Lume/SDK release carriers, not evidence of a timestamp fix.

Factory registry routes CUA to `kvnloo/cua`. Linear searches for 4954 and Lume found no corresponding item; the broader cua query showed other work, not this leaf. No origin authorization is inferred. Any future origin-facing promotion also requires the control-plane project-wide open-review sweep; this bounded qualification is not a declaration that the CUA queue is clean.

## Smallest useful next work

Independent review of this frozen characterization against the **existing Grok carrier**, with one narrow decision recorded separately: whether retaining 0.0 for unavailable times is the accepted compatibility behavior. Reuse the existing carrier and prior tracking if later publication is authorized. A deduplicated downstream QA mirror may reference this packet with `dedupe_key: trycua/cua#4954`, link Grok's branch and the existing factory record, and remain LIMITED/WAIT; it does not claim implementation ownership or duplicate the origin issue.

Useful test seams: Python `LumeRuntime.list` injected async rows; `ensure_base` through `httpx.MockTransport` for stopped/suspended GET responses; existing `test_runtime_adapters.py` recording fake for the SDK boundary. Rust has `OwnedVms::new(tempdir)` plus existing `mark_touch_forget`, and `tests/support/fake_lume.rs` used by `lume_clone_resources.rs`/`lume_resume.rs`. Those Rust seams were inspected only.

The official sandbox suite requires built native SDK/fixtures and explicit live-suite exclusions in `TESTING.md`. It was not run here. CUA #148/#149 ADB timeout evidence and its frozen files were not modified or duplicated.
