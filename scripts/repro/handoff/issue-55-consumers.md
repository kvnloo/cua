# Issue 55

```text
Changes.needs_restore -> restore decision
Changes.result_suffix -> tool text
Changes.poll          -> internal only
```

Smallest surface from the caller functions on this branch: no public field. `typed_choice` still returns continue, observe, or stop without `PollProvenance`.

A later GitHub comment, https://github.com/kvnloo/cua/issues/55#issuecomment-5841034826, says trycua/cua#4009 proposes `post_dispatch_observation` and cites trycua/cua#3971. The fetched #3971 body asks for skipped observation to be explicit. It does not contain a regression that fails without a new field. That comment is not this consumer graph, so this issue stays open.
