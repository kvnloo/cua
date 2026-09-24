# Jev verifier isolation: tested fork-only follow-up

Related work: https://github.com/trycua/cua/issues/3915, PRs #3961 and #4052.

Base source: `737cda114ae711713a3dbfa9c9ba76863dfd46b9`.

## Finding and scope

`verify_setup.py` uses the same `jev-guide-mock` token for the Python and TypeScript checks against one fixture. It checks the child's final report and the fixture's final state, but does not itself clear prior state. The current runner already resets the fixture; this is an independence gap in the verifier, not evidence that the current real browser runners fail or that prior passing results were false.

A controlled subprocess that writes a verified report but does not submit anything is rejected on a fresh fixture. If the matching result was already present, the unchanged verifier accepts it. The sequential regression proves this after a first subprocess genuinely submits the same token.

## Small candidate

The verifier calls the existing fixture `/reset` endpoint and confirms `submitted` is null before starting each child. Existing runner resets, deterministic tokens, command arguments, post-run report checks, and post-run independent state checks remain unchanged. No Driver/model/backend source, external service, new protocol, or automatic action retry is added.

Production delta: eight added lines and one removed line in `verify_setup.py`, including the import. Five new verifier tests are provided. The two already-queued browser-test PR heads are unchanged; this work is on a separate fork branch, not a competing upstream PR.

## Executed red/green evidence

Linux x86_64, Python 3.13.5, standard library. Full verifier and fixture-server modules; actual loopback HTTP and actual controlled subprocesses. No verifier function or HTTP I/O was mocked.

| Variant | Passed | Failed | Errors/skips |
| --- | ---: | ---: | ---: |
| Baseline plus new assertions | 10 | 2 | 0 |
| Candidate, identical assertions | 12 | 0 | 0 |

The 12 tests comprise seven unchanged existing verifier/fixture/lifecycle checks plus five new cases. The two expected baseline failures are `test_stale_matching_state_cannot_certify_a_noop` and `test_first_runner_success_cannot_certify_second_runner_noop`. Fresh-fixture false claims are rejected; genuine fresh and repeated submissions remain accepted.

Two original runner-launch checks were not executed here: Python CLI help and TypeScript argument validation require the complete MCP/npm environment. They were not removed or changed. No full locked example suite, real Driver/browser/MCP run, live model, or native desktop certification is claimed for this candidate.

Source Git blobs verified before execution:

- baseline verifier: `5a85df7fbc877d53b625df81cb05d2d85e380562`
- unchanged fixture server: `c30aea8a2629f52b74f1314b53fe9bfdd8a3cde3`
- unchanged existing tests: `3825bff0b800aa905acd1bbf723c47e9a0ca6200`
- tested candidate verifier: `feb867f67ce64ae8616b2f6c1b183bd5f1432527`
- new tests: `6789d07b0f533a53dbdd736139970528223c61bf`

## Reproduce new regressions

From this branch, no MCP, browser, model or third-party Python package is needed for the five new checks:

```sh
cd libs/cua-driver/examples/jev-use
python -B -m unittest discover -s python/tests -p test_verify_isolation.py -v
```

To reproduce the baseline failures without changing a working branch, copy this test file into a disposable checkout of the base source, then run the same command: three controls pass and the two named stale-state regressions fail. The tests' subprocesses are controlled verifier inputs, not a replacement for browser acceptance evidence.

## Remaining gate

Review the verifier-owned-reset choice, run the full locked example suite, then the canonical browser/MCP integration at the integrated candidate. Retain source-specific evidence: this candidate does not retroactively change or certify the two existing queued browser jobs.
