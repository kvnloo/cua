# Observation-provenance ledger (TS-side, #4009-ready)

`typescript/provenance.ts` is the loop-side half of the observation-provenance
design question raised on #4013: a router consuming the recipe loop cannot
distinguish "observed and settled" from "not observed", so it conservatively
re-observes on every handoff. The driver's half is the ActionResult vocabulary
thread (#4009, maintainer-owned) — the driver cannot report post-dispatch
observation provenance today, so this module fills the loop side and pins the
adapter shape the driver side will feed.

## What it records

Per step:
- **observations** — the `ObservationRecord`s the loop already keeps
  (`snapshot` / `visual`, capture id, latency).
- **dispatch** — which candidate was chosen, which tool executed, and which
  evidence kinds informed the decision (`snapshot` / `visual` / `driver`).
- **settlement** — how the loop confirmed the effect took hold:
  `fixture` (the jev-use oracle poll), `snapshot-diff` (the next step's
  snapshot re-observes the world the action acted on), or `unverified`.

`settled(step)` is only true when an action was dispatched AND the effect was
confirmed through some channel. An unverified step is explicitly not settled —
a consumer must re-observe rather than assume.

## The #4009 seam

`PostDispatchObservation` is a reserved type, not a live one: the driver
sends nothing like it today. It pins the shape the ledger will consume
(`observedBeforeEffect`, `observedAfterEffect`, `effectConfirmedBy`) so the
example-side contract doesn't drift from the contract-crate design while
#4009 is under discussion. `noteDriverField` is the only entry point that
accepts it; on `completed` it promotes `driver` into the step's evidence kinds
and upgrades an `unverified` settlement to `snapshot-diff` — never demoting a
`fixture`-confirmed one (the oracle is stronger than the driver's report).
On `skipped`/`unavailable` it records the status and touches nothing else.

### The post_dispatch_observation mapping (2026-09-25)

#4009's proposal now includes `post_dispatch_observation` with values
`completed` / `skipped` / `unavailable`, sitting beside `signal` and never
promoting `effect`. The ledger maps it as:

| #4009 value | ledger behavior |
|---|---|
| `completed` | Record `postDispatch: 'completed'`; fold `driver` evidence; settlement promotion still gated on `effectConfirmedBy` only — status alone never settles a step. |
| `skipped` | Record `postDispatch: 'skipped'`; settlement and evidence untouched. "Not performed" is explicit and must never read as "performed and saw no change." |
| `unavailable` | Record `postDispatch: 'unavailable'`; settlement and evidence untouched. |

The `postDispatch` field is part of the handoff record, so a consumer can
distinguish "the driver never observed this step" from "the driver
observed and saw no relevant change" without re-running the observation.

## Wiring points in run.ts (when #4009 lands)

1. After each `driver.call('get_browser_state', ...)` / visual block:
   `ledger.recordObservation(step, ...)` — already done for the
   ObservationLedger; route the same records here.
2. After `validateChoice`: `provenance.noteDispatch(step,
   { candidateId: candidate.id, tool: candidate.tool,
     evidenceKinds: visual ? ['snapshot', 'visual'] : ['snapshot'] })`.
3. After a `submit-form` dispatch: `provenance.noteSettlement(step,
   { verifiedBy: 'fixture', latencyMs })` once the oracle confirms.
   For other actions: `noteSettlement(nextStep - 1, { verifiedBy:
   'snapshot-diff', ... })` when the next snapshot arrives, else leave
   `unverified`.
4. On the driver's MCP response: if a `post_dispatch_observation` field
   appears (post-#4009), call `provenance.noteDriverField(step, field)`.
5. On the `outcome` event: attach `provenance: provenance.handoff()` next
   to the existing `observation_ledger`.

## Why the loop side ships first

The loop-side record is useful with no driver change: it already answers
"which evidence drove this dispatch" and "what confirmed it" for the
recipe's own event log. The driver side is additive — `noteDriverField`
only ever upgrades evidence, so shipping this now can't contradict the
driver when #4009 resolves.
