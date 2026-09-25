# Issue 43

Before: `run.py` calls the chooser per step.

After: `guarded_run.py` can admit one type-then-submit pair. `run.py` does not call it.

A second workflow was not implemented. Behavioral parity across two workflows was not shown. The abstraction is not adopted.
