# Issue 39

The live scan is `scripts/repro/handoff/issue-39-inventory.json`, produced by `extraction_inventory.inventory`. A production file counts when it names the module and is not the module file. An independent harness is a production file outside `libs/cua-driver/examples/jev-use/`. This scan finds none, so every disposition is recipe-local.

The production names inside the example include `caller_route.py`, `task_battery.py`, `handoff_emit.py`, `run_length.py`, `compatibility_matrix.py`, `cost_ledger.py`, `transfer_probe.py`, and `old_driver_fallback.py`. Those files share the jev-use recipe. They are not a second harness. The JSON lists every production path.

No row is `extract now`. No refactor was performed.
