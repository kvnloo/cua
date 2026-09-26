# Auth-lifetime deep dive — what session auth lifetime costs on the JSONL socket path

**Question:** is the auth-lifetime contract (draft dq-3383) the real blocker to
keep-alive landing, or is keep-alive independently valuable?

**Method:** mock_daemon.py gained `--auth-ms N` (artificial auth delay simulating
#3383's per-connection codesign verify), `--auth-mode accept|request`, and
`--auth-scope all|history`. Four arms on the same 3-call observation sequence
(snapshot + capture + parse), paired/interleaved per iteration with daemon
restarts cycled between configs (30 iters × 2 auth magnitudes × 3 configs).
Shape equivalence gate passed every iteration. Loopback asyncio unix socket,
50 regions.

**Results (median ms per 3-call sequence; speedup vs A):**

| arm | 5ms auth | 25ms auth |
|---|---|---|
| A — today: one-shot conn, auth at accept | 59.8 | 122.8 |
| B — keep-alive, auth once per conn (option b) | 31.5 (1.90×) | 44.5 (2.76×) |
| C — keep-alive, re-auth per request (conservative) | 54.7 (1.09×) | 114.6 (1.07×) |
| D — one-shot, auth scoped to history_* (option a) | 36.4 (1.64×) | 27.1 (4.53×) |

p90s were noisy (box under load from 8 concurrent waves; daemon spawn jitter) —
medians are the signal. Raw: auth_lifetime_py.json.

## What this says about the blocker

1. **Keep-alive without the auth decision is ~1.1× (arm C vs A).** The re-auth
   per request eats almost all the transport win because the auth cost itself
   dominates the per-call budget. The connection-setup tax keep-alive removes
   (~2.2ms/call measured earlier) is real but small next to the auth tax.

2. **The auth decision is the multiplier, not keep-alive.** The biggest single
   win on the observation path is option (a) scoping — 4.53× at 25ms auth —
   with NO keep-alive and NO connection-trust contract. It is strictly smaller
   and strictly less risky than (b): no multiplexing, no head-of-line blocking,
   no auth-lifetime contract to define.

3. **Keep-alive's honest value is conditional.** Alone: 1.07–1.09× (a transport
   nicety, not a 2× story). Combined with (a) or (b): 1.9–4.5×. So the auth
   decision is the gate to a *meaningful* win, even though keep-alive still
   technically helps without it.

4. **(a) is also the reporter's own ask.** #3383's expected behavior is
   "ordinary non-History CLI methods should not pay the full History-control
   trust check" — exactly arm D. The measurement says that ask alone captures
   most of the value on the hot path, and it sidesteps the TOCTOU question
   entirely (per-request History verification is unchanged).

## Honest scope

- asyncio.sleep stands in for codesign verify: it yields, while the real check
  is CPU-bound and serialized in the accept loop. Relative ordering holds for
  the single-client observation sequence; under concurrent load the real
  auth tax is *larger* than simulated, which only strengthens the scoping case.
- p90 noise is daemon-spawn jitter on a loaded box, not transport behavior.
- The History path itself was not re-measured here: under (a), History calls
  still pay per-request auth by design — that cost is the security point and
  is not on the chopping block.

**Recommendation to fold into dq-3383:** lead with (a). It is the reporter's
ask, it needs no new trust contract, and it delivers 1.6–4.5× on the
observation path by itself. Keep-alive becomes the follow-up once the
connection trust contract is defined — not the first move.
