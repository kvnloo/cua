# CUA SDK guide consumer-contract evidence

**LIMITED, independently reproduced.** Eight Python checks and four TypeScript compiler checks pass their stated expectations. The two advertised examples remain broken at the consumer boundary; this is evidence, not a fix or merge-readiness claim.

- [Origin #4683](https://github.com/trycua/cua/issues/4683): the printed `GetWindowStateInput` constructor omits required `max_image_dimension`.
- [Origin #4684](https://github.com/trycua/cua/issues/4684): the generic result field list advertises nonexistent `ToolResult.verified`.
- [Downstream #152](https://github.com/kvnloo/cua/issues/152) and [#153](https://github.com/kvnloo/cua/issues/153) own these evidence mirrors. Coygeek reported both issues; injaneity remains assigned. No production patch or competing implementation is included.

## Versions and evidence boundaries

Origin main was `8be7052a063aacb58c4d743b4e7efa3afd78143a` at qualification. The [guide](https://github.com/trycua/cua/blob/8be7052a063aacb58c4d743b4e7efa3afd78143a/docs/content/docs/cua-driver/guides/use-the-sdk.mdx) is retained byte-for-byte as `source-use-the-sdk.mdx` (Git blob `b707577d18521010a759de8cd7dc4a9cb5be3583`). Both issues remain open, with the original assignment comments only. Exact-number all-state PR searches and bounded semantic/downstream searches found no dedicated carrier. This is not an exhaustive absence claim.

Python used the official PyPI `cua-driver==0.35.4` manylinux x86_64 wheel, Python 3.12.14, Linux x86_64, glibc 2.41. SHA-256: `b4e415c068687946948065f444e51dbb4e190c34d3e527554ec18db668843588`. The whole installed `_native.py` and `_native_contract.py` files match the corresponding current-main Git blobs, `829ecf0ef305901e28a9c27219496dd96a81e96b` and `ce424c1cefdc2dd7e9a5244dce7a7daf780b0499`. `/proc/self/maps` confirms the wheel's actual native library was loaded. That library remains a released 0.35.4 artifact, not a newly built current-main binary. No native driver method was invoked.

TypeScript used the official npm `@trycua/cua-driver@0.33.4` package, unmodified declarations, real TypeScript 5.9.3, `@ubjs/core@0.31.0-3`, `@types/node@22.20.4`, and `undici-types@6.21.0`. The compiler and Node types were already installed; no compiler install was needed. Compilation used strict checking and **`skipLibCheck=false`**, with no `any` shim or fake declaration. npm metadata for 0.35.4 returned HTTP 404; no 0.35.4 npm artifact is claimed. Current-main TypeScript source independently agrees on the field names, but the 0.33.4 declaration artifact is not claimed byte-identical to current-main source.

All downloaded archive integrity checks passed. `artifact-provenance.json` holds exact registry URLs, versions, hashes and source identities. Binary archives and installed environments are intentionally not included in the evidence branch.

## Results

### Python, eight expected outcomes

1. The constructor expression is parsed directly from the pinned guide. Only `app.pid` and `window.window_id` are supplied as inert integer fixtures. It calls the actual imported `GetWindowStateInput`, not a reconstructed class. Exact failure: `TypeError: GetWindowStateInput.__init__() missing 1 required keyword-only argument: 'max_image_dimension'`.
2. Adding only `max_image_dimension=None` constructs successfully; every printed argument retains its value.
3. A separate `0` record stores `0`, distinct from `None`. This tests record values only and makes no capture-limit claim.
4. Removing `pid` produces its exact missing-keyword TypeError, guarding against an inert stand-in constructor.
5. Reading `verified` from a real imported `ToolResult` raises the exact `AttributeError`.
6. Its actual fields are `text`, `images`, `structured_json`, `is_error`, `error_code`, `action`, `verification`, `degraded`, `raw_json`. Valid optional fields and raw JSON remain accessible.
7. Passing an invented `verified=True` keyword raises the exact unexpected-keyword TypeError.
8. Omitting the real `verification` keyword raises its exact missing-keyword TypeError.

The guide's omitted argument fails before any driver call. The None control preserves the guide's printed argument choices; this experiment does not certify the subsequent capture/click workflow.

### TypeScript, four expected outcomes

1. The valid consumer compiles with no diagnostics.
2. `result.verified` fails with exactly `TS2339: Property 'verified' does not exist on type 'ToolResult'.`
3. Treating `result.verification` as a boolean fails with `TS2322`; its type is `VerifyStateOutput | undefined`.
4. Omitting required `rawJson` fails with `TS2741`.

The three nonzero compiler exits are expected negative evidence, not a green claim about the faulty guide. An initial compiler preflight lacked the ambient NodeJS namespace; supplying the already-installed Node types resolved that environment gap. Declaration checking stayed enabled.

## Requirement and semantics

The existing supported guide tells readers to install these bindings and copy its example/field list. Both original reports independently document observed failures; maintainer assignment acknowledges the reports. This packet reproduces their narrow consumer failures. It does not decide a new runtime contract.

`action` and `verification` retain separate fields. A returned action is not proof that the UI changed. No new `verified` boolean, compatibility change, generated-source edit, or weaker verification semantics is proposed. Future documentation changes remain under the assigned owner and normal selection/promotion gates.

## Replay

Use a Linux x86_64 host with Python 3.12 and an environment containing TypeScript 5.9.3 plus the above Node types. Download and verify the pinned wheel and npm archives from `artifact-provenance.json` before extracting. Install the wheel into a fresh venv with no dependencies; unpack the npm package unchanged under `typescript/package` and `@ubjs/core` under `typescript/node_modules/@ubjs/core`. There are no npm lifecycle scripts to run for this check.

The recorded invocations and setup notes are in `commands.txt`; the preparation notes are procedural, not an automated installer. The probes do not create a driver. Run:

```sh
HOME="$PWD/home" XDG_CONFIG_HOME="$PWD/xdg-config" XDG_CACHE_HOME="$PWD/xdg-cache" XDG_DATA_HOME="$PWD/xdg-data" .venv/bin/python -I -B python_contract_probe.py
python typescript_contract_probe.py --tsc /path/to/typescript/lib/tsc.js --type-roots /path/to/node_modules/@types
```

The Python probe verifies the pinned guide and generated-source Git hashes. The TypeScript probe requires the real compiler version and exact expected diagnostic codes. Source files and logs are reviewable without executing downloaded code.

## Explicit limits

No Rust/native build; no `CuaDriver.create`, daemon, GUI, input, capture, live application or provider; no JavaScript native FFI import; no complete guide execution; no upstream suite or docs production build. The actual Python import loads the native library and performs generated FFI contract checks; this is import/ABI evidence, not execution of a native driver operation. No exact-main native certification, cross-platform runtime acceptance, bug fix, origin acceptance, or release-readiness claim follows. Total task storage is approximately 141 MiB, below the 500 MiB bound. No default branch or origin resource was changed.
