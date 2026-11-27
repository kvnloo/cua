# CUDA Bend action-law experiments

## Verdict

**Do not put CUDA Bend in cua's per-action hot path on this evidence.**
The existing recipe-local Python guard took approximately 4.8–5.0 microseconds.
Bend's full 4,096-case finite model agreed with an independent Python oracle,
but GPU execution plus serialization took approximately 103 milliseconds.
This is exhaustive conformance of an explicit finite projection, **not** a
universal BendTT proof, a verified compiler, or evidence of correct GUI grounding.

These are research-only artifacts. No production module imports this directory.
No model calls, GUI actions, provider configuration changes or permissions were
issued by the experiments. No runtime treatment is promoted.

## Model and metrics

`model.bend` uses ten semantic action IDs plus six invalid IDs, and eight Boolean
state flags: fresh, granted, unique target, calculator open, calculator focused,
task complete, event confirmed and task supported. The full finite projection is
16 × 256 = **4,096** inputs. Action argument parsing, source authenticity,
intent classification and real observation truth are outside this projection.

- **C1:** GPU action guard versus hand-written Python, NumPy and the identical
  native binary with GPU disabled and two CPU threads. Exactly 236 allow and
  3,860 deny cases; zero false accepts/rejects against the independent semantic
  oracle. All-allow/all-deny output controls disagree on 3,860/236 inputs.
- **C2:** four candidate actions × four possible states, changing calculator and
  focus flags. Accept only one robustly legal candidate; abstain if zero or
  multiple remain. All 4,096 masks match the independent oracle. There are 340
  uniquely resolvable groups, 224 multi-safe groups and 3,532 no-safe groups.
  A first-candidate/single-observed-state baseline resolves 104/340 unique groups
  and has four unsafe accepts and 236 missed unique alternatives. Robust
  filtering resolves 340/340 with zero errors **relative to this finite model**.
  Python gives the same decisions; task/visual ambiguity is not measured.
- **C3:** the table emitted by CUDA runs in Python at 53.8 ns per lookup versus
  136.3 ns for the hand-written bit guard (loop/call overhead included). The same
  table is independently generated in Python; this is a table-compilation gain,
  not a Bend-specific improvement. Corrupting one entry causes one mismatch.

**Model-call count is zero in every kernel arm. No LLM-call saving was measured.**
Legality cannot substitute for choosing the right action for an informal request.

## Timing cohort

Python 3.14.7, NumPy 2.5.3, official Bend 2.0.35 executable SHA-256
`af967c7c37aced4491e0f4344e3bb9de837c2c89b7519f7e0b8c71935be1840a`,
RTX 3080 Ti. Native CUDA uses `!`, `CUDA_HOME=/opt/cuda`, adjacent `.gpu`
artifacts, explicit `--gpu 1GB`, `nice`, bounded commands and monitored admission.
Owned binaries were observed in `nvidia-smi`, up to 250 MiB in retained samples.
No silent CPU-only fallback is counted as GPU evidence.

Five kernel calls run in one process with a changing seed. The internal monotonic
clock has **1 ms resolution**. Small 0–1 ms measurements are quantized, not zero
cost. The following warm medians exclude the first call. Native-C is limited to
two threads, not the machine's full twenty. NumPy runs one process, chunked at
2^20 inputs, and includes array generation and reduction. Python larger than
2^20 is not run. Source compilation is outside runtime timings.

| Workload | Inputs | GPU warm ms | Native-C, 2 threads ms | NumPy median ms | Python ms |
|---|---:|---:|---:|---:|---:|
| Guard | 4,096 | 1 | <1, quantized | 0.078 | 1.011 |
| Guard | 1,048,576 | 1 | 0.5, quantized | 10.994 | 265.106 |
| Guard | 16,777,216 | 1 | 8 | 210.286 | not run |
| Guard | 268,435,456 | 8 | 306.5 | 4,879.046 | not run |
| Four candidates × four states | 4,096 groups | 1 | <1, quantized | 0.494 | 7.930 |
| Four candidates × four states | 1,048,576 groups | 1 | 3.5 | 880.180 | 2,833.817 |
| Four candidates × four states | 16,777,216 groups | 1 | 42.5 | 4,534.131 | not run |
| Four candidates × four states | 268,435,456 groups | 8.5 | 775 | 135,656.573 | not run |

These raw throughput crossovers are **not verification-speed wins**. The model
uses only the low twelve input bits. Large batches repeat the same 4,096 cases.
Python generates the complete guard table in 1.09 ms and complete candidate table
in 8.31 ms; both exactly match CUDA. A repeated batch checksum can then be folded
by period count in about 0.2 microseconds. This ablation invalidates a causal
claim that the enormous GPU/NumPy ratios accelerate this finite verification job.
The large candidate NumPy samples also varied from 93 to 187 seconds, so they
are unsuitable as a stable headline speedup.

Fresh-process five-call GPU wall times, including CUDA initialization and
monitoring, are retained in the receipts (about 98–481 ms); they must **not** be
divided into a one-call cold latency. The full-vector one-call jobs took
103.8/102.9 ms including serialization. A proposed microsecond-clock/fresh-call
refinement was refused before launch when IO PSI was 48.38/40.87, above 40.
The GPU was then released to another evaluation. No refined result is invented.
Shared-host GPU utilization ranged 19–57%; every command has adjacent telemetry.
This is not an exclusive-machine benchmark or an end-to-end cua speedup.

## Final research wave: genuinely large verification

The smallest remaining candidate is multi-step plan verification over ten real
semantic action categories. Depth eight has 10^8 nominal paths, but a faithful
256-state transition abstraction can use dynamic programming with at most
256 × 10 × 8 = **20,480** transition checks. An exponential path counter alone
would merely manufacture GPU work. No further CUDA stress test was run: a
faithful, path-dependent UI transition oracle and a noncompressible large state
corpus were not available in this experiment.

A useful next experiment needs at least roughly a million **distinct** state /
request / action evaluations, or a measured >0.15-second best CPU kernel, after
prefix sharing, state merging and decision-table caching. Freeze a faithful UI
transition model, retain per-path counterexamples, compare the best CPU dynamic
programming/bitset implementation, and include prediction, ingress, queue and
response latency. GPU Bend is plausible only for the residual large uniform
work. A kernel checksum alone is not per-trajectory correctness or task success.

## Reproduction and receipts

`experiment.py` creates the exact vector and batch sources from `model.bend`.
The measured sources and portable, privacy-minimized command receipts are under
`receipts/`. Native binaries/cubins and private runtime directories are excluded;
their measurement-time hashes are retained. The host-specific Bend path can be
overridden with `BEND_BIN`. The safety monitor uses the measured host's background
scan service and fails closed on a new compute tenant, interactive GPU use,
increased scan memory, scan errors, IO PSI ≥40, or less than 2 GiB GPU headroom.
Review these admission inputs for your host; do not remove gates to force a run.

```sh
CUDA_HOME=/opt/cuda BEND_BIN=/absolute/path/to/bend/bin/bend \
  nice -n10 timeout 900 python3 research/bend_action_laws/experiment.py
```

The command performs substantial optional research, including large NumPy loops;
it is not an ordinary CI test. It issues no desktop input. Do not run it alongside
another GPU experiment without coordinating ownership.

The ABAB decision, prior-work inventory, related work, maturity boundaries and
follow-on experiment are maintained in the owner's research report. The next
review is independent evidence review, not deployment approval.
