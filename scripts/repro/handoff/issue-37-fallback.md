# Issue 37

| Failure | Caller result | Gains authority |
| --- | --- | --- |
| visual tools absent | `optional_visual_observation` returns none | no |
| visual call raises | returns none | no |
| semantic executable candidate | fast path does not require the visual call | no |

Order: try the semantic candidate first. A missing perception result does not become permission to act on a visual target.
