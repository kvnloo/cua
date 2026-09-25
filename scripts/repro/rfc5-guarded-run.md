# kvnloo/cua#5 — guarded two-action run

Caller-side only. No new Driver tool.

## What is allowed to survive child 1

The run authorization: the two candidate ids, their tools, and the token the caller already held.

## What is not allowed to survive

The Submit ref, the field value, and the capture id from before the type. The second child runs only when a fresh observation says the field contains that token, the Submit ref is still the planned ref, and the fresh capture id is present. A rebound, a missing ref, an unknown or refuted postcondition, a stale capture, or a refusal stops the run. The second action is not retried.

A provider choice of one ordinary action is not a run.

## Verdict

Not issued. These tests do not measure wall time or success on the fixture.
