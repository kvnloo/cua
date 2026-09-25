# Live-protocol evidence for modality-gated observation — REPORT

Follow-up to `bench/observation-gating/REPORT.md` (fake in-process driver,
virtual latencies). This bench answers the next question: does the gating
policy's call-pattern reduction survive the real wire format?

## Method

- `mock_daemon.mjs`: speaks the daemon's newline-delimited JSON socket
  protocol (one request per connection, same shape as
  `libs/cua-driver/typescript/test/native-daemon-fixture.mjs`). Serves a
  stateful jev-use fixture: `get_browser_state` returns semantic_v2 snapshots
  whose refs depend on scenario + prior actions; `get_window_state` /
  `parse_visual_regions` return a full `cua.visual_regions_v1` payload with a
  parameterized region count.
- `live_bench.ts`: drives the loop through a real socket client —
  real serialization, real socket IPC, real `parseVisualRegions` over the
  wire payload. Same `buildCandidates` / `chooseMock` / `needsVisualObservation`
  / `ObservationLedger` as the shipped loop.
- 3 samples per cell, median reported. Node v24.20.0, loopback unix socket.

## Results (regions=50)

| scenario       | policy   | obs calls | visual calls | obs ms (real, median) |
|----------------|----------|-----------|--------------|-----------------------|
| dom-complete   | baseline | 6         | 2            | 93.0                  |
| dom-complete   | gated    | 2         | 0            | 17.1                  |
| visual-fallback| baseline | 6         | 2            | 57.2                  |
| visual-fallback| gated    | 4         | 1            | 16.4                  |

Every run verified the task (submitted === token). The call pattern is
deterministic and identical to the fake-driver bench (6→2, 6→4): the policy
effect is a property of the loop logic, not of the latency model.

## Visual-path cost vs payload size (real IPC)

| regions | wire round-trip | client parse |
|---------|-----------------|--------------|
| 10      | 22.2 ms         | 0.02 ms      |
| 100     | 20.1 ms         | 0.05 ms      |
| 500     | 191.0 ms        | 0.14 ms      |

Client-side parsing is negligible; the wire cost grows with payload size.
The gate skips the whole visual path in dom-complete, so its saving scales
with the payload — the bigger the screenshot analysis, the more the gate
matters.

## Honest limitations

- The fixture performs no real screenshot capture and runs no perception
  model, so absolute milliseconds here are local-IPC noise (a repeat run
  measured 46 ms vs 93 ms for the same cell). Do not quote these as
  production savings.
- The production cost model is `bench.ts` (virtual latencies for capture +
  model). What THIS bench proves: the gating decision, the ledger, and the
  fallback all behave correctly against the real wire format and real
  client-side parsing — the policy's effect is not an artifact of the fake
  driver.

## ABAB

- Baseline: loop pays both modalities every step (6 obs calls / 2 visual).
- Hypothesis: the visual result is consumed only by the visual-submit
  fallback, so gating on candidate actionability preserves behavior.
- Intervention: `needsVisualObservation` gate (shipped in
  `muse/observation-gating`).
- Measurement: real-protocol bench above; 6→2 and 6→4 calls, task verified,
  fallback intact.
- Comparison: matches the fake-driver bench's call pattern exactly; the
  stronger transport did not change the conclusion.

---

Research artifact on the fork; not proposed upstream.

Authored with AI assistance (Muse, Meta's Muse Spark) under the contributor's direction.
