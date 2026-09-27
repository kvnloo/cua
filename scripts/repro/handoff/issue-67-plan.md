# Issue 67

Verdict: NEEDS DESIGN DECISION.

The existing request-id owner is the seam. `cancellation_lifetime.Lifetime` does not choose the #3796 implementation. It becomes READY WHEN RFC APPROVES that slice. It is not ready before that approval. This is not BLOCKED BY MISSING SEAM: the issuance string is the seam, and the upstream implementation choice is still open.

| Fixture | Seam | What the order probe does |
| --- | --- | --- |
| Cancel while queued for native admission | `release` before `native_exit` | raises `capacity released before native exit` |
| Cancel after native admission | `native_exit`, then `release`, then `finish` | emits `public-result:req-1` |
| Admitted job retains capacity until exit | same raise as the queued cancel | covered as order only |
| Held key or modifier cleanup | real request-id owner | not in `Lifetime` |
| Pointer or drag cleanup | real request-id owner | not in `Lifetime` |
| Late cancel after completion | real request-id owner | not in `Lifetime` |
| Foreign transport or session cancel | `finish("req-2")` on a `req-1` object | raises `cancel reached the wrong issuance` |
| Request-id reuse rejected before dispatch | transport rule already accepted by #3796 | not reimplemented here |

No generic scheduler and no lifecycle registry were added.
