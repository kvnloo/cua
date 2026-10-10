# NEW Linux live metadata/EOF lifecycle evidence

This addendum extends fa5e08dcab195d97027699305cc125af4e53ef7b. All six earlier evidence files remain byte-for-byte unchanged. It records a NEW locked Driver build and bounded metadata-only runtime on the same tested public composition tree 9727e8cee4ec17c787b22457a72de36101a3b7be. The evidence branch retains injaneity's unchanged production owner source e7d056e8def8d5e0027025ee7b9511280bf8f8c5; it differs from the separately reconstructed/tested composition.

## Observed result

- Locked one-job release build: cargo build --locked --release -p cua-driver, from libs/cua-driver/rust, terminal 2026-10-10T16:07:58Z, exit 0. Driver binary SHA-256 8278bf0df45d0f2656957c1a8b71a8c58a18d9c4cb39527f4590b21e213cee06.
- At 2026-10-10T16:08:26.981557Z, the actual binary handled the exact initialize and tools/list requests, followed by EOF. Two success responses advertised 64 unique tools. Protocol version 2025-06-18; server cua-driver 0.34.0.
- run_steps and default run_script appear in the live inventory; the legacy run_actions name is absent from advertisement. No tools/call was sent, so this observation does not exercise hidden-alias dispatch or script execution.
- Clean process exit 0, no timeout, empty stderr and unchanged isolated filesystem. Elapsed 0.256942509 seconds is descriptive process time, not a benchmark. Binary hash, frozen index tree and tracked working source remain unchanged.
- Independent read-only output audit verified these records at 2026-10-10T16:09:42.850695Z, without another runtime execution or build.

## Exact bounded scope

The process used cua-driver mcp --direct --no-overlay under a 30-second supervisor. Its exact two request lines are included as runtime/requests.jsonl (SHA-256 957000262a3d5bc1ac04147da8d4dd235549eb2b69dcadf494a0d442a9dd82ba); stdin then closed. No extra RPC, notification, tool invocation, session/action, desktop operation or permission grant was sent. Supervisor source SHA-256 is 3070e20d94a662ebb4cc6be42229b26e1d4729a9451080960ff4819ec10ef1ff.

The process used fresh isolated cwd, HOME, TMPDIR and all XDG roots. DISPLAY, WAYLAND_DISPLAY and CUA_WAYLAND_NEST were absent. Dummy nonexistent XAUTHORITY and session-bus paths prevent the inspected discovery paths; NO_AT_BRIDGE=1 explicitly skips the Driver accessibility advertiser/listener, and --no-overlay disables its overlay. Telemetry and background updates were opted out. Normal built-in standard authorization remained in effect. Two inherited host controls were preserved opaque and byte-unchanged; their values were never inspected, logged, hashed or serialized. Any configured policy/manifest/grant ceiling must be preserved and reviewed before repeating this isolated metadata probe. Do not discard authorization controls to reproduce the inventory.

The frozen runtime receipt lists the portable process guards. Replace QUALIFICATION_ROOT, ISOLATED_SYSROOT_LIB and HOST_BIN_PATH tokens with appropriate local paths when reconstructing this observation; use fresh roots, not an existing user session. Raw stdout and stderr are preserved apart from disclosed portable path normalization. Each original and normalized byte hash is mapped in normalization-map.json. The archive excludes executables, caches, homes, machine paths and working reports.

## Remaining gates

This supersedes only the earlier Linux Driver metadata/EOF lifecycle NOT_RUN. It does not establish actual tools/call, hidden run_actions invocation, run_script execution through Driver, canonical snapshot generation, desktop/GUI input or capture, provider acceptance, other OS, old-native ABI compatibility, or empirical syscall/network certification. Full composed core still fails: 942 passed / 13 failed. The previous native SDK five-test gates and their unlocked UBRN/NAPI Cargo resolution caveats retain their separate scope. This is qualification evidence, not merge or release readiness, and preserves original contributor credit.
