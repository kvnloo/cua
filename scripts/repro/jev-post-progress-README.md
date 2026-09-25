# Jev: failure after partial progress

Fork-only validation of `trycua/cua` PR #3961, exact product candidate
`737cda114ae711713a3dbfa9c9ba76863dfd46b9`. No product file, contributor branch,
public API, or release configuration is changed.

## Intended outcome

Typing is already an effect. When the next provider response is invalid or
unavailable, stop without submitting or repeating the first action. Stopping
is not rollback: the earlier text may remain in the field.

Six hosted cases use the actual Python/TypeScript runner, HTTP, byte-forwarded
MCP, Cua Driver and Chromium. Each language gets a valid two-action control,
an invalid second candidate, and HTTP 503 on the second decision. The provider
is an owned deterministic fixture, not a live model. The original first-call
invalid-choice cases were already verified in workstream `4187a6b5`; they are
not being rerun as new work.

A test-only listener appended to the existing fixture reports `input`/`change`
events to a separate endpoint. It does not write the field. The second provider
response waits for a receipt of the expected text before injecting its fault.
Acceptance requires exactly two provider requests, exactly one `browser_type`,
no `browser_click` on failure, an abstained runner result with the correct
reason, and independently unsubmitted form state. Positive controls require
one submission with the expected token. The MCP auditor never stores arguments.

## Validation layers

Eight controller/fixture tests passed locally against the exact fixture blob
`c30aea8a2629f52b74f1314b53fe9bfdd8a3cde3`. They include real loopback HTTP and
negative oracle checks (missing evidence, duplicate input, unexpected mutation,
submission after failure, false status, and extra provider calls).
Those eight tests do **not** execute a browser or certify the product.

The separate hosted workflow builds the unchanged product using the existing
canonical Linux recipe's four bootstrap steps and then runs the six cases in
a disposable Xvfb/D-Bus desktop. The source is checked before and after. Logs,
input receipts, HTTP decisions, MCP method names, result JSON and SHA256SUMS are
retained even on failure. Native/browser completion must be read from the run;
creating this controller is not a passing native result.

Reused controller helpers are from `4187a6b5c35b934f31c9b77f0376e9bc0a0ebf51`:
`jev_wave1_http.py` supplies the unchanged byte-forwarding proxy and
`run_canonical_jev_browser.py` the recipe extraction/provenance checks.
No new input permission bypass is added; only the existing disposable recipe's
explicit test settings are preserved.

## Reproduction and limits

For controller checks, set `PYTHONPATH` to the pinned candidate's
`libs/cua-driver/examples/jev-use` and run:

```sh
python -B -m unittest -v test_jev_post_progress.py
```

The fork workflow contains the reproducible hosted setup. No automation is
scheduled and no external endpoints or credentials are used. Six cases do not
prove general recovery, all possible schedules, live-provider quality, other
platforms, or full desktop certification. Elapsed values are fixture-level
wall times through server cleanup, not model/Driver latency measurements.

Authored with AI assistance under the contributor's direction.
