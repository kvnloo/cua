# Stage profile: where the TS loop's per-step time goes after observation gating

**Method.** `bench/observation-gating/profile_stages.ts` drives the
visual-fallback scenario through `mock_daemon.mjs` over the real JSONL unix
socket (same harness as `live_bench.ts`) and times each stage with hrtime:
snapshot fetch, DOM candidate build, visual fetch (capture RPC + wire-parse
RPC), client-side `parseVisualRegions`, visual candidate rebuild,
`chooseMock`, and ledger/gate bookkeeping. 30 iterations each at 50 and 500
visual regions. `node --import tsx bench/observation-gating/profile_stages.ts`.

**Result (median ms).**

| stage | 50 regions | 500 regions |
|---|---|---|
| snapshot_fetch (RPC) | 4.0 | 4.0 |
| build_candidates_dom | 0.02 | 0.02 |
| visual_fetch_rpc (2 RPCs) | 4.4 | 6.5 |
| parse_visual_regions (client) | 0.04 | 0.19 |
| build_candidates_visual | 0.01 | 0.01 |
| choose | 0.01 | 0.01 |
| ledger_gate | 0.005 | 0.004 |

**Reading.** After gating, every TS-side stage is sub-0.2 ms — parsing,
candidate building, choice, and the ledger are ~1–2% of per-step time. The
remaining cost is the RPC round trips themselves (~4 ms each on loopback,
scaling with payload on the visual path). The next optimization is not in
TS code: it is transport batching — the loop makes three separate socket
round trips per step (snapshot, capture, wire-parse). Pipelining
snapshot+capture or folding the wire parse into the capture response would
cut per-step round trips from 3 to 1–2.

**Honest scope.** Mock daemon on loopback: absolute ms is local-IPC noise
(p95 spikes to 89 ms on snapshot_fetch at 500 regions are daemon-side
scheduling jitter, not client cost). The structural claim — client stages
are negligible next to RPC round trips — holds at both region counts and
matches chunk 3's finding that client parse is ≤0.16 ms while wire
round-trip scales 22→191 ms. Production cost model (perception model
latency) is out of scope for this fixture, same as REPORT-live.md.

**No code change.** Measurement only; recorded so the factory doesn't
spend a chunk micro-optimizing `parseVisualRegions` or candidate building.
