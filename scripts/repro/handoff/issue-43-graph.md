# Issue 43

Before: `run.py` calls the chooser once per step. It does not import `guarded_run.py` or `toggle_run.py`.

After, still with no shared type:

```text
run.py
  chooser, one step

guarded_run.py
  type-verification-value -> submit-form
  second child only when status is verified and the fresh token, submit ref, and capture id match

toggle_run.py
  toggle-setting -> confirm-dialog
  second child only when status is verified and the setting boolean is true
```

`toggle_run.py` does not import `guarded_run.py`. A form plan's submit ref is not the toggle workflow's boolean. Unknown and refuted stop both, and that shared stop is not enough to merge them: the oracles differ, and neither workflow rolls back or asks the model between children.

No shared primitive was added. `test_toggle_recipes.py` runs both functions.
