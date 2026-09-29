# A/B analysis: run-mock

Driver: `cua-driver 0.30.4` sha256 `f8b07d39df52c68f…` (same binary in every arm)

Arms: `main-default`@22456aa59 , `pr4316-default`@d391a663a , `pr4316-guarded`@d391a663a ['--guarded-completion']

Cells: 60 total; clean 60, traced 0; independently verified 60/60; hard-invariant violations 0

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
| main-default/python | 4141.13 [4111.36–4425.3] | 4136.82 [4109.57–4424.55] | 4716.5 [4666.3–4993.98] | 561.33 [537.63–594.93] |
| main-default/typescript | 4182.26 [4130.74–4343.19] | 4178.09 [4126.43–4341.64] | 4741.94 [4666.41–4917.56] | 559.68 [531.74–563.62] |
| pr4316-default/python | 4156.75 [4121.0–4189.77] | 4154.54 [4119.34–4189.0] | 4692.44 [4666.24–4754.64] | 546.86 [531.88–552.84] |
| pr4316-default/typescript | 4176.2 [4154.85–4305.05] | 4173.46 [4151.06–4301.82] | 4767.98 [4729.36–4894.89] | 573.77 [544.72–593.51] |
| pr4316-guarded/python | 4145.59 [4112.11–4220.21] | 4142.08 [4111.2–4215.48] | 4692.9 [4666.24–4755.39] | 549.73 [535.51–562.1] |
| pr4316-guarded/typescript | 4162.59 [4131.41–4182.4] | 4160.67 [4128.2–4178.42] | 4717.25 [4716.27–4768.14] | 562.87 [543.61–568.92] |

## Runner-reported phase timing, step 1, ms (clean cells; median [p25–p75])

| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |
|---|---|---|---|---|---|---|---|
| main-default/python | 28.73 [26.54–37.0] | 0.0 [0.0–0.0] | 0.08 [0.07–0.1] | 0.01 [0.01–0.01] | 28.87 [26.66–37.16] | 1618.36 [1617.35–1622.06] | 1648.97 [1644.64–1658.28] |
| main-default/typescript | 24.95 [20.62–26.96] | 0.0 [0.0–0.0] | 0.29 [0.28–0.41] | 0.11 [0.1–0.12] | 25.81 [21.42–27.95] | 1611.18 [1609.87–1613.98] | 1638.45 [1628.98–1643.03] |
| pr4316-default/python | 26.49 [25.28–30.76] | 0.0 [0.0–0.0] | 0.07 [0.07–0.08] | 0.01 [0.01–0.01] | 26.71 [25.37–30.88] | 1620.05 [1617.28–1621.01] | 1646.61 [1644.34–1650.22] |
| pr4316-default/typescript | 25.13 [22.94–31.26] | 0.0 [0.0–0.0] | 0.3 [0.29–0.37] | 0.1 [0.09–0.12] | 25.8 [23.62–32.02] | 1612.12 [1611.59–1614.2] | 1637.53 [1633.65–1645.38] |
| pr4316-guarded/python | 27.18 [25.71–29.65] | 0.0 [0.0–0.0] | 0.08 [0.06–0.09] | 0.01 [0.01–0.01] | 27.38 [25.81–29.8] | 1617.77 [1616.63–1620.16] | 1645.87 [1644.38–1647.62] |
| pr4316-guarded/typescript | 25.31 [21.12–27.0] | 0.0 [0.0–0.0] | 0.28 [0.26–0.36] | 0.1 [0.09–0.1] | 26.0 [21.84–27.88] | 1613.93 [1609.04–1614.84] | 1639.22 [1629.49–1642.29] |

## Runner-reported phase timing, step 2, ms (clean cells; median [p25–p75])

| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |
|---|---|---|---|---|---|---|---|
| main-default/python | 6.19 [5.8–6.69] | 0.0 [0.0–0.0] | 0.04 [0.04–0.05] | 0.01 [0.0–0.01] | 6.28 [5.88–6.77] | 1556.43 [1555.62–1560.71] | 1562.53 [1561.52–1567.21] |
| main-default/typescript | 6.86 [6.68–7.06] | 0.0 [0.0–0.0] | 0.11 [0.1–0.13] | 0.01 [0.01–0.02] | 7.02 [6.84–7.19] | 1544.09 [1536.25–1550.74] | 1550.05 [1543.32–1557.72] |
| pr4316-default/python | 7.21 [6.54–8.82] | 0.0 [0.0–0.0] | 0.04 [0.04–0.05] | 0.01 [0.0–0.01] | 7.3 [6.62–8.9] | 1553.55 [1549.05–1562.02] | 1560.72 [1556.7–1572.77] |
| pr4316-default/typescript | 6.75 [5.86–8.08] | 0.0 [0.0–0.0] | 0.1 [0.09–0.11] | 0.01 [0.01–0.01] | 6.88 [6.0–8.23] | 1540.29 [1537.9–1545.04] | 1546.83 [1543.93–1553.87] |
| pr4316-guarded/python | 6.39 [5.88–7.5] | 0.0 [0.0–0.0] | 0.04 [0.04–0.05] | 0.0 [0.0–0.0] | 6.48 [5.98–7.65] | 1554.69 [1550.86–1555.55] | 1560.75 [1559.17–1562.3] |
| pr4316-guarded/typescript | 6.94 [6.66–8.23] | 0.0 [0.0–0.0] | 0.1 [0.09–0.14] | 0.0 [0.0–0.0] | 7.22 [6.93–8.5] | 1549.6 [1540.52–1550.95] | 1557.87 [1546.75–1558.87] |

## Paired differences (guarded − main-default, same block & language)

| metric | n pairs | median diff ms | mean diff ms | bootstrap 95% CI of median | guarded faster / slower |
|---|---|---|---|---|---|
| verified_outcome_ms | 20 | -28.41 | -478.51 | [-199.67, 17.15] | 13 / 7 |
| runner_lifetime_ms | 20 | -50.83 | -488.98 | [-200.36, 25.12] | 13 / 7 |
| cleanup_after_outcome_ms | 20 | -2.17 | -10.47 | [-27.23, 19.68] | 11 / 9 |
| step2.provider_decision_ms | 20 | -0.01 | -0.01 | [-0.01, -0.01] | 16 / 0 |
| step2.decision_ms | 20 | 0.12 | -2.98 | [-0.5, 0.63] | 9 / 11 |
| step2.total_step_ms | 20 | -0.9 | -7.63 | [-3.08, 1.49] | 12 / 8 |

## Hard-invariant violations

None: every guarded cell has routes `[provider, guarded-completion]`, exactly 1 provider decision, guarded step `provider_decision_ms == 0.0`, 2 fresh semantic observations, 2 actions; every baseline cell has 2 provider decisions.

## MCP-trace proof (traced cells)

| cell | semantic snapshots | actions | action refs | pre-mutation Submit ref | post-mutation Submit ref | 2nd action ref | stale reuse | ref from latest snapshot | 2nd snapshot after 1st action | named-span coverage % |
|---|---|---|---|---|---|---|---|---|---|---|

## Default behavior unchanged without the flag (main vs #4316 head, flag off)

```json
{
 "python": {
  "main_cells": 10,
  "pr_default_cells": 10,
  "candidate_sequences_main": [
   "[\"type-verification-value\", \"submit-form\"]"
  ],
  "candidate_sequences_pr_default": [
   "[\"type-verification-value\", \"submit-form\"]"
  ],
  "tool_sequences_equal": true,
  "mcp_call_sequence_identical_across_traced_cells": null,
  "main_has_decision_route_field": false,
  "pr_default_routes": [
   "[\"provider\", \"provider\"]"
  ]
 },
 "typescript": {
  "main_cells": 10,
  "pr_default_cells": 10,
  "candidate_sequences_main": [
   "[\"type-verification-value\", \"submit-form\"]"
  ],
  "candidate_sequences_pr_default": [
   "[\"type-verification-value\", \"submit-form\"]"
  ],
  "tool_sequences_equal": true,
  "mcp_call_sequence_identical_across_traced_cells": null,
  "main_has_decision_route_field": false,
  "pr_default_routes": [
   "[\"provider\", \"provider\"]"
  ]
 }
}
```
