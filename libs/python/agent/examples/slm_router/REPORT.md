# Per-decision SLM routing experiment

## Verdict and scope

The measured frozen-corpus experiment does **not establish an end-to-end routing win**. Native Jev is a real evaluated policy, not a surrogate tree renamed as Jev. In the five-model replay, Jev improves the strict all-node task proxy from 1/11 to 2/11, but loses six correct decisions and takes longer than the training-selected fixed model. Distilled policies offer a latency/quality trade-off, not a Pareto improvement. The retrospective oracle is an unattainable upper bound, not a deployable policy.

**Clean native acceptance is pending.** An earlier native pilot is contention-confounded and lacks a completed fixed-model comparison. It must not be presented as clean end-to-end evidence. The seventh GPU candidate and clean remote-native comparison remain unavailable under the resource admission gates. This report preserves that distinction rather than substituting replay for native success.

## Frozen protocol

- 163 distinct semantic decision nodes from the union of original HobbyLM and Qwen traces over 31 supported tasks. Neither a successful-only corpus nor labels copied from candidate answers.
- Corpus SHA256: `c6dfbb96600d3f987a903bb6f94dab17b7d81565f9f4d4d3e675a760d13bd972`.
- Task-group split: 20 training tasks / 100 nodes; 11 held-out tasks / 63 nodes; seed 1729. Exact task IDs are in `results/final35/results.json`.
- Independent task-specification/state-derived progress scoring. Strict replay task success requires every frozen node of that task to be correct. This is **not native GUI final-state success**: routed actions would change future observations.
- Selection uses only decision-time request/context, depth, observation size, prior-action/error estimates, candidate availability, training quality profiles and measured device latency profiles. Held-out correctness is not a selection feature.
- All nodes expose the same ten action categories. Option-count/difficulty routing is therefore not established by this corpus.
- Three-model pool: Qwen3-1.7B Q4, Qwen2.5-0.5B, Qwen3-4B Q4. Five-model pool additionally includes Qwen3-0.6B and Qwen2.5-1.5B Q4. Frozen model identities and pool membership are in `groot.json`.
- R0 is a transparent training-profile rule; R1 is native TypeSafe Jev; R2/R3 are a depth-limited tree / 12-unit MLP distilled from training Jev choices; R4 selects the distilled family using training validation. Fastest-correct labels and the prespecified correctness-penalty sweep are separate cost-aware arms, not retroactive replacement of the original objective.
- Baselines include every fixed model, training-best fixed, seeded random, share-matched random, calibrated cheap-first cascade, and fastest-correct hindsight oracle. A cascade pays both generation calls.

## Final pinned three/five-model replay

Each row covers the same 63 held-out nodes / 11 tasks. Total time is the sum of measured frozen candidate generation and measured routing overhead, **not live trajectory wall time**. Model loading, dispatch/network, queueing and GUI execution are excluded from these replay totals.

| Pool | Policy | Correct nodes /63 | Strict replay tasks /11 | Total generation + routing, s |
|---|---|---:|---:|---:|
| 3 | Training-best fixed Qwen3-4B | 39 | 1 | 20.4694 |
| 3 | R1 native inline Jev | 27 | 1 | 29.1292 |
| 3 | R2 distilled tree | 21 | 0 | 35.1602 |
| 3 | R3 distilled MLP | 25 | 1 | 35.5680 |
| 3 | R4 training-validation selection | 25 | 1 | 35.5682 |
| 3 | Hindsight fastest-correct oracle | 39 | 1 | 15.3344 |
| 5 | Training-best fixed Qwen3-4B | 39 | 1 | 20.4694 |
| 5 | R1 native inline Jev | 33 | 2 | 28.0594 |
| 5 | R2 distilled tree | 32 | 1 | 16.8130 |
| 5 | R3 distilled MLP | 32 | 2 | 16.7490 |
| 5 | R4 training-validation selection | 32 | 2 | 16.7494 |
| 5 | Hindsight fastest-correct oracle | 42 | 2 | 10.4610 |

Authoritative artifacts: `results/final35/{results,analysis,r1-inputs,jev-training,jev-inline}.json`, fastest-correct training labels and exported tree text. Fitting ran off the desktop on an admitted MBP worker, Python 3.12, scikit-learn 1.7.2, numpy 2.4.6, scipy 1.17.1, joblib 1.6.0, one BLAS/OMP thread. Three 500-iteration MLP convergence warnings were retained; these are not claimed converged optima. No holdout-selected sweep point is promoted as a live policy.

The initial three-model experiment and its negative result remain separate evidence. Its R2 versus training-best fixed strict-proxy paired task-bootstrap difference was -9.09 percentage points, 95% percentile interval [-27.27, 0], 2,000 task resamples. That interval applies to the initial experiment, **not** the later final35 policies. Eleven held-out tasks are insufficient for an equivalence or broad generalization claim.

## Jev latency and spend

Final35 uses `typesafe/jev-1.14.0`:

