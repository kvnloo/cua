# Canonical Linux snapshot/docs check: blocked setup

This small addendum preserves the completed qualification checkpoint 0e3acf4610649a7859f8ede3f8da30303659a63c and all nine earlier evidence files unchanged. The tested composition remains tree 9727e8cee4ec17c787b22457a72de36101a3b7be; the evidence branch retains injaneity's unchanged production source.

The canonical Linux snapshot/shared-docs drift result is NOT_RUN. A first names-only setup preflight stopped at inherited NODE_PATH (exit 78, before any Node/Driver launch). After its module closure was reviewed and NODE_PATH preserved unchanged, the exact official pinned tsx launcher failed at its required Unix-socket listen with EPERM (exit 1, no timeout, empty stdout). Independent source/control-flow and output review confirms this precedes generator/script-child and Driver dump execution. It is a launcher setup blocker, not an observed docs drift failure.

No retry, different launcher, transport, permission change or host substitution was used. Only a new tsx directory appeared under the fresh isolated temp root; tracked source and verified Driver/launcher/esbuild/generator/Node hashes stayed unchanged.

## Reproduction in a suitable authorized environment

Use the reconstructed exact public composition and qualified Linux Driver binary. The official docs-lock subset is tsx 4.21.0, esbuild 0.27.2, get-tsconfig 4.13.0, resolve-pkg-maps 1.0.0 and @esbuild/linux-x64 0.27.2; all five tarballs matched the tracked SHA-512 integrities, with no install/lifecycle scripts executed.

Canonical command: node <pinned-tsx>/dist/cli.mjs <checkout>/scripts/docs-generators/cua-driver.ts --check, with the supported CUA_DRIVER_BINARY=<qualified-driver> override. It preserves the canonical generator and normal finite-command wrapper, skips another Cargo build, and obtains the native snapshot through dump-docs --type all --pretty. --check compares without writing generated source/docs.

This launcher requires a permitted local Unix socket, Node child processes and the piped esbuild service. Use a short fresh isolated TMPDIR/cwd/HOME/XDG root and supported TSX_DISABLE_CACHE=1 before starting parent Node. Preserve inherited authorization and opaque host controls; do not remove them to run the check. Both CUA_DRIVER_POLICY_FILE and CUA_DRIVER_MANAGED_POLICY_FILE must be absent case-insensitively because the canonical extractor strips them; if either is configured, stop for legitimate review rather than clearing it. Keep nesting/display absent and telemetry/background updates off as recorded. No source edits, hidden wrapper bypass or weakened comparison are needed.

Only Linux's native registry plus shared CLI/rendered docs could be qualified by a successful run; macOS and Windows snapshots remain committed-source inputs until native runs on those hosts. Existing canonical UniFFI, native SDK planner and Driver metadata/EOF lifecycle receipts retain their narrow passes. Full composed core remains FAIL: 942 passed / 13 failed. Desktop/actions, tools/call, provider, old-native ABI and broader merge/readiness claims remain outside this evidence.

receipt.json transparently embeds the setup receipts, exact startup stderr and independent terminal audit. Each original and portable byte hash is preserved; only disclosed local path tokens were substituted. It contains no binary, cache, home, credential, opaque environment value or working source-review report. Raw originals remain local.
