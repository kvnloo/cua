# Baseline native SDK compatibility witness — 2026-10-09

## Result

**The actual baseline native SDK accepts legacy cursor-effect booleans.**
With the exact baseline library staged beside its own committed Python bindings,
`trail=True`, `trail=False`, and omitted (`None`) each returned `CursorTrajectory`
through `plan_cursor_move`. The assertion-bearing probe exited **0**.

Compared with the already published successor native result, this establishes a
legacy Python SDK compatibility break: the same boolean calls accepted on baseline
are rejected with `ValueError` on successor. The successor's omitted and explicit
enum controls succeed. Rejection occurs in its generated lowering contract before
native dispatch; this does not claim the Rust trajectory planner rejects booleans.

## Exact sources and ownership

- Tested baseline: fork [#115](https://github.com/kvnloo/cua/pull/115),
  `2ef54490cf51b3aca224eb45a3421482666d5276`.
- Its upstream [#4871](https://github.com/trycua/cua/pull/4871) base:
  `f520a122f2a7e987544a53fb49e9301883779afb`.
- Successor [#4888](https://github.com/trycua/cua/pull/4888):
  `6dba09b0394f93b0d6a7ad0cc31c62c764538af1`.
- Prior actual successor results and original probe:
  [evidence at 647f9da10f49a448d29dd55f87baff44aca63001](https://github.com/kvnloo/cua/tree/647f9da10f49a448d29dd55f87baff44aca63001/evidence/4798-legacy-compat).

`baseline-source-diff.txt` records the complete #4871-to-#115 path diff: only
three testkit/Vertex test files differ. All runtime/SDK implementation and Python
bindings are identical. Python tree `9be9bf98bdf911ff564010696e6ab3d9a9ce2239`
and SDK tree `ad794e71c91339e64099b75bf83f4c149bb3d070` match both pins.

The fork owner and connected GitHub identity were verified as `kvnloo`; the fork's
parent is `trycua/cua`. This branch adds only evidence. No implementation changes,
upstream posts, PRs, main-branch pushes, or contributor-history rewrites.
Credit remains with kvnloo (#4871/#115), injaneity (#4888), and RitikaxG for the
original live-inventory diagnosis. This does not duplicate the typed-null fix
already owned by fork #118.

## Build: PASS

An isolated checkout and isolated Rust/Cargo/sysroot/target directories were used.
Official rustup installed the repository's exact Rust **1.97.1** toolchain, with
rustfmt required by rust-toolchain.toml. No host installation was changed.
The 32 Debian trixie packages were downloaded from deb.debian.org, verified against
the same official Packages.xz index SHA256 as the successor, then extracted using
`dpkg-deb -x`. `sysroot-packages.json` records package versions and SHA256s.

```sh
sh evidence/baseline-native-compat/build-sdk.sh
# Inside libs/cua-driver/rust, with script's recorded local environment:
cargo build --locked -p cua-driver-sdk --lib
```

Exit **0**, **2m 38s**, two jobs, debug symbols disabled. Full output is in
`build-sdk.log`; the existing nom 1.2.4 future-incompatibility warning is retained.
No release build or whole driver/testkit gate was rerun.

Built and staged library SHA256:
`d4c4634283775dd689a4688397f8288a6686ce4ceb27997d19b71ceb1ad2ae68`.
`native-library-sha256.txt` records matching source/staged hashes;
`native-library-ldd.txt` records all runtime dependencies resolved. Only baseline
bindings and its own newly built library were combined. Bindings were not generated
or edited, and no successor library was reused.

## Native-required Python suite: PARTIAL, 18 pass / 2 environment errors

```sh
cd libs/cua-driver/python
LD_LIBRARY_PATH=/workspace/shared/cua-baseline-native-compat/sysroot/usr/lib/x86_64-linux-gnu \
CUA_DRIVER_REQUIRE_UNIFFI=1 PYTHONPATH=src \
python3 -m unittest tests/test_uniffi_loader.py tests/test_remote_channel.py tests/test_cursor_motion.py -v
```

Python **3.12.14**. First invocation: exit **1**, 20 tests, 0.661s, 18 passed,
2 errors, zero skips (`native-tests-sandbox-limited.log`). A permitted elevated
execution retry still hit the same `socket(AF_UNIX, SOCK_STREAM)` **EPERM** host
restriction: exit **1**, 20 tests, 0.630s, 18 passed, 2 errors, zero skips
(`native-tests.log`). No security setting was changed or restriction bypassed.

Blocked fixture tests:
- `test_generated_python_embedded_host_owns_the_rust_lifecycle`: its Python fake
  driver cannot create the fixture socket, yielding `ExitedBeforeReady: code=1`.
- `test_generated_python_sdk_calls_the_rust_daemon_interface`: cannot create the
  fixture socket directly (`PermissionError: [Errno 1] Operation not permitted`).

All cursor-motion golden trajectory tests and foreign-channel fixture tests passed.
Fixture remote-channel coverage is not a real provider/remote transport claim.
This is explicitly **not** a 20/20 baseline pass. The successor's separate receipt
records its own 20/20 result in its execution environment.

## Identical-call probe: PASS

```sh
cd libs/cua-driver/python
LD_LIBRARY_PATH=/workspace/shared/cua-baseline-native-compat/sysroot/usr/lib/x86_64-linux-gnu \
CUA_DRIVER_REQUIRE_UNIFFI=1 PYTHONPATH=src \
python3 ../../../evidence/baseline-native-compat/baseline_native_probe.py
```

The original successor probe is retained byte-for-byte as
`successor_native_probe.py`. `probe-adaptation.diff` shows the only changes:
remove unavailable enum cases, assert expected baseline acceptance, and explicitly
assert the successor-only enum is absent. Request construction, native parameter
creation, assignments, and `plan_cursor_move` calls are unchanged.

| Input | Baseline observed | Successor observed in prior receipt |
| --- | --- | --- |
| `trail=True` | `CursorTrajectory` | `ValueError` |
| `trail=False` | `CursorTrajectory` | `ValueError` |
| `trail=None` (omitted) | `CursorTrajectory` | `CursorTrajectory` |
| explicit enum On/Off/Default | unavailable API | `CursorTrajectory` each |

`native-probe-results.json` is the actual baseline stdout, exit **0**. The full
suite runner is fail-fast, so this probe was executed separately after its two
fixture errors; no suite error was hidden or converted into a pass.

## Limits and cleanup

No display or Wayland session exists here. No desktop input, real driver GUI,
live provider, Windows/macOS, release distribution, numeric direct/batch, or raw
JSON reset certification is asserted. Existing completed live tools/list evidence
was not rerun. Cross-platform behavior still needs its own native desktop lane.

After the evidence commit is pushed and verified, only this task's rebuildable
`target-baseline`, staged `.so`, downloaded package archives/index, local sysroot,
and local Cargo/Rust toolchains are to be removed. Source checkout and published
receipt/logs/probes remain; other workers' files are untouched. Cleanup results
are recorded separately after remote verification.
