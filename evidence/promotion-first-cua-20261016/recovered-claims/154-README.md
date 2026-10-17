# CUA #4898: bounded timeout-revalidation evidence

**LIMITED / independently reproduced file-level PASS.** This packet tests an existing guard; it contains no production repair and does not replace human review or required CI.

- Origin: [trycua/cua #4898](https://github.com/trycua/cua/pull/4898)
- Evidence tracker: [kvnloo/cua #154](https://github.com/kvnloo/cua/issues/154)
- Implementation owner: TanishGudise. Assigned human reviewer: ddupont808. The origin `risk:human` gate is unchanged.
- Exact candidate: `4fa9c8e8ba2e11cc9a0a98f1ad057886117988b3`; reported base: `9efe357a11cfb7d62487031bdc3d17463b9437df`.
- Exact [worker_server.py](https://github.com/TanishGudise/cua/blob/4fa9c8e8ba2e11cc9a0a98f1ad057886117988b3/libs/cua-bench-rl/cua_bench_rl/workers/worker_server.py) blob: `524413d0cc3fbe662805010c320ba4f2537aa7a2`; SHA256: `60266d6a5ebd9aa05926c2f2fecc0ef9e96cb36264102b44dff6922647d4f68d`.

## Question and supported result

The author explicitly notes missing deterministic coverage for an environment accessed between timeout selection and release. The real checker first selects an expired environment, drops its real `threading.Lock`, and reaches a test-side release barrier. The main event-loop thread then calls the real `_get_env`, updating the original `EnvState` under that same lock. The checker resumes into the unmodified `_release_env` with its original expiry cutoff.

At cutoff 1000 and timeout 300:

| Control | Timestamp at release | Candidate | Deliberate mutant |
| --- | ---: | --- | --- |
| Expired, untouched | 0 | Closed once; slot returned | Same, PASS |
| Refreshed after selection | 1000 | Original state remains registered and open | Wrongly closed, FAIL |
| Exact timeout equality | 700 | Original state remains registered and open | Wrongly closed, FAIL |
| Still expired after touch | 699 | Closed once; slot returned | Same, PASS |

Both the primary execution and independent rerun produced **4 PASS** for the candidate and the expected **2 PASS / 2 FAIL** for the mutant. Every case drained pending close futures. All four executions recorded zero guard denials and ended with only `MainThread` alive.

The equality and 699 controls deliberately move the controlled clock backward after selection. They are constructed threshold controls, not claims about a naturally occurring clock sequence. The timestamp-1000 case models the ordinary access-between-selection-and-release race.

The negative control changes only `if state is None or expired_at - state.last_accessed <= state.timeout:` to `if state is None:` in `mutant/worker_server.py`. It preserves the missing-state safeguard. The mutant is intentionally incorrect, is not an observed production defect, and is never placed on a production branch. See `mutant/mutation.patch`.

## What actually ran

`probe.py` loads the complete, byte-verified candidate file through Python's file-module loader. Its absolute imports resolve to nine complete, unchanged genuine `cua_bench` dependency files, frozen under `dependency/`. Those files match the existing checkout's index blobs and content hashes, with a clean tracked-checkout status. The checkout reports commit `2600a2abb095a70e01a56bfe8f8308a03b4cdc67`; this is a separately qualified dependency source, not the PR's full dependency tree. See `dependency-provenance.json`.

The `cua_bench_rl.workers` package initializer and its unrelated client/manager imports are not executed. The frozen dependency directory is an incomplete import closure, not a complete package installation. No function was extracted, rewritten or replaced with a source stand-in. Real `_timeout_checker`, `_get_env`, `_release_env`, `_close_env_soon` and `_close_env_async` execute; only the environment's `close()` is inert and records calls.

Test-side adaptations are explicit:

1. Suppress the one identified import-time timeout daemon, recording its target. Automatic daemon startup/lifetime is outside this result.
2. Run the real checker in one owned thread for one controlled sweep.
3. Replace only the module's clock and the call-site wrapper around release with deterministic test barriers; the wrapper invokes the original release function.
4. Set the real server-loop reference to the owned asyncio loop, so the actual cross-thread close scheduler executes.
5. Refuse any environment-factory call.

## Isolation and replay

`commands.txt` contains the exact launchers. Each uses the existing Python 3.12.14 interpreter with `-I -B`, an empty HOME, an explicitly sanitized environment, a 20-second outer timeout, 15-second CPU bound and 1-GiB address-space bound. Source/evidence disk use is below 500 MiB. No dependencies were installed.

Audit/import/thread guards precede target imports and reject IP sockets/network access, child-process creation, native SDK/environment modules, filesystem writes and unapproved thread starts. Reads are restricted to the packet, approved dependency source and installed Python runtime. These are Python defense-in-depth checks, not a claim of an adversarial OS security boundary.

The first import-only preflight correctly stopped because importlib needed to list the already-approved dependency search directory. It ran no case and started no thread. A specifically authorized directory-listing-only correction preserved file-read, network, process and environment restrictions. Its original log and rationale remain in `logs/import-only.json` and `guard-adjustments.json`. The subsequent import preflight passed. Later packaging copied the already-read genuine dependency files into this packet without fetching or broadening read scope.

For replay, use Python 3.12 and the versions in `environment.json`, substitute local packet/interpreter/empty-HOME paths in the launcher, and retain its isolation flags, limits and source hashes. Candidate exit is 0; the deliberate mutant exits 2 with exactly the two preservation controls failing.

## Evidence and limits

- Final primary runs: `logs/final-head.json`, `logs/final-mutant.json`.
- Independent runs: `logs/reviewer-head.json`, `logs/reviewer-mutant.json`.
- Independent assessment: `INDEPENDENT_REVIEW.md`.
- Earlier runs remain separately named; they are not added to the distinct-case count.
- No main/base regression run was performed: the negative control is the specifically labeled recency-guard mutant.
- No full-package suite, live sandbox, VM/container, driver, provider, credentials, host input, RL training or automatic daemon lifecycle was exercised.
- The author's client-404 recovery and #4899/#4929 scopes are not reviewed here.
- Six origin head workflows were awaiting maintainer approval when qualified. This packet does not approve them, satisfy the `risk:human` gate, or authorize an origin post, merge or release.

Credit remains with TanishGudise for the implementation. This packet contributes bounded independent evidence only.
