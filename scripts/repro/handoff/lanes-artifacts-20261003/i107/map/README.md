# i107 pin and map (2026-10-02)

kvnloo/cua#107, execution step 1. No measured trial ran.

- `MAP.md`: pins, seam map (caller observation path, `BrowserStore`/`SnapshotStore`, CDP machinery, ref resolution and stale refusal, verification), the arm-B feasibility verdict (**BLOCKED**: no producer-side scoped read through the existing contract; fallback B-proj is payload projection only), CDP event sources and their gaps, active-C admissibility, and the #10 span decomposition of baseline A (reused from B-01, valid on this source).
- `PREREG.json`: the frozen pre-registration for lanes AB, CSHADOW and D.
- `provenance.json`: identities, build and unit receipts, the blocked smoke.

Driver for every arm: `cua-driver-i107-092b065d5`, sha256 `f3a5c01a2c1b5bce75ccb611d0bacd491a7c3b1a8c3fac65889a1fc9d6977aed`, built from `092b065d5` on this branch.

**Blocker:** under the `hostless` wrapper the Driver refuses to launch Chrome (host root files appear as uid 65534 in the user namespace, failing the Driver's root-owned executable check). Every REAL browser cell is BLOCKED until the orchestrator or owner chooses an isolation wrapper that does not remap ownership.
