# Issue 71 — final decision

This checkout: NO PUBLIC FIELD. `post_dispatch_observation` is absent from the contract crate here.


Final disposition: **ADD OPTIONAL FIELD / completed**.

Live upstream state supersedes the earlier downstream "NO PUBLIC FIELD" recommendation.

trycua/cua#3946 now preserves truthful internal poll provenance.

trycua/cua#4009 has folded the public result field:

`post_dispatch_observation: completed | skipped | unavailable`

Consumer reason:
- `completed`: Driver actually ran its post-dispatch observation to the selected bound.
- `skipped`: caller/host explicitly did not request that observation.
- `unavailable`: observation started but its result was lost/unavailable.

This distinction changes the caller's safe next action. Existing #3971 / #2958 evidence shows that treating absence of effect evidence as "no effect" can cause destructive replay of a mutation that already landed.

Implementation/version compatibility is now downstream #38 / upstream #4009.

The old "NO PUBLIC FIELD" table in this file was stale and is replaced by this final disposition.
