# A/B analysis: run-mock-traced

Driver: `cua-driver 0.30.4` sha256 `f8b07d39df52c68f…` (same binary in every arm)

Arms: `main-default`@22456aa59 , `pr4316-default`@d391a663a , `pr4316-guarded`@d391a663a ['--guarded-completion']

Cells: 18 total; clean 0, traced 18; independently verified 18/18; hard-invariant violations 0

## Work counts per cell (min–max over clean cells)

| arm/lang | n | verified | provider | guarded | semantic obs | visual obs | driver actions | refusals | abstentions |
|---|---|---|---|---|---|---|---|---|---|

## Independent outcome timing, ms (clean cells; median [p25–p75])

| arm/lang | verified_outcome (oracle /state) | state_changed (server) | runner_lifetime | cleanup_after_outcome |
|---|---|---|---|---|

## Runner-reported phase timing, step 1, ms (clean cells; median [p25–p75])

| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |
|---|---|---|---|---|---|---|---|

## Runner-reported phase timing, step 2, ms (clean cells; median [p25–p75])

| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |
|---|---|---|---|---|---|---|---|

## Paired differences (guarded − main-default, same block & language)

| metric | n pairs | median diff ms | mean diff ms | bootstrap 95% CI of median | guarded faster / slower |
|---|---|---|---|---|---|

## Hard-invariant violations

None: every guarded cell has routes `[provider, guarded-completion]`, exactly 1 provider decision, guarded step `provider_decision_ms == 0.0`, 2 fresh semantic observations, 2 actions; every baseline cell has 2 provider decisions.

## MCP-trace proof (traced cells)

| cell | semantic snapshots | actions | action refs | pre-mutation Submit ref | post-mutation Submit ref | 2nd action ref | stale reuse | ref from latest snapshot | 2nd snapshot after 1st action | named-span coverage % |
|---|---|---|---|---|---|---|---|---|---|---|
| traced-b01-p1-main-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.25 |
| traced-b01-p2-main-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 90.19 |
| traced-b01-p3-pr4316-guarded-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 90.47 |
| traced-b01-p4-pr4316-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 92.49 |
| traced-b01-p5-pr4316-guarded-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.04 |
| traced-b01-p6-pr4316-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.21 |
| traced-b02-p1-main-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.3 |
| traced-b02-p2-pr4316-guarded-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.65 |
| traced-b02-p3-pr4316-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.66 |
| traced-b02-p4-pr4316-guarded-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 89.26 |
| traced-b02-p5-pr4316-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 90.72 |
| traced-b02-p6-main-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 90.43 |
| traced-b03-p1-pr4316-guarded-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 90.93 |
| traced-b03-p2-pr4316-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 92.65 |
| traced-b03-p3-main-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 90.53 |
| traced-b03-p4-pr4316-guarded-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.89 |
| traced-b03-p5-main-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.66 |
| traced-b03-p6-pr4316-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.3 |

## Default behavior unchanged without the flag (main vs #4316 head, flag off)

```json
{
 "python": {
  "main_cells": 3,
  "pr_default_cells": 3,
  "candidate_sequences_main": [
   "[\"type-verification-value\", \"submit-form\"]"
  ],
  "candidate_sequences_pr_default": [
   "[\"type-verification-value\", \"submit-form\"]"
  ],
  "tool_sequences_equal": true,
  "mcp_call_sequence_identical_across_traced_cells": true,
  "main_has_decision_route_field": false,
  "pr_default_routes": [
   "[\"provider\", \"provider\"]"
  ]
 },
 "typescript": {
  "main_cells": 3,
  "pr_default_cells": 3,
  "candidate_sequences_main": [
   "[\"type-verification-value\", \"submit-form\"]"
  ],
  "candidate_sequences_pr_default": [
   "[\"type-verification-value\", \"submit-form\"]"
  ],
  "tool_sequences_equal": true,
  "mcp_call_sequence_identical_across_traced_cells": true,
  "main_has_decision_route_field": false,
  "pr_default_routes": [
   "[\"provider\", \"provider\"]"
  ]
 }
}
```
