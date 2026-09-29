# A/B analysis: run-live

Driver: `cua-driver 0.30.4` sha256 `f8b07d39df52c68f…` (same binary in every arm)

Arms: `main-default`@22456aa59 , `pr4316-guarded`@d391a663a ['--guarded-completion']

Cells: 36 total; clean 36, traced 0; independently verified 36/36; hard-invariant violations 0

## Work counts per cell (min–max over clean cells)

| arm/lang | n | verified | provider | guarded | semantic obs | visual obs | driver actions | refusals | abstentions |
|---|---|---|---|---|---|---|---|---|---|
| main-default/python | 9 | 9 | 2 | 0 | 2 | 0 | 2 | 0 | 0 |
| main-default/typescript | 9 | 9 | 2 | 0 | 2 | 0 | 2 | 0 | 0 |
| pr4316-guarded/python | 9 | 9 | 1 | 1 | 2 | 0 | 2 | 0 | 0 |
| pr4316-guarded/typescript | 9 | 9 | 1 | 1 | 2 | 0 | 2 | 0 | 0 |

## Independent outcome timing, ms (clean cells; median [p25–p75])

| arm/lang | verified_outcome (oracle /state) | state_changed (server) | runner_lifetime | cleanup_after_outcome |
|---|---|---|---|---|
| main-default/python | 4527.73 [4487.69–4595.1] | 4525.4 [4483.45–4591.64] | 5119.36 [5017.3–5167.51] | 570.96 [520.37–587.32] |
| main-default/typescript | 4525.9 [4408.94–4657.59] | 4525.26 [4406.49–4652.29] | 5166.68 [4968.89–5266.99] | 569.72 [559.97–665.74] |
| pr4316-guarded/python | 4363.2 [4302.48–4400.21] | 4361.24 [4301.03–4399.21] | 4866.65 [4816.0–4967.59] | 513.72 [503.45–568.71] |
| pr4316-guarded/typescript | 4381.84 [4322.46–4466.29] | 4381.17 [4321.52–4461.77] | 4966.93 [4867.62–5017.11] | 550.95 [549.34–580.47] |

## Runner-reported phase timing, step 1, ms (clean cells; median [p25–p75])

| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |
|---|---|---|---|---|---|---|---|
| main-default/python | 24.65 [23.17–25.07] | 0.0 [0.0–0.0] | 0.07 [0.05–0.07] | 237.82 [227.71–242.78] | 261.98 [253.19–271.23] | 1615.46 [1612.25–1619.42] | 1886.42 [1873.64–1889.96] |
| main-default/typescript | 23.31 [20.1–33.06] | 0 [0.0–0.0] | 0.31 [0.28–0.38] | 237.06 [214.99–242.22] | 259.17 [246.6–280.01] | 1611.58 [1607.83–1617.4] | 1864.17 [1859.56–1898.24] |
| pr4316-guarded/python | 25.54 [24.41–26.09] | 0.0 [0.0–0.0] | 0.06 [0.05–0.07] | 255.11 [235.72–277.35] | 280.77 [261.72–315.07] | 1612.68 [1610.48–1619.14] | 1891.26 [1876.51–1934.22] |
| pr4316-guarded/typescript | 22.79 [19.31–25.04] | 0 [0.0–0.0] | 0.31 [0.24–0.35] | 252.08 [239.47–253.64] | 275.48 [265.44–281.03] | 1610.78 [1605.86–1612.96] | 1881.4 [1877.92–1912.14] |

## Runner-reported phase timing, step 2, ms (clean cells; median [p25–p75])

| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |
|---|---|---|---|---|---|---|---|
| main-default/python | 5.83 [5.36–7.44] | 0.0 [0.0–0.0] | 0.04 [0.04–0.05] | 189.29 [186.45–212.66] | 194.46 [192.35–222.7] | 1548.84 [1543.51–1552.56] | 1739.7 [1737.73–1774.29] |
| main-default/typescript | 6.22 [5.39–6.71] | 0 [0.0–0.0] | 0.1 [0.09–0.14] | 144.97 [141.74–152.06] | 150.44 [147.24–157.63] | 1537.69 [1536.84–1546.71] | 1687.56 [1681.7–1703.78] |
| pr4316-guarded/python | 5.44 [5.23–5.72] | 0.0 [0.0–0.0] | 0.04 [0.04–0.04] | 0.0 [0.0–0.0] | 5.56 [5.32–5.8] | 1546.07 [1544.67–1555.84] | 1552.3 [1550.09–1561.42] |
| pr4316-guarded/typescript | 6.06 [5.39–6.76] | 0 [0.0–0.0] | 0.11 [0.1–0.12] | 0 [0.0–0.0] | 6.29 [5.59–6.99] | 1539.12 [1538.64–1548.81] | 1544.97 [1544.46–1556.02] |

## Paired differences (guarded − main-default, same block & language)

| metric | n pairs | median diff ms | mean diff ms | bootstrap 95% CI of median | guarded faster / slower |
|---|---|---|---|---|---|
| verified_outcome_ms | 18 | -182.72 | -147.59 | [-210.72, -83.97] | 15 / 3 |
| runner_lifetime_ms | 18 | -199.61 | -180.71 | [-299.26, -100.03] | 16 / 2 |
| cleanup_after_outcome_ms | 18 | -11.41 | -33.12 | [-71.25, 5.6] | 12 / 6 |
| step2.provider_decision_ms | 18 | -176.25 | -171.34 | [-188.88, -146.95] | 18 / 0 |
| step2.decision_ms | 18 | -174.72 | -171.55 | [-188.59, -146.51] | 18 / 0 |
| step2.total_step_ms | 18 | -155.99 | -167.82 | [-193.12, -143.58] | 18 / 0 |

## Hard-invariant violations

None: every guarded cell has routes `[provider, guarded-completion]`, exactly 1 provider decision, guarded step `provider_decision_ms == 0.0`, 2 fresh semantic observations, 2 actions; every baseline cell has 2 provider decisions.

## MCP-trace proof (traced cells)

| cell | semantic snapshots | actions | action refs | pre-mutation Submit ref | post-mutation Submit ref | 2nd action ref | stale reuse | ref from latest snapshot | 2nd snapshot after 1st action | named-span coverage % |
|---|---|---|---|---|---|---|---|---|---|---|

## Default behavior unchanged without the flag (main vs #4316 head, flag off)

```json
{
 "python": {
  "main_cells": 9,
  "pr_default_cells": 0,
  "candidate_sequences_main": [
   "[\"type-verification-value\", \"submit-form\"]"
  ],
  "candidate_sequences_pr_default": [],
  "tool_sequences_equal": false,
  "mcp_call_sequence_identical_across_traced_cells": null,
  "main_has_decision_route_field": false,
  "pr_default_routes": []
 },
 "typescript": {
  "main_cells": 9,
  "pr_default_cells": 0,
  "candidate_sequences_main": [
   "[\"type-verification-value\", \"submit-form\"]"
  ],
  "candidate_sequences_pr_default": [],
  "tool_sequences_equal": false,
  "mcp_call_sequence_identical_across_traced_cells": null,
  "main_has_decision_route_field": false,
  "pr_default_routes": []
 }
}
```
