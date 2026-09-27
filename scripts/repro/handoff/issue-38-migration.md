# Issue 38

Matrix: `scripts/repro/handoff/issue-38-matrix.tsv`, from `migration_matrix.migration_rows`.

Documented versions are read from `libs/cua-driver/contract/README.md`: `contract_version` 0.8.0, `capability_version` 1. `GetWindowStateInput` and `VerifyStateInput` use deny_unknown_fields, so a newer client that sends an unknown field to an older daemon is rejected.

Shapes compared: additive optional field, new nested record, capability-gated variant, new tool or result type, and no field added. The selected row on this checkout is no field added. Consumer trials were not run. Bindings were not regenerated. No production field was added.

`scripts/repro/handoff/issue-38-commands.json`, from `migration_matrix.command_report`, searches the contract crate for `post_dispatch_observation`. The symbol is absent. `selected_implementation_sha` is null. `generator_check`, live registry parity, the old-client trial, and the new-client/old-daemon trial are `not run`.

`PollProvenance` stays a private field of macOS `Changes`. The macOS crate was not compiled on this host. Installed binary: `cua-driver 0.28.2`.
