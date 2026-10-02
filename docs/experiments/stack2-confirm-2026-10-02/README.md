# stack2-confirm-2026-10-02: fresh frozen sample set and julia_1 confirmation test

Lane: stack v2 CONFIRM (kvnloo/hermes-agent#319). This lane collected a fresh set of 142 ordinary Hermes turns on the
fixed integration (ADDR token addressing, cua-driver 0.32.0, tool search off). It froze the set before any scoring and
then ran the preregistered one-sided test of julia_1 against the SAMPLES deterministic prior on `verification_needed`.
No behaviour was changed, nothing ran as a shadow sidecar, and no active control was added. An independent fixture
oracle graded every turn.

Commit order on `exp/stack-confirm-20261002` (kvnloo/cua):

| Commit | Content | Time (UTC) |
|---|---|---|
| f11cd9d8 | `PREREG.json`, workload, collection harness | before the first measured run (19:29:47Z) |
| 821d895a | analysis and scoring harness, including the confirmatory test | during collection, before the freeze |
| fa8399e1 | frozen `dataset/` and raw collection receipts | 20:02:56Z, after the last run (20:00:54Z) and before the first scorer (20:03:09Z) |
| this commit | scoring outputs, analysis, summary, README, verifier | after scoring |

`python3 verify_artifacts.py` from this directory checks all of the above and prints `RESULT PASS`.

## Answer

**Not confirmed.** On the fresh set, julia_1 did worse than the deterministic prior, not better:

| Metric (n = 142, 48 positives) | julia_1 | LOO-family prior | Mean difference | One-sided 95% upper bound | p_boot | H0 rejected |
|---|---|---|---|---|---|---|
| Brier | 0.2563 | 0.2468 | +0.0094 | +0.0454 | 0.67 | no |
| log-loss | 0.744 | 0.692 | +0.052 | +0.150 | 0.81 | no |

- **Verdict: NOT_CONFIRMED.** The preregistered rule needed both bounds below 0 (intersection-union test, alpha 0.05).
- **Preconditions met.** 142 labelled turns, 48 positives, 94 negatives, julia_1 coverage 142/142. No probability was
  imputed, so the complete-case sensitivity analysis is identical to the primary one.
- **The SAMPLES lead did not replicate.** In SAMPLES, julia_1 had the best point Brier (0.2466 vs 0.2709, CI
  crossing 0). Here its point estimate is on the wrong side.
- **Other rows** (descriptive only, no test, no ranking; see below):
  - nanojev and laya_421m have Brier and log-loss intervals entirely below the reference. Both still answer "safe"
    (p < 0.5) on every turn, as do decider_2b and the Qwen row (accuracy 0.662 = the negative rate). Their Brier
    (0.2231 and 0.2281) is about the in-sample base-rate constant (0.2238).
  - So the reference is beaten by calibration near the base rate, not by separating the classes. The
    LOO-family prior is weaker than that constant here, because the pass rate differs a lot between families.
  - julia_1 is the only row that ever predicts "verify" (40/142 turns at p >= 0.5). Its calls are poorly
    calibrated (ECE 0.186).
- **api.attempt_will_fail is DEGENERATE.** 0 positives in 418 joined attempts (one-sided 95% Clopper-Pearson upper
  bound 0.71%). 1 orphan pre-request, from the one timed-out turn, is counted. This row is reported, not ranked.

## 1. Fixed integration and isolation

- **Hermes:** `exp/stack-confirm-20261002` @ b51c7a22 (kvnloo/hermes-agent).
  - Runtime: byte-identical to the ADDR head d39e1175. `git diff d39e1175 b51c7a22` touches only the offline scripts
    `lab/z0_hermes_observer/{shadow_api_failure,evaluate_shadow,ollama_logprob_backend}.py` and `tests/lab`.
  - No runtime file references z0int (SOURCE grep). The observer plugin is unchanged and every hook returns None.
- **Hermes profile:** the SMOKE/ADDR profile, verbatim:
  - tool search off; computer_use `standard`;
  - the SMOKE explicit per-action cua grants;
  - no `--yolo`, no single-query approval mode, no bypass variable;
  - the observer plugin on.
- **Executor model:** qwen2.5:7b-instruct 845dbda0 (Q4_K_M) on the shared user-local Ollama 0.35.0 at 127.0.0.1:11500
  (GPU), with a 32768-token served context. The peak prompt was 12,837 tokens, so nothing was truncated.
  - Sampling was ordinary: no temperature-0 tag was created.
  - The server was not started, stopped or reconfigured, and nothing was pulled into it.
- **cua-driver** 0.32.0 (sha256 8b037961...). Each CUA turn ran in a fresh private Xvfb session (`cua-x11-session.sh`
  under hostless v2, private AT-SPI).
- **Isolation receipts:** 142/142 runs (`isolation.ok` in `dataset/runs.jsonl`). Inside Hermes:
  - the live Hermes home, the real home, the fixture-state dir and the host runtime dir were empty tmpfs;
  - `/tmp/.X11-unix` was empty in file runs and held only the private display socket in GUI runs;
  - no host display variable and no live-home path appeared in the environment;
  - the packet dir and the lane collect dirs (the answer keys) were also masked.
- **Live-home stat.** The file entries were unchanged in 141/142 runs. In one run (c086, 19:50Z), `auth.json`'s mtime
  moved with no size change. Hermes saw the live home only as an empty tmpfs in that run, as in every run. This matches
  the ADDR finding that the long-running live Hermes processes rewrite `auth.json`. Disclosed, not attributed to this lane.

## 2. Workload and frozen set (REAL)

There are 142 tasks (`workload/tasks.jsonl`, sha256 f192ff16...), generated with seed 20261012 and shuffled with seed
20261013 before any outcome existed. Every task ran in file order within the 4-hour budget: 31 min wall, deadline
23:14:41Z, 0 NOT_RUN.

- **100 file-tool turns.** The 10 SAMPLES families, verbatim, with fresh instances; `-t file`, `--max-turns 6`.
- **42 computer-use turns.** `-t computer_use`, `--max-turns 12`:
  - GTK3 TaskWindow: `cua_agree` 8, `cua_increment` 8, `cua_size` 6, `cua_note` 6, `cua_button_present` 6;
  - the jev-use form in Chrome: `browser_submit` 8.
- **Oracle:** `fixture_oracle:stack2-confirm-v1` (`harness/workload.py`). It reads only the reply, the cwd files or the
  fixture-owned state captured after Hermes exited.
  - GTK tasks pass only if the target holds and nothing else changed.
  - The self-test passed 142/142 before the measured runs.
  - Re-running the oracle on the committed raw receipts reproduces all 142 verdicts.
- **Freeze:** `dataset/MANIFEST.json`, content sha256 281a20e4... It holds 2039 observer rows, 0 dropped. One session id
  came from the observer spool (counted in the audit) because the timed-out turn printed none.

| Slice | Pass | Fail |
|---|---|---|
| all | 94 | 48 |
| file | 76 | 24 |
| cua | 18 | 24 |
| `uppercase_copy` | 0 | 10 |
| `sum_numbers` | 1 | 9 |
| `no_tool_math` | 7 | 3 |
| `count_errors`, `find_file` | 9 each | 1 each |
| other file families | 10 each | 0 |
| `cua_button_present` | 6 | 0 |
| `cua_agree` | 6 | 2 (both at density 24: 1 distractor action) |
| `cua_size` | 5 | 1 |
| `cua_increment` | 1 | 7 (wrong count 5, collateral 2) |
| `cua_note` | 0 | 6 |
| `browser_submit` | 0 | 8 |

Hermes exit codes: 141 runs exited 0, and 1 run exited 124 (c069 `sum_numbers`, the 300 s timeout; kept). There were 0
harness errors. The median turn took 6.0 s (a descriptive figure from unlocked collection, not a latency). Tool calls:
computer_use 157 ok / 6 error; the file tools 105 ok / 6 error.

**Finding (recorded, not fixed; outside this lane's scope).** All 6 `cua_note` and 6 of the 8 `browser_submit`
failures share one pattern:

- The model called `type` with an `element` index on the entry, then clicked Submit / Save note.
- Hermes' `type` action does not use `element` (`tools/computer_use/tool.py`: `backend.type_text(text)`), so the keys
  went to whatever had focus. The Driver reported `effect: unverifiable`, and the state shows an empty note or no
  submission.
- The other 2 browser runs used `set_value(e15)` on the Chrome entry, which also did not land.
- cua-driver 0.32.0's `type_text` advertises `element_token`. Wiring it, or refusing `element` on `type`, is an owner
  decision for kvnloo/hermes-agent. It is a natural next contract fix after ADDR.

## 3. Shadow evaluation (offline, after the freeze)

Every scorer ran under hostless with HF_HUB_OFFLINE=1, a private Z0INT_HOME/TMPDIR and explicit checkpoints. Each ran
in its own process, wrapped in `quiet-timed` (10 ledger lines, all rc 0, all after the freeze commit). The 11500 chat
model was unloaded (keep_alive=0, `/api/ps` empty) before nanojev and decider_2b, which then ran alone. A foreign
process held about 0.9 GB and 18-32% GPU utilisation throughout (`raw/gpu/gpu-snapshots.log`).

### verification_needed (142 labelled, 48 positive; reference = LOO-family prior)

| Row | Brier | log-loss | ECE | acc@0.5 | Brier diff vs ref [95% CI] | log-loss diff vs ref [95% CI] | coverage |
|---|---|---|---|---|---|---|---|
| deterministic_loo_group_prior (ref) | 0.2468 | 0.692 | 0.002 | 0.662 | ref | ref | 142/142 |
| **julia_1 (confirmatory)** | 0.2563 | 0.744 | 0.186 | 0.620 | +0.0094 [-0.034, +0.053] | +0.052 [-0.065, +0.167] | 142/142 |
| laya_421m | 0.2281 | 0.649 | 0.056 | 0.662 | -0.0188 [-0.030, -0.008] | -0.043 [-0.069, -0.019] | 142/142 |
| nanojev (comparison only) | 0.2231 | 0.638 | 0.012 | 0.662 | -0.0237 [-0.030, -0.018] | -0.054 [-0.068, -0.041] | 142/142 |
| qwen_7b_logprob | 0.3380 | 3.754 | 0.338 | 0.662 | +0.0912 [+0.043, +0.139] | +3.062 [+2.284, +3.845] | 142/142 |
| decider_2b | 0.2841 | 0.875 | 0.247 | 0.662 | +0.0373 [+0.002, +0.075] | +0.183 [+0.065, +0.309] | 142/142 |
| constant 0.5 | 0.2500 | 0.693 | 0.162 | 0.338 | +0.0032 [-0.024, +0.030] | +0.001 [-0.057, +0.057] | 142/142 |
| SAMPLES prior 57/105 | 0.2657 | 0.725 | 0.205 | 0.338 | +0.0189 [-0.016, +0.053] | +0.033 [-0.040, +0.104] | 142/142 |
| base rate in-sample (optimistic ref) | 0.2238 | | | | | | |
| fail-open control (dead-port Ollama adapter) | coverage 0: 142/142 `backend_error` stage=create, scorer rc 0, no row dropped | | | | | | |
| JEV reference | NOT_RUN (paid) | | | | | | |

The difference intervals are descriptive: two-sided, 2000 resamples, seed 20261002. They carry no claim. Calibration
bins (5 per row, plus 10 for julia_1) are in `raw/analysis/turn-analysis.json`.

**Slices (Brier).**

| Row | file (n = 100, 24 pos) | gtk3 (n = 34, 16 pos) | browser (n = 8, 8 pos) |
|---|---|---|---|
| julia_1 | 0.219 | 0.314 | 0.473 |
| reference | 0.215 | 0.284 | 0.490 |
| nanojev | 0.193 | 0.266 | 0.420 |
| laya_421m | 0.206 | 0.255 | 0.385 |
| decider_2b | 0.201 | 0.399 | 0.839 |
| qwen_7b_logprob | 0.240 | 0.471 | 1.000 |

**Disagreement at 0.5.** julia_1 disagrees with every other row on 40/142 turns (28.2%). All other model rows and the
reference agree on every turn ("safe"). Every model row was wrong on 31 turns:

| Family | Turns where every model row was wrong |
|---|---|
| `sum_numbers` | 7 |
| `uppercase_copy` | 7 |
| `browser_submit` | 5 |
| `cua_increment` | 5 |
| `cua_note` | 4 |
| `cua_agree` | 2 |
| `find_file` | 1 |

Every model row was right on 71 turns.

### api.attempt_will_fail (418 joined attempts)

DEGENERATE: 0 positives. Denominators (`raw/examples/api-audit.json`):

| Count | Value |
|---|---|
| pre-requests | 419 |
| joined | 418 |
| orphan pre-requests (unclosed) | 1 |
| overwritten orphans | 0 |
| terminals without a pre-request | 0 |
| rows dropped | 0 |

Brier with full coverage: prior 0.0000, decider_2b 0.039, nanojev 0.091, qwen_7b_logprob 0.150, constant 0.5 0.250,
laya_421m 0.335, julia_1 0.518. These measure miscalibration only, not signal. No ranking.

### Latency (BENCHMARK, quiet-timed; turn-lane process; ms)

| Backend | Cold (create + first call) | Warm p50 | Warm p95 | Warm max |
|---|---|---|---|---|
| julia_1 (CPU worker) | 10,803 | 69.2 | 105.0 | 109.6 |
| laya_421m (CPU) | 13,452 | 420.6 | 451.4 | 695.4 |
| nanojev (GPU, alone) | 17,262 | 27.8 | 29.6 | 36.8 |
| qwen_7b_logprob (GPU Ollama, model resident) | 537 | 52.4 | 57.6 | 79.1 |
| **decider_2b (GPU, alone; the GPU slot)** | **240,712** | 28.4 | 28.9 | **183,222** |

decider_2b's first process paid 240.6 s on the first call (torch.compile/inductor). One warm call (index 13) stalled
for 183.2 s, which reproduces the SAMPLES call-3 stall. The second decider process (api lane, same TMPDIR) had a cold
start of 35.2 s, a warm p50 of 22.7 ms and a max of 30.8 ms, so a persisted compile cache removes most of the cold
cost. All five rows report the scorer wall-clock series; it matches the backend `latency_ms` series to 0.1 ms.

## 4. Evidence classes

- **REAL:** 142 Hermes turns and their oracle verdicts; the frozen dataset; the joins through
  `adapters.hermes_z0int.normalize_envelope`, `close_observation` and `join_outcome`.
- **BENCHMARK:** scorer latency under `quiet-timed`.
- **UNIT:**
  - The Ollama adapter's single-label refusal: red before b51c7a22 (2 failed), then `tests/lab` 29 passed.
  - The token-contract suite: 16 passed (`raw/unit/`).
- **SOURCE:**
  - Hermes runtime identical to d39e1175; no runtime z0int reference.
  - The `type` action ignores `element`.
- **NOT_RUN:**
  - JEV reference (paid);
  - openjev (not registered);
  - single-compositor multi-seat (not in scope).
- **BLOCKED:** none.

## 5. Changes made (allowed scope only)

- **kvnloo/hermes-agent `exp/stack-confirm-20261002`:**
  - 7dc9ea03: a cherry-pick of the SAMPLES harness hygiene 5d01f608 (question-id parameter, explicit denominators,
    the Ollama logprob adapter).
  - b51c7a22: the adapter now refuses when only one of true/false is in the top-20 first-token logprobs, instead of
    emitting p = 0 or 1. This is the edge case SAMPLESFIX disclosed. It was not triggered here: 0 rows hit exactly
    0/1, and 0 backend errors.
- **kvnloo/cua:** this packet and its harness only. No Driver change.

## 6. Deviations and disclosures

- **Pilots.** 4 tasks generated with seed 777 were excluded (`raw/pilots/`). They found 3 harness defects, fixed
  before the PREREG commit:
  - `run_task.sh` was not executable;
  - `CUA_HOSTLESS` was not forwarded into the X11 session;
  - the host `/run/user/<uid>` and `/tmp/.X11-unix` were visible inside Hermes in GUI runs. They are masked now.
  - The same exposure existed in the ADDR and SMOKE `run_one.sh`. There, Hermes connected only to the private
    display; that is recorded for the next lane.
- **Analysis code.** It was committed after collection began but before the freeze, as PREREG states. While writing
  it, the lane owner saw only task counts, not verdicts.
  - `make_summary.py`, `sanitize_copy.py` and `verify_artifacts.py` were written after scoring. They only read
    committed files.
  - `build_turn_examples.py` gained an observer session-id fallback (used once, counted) before the freeze.
- **Sanitization.** Local path prefixes in raw receipts were replaced by placeholders (`raw/runs/sanitized.json`
  lists the 639 files). Oracle verdicts are unaffected: the re-run on the sanitized copies matches 142/142.
  `state.db`, configs and screenshots are not committed.
- **The 11500 server** is shared and was not started by this lane, so this lane did not stop it. The chat model is
  left unloaded, and `users.d/stack2-confirm.json` is marked DONE.

## 7. Claim boundary

- One executor (qwen2.5:7b-instruct Q4_K_M, GPU, 32K context), one machine, synthetic fixture tasks, 142 turns.
- `verification_needed` labels use the proxy "the unverified outcome failed the oracle".
- The reference is the SAMPLES LOO-family prior. Here it is weaker than the in-sample base-rate constant.
- Descriptive differences for other rows are not tests.
- Latency is small-cohort grade on a shared GPU.
- No backend is promoted (`promotion_ready: false`), and nothing here enables active control.

## Layout

- `PREREG.json`, `README.md`, `summary.json` (from `harness/make_summary.py`), `provenance.json`, `verify_artifacts.py`,
  `SHA256SUMS`.
- `workload/`: tasks and fixtures.
- `dataset/`: the frozen set.
- `harness/`:
  - collection: `drive.py`, `run_task.sh`, `workload.py`, `oracle_selftest.py`, `fixture_serve.py`;
  - freeze, examples and scoring: `freeze.py`, `build_turn_examples.py`, `score_lane.py`, `run_scoring.sh`;
  - analysis and summary: `analyze.py`, `make_summary.py`, `sanitize_copy.py`;
  - `vendor/lab/z0_hermes_observer/`: the offline scorer scripts at b51c7a22, which the verifier uses.
- `raw/`:
  - `collect/`, `runs/<run_id>/` (sanitized per-run receipts), `pilots/`;
  - `examples/`, `scored/`, `eval/`, `analysis/`, `scoring-logs/`, `controls/`, `gpu/`;
  - `quiet-lane-ledger.confirm.jsonl`, `unit/`, `run_scoring.log`, `freeze_commit.txt`.
