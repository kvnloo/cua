# Lane 5: isolated Chromium reduced-motion preflight — 2026-10-14

**Classification: LOCAL_ONLY / direct CDP, not a CUA Driver benchmark.**

## Question
Does the existing proposed driver-owned `prefers-reduced-motion` CDP policy in [kvnloo/cua#110](https://github.com/kvnloo/cua/pull/110) reduce decorative visual churn without affecting a simple independent button-submit oracle? This is *not* an end-to-end latency claim.

**Candidate source**: `7694da458342198dbce7f97eaa623450dcb022eb` (PR #110). **Actual experiment**: local Chromium `Chromium 144.0.7559.96 built on Debian GNU/Linux 13 (trixie)`, Python 3.13.5; policy applied through Playwright CDP rather than the CUA Driver. Browser fixture is embedded in `motion_ab.py`.

## Method
30 alternated AB/BA matched pairs (60 full attempts). Fresh isolated page/context per attempt; `Emulation.setEmulatedMedia` with `features: []` or `prefers-reduced-motion: reduce`. Same HTML, viewport, semantic Submit target, click path and independent target-owned journal. Five screenshot hashes per attempt; four successive comparisons. Failed/refuted attempts would remain in the ledger. Local Playwright motion setting is fixed to no-preference so CDP is the variable.

Reproduce on a disposable Linux host with Chromium at `/usr/bin/chromium` and `pip install playwright`:

```sh
python3 motion_ab.py
```

## Verified result

| Metric | Default | Reduce |
|---|---:|---:|
| Independent target journal verified | 30/30 | 30/30 |
| Median screenshot hash changes (of four) | 4 | 0 |
| Median click to oracle (ms) | 54.58 | 53.67 |
| P95 click to oracle (ms) | 65.85 | 67.35 |

Paired click-to-oracle median Δ (reduce minus default): −0.694 ms; 4,000-sample seeded paired-bootstrap 95% interval [−1.9915, +0.5855] ms. It crosses zero; **do not claim a latency improvement**. Reduced visual churn is a property of this cooperative decorative-animation fixture only, not all websites or downstream agents.

## Safety and promotion boundaries

This run executed **no CUA Driver, MCP, semantic snapshot, native Hyprland, permissions or real-user input**. Direct screenshot hashing says nothing about model-perception latency. Verify a real Driver-owned isolated browser, session/ref binding, unchanged semantic action set, negative cases and end-to-end whole-task costs before any upstream promotion. No new default or CSS suppression is proposed.

## CI follow-up on PR #110
Read-only audit of Oct 3 exact-head CI found three distinct gates: motion-tool input schema accepted unknown properties, ignored E2E test missing from allowlist/canonical runner, and Rust formatting. Branch `lane5/motion-policy-ci-20261014` contains **two source-level CI repairs** (closed schema; explicit manual inventory row). Original format violations and real native qualification remain open; no Rust CI pass claimed.

**Attribution:** #110 and #109 provide the motion-policy concept and CUA Driver-owned boundary; CUA's existing visibility/semantic contract and maintainer review constrain this work. This ChatGPT worker authored the isolated CDP preflight and fork-only CI follow-up; no other contributor's work was rewritten or claimed as a new feature.

Artifacts: `motion_ab.py`, `motion_ab_trials.json` (all 60 attempts), `motion_ab_summary.json`.
