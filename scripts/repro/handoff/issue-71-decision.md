# Issue 71

Closed at https://github.com/kvnloo/cua/issues/71#issuecomment-5841780594.

That comment says trycua/cua#4009 folded `post_dispatch_observation: completed | skipped | unavailable` into the proposal. The concrete consumer is whether the caller must observe before a replay. Implementation and compatibility stay with #4009 and kvnloo/cua#38.

This checkout: the symbol is absent from the contract crate. `migration_matrix.command_report` records an empty `symbol_in_this_checkout` and `generator_check` as not run.

`typed_choice` still returns continue, observe, or stop without reading that symbol. `PollProvenance` stays a private field of macOS `Changes`. The macOS crate was not compiled on this host.
