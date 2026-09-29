# #4317 isolation: per-attempt results

```json
{
 "runs": 5,
 "runs_complete": 5,
 "runs_with_expected_journals": 5,
 "cross_session_mutations_total": 0,
 "foreign_values_landed_total": 0,
 "attempts_total": 25,
 "attempts_accepted_by_driver": 0,
 "attempt_refusal_codes": [
  [
   "cross_session",
   "browser_click",
   "A",
   "B",
   "browser_binding_stale"
  ],
  [
   "cross_session",
   "browser_click",
   "B",
   "A",
   "browser_binding_stale"
  ],
  [
   "cross_session",
   "browser_type",
   "A",
   "B",
   "browser_binding_stale"
  ],
  [
   "cross_session",
   "browser_type",
   "B",
   "A",
   "browser_binding_stale"
  ],
  [
   "ended_session",
   "browser_click",
   "A",
   "A",
   "session_ended"
  ]
 ]
}
```

| run | seq | kind | tool | calling session | target owner | ref (minted by) | driver result | code | journals A/B submissions before -> after |
|---|---|---|---|---|---|---|---|---|---|
| run01 | 11 | cross_session | browser_type | B | A | p1:0 (A) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run01 | 13 | cross_session | browser_type | A | B | p2:0 (B) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run01 | 21 | cross_session | browser_click | B | A | p5:2 (A) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run01 | 22 | cross_session | browser_click | A | B | p6:2 (B) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run01 | 26 | ended_session | browser_click | A | A | p5:2 (A) | refused | session_ended | A 1->1, B 1->1 |
| run02 | 11 | cross_session | browser_type | B | A | p1:0 (A) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run02 | 13 | cross_session | browser_type | A | B | p2:0 (B) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run02 | 21 | cross_session | browser_click | B | A | p5:2 (A) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run02 | 22 | cross_session | browser_click | A | B | p6:2 (B) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run02 | 26 | ended_session | browser_click | A | A | p5:2 (A) | refused | session_ended | A 1->1, B 1->1 |
| run03 | 11 | cross_session | browser_type | B | A | p1:0 (A) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run03 | 13 | cross_session | browser_type | A | B | p2:0 (B) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run03 | 21 | cross_session | browser_click | B | A | p5:2 (A) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run03 | 22 | cross_session | browser_click | A | B | p6:2 (B) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run03 | 26 | ended_session | browser_click | A | A | p5:2 (A) | refused | session_ended | A 1->1, B 1->1 |
| run04 | 11 | cross_session | browser_type | B | A | p1:0 (A) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run04 | 13 | cross_session | browser_type | A | B | p2:0 (B) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run04 | 21 | cross_session | browser_click | B | A | p5:2 (A) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run04 | 22 | cross_session | browser_click | A | B | p6:2 (B) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run04 | 26 | ended_session | browser_click | A | A | p5:2 (A) | refused | session_ended | A 1->1, B 1->1 |
| run05 | 11 | cross_session | browser_type | B | A | p1:0 (A) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run05 | 13 | cross_session | browser_type | A | B | p2:0 (B) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run05 | 21 | cross_session | browser_click | B | A | p5:2 (A) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run05 | 22 | cross_session | browser_click | A | B | p6:2 (B) | refused | browser_binding_stale | A 0->0, B 0->0 |
| run05 | 26 | ended_session | browser_click | A | A | p5:2 (A) | refused | session_ended | A 1->1, B 1->1 |
