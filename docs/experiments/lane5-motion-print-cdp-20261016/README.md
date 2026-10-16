# Lane 5: browser_motion_policy print-media compatibility (CHECK)

Date: 2026-10-16 UTC. Source: kvnloo/cua PR #110 head 25634766580fe4db2ecc333058cf199e9b4f4ea2 (motion_policy.rs blob 15a1ce97904c7d97d6fa08e55ac0138f30569fd5).

Independent Linux Chromium 144.0.7559.96 direct-CDP experiment, **not CUA Driver**: 24 isolated browser contexts; matched ABC/CBA arm order; 72 total arm applications; fresh print media precondition and independent matchMedia + CSS-width oracle.

- A: exact PR #110 payload (media: empty, reduced-motion feature): reduced 24/24, print preserved **0/24**, screen restored 24/24.
- B: same feature with media omitted: reduced 24/24, print preserved **0/24**, screen restored 24/24.
- C: carry-forward media: print: reduced 24/24, print preserved **24/24**, screen restored 24/24.

Two-sided 95% Wilson bounds: 0/24 [0, .138]; 24/24 [.862, 1]. Eight verifier unit tests passed, including tampered-ledger rejection. Raw SHA256: d954181d510b5614cb2d1880414bede3b5cecf53b0324aba96bb230ab5de2efa; full reproducible local packet retained separately.

Interpretation: setEmulatedMedia replaces print-mode overrides as well as media features; merely omitting media does not preserve print. This is **compatibility risk**, not a proven supported Driver regression. Requirement/ownership must be established before a source patch. No latency or Driver certification claimed. Rustfmt, native docs, SDK CI, Driver E2E still NOT_RUN; PR draft unchanged.

Cross-lane: distinguish attempted/applied/verified/unknown; no blind replay after lost ACK/cancel. Preserve session/ref/generation and admission. z0evals tag browser-CDP/synthetic-compatibility, whole_task=false.

Credit: original browser semantic, authorization, and motion-policy contributors retain attribution; this wave supplies independent CDP evidence only. No origin write or default merge.
