# Native compatibility validation for #4888

Fork-only repair based on injaneity's unchanged upstream head `6dba09b0394f93b0d6a7ad0cc31c62c764538af1`.
The implementation and tests are byte-identical to the locally native-tested code candidate `fcfa929ee923b44e5fab971df5bcdb9a66927518`. Publication preserves PR #118's original commits as ancestors. Raw execution logs and environment metadata are retained locally and are not part of this publication.

## Changes and attribution
- Preserve omitted versus explicit null/default cursor effects through typed direct and start-session JSON round trips.
- Preserve Python and TypeScript legacy boolean effect aliases through generated SDK lowerers and actual native FFI. Generation owns the change; explicit enums remain supported.
- Preserve Linux numeric set_value admission parity between direct and batch calls without widening the advertised Vertex-compatible schema.
- Credit @injaneity for #4888's typed/Vertex design and shared testkit, @kvnloo for the compatibility repairs and #4871/#115, and @RitikaxG for the original live-inventory diagnosis.

Correction to earlier review: Serde Option<bool> already collapsed explicit null into omission before #4888. The typed-null repair fixes that older issue. Native SDK boolean rejection is the separately demonstrated #4888 compatibility change.

## Verified local results
- Rust contract: 66 passed, zero ignored.
- Cursor overlay: 93 passed, zero ignored, including five effects and null/default/true/false plus omitted peers.
- Actual native Python cursor tests: 5 passed, zero skips.
- Actual native TypeScript cursor tests: 5 passed, zero skips; typecheck passed.
- Canonical fresh UniFFI generation and drift check passed. Formatting and generated manifest drift check passed.
- Source-built direct-stdio MCP: 63 live tool input schemas checked; numeric direct/batch admission passed.
- Mutation and unchanged-lowerer comparisons established RED/GREEN for null reset intent and native SDK boolean aliases.

Python None and TypeScript undefined mean omission; use the Default enum for an SDK reset. TypeScript null and invalid strings/objects/arrays/enums are rejected. Numeric TypeScript enum values remain supported.

## Explicit limits
- Core suite: 938 passed, 13 failed in environment-dependent perception-worker fixtures.
- Canonical daemon transport blocked before readiness by AF_UNIX bind permission; direct stdio does not certify it.
- Broader Python suite: 20 passed, 2 fixture errors. Broader TypeScript: 16 passed, 2 failed, 1 cancelled; socket and missing display-runner limitations.
- Numeric checks assert exact pre-input refusal with no element token: argument admission only, not delivery to a GUI application.
- No desktop input, cross-platform GUI matrix, release packaging, external-provider or merge-readiness certification.
- #4888 intentionally still rejects run_actions observe strings "true"/"false". This branch does not restore them and does not claim every legacy input is preserved.
- Clients validating locally against the advertised schema may still reject legacy raw forms before dispatch.

## Reproduction
From libs/cua-driver/rust:
```sh
cargo fmt --all -- --check
cargo test --locked -p cua-driver-contract --lib
cargo test --locked -p cursor-overlay --lib
cargo run --locked -p cua-driver-contract --bin cua-contract-gen -- all --check
cargo test --locked -p cua-driver --test protocol_set_value_compat_test -- --nocapture
cargo test --locked -p cua-driver --test protocol_schema_test explicit_direct_tools_list_schema_shape -- --exact --nocapture
```
From the repository root, with the repository-pinned toolchain and supported native prerequisites:
```sh
node libs/cua-driver/scripts/generate-uniffi-bindings.mjs
node libs/cua-driver/scripts/generate-uniffi-bindings.mjs --check
(cd libs/cua-driver/python && CUA_DRIVER_REQUIRE_UNIFFI=1 PYTHONPATH=src python3 -m unittest tests/test_cursor_motion.py -v)
(cd libs/cua-driver/typescript && npm run typecheck && npm run build && CUA_DRIVER_REQUIRE_UNIFFI=1 node --test test/cursor-motion.test.mjs)
```

