# Linux native regression receipts for #4798

## Decision

**Not merge-ready.** The real, source-built Linux driver's complete `tools/list`
fails the added Vertex input-schema gate. Linux `set_value.value` still publishes
`type: ["string", "number"]`. Formatting and two existing batch regressions also
fail. These receipts do not claim a native desktop, provider, or cross-platform pass.

No implementation or test source was changed for this run. This evidence-only
branch is based on the exact fork #115 head below. Its documentation commit does
not alter the executable candidate. No new upstream PR is proposed.

## Exact sources and ownership

Verified with GitHub PR metadata and fetched Git refs on 2026-10-09 UTC:

| PR | Head owner / author | Exact head | Scope relative to its own base |
| --- | --- | --- | --- |
| [kvnloo/cua#115](https://github.com/kvnloo/cua/pull/115) | kvnloo / Kevin Rajan | `2ef54490cf51b3aca224eb45a3421482666d5276` | 3 test-only files, 324 additions, 3 commits; draft |
| [trycua/cua#4871](https://github.com/trycua/cua/pull/4871) | kvnloo / Kevin Rajan | `f520a122f2a7e987544a53fb49e9301883779afb` | 13 files; base `5a364bbe60e1f8a901ceacd889606b6367dc96ab` |
| [trycua/cua#4888](https://github.com/trycua/cua/pull/4888) | trycua / injaneity | `6dba09b0394f93b0d6a7ad0cc31c62c764538af1` | 47 files; base `b6c3814e416f4bd0ea041d47f1891b36c0837a4a`; draft |

#115's base is exactly #4871's head. Its description still names `be8d5ffd...`
and says one commit, so its validation boundary/count need updating before
promotion. All three commits on #115 retain Kevin's authorship. The original
gate motivation belongs to RitikaxG's review; injaneity's #4888 supplies the
shared-testkit direction. This evidence preserves those credits and adds no
competing implementation.

## Environment and execution

Debian 13 x86_64 container, 4 CPU quota, 16 GiB memory limit; no interactive
desktop / AT-SPI session. Rust `1.97.1` is the repository-pinned version.
The initial environment had no Rust tools on PATH or X11 development metadata.
Rust was installed only under `/workspace/cua-gate-support/{cargo,rustup}` with
`--no-modify-path`; Debian packages were downloaded and extracted under
`/workspace/cua-gate-support/sysroot`, not installed into the operating system.
No desktop-user installation, credential, or security setting was changed.

The worktree was clean and at the tested head throughout all test execution:
`/workspace/cua-native-gate`, branch `dot/cua/4798-native-regression-gate`.
Every Cargo command below ran from `libs/cua-driver/rust` with four build jobs.
`native-env.sh` records the local dependency paths. `run-check.sh` records each
command, timestamps, output and exit code. The original build failure is kept;
trailing whitespace in its committed log was normalized (raw copy retained locally).

| Exact command (environment below) | Result | Receipt |
| --- | --- | --- |
| `cargo fmt --all -- --check` | FAIL, exit 1 | `fmt.log` |
| `cargo test --locked -p cua-driver-testkit --lib` | PASS, 128 passed, no ignored | `testkit.log` |
| `cargo test --locked -p cua-driver-testkit --lib vertex::tests` | PASS, 4 passed, 124 filtered | `testkit-requested.log` |
| `cargo test --locked -p cua-driver-contract --lib` | PASS, 69 passed, no ignored | `contract.log` |
| `cargo test --locked -p cua-driver-core --lib` | FAIL, 932 passed, 15 failed | `core.log` |
| `cargo build --locked -p cua-driver` before local sysroot | FAIL, exit 101, missing `x11.pc` | `build.log` |
| `cargo build --locked -p cua-driver` with local sysroot | PASS, exit 0 | `build-local-deps.log` |
| `CUA_TEST_REQUIRE_DRIVER_BIN=1 CUA_TEST_DRIVER_BIN=/workspace/cua-native-gate/libs/cua-driver/rust/target/debug/cua-driver CUA_TEST_DRIVER_STDERR=1 cargo test --locked -p cua-driver --test protocol_vertex_schema_test -- --nocapture` | LIVE FAIL, 0 passed / 1 failed, exit 101 | `live-vertex.log` |
| `CUA_TEST_REQUIRE_DRIVER_BIN=1 CUA_TEST_DRIVER_BIN=/workspace/cua-native-gate/libs/cua-driver/rust/target/debug/cua-driver cargo test --locked -p cua-driver --test protocol_schema_test -- --nocapture` | LIVE PASS, 3 passed | `live-protocol-schema.log` |

The live gate spawned an isolated testkit daemon, initialized MCP, and received
the real tool inventory. It did not invoke action tools. Its assertion at line
73 failed only after the nonempty, unpaginated, unique-name, required
`run_actions`, and platform-filtered portable-roster checks passed. Its loop
inspected every returned input schema and reported exactly one violation.
`run_actions`' current input schema produced no violation. Output schemas and
literal payloads are deliberately outside this input lint.

The executable SHA-256 is
`48a43771562ca3d53bb80a311dfa9322d763525aaba6cab208b1d1778d82f491`.
The baseline implementation is unchanged from #4871 because #115 changes only
test code. These executions specifically identify #115's source tree, not a
separately compiled #4871 or #4888 binary.

## Findings at the tested source

1. **P1: live Vertex shape failure.**
   `rust/crates/platform-linux/src/tools/impl_.rs:9173` advertises the Linux
   `set_value.value` type array. The real failure is at
   `rust/crates/cua-driver/tests/protocol_vertex_schema_test.rs:73`;
   the lint detects it in `cua-driver-testkit/src/vertex.rs:63`.
   The older `protocol_schema_test` passes despite this nested type array.
2. **Existing batch compatibility tests fail.**
   `cua-driver-core/src/batch_tools/reliability_tests.rs:24` and `:71` reject
   string `observe` with the exact message
   `` `observe` must be true or an object of get_window_state arguments ``.
   These are compiled Rust tests using the existing probe harness, not native
   input-delivery proof. They remain failures, not environment skips.
3. **Formatting fails.** The full formatter diff is retained in `fmt.log`:
   `protocol_vertex_schema_test.rs:34`, `cua-driver-testkit/src/vertex.rs`
   (multiple locations), and inherited `cua-driver-core/src/batch_tools/tests.rs`
   around lines 409, 425 and 433. Nothing was autoformatted here.
4. **Source-only null-validation concern, handed to the separate compatibility
   worker.** `cua-driver-core/src/batch_tools.rs:1903` passes the advertised schema
   directly to `jsonschema::validator_for`. The helper
   `cua-driver-contract/src/inputs.rs:79` is referenced only by contract tests,
   not by this runtime call site. Passing helper tests therefore do not certify
   legacy null behavior. This record makes no new runtime-compatibility claim.
5. **Environment limitation in broad core testing.** Thirteen perception-worker
   tests fail: twelve report unavailable Linux Landlock containment or the
   resulting `UnsupportedPlatform` code, and one never reaches its worker.
   The latter is consistent with that containment failure but does not itself
   print the Landlock message. Full failures and expected/actual codes are in
   `core.log`. No security bypass was attempted.

## Comparison with #4888 (source inspection, not native certification)

Compare each PR against its own base. A raw head-to-head diff has 63 changed
files, including unrelated changes inherited through #4888's newer main;
it is not a 63-file schema patch.

- #4871 uses `nullable: true` and retains boolean cursor-effect SDK fields.
  #115 adds strict live-roster checks and malformed-container regressions while
  preserving that lint policy, including `$ref`.
- #4888 adds the live lint to `protocol_schema_test.rs:97` and extracts its
  helper into testkit. Its helper omits `nullable`/`$ref` from the allowlist;
  malformed `properties`/`anyOf` containers can be skipped by `and_then` at
  `vertex.rs:76` and `:91`, unlike #115's fail-closed container checks.
- #4888's Linux `tools/impl_.rs:9173` advertises a single string for `set_value`,
  addressing this particular live shape failure. That is source evidence only.
- #4888 also changes `CursorMotionEffects` to `Option<CursorEffectSetting>`
  (`cursor.rs:331`) and the set_config / null wire contracts. Its intentional
  breaking change must not be equated with #115's test-only scope. The separate
  compatibility worker owns numeric, null-reset and SDK behavior checks.

Linux CI already selects both affected crates with `--all-targets` at
`.github/workflows/ci-rust-linux.yml:153`; no workflow was added. CI metadata
and GitHub's mergeable flag are not counted as native test results.

## Remaining gates

Resolve the real live schema failure and formatting failures; reconcile the
batch regressions and separate legacy compatibility evidence. Run the corrected
exact candidate again. Native macOS/Windows, interactive desktop E2E, and live
Vertex/Gemini provider acceptance were not run here. A shape lint pass alone
would not establish those outcomes. The full core suite needs a Landlock-capable
executor for its environment-dependent rows. This branch does not waive any gate.
