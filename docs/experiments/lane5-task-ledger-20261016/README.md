# Lane 5 · fail-closed offline task-ledger qualification

**Scope:** local Python measurement-gate validator for [whole-task accounting #10](https://github.com/kvnloo/cua/issues/10). This directory does **not** implement or authenticate CUA Driver, a native desktop target, model, or browser CDP. It does not define a public `ActionResult` schema.

## Published implementation and reproducibility

- Existing non-default branch: `lane5/task-ledger-fail-closed-types-20261016`.
- Ledger baseline: `a57564cb68db05c8865e241000deda9fb019da2a`; baseline validator blob `0bc51bd19221e02a79d05f5770a8952c7efce983`.
- Fail-closed guard: `006435dad9d03c3646150e5978986b531bc11b8b`; validator blob `480a5c0d5dbe64760106083ed1f7393615c75cb9`.
- Five new regressions: `7e6aaeca529853a30629d1344abd1afed5c1b183`; test blob `a5e6f20c69b14012eb36e4d751dcb1ca062176f1`.
- Tested artifact identity: local git blob IDs match both published source and tests. Current suite: `python -m unittest discover -v` from this directory: **62/62 PASS**, Python 3.13. Malformed numeric sweep: `python numeric_fuzz.py`: **396 invalid / 396 rejected, zero exceptions** (runner supplied in earlier local evidence packet; not currently committed here). Five new regressions: three rejection scenarios plus two safe controls. Baseline red tests reproduced before guard, fixed version green.
- No full Rust/native CI, real Driver, AB/BA run_steps-vs-run_script trial, or speedup measurement from this source. `evidence_class=synthetic/offline validator`, **LIMITED**. No matched task arm order, independent target oracle, driver binary digest, latency CI or fallback overhead exists for this packet; do not populate them by inference.

## Cross-lane consumption

For Hermes, OMP, T3Code, GEV, z0evals: preserve the `session/ref/generation` binding and admission invariant; distinguish **attempted**, **applied**, **verified**, **refuted**, **refused**, **unknown** and cancellation; an ACK loss or cancelled action with possible effect is **unknown**, never permission for blind replay. Log logical mutation identities, each attempted route, actual delivery/effect, independent fresh oracle, and fallback overhead. A self-reported oracle flag is not independent physical-world proof. This document is a measurement handoff, not a schema proposal.

## Promotion boundary and credit

Existing repo-level promotion queue is [#74](https://github.com/kvnloo/cua/issues/74); keep #10 as the measurement owner and #73/#93 as architecture/research inputs. Original CUA authors, prior Lane 5 contributors, and their source/test history retain credit. These incremental validator checks were prepared from the existing offline evidence packets. No upstream action authorized by this publication.

**Next:** on existing draft [#110](https://github.com/kvnloo/cua/pull/110), finish exact-head Rustfmt/SDK/E2E and actual Driver-owned browser binding/refusal/override validation. Then real paired complete-task A/B in #10, preserving every failure/timeout/fallback and reporting uncertainty without invented speedups.
