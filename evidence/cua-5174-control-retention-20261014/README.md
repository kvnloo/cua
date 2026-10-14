# CUA #5174: success-control retention review

**LIMITED: the selected head unit behaviors pass; two omitted regression controls provide useful coverage.** This is independent downstream evidence, not an implementation replacement, an upstream review approval, or a new rollback discovery.

- Origin: [trycua/cua #5174](https://github.com/trycua/cua/pull/5174)
- Evidence tracker: [kvnloo/cua #155](https://github.com/kvnloo/cua/issues/155)
- Tested head: `a0fbe31a3bf544b1ba231439aedb1b592f0b6c58`
- Tested production base: `5e607bc5d7bc60ae0b80c8fcd9659847f575cc33`
- Salvage owner: injaneity. Original implementation and the recovered tests: Guillaume Demay / GDemay, [#3989](https://github.com/trycua/cua/pull/3989). Original report and proposed approach: anxkhn, [#3770](https://github.com/trycua/cua/issues/3770).

The original PR already records independent real-loopback rollback checks. We did not repeat or claim those as new. Its production tunnel file and the salvage file share Git blob `d6da76629dc2a83a9708117c6879fff43a1dad82`. The salvage preserves Guillaume Demay as author of commit `95819cce0e01115af5111fc969342d3c7ea8d848`.

## Finding

The salvage's last commit intentionally removes the two tests that pass before the rollback fix. Those tests observe existing documented contracts: normal context exit closes its tunnels, and single-target plain await returns a `TunnelInfo` which stays open until explicitly closed.

Both original controls pass against the exact current package. Deliberate, isolated mutations demonstrate that the six retained rollback tests do not cover the entire success contract:

| Production variant | Retained six rollback tests | Original two success controls |
| --- | --- | --- |
| Exact PR head | 6 pass | 2 pass |
| Exact base production package | Not run | 2 pass |
| Deliberately remove context-exit close calls | 6 pass | Context-exit control fails; single-target control passes |
| Deliberately return a dict for a single target | 6 pass | Single-target return-shape control fails; context-exit control passes |

The mutants are deliberately wrong test instruments, not defects observed in the PR. The single-target mutant establishes missing return-shape coverage, not independently missing close/idempotence coverage. Nothing here shows that every assertion in the removed tests is unique.

The coverage finding concerns these six retained tests, not the entire repository. Exact-head `test_env_transport_mock.py::test_port_forward_over_the_real_driver_tunnel` and live unified-API tests also exercise single-handle return shape at stronger/native boundaries. They were not run here and may cover some of the same contracts.

**Recommendation:** retain the two existing GDemay success controls alongside the six rollback cases, or preserve equivalent contract coverage in another owner test. Requiring every test in a fix to fail on the pre-fix baseline loses these compatibility checks. This is a narrow test-retention suggestion; no production correction is proposed.

## What actually ran

The complete 80-file production package was reconstructed and byte-verified against the exact head's Git tree. The original 87-file head test tree was also staged and verified, but only the six retained cases and two original success controls were executed. All 80 base production files independently match the exact base tree; the only production-file difference is `interfaces/tunnel.py`.

Normal `import cua_sandbox` and normal imports of `Tunnel`, `TunnelInfo`, and `Transport` executed. No package initializer, source function, or dependency was replaced by a stand-in. The original tests use `AsyncMock(spec=Transport)`, so these remain mocked-transport unit checks, not real socket/backend tests.

Execution used Python 3.12.14, pytest 9.1.1, and pytest-asyncio 1.4.0 with existing installed dependencies read-only. All 538 loaded third-party module files from the first successful retained-suite run match their installed distribution RECORD hashes. This proves installed-file self-consistency, not original wheel authenticity. The environment's distribution versions are recorded separately; this is not a frozen-lock or clean-install result. No dependencies were installed.

The launcher uses `-I -B -S`, a sanitized environment and empty HOME, and inserts only the selected source and dependency directories. It bypasses editable-install `.pth` startup. Pytest plugin autoload, its cache/logging plugins, and repository conftest loading are disabled; pytest-asyncio is explicitly loaded. In particular, this avoids conftest's native Fleet/image fixtures. This is **not** the repository's canonical full-package suite.

The Python audit/import/thread guards reject IP socket creation, connections/binds/DNS, subprocess execution, native CUA SDK imports, background threads and filesystem writes outside the packet's temporary directory. Standard-library native extensions and installed dependency extension modules do import. These guards are defense in depth, not an OS sandbox guarantee.

There is one recorded guard refusal per successful run: urllib3's import-time IPv6 capability probe tries to create an IPv6 socket, is denied before socket creation, and catches that exception internally. Thus urllib3 sees IPv6 as unavailable. No network, bind, or live tunnel runs. This does not affect the tested mocked tunnel control path, but it is an explicit import-environment difference, not a zero-denial claim.

Initial pytest attempts executed no tests because pytest's logging plugin tried to open `/dev/null` for writing and the guard rejected it. Those logs are preserved. The logging plugin was disabled; the write and network guards were not relaxed.

Every final run ends with only `MainThread` and no native CUA module imported. Per-run imports, hashes, denials, counts and failures are retained in the packet.

## Current upstream gates and limits

At review, the head was unchanged, with no submitted reviews or inline review threads. All 36 exact-head checks were inspected: 34 success, one skipped installer-compatibility check, and a failing CLA check. Contributor attribution passes. Those are origin CI results, separate from this independent local evidence; nothing here clears the CLA gate or authorizes merge/publication upstream.

No ADB, SSH, Fleet, cloud, VM/container, Driver/native SDK operation, full-package suite, Windows/macOS run, or source implementation edit was performed. No upstream comment/PR or default-branch change was made. The exact-head tests do not establish support for untested dependency versions or a released artifact.

## Contents and replay

The downloadable `packet.tar.xz` contains the complete frozen source variants, original tests, selected provenance and all raw execution logs. `CONTENTS.json` enumerates its members and hashes. See `commands.txt` for sanitized launch commands, `qualification/verified-source-hashes.json` for final head/base source identities, and `qualification/dependency-record-verification.json` for installed dependency provenance. `mutations.patch` identifies the two isolated deliberate changes. The original full test file is preserved unchanged under `tests/test_tunnel_original.py`, with its Git blob identity in `source-provenance.json`. `INDEPENDENT_REVIEW.md` records the critical reviewer and separate reruns.

For replay, use Python 3.12 and an existing dependency environment matching the recorded versions. Extract the source/evidence archive into a new empty directory, inspect its contents, set `CUA_EVIDENCE_SITE` to that environment's site-packages directory, create the packet-local empty `home` and `tmp` directories, and run the commands. Expected mutant-control exit is 1; normal and retained-mutant suites exit 0. Do not interpret the intentionally failing mutants as failing production code.

Publication identity, if present, is the evidence commit and is not the tested product commit. All reused implementation/test credit remains with the original contributors.
