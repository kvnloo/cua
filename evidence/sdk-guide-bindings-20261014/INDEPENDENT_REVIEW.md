# Independent review: SDK consumer-contract evidence

Reviewed on 2026-10-14, approximately 15:27–15:30 UTC.

## Verdict

No publication-blocking issue found for this narrowly scoped evidence packet. The two reported consumer failures are reproduced, rather than fixed. This is not approval of native operations, exact-main binary behavior, a complete documentation example, a production change, or merge/release readiness.

## Independently checked

- Reran the existing Python consumer probe in the existing isolated environment: **8 of 8 expected outcomes**. Its output agrees with the original after normalizing process-specific object addresses in the printed signature.
- Reran the existing TypeScript consumer probe with the existing TypeScript 5.9.3 compiler and Node types: **4 of 4 expected outcomes**. Its JSON output agrees byte-for-byte with the original. Three compiler exits are intentionally nonzero; these are negative controls, not successful examples.
- Recomputed all three archive SHA-256 values and both npm SHA-512 integrity values. Checked every extracted ordinary npm file against its archive: 22 driver-package files and 138 core-package files matched. All 12 unchanged wheel members matched the installed bytes; the installer-managed RECORD is the sole changed archived member, explained by installation metadata and the entrypoint. No installed SDK source or native payload was changed.
- Read the probes and the real package imports/declarations. Python imports the real wheel classes; the two small namespaces supply only inert pid/window_id inputs. The guide constructor is obtained from the pinned document AST. The TypeScript fixtures use a type-only import of real published declarations and real tsc with strict checking and skipLibCheck=false. There is no substitute record implementation, any shim, fake declaration, or JavaScript native import.
- Independently read GitHub main and pinned directory metadata. Main still resolved to `8be7052a063aacb58c4d743b4e7efa3afd78143a`; the guide and both generated Python blob IDs match the locally recomputed IDs. Read the pinned TypeScript source's actual ToolResult declaration and confirmed the same field names. This does not make the released TypeScript declarations byte-identical to main, nor establish main's native binary identity.
- Independently read origin issues [#4683](https://github.com/trycua/cua/issues/4683) and [#4684](https://github.com/trycua/cua/issues/4684): both remain open, reported by coygeek and assigned to injaneity. Downstream [#152](https://github.com/kvnloo/cua/issues/152) and [#153](https://github.com/kvnloo/cua/issues/153) exist and explicitly preserve implementation ownership. The broader carrier/deduplication searches in origin-snapshots.json were not independently rerun; their stated bounded-search limit is appropriate.

## Interpretation and limits

The controls support exactly the stated conclusions: adding only max_image_dimension=None permits construction; 0 and None remain distinct stored values; required and invented keywords are rejected; verified is absent; action, verification and raw JSON are present at the record/type boundary. The optional Python values are None fixtures, not populated runtime results. These checks do not establish capture defaults, verification success, action delivery, driver behavior, or UI effects.

Python import loads the released native library and executes generated FFI contract/version checks. It is therefore real import/ABI evidence, not a native-operation test. No driver instance or driver method was invoked by the reviewed probes. TypeScript uses a relative declaration import, so it does not certify package installation/export resolution or runtime loading. Eight Python rows and four compiler cases are an accurate count of these checks, not twelve end-to-end tests.

Replay succeeded using the existing environment. A clean-host replay still requires fetching/verifying the pinned archives and providing the recorded compiler and type versions. The packet now correctly calls commands.txt procedural preparation notes plus recorded invocations, not an automated installer. No fresh installation or build was attempted in this review. Exact compiler diagnostics and Linux /proc mapping checks deliberately make the probe environment-specific.

## Publication hygiene and review artifacts

Read and scanned the 22 proposed existing publication files: README, provenance, pinned guide, commands, both probes, origin snapshot, the original eight log files, three independent review logs, and four TypeScript fixtures. No credentials, private keys, authentication URLs, contact emails, or unrelated personal information were found. The files contain relevant public GitHub handles and sandbox/toolchain paths. Excluded raw registry metadata does contain publisher/maintainer contact emails and should remain excluded, along with archives, installed environments, caches and package sources.

Review outputs are logs/review-python-contract.json, logs/review-typescript-contract.json and logs/review-artifact-parity.json. This review added less than 32 KiB and performed no installation, build, GUI/daemon/input operation, package edit or public write. SHA256SUMS is to be generated after the final review file is in place; verify that final manifest and the publication allowlist before pushing. This review does not independently certify a future branch or commit.
