# Issue 11

No capture skipping was enabled. `shadow_probe.record` stores `skip_capture` false. The constructor rejects a skip.

| Surface | skip_capture | false_retention_observed | reconciliation_cost_ms |
| --- | --- | --- | --- |
| gtk3-entry | false | not measured | not measured |

Invalidators on that surface, from `scripts/repro/atspi-census-20260925.json`:

- `object:children-changed:add`
- `object:state-changed:focused`
- `object:text-caret-moved`
- `object:text-changed:delete`
- `object:text-changed:insert`

The census is one GTK3 trace. It does not include a controlled replay that would show false retention or a reconciliation cost.

Missing machine: macOS. Missing machine: Windows. Those surfaces were not probed.
