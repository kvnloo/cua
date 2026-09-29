# A/B analysis: run-mock-20260928

Driver: `cua-driver 0.30.4` sha256 `f8b07d39df52c68f…` (same binary in every arm)

Arms: `main-default`@b8d619f57 , `pr4316-default`@e2e86d704 , `pr4316-guarded`@e2e86d704 ['--guarded-completion']

Cells: 78 total; clean 60, traced 18; independently verified 78/78; hard-invariant violations 0

## Work counts per cell (min–max over clean cells)

| arm/lang | n | verified | provider | guarded | semantic obs | visual obs | driver actions | refusals | abstentions |
|---|---|---|---|---|---|---|---|---|---|
| main-default/python | 10 | 10 | 2 | 0 | 2 | 0 | 2 | 0 | 0 |
| main-default/typescript | 10 | 10 | 2 | 0 | 2 | 0 | 2 | 0 | 0 |
| pr4316-default/python | 10 | 10 | 2 | 0 | 2 | 0 | 2 | 0 | 0 |
| pr4316-default/typescript | 10 | 10 | 2 | 0 | 2 | 0 | 2 | 0 | 0 |
| pr4316-guarded/python | 10 | 10 | 1 | 1 | 2 | 0 | 2 | 0 | 0 |
| pr4316-guarded/typescript | 10 | 10 | 1 | 1 | 2 | 0 | 2 | 0 | 0 |

## Independent outcome timing, ms (clean cells; median [p25–p75])

| arm/lang | verified_outcome (oracle /state) | state_changed (server) | runner_lifetime | cleanup_after_outcome |
|---|---|---|---|---|
| main-default/python | 4005.81 [3997.73–4008.76] | 4001.4 [3996.2–4005.95] | 4515.69 [4515.53–4516.12] | 513.75 [509.94–520.58] |
| main-default/typescript | 4081.4 [4053.1–4098.59] | 4078.51 [4050.78–4094.99] | 4665.69 [4615.64–4740.9] | 574.56 [560.39–585.22] |
| pr4316-default/python | 4028.15 [4019.71–4048.61] | 4026.3 [4019.05–4044.94] | 4515.79 [4515.41–4565.65] | 499.91 [486.56–510.75] |
| pr4316-default/typescript | 4056.87 [4053.14–4067.73] | 4053.63 [4051.2–4065.86] | 4616.15 [4615.7–4653.71] | 562.15 [551.99–610.35] |
| pr4316-guarded/python | 4037.28 [4012.0–4055.24] | 4034.76 [4008.87–4053.7] | 4515.98 [4515.65–4566.58] | 511.87 [502.19–519.42] |
| pr4316-guarded/typescript | 4061.38 [4057.88–4093.32] | 4057.81 [4053.04–4091.76] | 4640.84 [4615.65–4665.74] | 579.87 [557.3–601.3] |

## Runner-reported phase timing, step 1, ms (clean cells; median [p25–p75])

| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |
|---|---|---|---|---|---|---|---|
| main-default/python | 20.32 [19.89–22.39] | 0.0 [0.0–0.0] | 0.06 [0.05–0.07] | 0.01 [0.01–0.01] | 20.4 [19.98–22.49] | 1611.73 [1611.03–1613.01] | 1631.94 [1630.85–1635.28] |
| main-default/typescript | 18.98 [18.39–20.81] | 0.0 [0.0–0.0] | 0.28 [0.24–0.31] | 0.1 [0.09–0.14] | 19.73 [19.01–21.48] | 1607.03 [1605.67–1607.71] | 1627.47 [1626.37–1632.05] |
| pr4316-default/python | 22.21 [20.72–23.12] | 0.0 [0.0–0.0] | 0.06 [0.05–0.07] | 0.01 [0.0–0.01] | 22.31 [20.79–23.23] | 1610.47 [1607.15–1612.83] | 1631.28 [1628.95–1635.64] |
| pr4316-default/typescript | 18.81 [17.68–19.18] | 0.0 [0.0–0.0] | 0.26 [0.26–0.26] | 0.09 [0.09–0.11] | 19.44 [18.35–19.79] | 1606.3 [1603.0–1607.28] | 1624.31 [1622.22–1626.85] |
| pr4316-guarded/python | 21.55 [20.95–23.42] | 0.0 [0.0–0.0] | 0.06 [0.06–0.08] | 0.01 [0.01–0.01] | 21.69 [21.08–23.55] | 1613.93 [1608.81–1616.2] | 1635.55 [1632.1–1638.73] |
| pr4316-guarded/typescript | 19.38 [18.21–20.25] | 0.0 [0.0–0.0] | 0.28 [0.25–0.3] | 0.1 [0.09–0.1] | 20.04 [19.0–21.01] | 1606.3 [1605.56–1607.62] | 1625.64 [1624.83–1628.45] |

## Runner-reported phase timing, step 2, ms (clean cells; median [p25–p75])

| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |
|---|---|---|---|---|---|---|---|
| main-default/python | 5.17 [5.08–5.46] | 0.0 [0.0–0.0] | 0.03 [0.03–0.04] | 0.0 [0.0–0.0] | 5.23 [5.15–5.55] | 1540.12 [1539.93–1548.23] | 1545.38 [1545.2–1554.0] |
| main-default/typescript | 5.46 [5.1–5.56] | 0.0 [0.0–0.0] | 0.09 [0.08–0.1] | 0.01 [0.01–0.01] | 5.57 [5.21–5.69] | 1537.8 [1537.53–1538.66] | 1543.43 [1543.28–1543.85] |
| pr4316-default/python | 5.42 [5.36–5.63] | 0.0 [0.0–0.0] | 0.04 [0.04–0.05] | 0.0 [0.0–0.01] | 5.5 [5.43–5.72] | 1542.18 [1540.24–1546.95] | 1547.72 [1545.61–1552.67] |
| pr4316-default/typescript | 5.56 [5.25–6.09] | 0.0 [0.0–0.0] | 0.09 [0.09–0.1] | 0.01 [0.01–0.01] | 5.69 [5.36–6.21] | 1537.37 [1536.88–1537.96] | 1543.26 [1542.78–1543.37] |
| pr4316-guarded/python | 5.3 [5.25–5.58] | 0.0 [0.0–0.0] | 0.04 [0.03–0.04] | 0.0 [0.0–0.0] | 5.38 [5.33–5.67] | 1539.88 [1539.52–1540.87] | 1545.28 [1545.2–1546.1] |
| pr4316-guarded/typescript | 5.43 [5.18–5.49] | 0.0 [0.0–0.0] | 0.09 [0.08–0.1] | 0.0 [0.0–0.0] | 5.65 [5.42–5.73] | 1539.0 [1537.57–1547.28] | 1544.39 [1543.31–1552.85] |

## Paired differences (guarded − main-default, same block & language)

| metric | n pairs | median diff ms | mean diff ms | bootstrap 95% CI of median | guarded faster / slower |
|---|---|---|---|---|---|
| verified_outcome_ms | 20 | 16.78 | 5.7 | [-3.3, 28.81] | 7 / 13 |
| runner_lifetime_ms | 20 | 0.55 | 4.99 | [0.0, 49.77] | 6 / 14 |
| cleanup_after_outcome_ms | 20 | 3.72 | -0.71 | [-19.39, 26.42] | 8 / 12 |
| step2.provider_decision_ms | 20 | -0.01 | -0.01 | [-0.01, 0.0] | 11 / 0 |
| step2.decision_ms | 20 | 0.16 | 0.12 | [-0.27, 0.35] | 9 / 11 |
| step2.total_step_ms | 20 | 0.15 | 2.17 | [-0.7, 5.08] | 7 / 13 |

## Hard-invariant violations

None: every guarded cell has routes `[provider, guarded-completion]`, exactly 1 provider decision, guarded step `provider_decision_ms == 0.0`, 2 fresh semantic observations, 2 actions; every baseline cell has 2 provider decisions.

## MCP-trace proof (traced cells)

| cell | semantic snapshots | actions | action refs | pre-mutation Submit ref | post-mutation Submit ref | 2nd action ref | stale reuse | ref from latest snapshot | 2nd snapshot after 1st action | named-span coverage % |
|---|---|---|---|---|---|---|---|---|---|---|
| traced-b01-p1-pr4316-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 94.02 |
| traced-b01-p2-main-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.24 |
| traced-b01-p3-main-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.49 |
| traced-b01-p4-pr4316-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.5 |
| traced-b01-p5-pr4316-guarded-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.97 |
| traced-b01-p6-pr4316-guarded-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.51 |
| traced-b02-p1-pr4316-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.37 |
| traced-b02-p2-pr4316-guarded-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.84 |
| traced-b02-p3-main-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.51 |
| traced-b02-p4-pr4316-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 94.0 |
| traced-b02-p5-main-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.92 |
| traced-b02-p6-pr4316-guarded-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.66 |
| traced-b03-p1-pr4316-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 93.94 |
| traced-b03-p2-pr4316-guarded-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.71 |
| traced-b03-p3-pr4316-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.78 |
| traced-b03-p4-main-default-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 94.0 |
| traced-b03-p5-main-default-typescript | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 91.42 |
| traced-b03-p6-pr4316-guarded-python | 2 | 2 | [('browser_type', 'p1:0'), ('browser_click', 'p2:2')] | p1:1 | p2:2 | p2:2 | False | True | True | 94.1 |

## Default behavior unchanged without the flag (main vs #4316 head, flag off)

```json
{
 "python": {
  "main_cells": 13,
  "pr_default_cells": 13,
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
  "main_cells": 13,
  "pr_default_cells": 13,
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
