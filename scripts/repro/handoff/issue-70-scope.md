# Issue 70

Scope lock suitable for trycua/cua#3961. NO CHANGE NEEDED.

Pinned provider head named by the issue: `737cda114ae711713a3dbfa9c9ba76863dfd46b9`. This fork did not edit that pull request.

Classification of the speed-RFC files against the provider adapter `libs/cua-driver/examples/jev-use/python/jev_adapter.py`:

| Behavior | Class | On the adapter |
| --- | --- | --- |
| `choose_bounded_with_typesafe` / `choose_mock_adapter` | provider adapter plumbing | already there |
| one supplied candidate id | shared closed-choice validation | already there; this branch did not move it |
| `deterministic_fast_path.py` | caller policy | not imported |
| `guarded_run.py` | caller policy | not imported |
| `lazy_vision.py` | caller policy | not imported |
| `goal_gates.py` model done-gate | experiment-only | not imported |

`run.py` does not import those policy modules either. Model completion and reobserve heads were not added to the adapter. Partial progress and invalid provider responses stay on the existing chooser path.

No code was added to satisfy this checklist.
