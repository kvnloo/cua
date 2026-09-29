# A/B analysis: run-live-20260928

Driver: `cua-driver 0.30.4` sha256 `f8b07d39df52c68f…` (same binary in every arm)

Arms: `main-default`@b8d619f57 , `pr4316-guarded`@e2e86d704 ['--guarded-completion']

Cells: 12 total; clean 12, traced 0; independently verified 12/12; hard-invariant violations 0

## Work counts per cell (min–max over clean cells)

| arm/lang | n | verified | provider | guarded | semantic obs | visual obs | driver actions | refusals | abstentions |
|---|---|---|---|---|---|---|---|---|---|
| main-default/python | 3 | 3 | 2 | 0 | 2 | 0 | 2 | 0 | 0 |
| main-default/typescript | 3 | 3 | 2 | 0 | 2 | 0 | 2 | 0 | 0 |
| pr4316-guarded/python | 3 | 3 | 1 | 1 | 2 | 0 | 2 | 0 | 0 |
| pr4316-guarded/typescript | 3 | 3 | 1 | 1 | 2 | 0 | 2 | 0 | 0 |

## Independent outcome timing, ms (clean cells; median [p25–p75])

| arm/lang | verified_outcome (oracle /state) | state_changed (server) | runner_lifetime | cleanup_after_outcome |
|---|---|---|---|---|
| main-default/python | 4475.71 [4444.1–4500.93] | 4472.3 [4441.99–4497.66] | 5016.25 [4991.42–5066.28] | 554.1 [547.32–572.13] |
| main-default/typescript | 4405.02 [4402.44–4417.96] | 4401.62 [4398.72–4413.86] | 5016.91 [4991.72–5042.42] | 611.89 [589.28–624.46] |
| pr4316-guarded/python | 4211.26 [4206.94–4216.76] | 4208.68 [4205.44–4213.77] | 4716.42 [4716.39–4716.56] | 505.44 [499.77–509.62] |
| pr4316-guarded/typescript | 4359.06 [4299.42–4361.2] | 4354.63 [4294.94–4357.34] | 5066.43 [4991.46–5091.56] | 707.37 [692.05–730.36] |

## Runner-reported phase timing, step 1, ms (clean cells; median [p25–p75])

| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |
|---|---|---|---|---|---|---|---|
| main-default/python | 21.58 [21.36–21.74] | 0.0 [0.0–0.0] | 0.06 [0.06–0.07] | 262.57 [242.09–267.82] | 283.79 [263.54–289.44] | 1607.29 [1605.89–1609.53] | 1891.09 [1873.08–1895.34] |
| main-default/typescript | 19.26 [17.16–19.27] | 0 [0.0–0.0] | 0.24 [0.23–0.24] | 229.34 [213.62–230.67] | 247.51 [232.57–248.3] | 1602.5 [1599.03–1604.53] | 1844.71 [1832.46–1849.43] |
| pr4316-guarded/python | 19.75 [19.74–21.41] | 0.0 [0.0–0.0] | 0.05 [0.04–0.06] | 238.87 [234.01–241.15] | 262.02 [255.52–262.63] | 1603.24 [1602.09–1604.51] | 1865.26 [1857.62–1867.15] |
| pr4316-guarded/typescript | 22.48 [21.77–34.01] | 0 [0.0–0.0] | 0.31 [0.3–0.33] | 213.92 [207.19–256.64] | 260.13 [241.14–291.37] | 1605.51 [1602.65–1605.75] | 1859.99 [1844.1–1894.08] |

## Runner-reported phase timing, step 2, ms (clean cells; median [p25–p75])

| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |
|---|---|---|---|---|---|---|---|
| main-default/python | 5.56 [5.51–5.6] | 0.0 [0.0–0.0] | 0.05 [0.04–0.06] | 204.93 [192.4–248.72] | 210.63 [198.03–254.43] | 1535.61 [1535.53–1543.62] | 1746.09 [1733.57–1797.99] |
| main-default/typescript | 5.43 [5.4–5.58] | 0 [0.0–0.0] | 0.09 [0.08–0.09] | 165.74 [148.09–168.37] | 171.22 [153.59–174.02] | 1534.99 [1533.84–1539.01] | 1703.92 [1687.45–1711.9] |
| pr4316-guarded/python | 5.13 [5.12–5.28] | 0.0 [0.0–0.0] | 0.03 [0.03–0.04] | 0.0 [0.0–0.0] | 5.21 [5.21–5.36] | 1542.36 [1541.83–1550.63] | 1547.89 [1547.21–1556.01] |
| pr4316-guarded/typescript | 5.32 [5.31–5.35] | 0 [0.0–0.0] | 0.08 [0.08–0.08] | 0 [0.0–0.0] | 5.55 [5.52–5.56] | 1537.24 [1537.2–1537.68] | 1542.81 [1542.74–1543.26] |

## Paired differences (guarded − main-default, same block & language)

| metric | n pairs | median diff ms | mean diff ms | bootstrap 95% CI of median | guarded faster / slower |
|---|---|---|---|---|---|
| verified_outcome_ms | 6 | -175.16 | -175.3 | [-293.99, -56.75] | 6 / 0 |
| runner_lifetime_ms | 6 | -150.14 | -150.24 | [-349.73, 49.14] | 5 / 1 |
| cleanup_after_outcome_ms | 6 | 21.79 | 25.06 | [-72.36, 125.75] | 3 / 3 |
| step2.provider_decision_ms | 6 | -175.43 | -190.75 | [-248.72, -148.09] | 6 / 0 |
| step2.decision_ms | 6 | -175.77 | -190.96 | [-249.08, -148.03] | 6 / 0 |
| step2.total_step_ms | 6 | -175.87 | -187.34 | [-241.98, -144.18] | 6 / 0 |

## Hard-invariant violations

None: every guarded cell has routes `[provider, guarded-completion]`, exactly 1 provider decision, guarded step `provider_decision_ms == 0.0`, 2 fresh semantic observations, 2 actions; every baseline cell has 2 provider decisions.

## MCP-trace proof (traced cells)

| cell | semantic snapshots | actions | action refs | pre-mutation Submit ref | post-mutation Submit ref | 2nd action ref | stale reuse | ref from latest snapshot | 2nd snapshot after 1st action | named-span coverage % |
|---|---|---|---|---|---|---|---|---|---|---|

## Default behavior unchanged without the flag (main vs #4316 head, flag off)

```json
{
 "python": {
  "main_cells": 3,
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
  "main_cells": 3,
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
