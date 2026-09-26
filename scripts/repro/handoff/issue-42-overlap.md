# Issue 42

Two recipe-local compilers. They do not import each other.

| | Form fixture | Toggle workflow |
| --- | --- | --- |
| Module | `compiled_expectations.py` and `typescript/compiled_expectations.ts` | `toggle_expectations.py` |
| Candidates | `type-verification-value`, `submit-form`, `visual-submit` | `toggle-setting`, `confirm-dialog` |
| Predicates | `field_value_equals`, `fixture_submitted_equals` | `setting_equals`, `dialog_closed_equals` |
| Oracle | fixture field or `/state` | dialog closed |
| Reserved ids | no expectation | no expectation |
| `verify_state` mapping | not wrapped | not wrapped |
| Freshness | capture id on visual submit; ref generation before success | not the same ref |

Overlap: both return a kind and a token, or nothing for `reobserve` and `abstain`. That is not the same predicate or the same oracle.

No shared compiler was extracted. Completion stays in the recipe that owns it.
