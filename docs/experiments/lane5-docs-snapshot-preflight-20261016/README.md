# Lane 5: native Driver documentation snapshot preflight

QA class: **CHECK / SOURCE_ONLY**, independently inspected exact PR #110 head `b8fd5c189545dcd658c694c5ca28faa19fc73fd7`.

A new `browser_motion_policy` tool is registered by `register_browser_tools` and included in `.github/scripts/cua-driver-mcp-compat/expected-tools.json`, but the committed `cua-driver-mcp-{linux,macos,windows}.json` snapshots do **not** expose it (live repo readback).

| Host | Tool count | Native snapshot blob | Has browser_motion_policy |
|---|---:|---|---|
| Linux | 62 | `d9b74f55758a7cb2063542f60741a6d7216e33ca` | No |
| macOS | 58 | `a34de45638d5fad4da44dc7bb8cf6a3507cb909a` | No |
| Windows | 59 | `8b0f09d484dd7f28cd86cc9054dd8c35b58a33da` | No |

**Why this matters:** `.github/workflows/ci-check-docs.yml` runs native `cua-driver` reference checks for all three hosts on Driver source changes. `scripts/docs-generators/cua-driver.ts` builds Driver and runs `dump-docs --type all`, then checks native snapshot + rendered MDX. As the new tool is in registration but missing in all three committed snapshots, **native docs drift is predicted** if the Driver includes the registered tool as expected. This is source-level inference; CI has not actually run on this head.

**Executed:** 10/10 live GitHub source assertions (registration, native generator, check mode, workflow routes, compatibility roster, three missing native snapshots); seven local Python unit tests on the fail-closed preflight verifier. No Driver, Rustfmt, SDK CI, model, or A/B latency result. No performance claim.

**Next:** refresh *each native host's* MCP registry using the repository's generator or the three CI-generated native snapshot artifacts; regenerate affected reference MDX; run exact-head native Rustfmt/SDK/Docs/Driver CI. Do not invent a platform snapshot or hand-edit runtime schemas. Keep PR #110 draft and existing contributors' credit. PR: https://github.com/kvnloo/cua/pull/110; upstream scope remains read-only.

**Credit:** Existing #110 implementers and CUA browser binding/authorization maintainers own the underlying work; this note is an independent source-level CI preflight, not a claim of implementation authorship.
