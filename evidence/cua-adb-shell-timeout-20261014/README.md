# Android ADB shell timeout forwarding

Classification: **LIMITED / Python adapter qualified**. Canonical work claim: [kvnloo/cua#148](https://github.com/kvnloo/cua/issues/148). Downstream only; no upstream contribution or live Android qualification.

## Requirement, behavior and scope

The existing public `Shell.run(command, timeout=30)` forwards the caller's timeout to its transport. Both current Sandbox Android fallback selection paths can choose `ADBTransport`. That adapter discarded the supplied value and always used the lower-level 15-second default. Thus commands could expire earlier or later than requested. The existing Android integration test requests 10 seconds; [merged #1343](https://github.com/trycua/cua/pull/1343) explicitly establishes the same SDK-controlled timeout requirement for the adjacent computer-server path.

This independent one-line correction forwards `params.get("timeout", 15)` to `_adb_cmd_async`. It preserves the direct-transport 15-second default and existing exception behavior. The public default now arrives as 30 seconds. No validation policy, retry, background-command behavior, native protocol, general cancellation policy, or guest process-termination guarantee is added.

- Original triage main: `2600a2abb095a70e01a56bfe8f8308a03b4cdc67`.
- Pinned base: `8ccf531fb54b6e4f974437a8c2f5af7abc4d45d6`; intervening change is unrelated CI, with package and policy trees unchanged.
- Tested code: `16386a256a7a7d5deae7f3c54e73ea77b3dae250`.
- Final test SHA256: `50e5aea42511bf4bcfc2d5c93efb037812c3bb492b9680bfc2d3bc8475782dd6`.

## Executed checks

| Check | Result |
| --- | --- |
| Untouched base plus final test | 10 FAIL / 5 PASS |
| Candidate plus identical test | 15 PASS |
| Bounded adjacent EnvTransport tests | 20 PASS / 6 DESELECTED |
| Ruff lint, Ruff format, source whitespace | PASS |

The failing baseline cases all reach the genuine adapter and observe 15 seconds instead of the caller's value. No setup/import failure is counted as behavioral RED. Cases cover public 0/1/10/75-second values, public default 30, direct shell/execute/run_command aliases with default 15 and explicit 45, unchanged exact `TimeoutExpired` propagation without retry, command/environment/result preservation, worker-thread dispatch, failed exit/UTF-8 replacement decoding, and unchanged screen-size command timeout.

The actual Sandbox, Shell, ADBTransport, asynchronous executor and `_adb_cmd` run. Only `subprocess.run` is replaced by a recording test seam. The evidence plugin refuses native `cua` imports, real process launches and network connections. It verifies the native SDK stayed unloaded. No connection method, emulator, VM, ADB executable, guest RPC, physical desktop, or provider was used. These tests prove timeout forwarding and exception preservation, not elapsed-time enforcement or guest process cancellation.

Initial broad adjacent execution reached six cases dependent on native SDK classes and failed under the deliberate guard (20 other cases passed). A subsequent incorrect path-prefixed `--deselect` repeated those failures. Both diagnostics remain visible; guards were unchanged, and the final scope excludes those six native-dependent cases. Neither broad attempt qualifies the full package suite. Full native SDK/Android/hosted CI acceptance remains unrun.

## Ownership and provenance

Bounded current upstream/downstream issue and PR searches found no competing ADB timeout repair. Actual #3987 diff changes the former HTTP transport only; merged #1343 changes computer-server; active #1226 does not edit this adapter. Older named Android-routing, HTTP-timeout and SDK-timeout branch source retains the omitted argument. An old `fix/async_shell` adb.py lookup returned 404 and remains unverified; no alternate route was used.

Original adapter and environment-prefix implementation: **Dillon DuPont / ddupont808**, [#1218](https://github.com/trycua/cua/pull/1218), [#1242](https://github.com/trycua/cua/pull/1242); exact commits are in attribution.json. **r33drichards** authored the adjacent requirement precedent #1343. No external patch was copied. New work identifies OpenAI Codex, with no fabricated human coauthor, DCO/CLA or signoff.

The initial downstream tracking-issue creation was rejected for missing authorization evidence. The same call was retried once only after the parent supplied verbatim user authorization for downstream OSS tracking; it succeeded as #148 before source/test edits. A local branch had already been created, with no source changes at that point. Existing denied/canceled operations and other carriers remain untouched.

Exact commands, versions, guards, source hashes and whitespace-normalized diagnostic logs accompany this receipt. Raw pre-normalization log hashes are retained in environment.json. Independent review approved the bounded fix with no blocking findings. The reviewer reproduced the same RED/GREEN and matched full/scoped adjacent results on both base and candidate, confirming the six native-dependent failures are inherited under the guard. See review/REVIEW.md and its accompanying logs, import-origin audit, and source hashes. The guard is a Python-level safeguard, not system-wide isolation. No code or test changes followed review.

## Downstream publication shape

The focused draft PR targets a separate baseline branch pinned to the exact upstream base, rather than the stale fork default branch. This does not merge or update either default branch and does not claim upstream selection/readiness. The exact publication SHA and final-tree rerun result are recorded in the PR and #148 result receipt.
