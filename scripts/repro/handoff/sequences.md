# Freshness and cancellation sequences

No third state owner. Freshness is `browser_revision.bind`. Cancellation is `cancellation_lifetime.Lifetime`.

## 1. Fresh guarded child

```text
admit run (type, submit, token, submit ref)
dispatch type
status = verified
fresh observation: field == token, submit ref unchanged, capture id present
dispatch submit
```

## 2. Stale child refusal

```text
admit run
dispatch type
fresh observation: submit ref changed or missing
stop
submit is not dispatched
```

## 3. Cancel while queued

```text
admitted:req-1
cancellation-observed:req-1
native work has not exited
release raises
```

## 4. Cancel after native admission

```text
admitted:req-1
cancellation-observed:req-1
native-exit:req-1
permit-released:req-1
public-result:req-1
```

## 5. Session end during admitted work

The lifetime object is the issuance. Dropping it without `native_exit` then `release` cannot emit `public-result`. A second issuance string is rejected by `finish`.