- Training: 198 unique calls / 200 aliases, $0.015438906, concurrent batch wall 3.6856 s. This is throughput, not inline per-call latency.
- Held-out serial R1: 126 calls, $0.009773190. Three-pool client wall 8.483421 s /63 = 134.657 ms per choice; five-pool 11.296876 s /63 = 179.315 ms per choice. Per-call percentiles are not available from these serial batches.
- Separate uncached warm diagnostic: 20 sequential semantically equivalent requests with unique inert nonces, p50 234.98 ms, p95 4,045.39 ms, mean 1,284.65 ms. Identical-payload repeated calls had a 1.47 ms median and are cache/replay diagnostics, not credible inference latency. A cold 4.3 s probe includes adapter setup and is not steady-state inference.
- Direct native answers expose no isolated model-time field; model-only latency is unmeasured. Native policy evaluations include client wall overhead. Local candidate API dollar spend is zero; energy is unmeasured.

## Device coverage and missing seventh GPU column

The exported GPU matrix has six Qwen columns /978 rows. Its SHA256 is `98c7c8d6235fa9748f0c46e70677c9587e2813776ab6ce9bbbac52d89f689203`; provenance is adjacent to the matrix. The first three-candidate raw run requested CUDA and observed GPU allocation, but lacked per-model offload log lines. New collection rejects GPU claims without positive layer-offload evidence; that stricter proof must not be retroactively attributed to the original rows.

The MBP matrix has three columns /489 rows: HobbyLM Q4, Qwen2.5-0.5B and Qwen3-0.6B. Their independently scored held-out progress is respectively 31/63, 8/63, 7/63; per-node warm median generation is 2.945 s, 3.031 s, 4.345 s. Initial loads 0.505 s, 0.719 s, 0.621 s are separate. CPU measurements are not GPU measurements.

HobbyLM's 163-node GPU column remains unavailable: the matching CUDA plugin was built off-host, but the GPU owner's admission attempt exited 75 before model initialization. Five-prompt tuning results are not substituted for the corpus. Accordingly there is no final seven-model fit or ten-pair device ablation in this report.

The preserved nine-pair counterfactual device replay is not live dispatch and excludes queue/network/load costs. With both measured devices available its hand router scores 41/63 at 69.937 s, cost tree 29/63 at 17.025 s, cost MLP 34/63 at 64.633 s, and oracle 55/63 at 43.014 s. The training-best available fixed model differs by device: Qwen2.5-3B on GPU (27/63, 20.695 s), HobbyLM on MBP (31/63, 186.341 s). A better held-out fixed score does not authorize replacing the training-selected baseline after evaluation.

## Native execution and clean-run status

An earlier R2 native pilot completed 11 tasks: 4/11 final-state successes, 37 decisions, 1,978.016 s total task wall. Its host was subsequently found severely memory-contended, and the fixed arm was interrupted. These times are **not clean comparative CPU performance**. An earlier R1 arm failed at native adapter transport before inference; those transport errors are not model-quality failures.

The repaired runtime supports an admitted MBP resident model worker over finite stdin/stdout JSONL, without weakening SSH forwarding policy. It verifies model hashes, records model-switch/load and generation time, checks remote memory PSI before/after inference, and closes on EOF/stop. The native client persists route-level events and task-level results, including native Jev receipts and independent final-state oracles. GUI-only work is restricted to the owned headless guest, under exclusive ownership and host memory gates.

A subsequent finite MBP protocol probe completed and acknowledged stop (fleet job `20261023-191626-8386`). One cold Qwen3-4B request returned `OPEN Calculator`: model load 17.557729 s; generation 31.752557 s; memory PSI full avg60 0.07 before /0.96 after. This is **one cold transport/inference probe**, not a native task comparison, warm speed claim or acceptance result. The 3 GiB worker cap was admitted; no local desktop model process was started.

Clean R1 / distilled / fixed native arms have not run after recovery because the existing guest has not passed its owner's memory-gated prerequisite and ownership handoff. No guest was independently resumed. Completion requires fresh per-arm trace directories, identical remote model runtime and guest setup, all 11 held-out tasks, all route/switch/dispatch/GUI wall time, and the final-state oracles. The oracle remains a replay upper bound; an oracle live selector cannot be claimed free or implementable.

## Reproduction and publication boundaries

The recipe is opt-in and experiment-local. It adds no Cua Driver router service. Start with `corpus.py`, collect with `collect.py`, independently score/export with `export.py`, prepare/evaluate with `experiment.py`, and inspect trade-offs with `analyze.py`. Run teacher and inline adapters inside the native OMP evaluation context; a substitute or unavailable backend must be disclosed rather than called native Jev. Native GUI arms use `dynamic.py`, `remote.py` and `jev_bridge.py`. Dependencies are in `requirements.txt`; model paths are environment-specific manifests, not bundled weights.

Only trusted locally generated policy bundles may be loaded by the native harness. Joblib artifacts, model weights, caches, temporary sockets, account credentials and private operational handoffs are excluded from publication. Builds, lint and unit-test verification are assigned to the integrating agent; no passing claim is made here. This downstream research result must not be represented as an accepted clean end-to-end improvement.
