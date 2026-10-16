# Lane 5: CUA #110 tab scope check (independent CDP)

Base source: `25634766580fe4db2ecc333058cf199e9b4f4ea2`.
Host: Linux x86_64, Chromium 144.0.7559.96.
Scope: **direct CDP, not CUA Driver/MCP/native input**.

30 paired A/B and B/A trials (60 fresh two-tab contexts) applied the exact motion policy CDP payload to one tab, then cleared it. Independent DOM matchMedia and computed-CSS oracles inspected both tabs.

Result: 60/60 target reduced-motion, 60/60 untouched sibling, 60/60 target reset to ambient; 0 refuted or unknown after successful fixture setup. Exact 95% lower binomial bound for 60/60: 0.9404, under independent-trial assumption. No latency/speedup claim.

Fixture preflight: initial data: URL navigation was denied by browser administrator policy in 60/60 attempts. Replaced with set_content and restarted 30 pairs. The failed preflight is retained in the local archive.

Verification: independent JSON ledger validator and nine corruption/detection tests, 9/9 PASS. Original browser-motion-policy authors remain credited; this is a separate Lane 5 experiment. Unresolved: Rustfmt, native SDK/docs CI, native CUA Driver E2E, real-Driver whole-task tests. Do not label this Driver-certified.
