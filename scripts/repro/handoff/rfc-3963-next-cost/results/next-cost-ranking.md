# Next dominant cost after guarded decision deletion (arm `pr4316-guarded`)

## python (n=10 verified clean cells)

| phase | p50 ms | p95 ms | max saved if phase -> 0 (% of verified-outcome p50) |
|---|---|---|---|
| action | 3171.82 | 3186.35 | 76.5% |
| setup_before_step1 | 938.94 | 1873.0 | 22.6% |
| semantic_observe | 33.44 | 38.71 | 0.8% |
| step_gap | 1.14 | 1.8 | 0.0% |
| step_other | 0.17 | 0.2 | 0.0% |
| candidate_build | 0.11 | 0.16 | 0.0% |
| provider_decision | 0.01 | 0.02 | 0.0% |
| residual | 0.0 | 0.0 | 0.0% |
| verify_tail | -2.45 | 0.31 | -0.1% |

verified_outcome p50 4145.59 ms, p95 5075.23 ms; cleanup after outcome p50 549.73 ms (not in verified-outcome time)

## typescript (n=10 verified clean cells)

| phase | p50 ms | p95 ms | max saved if phase -> 0 (% of verified-outcome p50) |
|---|---|---|---|
| action | 3163.55 | 3168.53 | 76.0% |
| setup_before_step1 | 967.04 | 1024.56 | 23.2% |
| semantic_observe | 32.41 | 36.43 | 0.8% |
| verify_tail | 4.73 | 7.82 | 0.1% |
| step_gap | 2.15 | 3.35 | 0.1% |
| step_other | 0.66 | 0.86 | 0.0% |
| candidate_build | 0.43 | 0.57 | 0.0% |
| provider_decision | 0.1 | 0.14 | 0.0% |
| residual | 0.0 | 0.0 | 0.0% |

verified_outcome p50 4162.59 ms, p95 4227.79 ms; cleanup after outcome p50 562.87 ms (not in verified-outcome time)

## Driver/MCP call durations (traced cells, n small)

### python
| call | n | p50 ms | max ms |
|---|---|---|---|
| initialize#1 | 3 | 156.07 | 193.5 |
| tools/list#1 | 3 | 50.66 | 51.7 |
| browser_prepare#1 | 3 | 264.3 | 284.0 |
| list_windows#1 | 3 | 8.01 | 15.0 |
| get_browser_state#1 | 3 | 39.71 | 56.0 |
| browser_navigate#1 | 3 | 34.03 | 41.9 |
| get_browser_state#2 | 3 | 26.1 | 27.1 |
| browser_type#1 | 3 | 1610.71 | 1614.8 |
| get_browser_state#3 | 3 | 8.93 | 10.8 |
| browser_click#1 | 3 | 1541.85 | 1546.8 |

### typescript
| call | n | p50 ms | max ms |
|---|---|---|---|
| initialize#1 | 3 | 164.52 | 210.8 |
| tools/list#1 | 3 | 56.07 | 70.3 |
| browser_prepare#1 | 3 | 280.5 | 285.7 |
| list_windows#1 | 3 | 8.91 | 22.5 |
| get_browser_state#1 | 3 | 62.53 | 68.4 |
| browser_navigate#1 | 3 | 47.64 | 48.5 |
| get_browser_state#2 | 3 | 25.57 | 30.0 |
| browser_type#1 | 3 | 1613.84 | 1614.2 |
| get_browser_state#3 | 3 | 6.12 | 7.6 |
| browser_click#1 | 3 | 1550.28 | 1556.2 |

