# NEW Linux native SDK qualification addendum

This is additive evidence for checkpoint 81dfc6008ac59bc5739bcafaef56c03ac37f9c4d. Its original README, manifest and public-evidence archive remain byte-for-byte unchanged. All results below are NEW after workspace reset, on tested public composition 9727e8cee4ec17c787b22457a72de36101a3b7be, reconstructed from the original checkpoint. Production owner e7d056e8def8d5e0027025ee7b9511280bf8f8c5 remains untouched on the evidence branch.

## Time-stamped supersession

- First canonical SDK attempt failed at 2026-10-10T15:20:28Z: Cargo 101 / node 1, missing xproto/kbproto discovery. Official files already existed in the isolated sysroot. A versioned process-local pkg-config path added its share/pkgconfig directory; no dependency, feature, source or system setting changed. The failed logs remain preserved.
- Canonical binding check passed at 2026-10-10T15:37:13Z, superseding only the original binding-drift NOT_RUN. The full unedited generator built the default Linux SDK cdylib and generated Python/TypeScript bindings; all seven owned files and two inventories match the frozen source.
- Native fixtures observed terminal by 2026-10-10T15:43:57Z: Python 5/5 and TypeScript 5/5, CUA_DRIVER_REQUIRE_UNIFFI=1, zero skips. TypeScript source typecheck and fresh package build also pass. Each fixture file has five top-level tests; 20 legacy-effect subcases occur inside one test.
- Independent replay passed at 2026-10-10T15:44:57Z: five tests per language, zero skips; actual Python ctypes/SDK process mappings and Node SDK+bridge mappings match the recorded hashes. All 28 inspected source/dist/native/lock artifacts remain unchanged. Independent retained-output canonical comparison matches nine frozen Git blobs and rejects two output mutations. No duplicate native build is claimed.

Full composed core remains FAIL: 942 passed / 13 failed. Those exact 13 selected failures also fail on unchanged main as previously documented; this is not a full-main pass or general environmental-cause proof. Original V1 compiler failure and V2 failed test oracle remain untouched in the first archive.

## Scope and reproduction

Canonical command: node libs/cua-driver/scripts/generate-uniffi-bindings.mjs --check --keep-temp. SDK release and Python bindgen are separately locked. Official UBRN 0.31.0-3 and the canonical NAPI bridge builder use Cargo without --locked: package/source versions, actual resolved locks and executable hashes are recorded, but a fully locked or hermetic generator/bridge graph is not claimed. Keep that limitation when repeating the command.

Canonical staging: node libs/cua-driver/scripts/stage-uniffi-library.mjs. It receives the identical completed SDK through an ignored artifact link at rust/target/release; its unedited temporary-runtime builder uses its own target directory. No generator or drift check was weakened.

Use the unchanged public fixtures from the reconstructed source. From libs/cua-driver/python, set CUA_DRIVER_REQUIRE_UNIFFI=1 and run PYTHONPATH=src python3 -m unittest discover -s tests -p test_cursor_motion.py -v. From libs/cua-driver/typescript, run npm run typecheck and npm run build, then CUA_DRIVER_REQUIRE_UNIFFI=1 node --test test/cursor-motion.test.mjs.

The native calls exercise current cursor planner ABI, golden trajectories/specs, valid legacy booleans and invalid input refusal. Python None, TypeScript undefined and enum Default establish planner acceptance; they do not establish persistent reset semantics. TypeScript null is refused by the tested runtime and strict type fixture. JSON null wire reset, tool transport, actual Driver/MCP, desktop/GUI, other OS, provider acceptance and old-native-binary ABI compatibility remain unverified here.

The archive includes sanitized concrete receipts, logs, source/artifact identity mappings, resolved locks and observation wrappers. It excludes executables/libraries, caches, homes, machine paths and working reports. QUALIFICATION_ROOT and HOST_* tokens replace paths; observation wrappers are preserved as normalized evidence and require replacing those tokens to rerun. normalization-map.json maps every raw-original hash to the exact normalized bytes. Raw originals remain local. No source schema implementation, landing request or product/readiness certification is implied. Original injaneity ownership and Kevin Rajan compatibility repair credit remain preserved.
