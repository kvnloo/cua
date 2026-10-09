# CUA compatibility evidence — 2026-10-09

Review only. No implementation edited, no upstream post, no Rust/testkit/live tools-list
commands run. Contributor credit remains with kvnloo (#4871/#115/#118), injaneity
(#4888) and RitikaxG (original live-inventory diagnosis).

## Pinned scope

- Fork #115: `2ef54490cf51b3aca224eb45a3421482666d5276`.
- Upstream #4871: `f520a122f2a7e987544a53fb49e9301883779afb`.
- Upstream #4888: `6dba09b0394f93b0d6a7ad0cc31c62c764538af1`.
- Existing typed-null fix owner: fork #118 at `3771b6913235b149461e215b2e82c9891655d198`.

Latest heads/comments were read before work and heads rechecked at completion.
`git diff --name-only f520a122 2ef54490` lists only the testkit export,
Vertex helper and live schema test. All runtime/SDK sources examined here are
identical between #115 and #4871. Separate detached worktrees preserve the inputs.

## Actually executed

TypeScript 5.7.3 against the unchanged generated package modules, not copied types:

| Probe | #115/#4871 | #4888 |
| --- | --- | --- |
| `CursorMotionEffects = {trail: true, glow: false}` | exit 0 | exit 2, two TS2322 diagnostics |
| Omitted effects `{}` | exit 0 | exit 0 |
| Explicit `CursorEffectSetting.On/Off/Default` | N/A | exit 0 |

Command (substitute each supplied `.mts` file):

```sh
/workspace/scratch/cua-compat-tools/node_modules/.bin/tsc \
  --noEmit --strict --skipLibCheck --target ES2022 --module NodeNext \
  --typeRoots /workspace/scratch/cua-compat-tools/node_modules/@types \
  /workspace/scratch/cua-compat-evidence/legacy-bool-4888.mts
```

Full commands, exit codes and diagnostics: `typescript-typechecks.json`.
Initial missing-Node-type-root attempts are separately preserved, not counted as
the observed compatibility failure. Final failure contains only the two expected
TS2322 messages. This is compiler evidence, NOT SDK native execution.

Existing Python source-contract suite: `test_compatibility_contract.py`, 2 passed
on each head (0.07 seconds each), pytest 8.4.2/Python 3.12.14. Full invocation and
results in `python-tests.json`. These tests check exports/signatures and released
ClickPosition ordinal source; they do not check CursorMotionEffects field types.

Existing Python native-required cursor-motion suite was attempted on both heads:
exit 1, missing `src/cua_driver/libcua_driver_sdk.so`. No native test passed or
silently skipped. Command:

```sh
CUA_DRIVER_REQUIRE_UNIFFI=1 PYTHONPATH=<checkout>/libs/cua-driver/python/src \
  python -m unittest discover -s <checkout>/libs/cua-driver/python/tests \
  -p test_cursor_motion.py
```

## Source findings, explicitly not native execution

1. **Legacy SDK booleans:** #4888 TypeScript generated
   `src/native/cua_driver_contract.ts:1362` replaces boolean with the enum;
   #115 equivalent is line 1327. Python `_native_contract.py:2514` likewise
   changes constructor annotations and `:2463` only accepts enum members at
   `check_lower` (raises ValueError otherwise). Native Python behavior remains
   unexecuted because the staged exact-head library is absent. The existing
   golden fixture tests adapt booleans to enums before calling the package,
   so they do not establish unchanged legacy-client acceptance.

2. **Linux numeric set_value:** #4888
   `rust/crates/platform-linux/src/tools/impl_.rs:9173` advertises string-only;
   #115 same line admits `[string,number]`. Both direct handlers still convert
   `Value::Number` to text at `:9187-9193`. #4888
   `cua-driver-core/src/batch_tools.rs:1736` validates every planned action;
   `:1901-1909` compiles the advertised schema and reports `/value` for invalid
   numbers. Thus the narrowing affects batch acceptance before dispatch while
   the direct handler retains its numeric branch. No native numeric action was
   invoked; no mock transport is represented as native proof.

3. **Do not conflate raw set_config reset with typed null collapse.** #4888
   `cua-driver-core/src/tool.rs:268-274` retains a present null while rewriting
   `{key,value}`. Linux `impl_.rs:13315` calls the raw motion-config helper.
   `cursor-overlay/src/motion_defaults.rs:100-105` explicitly clears on null;
   `:87-90` / `:152-158` maps per-effect null to no override.
   Separately, typed `CursorMotionEffects` uses Option at
   `cua-driver-contract/src/cursor.rs:333-335`; its existing test at `:613-614`
   explicitly expects null to collapse to None. Fork #118 already owns its fix
   and direct/nested regressions; no duplicate test/fix was authored here.
   **Attribution nuance:** #115/#4871 already uses `Option<bool>` with omission
   serialization at `cursor.rs:287-288`, so the general typed-null/omission
   collapse is not shown to be newly introduced by #4888. Do not label every
   raw reset broken or all typed-null behavior a new regression on this evidence.

## Native handoff and limits

No cargo/rustc in this executor, no staged UniFFI .so, no native Node SDK library,
no display. Primary worker retains Rust build/format/testkit/live inventory scope.
Existing focused reset tests to execute once its exact-head build is available:

```sh
cd libs/cua-driver/rust
cargo test --locked -p cursor-overlay --lib motion_defaults::tests -- --nocapture
```

This command is a handoff, NOT an executed result. It includes authored saved-config
and effect-reset tests; a native direct-vs-batch numeric witness still needs a safe
test registry or desktop fixture. No host input/config/security mutation occurred.

Napari controls remain at `/workspace/scratch/dot-napari9515/`. Its fork lookup
returned HTTP 404, so no downstream evidence push was made. Library 403 was not
bypassed. Physical pressure/cold disk/baseline extension remain blocked.
