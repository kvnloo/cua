# Freshness and cancellation sequences

No ExecutionContext. No LifecycleService. Those names would only mirror the owners below.

| Invariant | Owner | Fact that crosses the boundary |
| --- | --- | --- |
| Freshness | observation `snapshot_id` / `capture_id`, and `browser_revision.bind` for a browser ref | ref and generation |
| Authorization | existing session policy | unchanged on this branch |
| Admission lifetime | `cancellation_lifetime.Lifetime` on the existing request-id owner | issuance string |
| Cancellation | `Lifetime.observe_cancel`, then `release` only after `native_exit` | same issuance |
| Session lifetime | `Lifetime.finish` | a different issuance is rejected |

## 1. Fresh guarded child

```text
admit run (type, submit, token, submit ref)
dispatch type
status = verified
fresh observation: field == token, submit ref unchanged, capture id present
dispatch submit
```

`second_child_allowed("verified", fresh, plan)` is the check. The prior Submit ref does not survive by itself.

## 2. Stale child refusal

```text
admit run
dispatch type
fresh observation: submit ref changed or missing
stop
submit is not dispatched
```

`browser_revision.bind` raises `StaleRefError` when the label is reused on a new generation.

## 3. Cancel while queued

```text
admitted:req-1
cancellation-observed:req-1
native work has not exited
release raises
```

`Lifetime.release` raises `capacity released before native exit`.

## 4. Cancel after native admission

```text
admitted:req-1
cancellation-observed:req-1
native-exit:req-1
permit-released:req-1
public-result:req-1
```

That order is `admit`, `observe_cancel`, `native_exit`, `release`, `finish`.

## 5. Session end during admitted work

The lifetime object is the issuance. `finish` before `release` raises `public result returned before permit release`. `finish("req-2")` on a `req-1` lifetime raises `cancel reached the wrong issuance`. Dropping the object without `native_exit` then `release` cannot emit `public-result`.
