# stack-samples-2026-10-02: Hermes sample collection and shadow backend evaluation

Lane: stack SAMPLES (kvnloo/hermes-agent#319, 2026-10-01 directive). Scope: collect joined decision
receipts from an ordinary Hermes workload without changing Hermes behaviour, freeze them, and compare
base-rate and deterministic baselines with every locally runnable z0int backend on exactly the same
examples. No new architecture, protocol or question family, and no active control. `promotion_ready`
is false for every row.

`PREREG.json` was committed (726d6bf30) before any measured run. `python3 verify_artifacts.py` re-checks
everything below from committed data and prints `RESULT PASS`. A tamper test (one oracle verdict and one
turn label flipped in a scratch copy) prints `RESULT FAIL` (checks 4, 6 and 8).

## Results

**Workload (REAL).** 112 preregistered tasks; 105 ran and 7 were cut by the 08:35Z stop rule (NOT_RUN,
listed in `dataset/runs.jsonl`). Each ran as one isolated one-shot Hermes turn (hermes `exp/stack-samples-20261002`
5d01f608) with the metadata-only observer (#385), executor qwen2.5:3b on the system Ollama (0.16.1, CPU,
digest 357c53fb). The independent fixture oracle passed 48 and failed 57; 0 were unknown.

| kind | run | oracle pass | oracle fail |
|---|---|---|---|
| file tools (10 families) | 93 | 46 | 47 |
| CUA, GTK3 TaskWindow in a private Xvfb session | 12 | 2 | 10 |

- 97 runs exited 0 and 8 exited 1. Every exit 1 is Hermes's own `max_iterations_reached(4/4)`; there were no timeouts.
- Median wall time was 92 s per task.
- 0 observer rows were dropped, and 0 of 235 API attempts reached the 4096-token served context
  (`usage.prompt_tokens`).
- Per family: `find_file` 0/10 and `uppercase_copy` 0/10 passed; `json_field` 9/10 and `read_code` 8/9 passed.
- CUA: only 2 of 5 `cua_button_present` tasks passed. `cua_increment` and `cua_agree` failed (0/4) as preregistered:
  default approvals fail-close input actions in `-q` mode, and no approval bypass was used. `cua_read_counter`
  failed 0/3: the 3B model calls the default tool-search bridge (`tool_call`) with the wrong arguments.

**api.attempt_will_fail: DEGENERATE (H1 confirmed).** There were 235 joined attempts with 0 positives. The exact
one-sided 95% upper bound on the failure rate is 1.27%. The join audit counts 235 pre-request rows, 235 joined,
0 orphans, 0 terminals without a pre and 0 dropped rows. No backend ranking is claimed on this lane. The table
only shows miscalibration against an all-negative label.

| row | Brier | log-loss | note |
|---|---|---|---|
| deterministic LOO-run prior | 0.0000 | 0.002 | smoothed prior from other runs (all 0) |
| decider_2b | 0.0389 | 0.219 | every p < 0.4 |
| nanojev | 0.0864 | 0.348 | p ≈ 0.3 |
| deterministic 0.5 | 0.25 | 0.693 | |
| laya_421m | 0.3051 | 0.804 | p ≈ 0.55 on every attempt |
| julia_1 | 0.6285 | 2.111 | |
| qwen_3b_baseline | 0.9706 | 4.584 | p(fail) ≈ 0.98 on every attempt |

**verification_needed: carries signal (H2 confirmed); no backend beats the preregistered baseline (H3 not supported).**
There are 105 turn examples, all labelled: 57 positive ("the unverified outcome failed the oracle") and 48
negative. Every model row had coverage 1.0 (0 backend errors, 0 missing probabilities, no p exactly 0 or 1).

In the table, G3 compares each row with the deterministic leave-one-family-out prior using a paired bootstrap
(95% CI of the Brier difference, 2000 resamples over tasks). Latency columns: first call (cold, includes weight
load), then warm per-call p50 / p95. All latency comes from quiet-lane timed scoring processes (BENCHMARK,
canary-to-small-cohort grade).

| row | Brier | log-loss | ECE | acc@0.5 | G3 (Brier diff, CI) | first call ms | warm p50 / p95 ms |
|---|---|---|---|---|---|---|---|
| base rate in-sample (oracle-optimistic ref) | 0.2482 | | | | | | |
| deterministic constant 0.5 | 0.2500 | 0.693 | 0.043 | 0.543 | beats −0.021 [−0.032, −0.011] | | |
| deterministic LOO-family prior | 0.2709 | 0.735 | 0.000 | 0.352 | (reference) | | |
| julia_1 (CPU) | **0.2466** | 0.852 | 0.113 | **0.667** | no difference −0.024 [−0.074, 0.031] | 10 815 | 68.5 / 87.8 |
| laya_421m (CPU, current default candidate) | 0.2513 | 0.696 | 0.096 | 0.505 | no difference −0.020 [−0.042, 0.001] | 16 963 | 433.8 / 465.4 |
| nanojev (GPU, comparison only) | 0.2906 | 0.779 | 0.212 | 0.457 | no difference +0.020 [−0.022, 0.063] | 17 169 | 28.4 / 34.5 |
| decider_2b (GPU) | 0.4348 | 1.280 | 0.439 | 0.457 | **worse** +0.164 [0.081, 0.250] | 197 540 | 24.3 / 24.6 |
| qwen_3b_baseline (Ollama logprobs, CPU) | 0.5426 | 4.630 | 0.543 | 0.457 | **worse** +0.272 [0.170, 0.378] | 9 356 | 2 057.8 / 2 290.6 |
| JEV reference | NOT_RUN (TypeSafe, paid) | | | | | | |
| fail-open control (dead-port adapter) | coverage 0.0, 105/105 rows `backend_error` stage=create, scorer exit 0 | | | | | | |

**Reading the table.**
- The preregistered LOO-family prior is a weak reference: family prevalence varies from 0/10 to 10/10, so
  leave-one-family-out estimates move away from each held-out family's rate.
- Descriptively (not preregistered for G3), every model row is within ±0.004 Brier of the constant 0.5 except
  NanoJev, Decider and Qwen, which are worse.
- Julia has the best accuracy (0.667) and is the only row that separates classes.
- Decider, NanoJev and Qwen never cross 0.5 (pairwise disagreement 0.0), so they always say "safe to respond".
  Laya agrees with them on 98 of 105 examples (disagreement 0.067). Julia disagrees with each of them on 51% of
  examples.
- 19 of 105 examples are wrong for every model row; 32 are right for every model row.
- Brier by kind (cua / file): Julia 0.214 / 0.251, Laya 0.232 / 0.254, NanoJev 0.372 / 0.280,
  Decider 0.588 / 0.415, Qwen 0.833 / 0.505.
- Decider's api-lane first call (28.9 s) reused the turn run's compile cache; its turn-lane 197.5 s is the true
  cold start. `backend_create_ms` is under 0.1 s for every backend because weights load lazily on the first call.

## Evidence classes

- **REAL:**
  - The 105 Hermes runs, the observer rows and the oracle verdicts.
  - Every backend distribution: laya_421m, julia_1, decider_2b, nanojev (z0int 6764ae7) and the Qwen logprob baseline.
  - The fail-open control.
- **BENCHMARK:** each latency number above comes from a scoring process wrapped in `quiet-timed`.
  - Ledger lines are in `raw/quiet-lane-ledger.samples.jsonl`. All have rc 0, and all were acquired after
    collection ended at 08:36:45Z.
  - Load averages and GPU use before and after each process are in `raw/scoring-logs/`. The machine and GPU
    are shared with other lanes (load average ranged from about 2 to 12).
- **FIXTURE:**
  - The deterministic rows are arithmetic over the REAL labels.
  - The oracle self-test passes on 112 of 112 tasks.
- **UNIT:** the hermes lab suite gave 25 passed and 2 skipped through `run_tests.sh`. The 2 Ollama-adapter tests
  skip there because z0int is not on that runner's path; they pass under direct pytest with z0int on the path
  (13/13 in the 3 shadow test files).
- **SOURCE:**
  - Shadow output cannot reach Hermes: scoring is offline and starts after collection, and no Hermes runtime
    module reads examples or scored files.
  - The only Hermes code change touches the offline lab scripts. The observer plugin is unchanged from #385.
- **NOT_RUN:**
  - The JEV reference observer (TypeSafe, paid).
  - openjev_06b and openjev_4b (not registered; outside the requested set).
  - Plugin on/off behavioural equivalence (not in this lane's scope).
- **BLOCKED:**
  - CUA input tasks under default `-q` approvals (preregistered expectation; no bypass was used).
  - The orchestrator-allowed 64K-context Ollama on 127.0.0.1:11500. It is shared with other lanes, and this
    lane's model pull there was denied by the permission system, so the executor is qwen2.5:3b at a 4096-token
    served context on CPU. The observed 0/235 truncation means the 4K limit did not bind for this workload.

## Isolation

- Every run executed under `hostless` inside a bwrap that mounted an empty tmpfs over the live Hermes home,
  the real home, the host runtime dir and the host X11 socket dir.
- GUI runs kept only their private Xvfb socket bound. `mask.inside` shows 0 entries for every run, and
  `raw/env_checks.json` shows no live paths or provider-secret variables.
- HERMES_HOME was a fresh private dir per run. HTTP(S) egress went to a dead proxy except loopback.
- CUA tasks each ran in a fresh `cua-x11-session.sh` under `hostless` with private AT-SPI. The X11 kit was
  chosen because the Driver's AT-SPI path is verified there; the sway kit (canary-verified) was not needed.
- Live-home stat receipts (metadata only):
  - The live home directory's own mtime moved during every run, and `auth.json`'s mtime moved during 4 runs,
    with its size unchanged.
  - The `auth.json` mtimes step at about 45-minute intervals, and the first one observed (05:36Z) predates
    the first measured run (05:38Z). It is the concurrently running live Hermes; this lane's processes saw
    that directory as an empty tmpfs.
  - state.db, its WAL, config.yaml, .env and logs were unchanged in every run.

## Deviations and disclosures

1. **Isolation receipt redefined after the first freeze (no outcome impact).** The first freeze defined
   "live home unchanged" as all stat lines equal, which the live Hermes's own writes made false for every run.
   The receipt now compares file entries and lists the changed ones. The dataset was re-frozen twice for this
   receipt field only. `events.jsonl`, api examples, and turn requests and labels are byte-identical across
   all three freezes (content hashes 54f5aa49…, 3831e02e…, final 648e418e…).
2. **Harness changes after PREREG, before scoring.**
   - GPU headroom thresholds for decider/nanojev were set to 4800 / 3000 MiB.
   - `verify_artifacts.py` compares the re-run of `evaluate_shadow` with a 1e-9 float tolerance. The scorer
     venv is Python 3.11, and newer Python sums floats with compensation, so results differ in the last bits.
3. **Sanitizing.** Committed copies replace local path prefixes with `$VARS`. This includes 3 model-written
   `upper.txt` files that contained mangled local path fragments; their verdict (fail) is unchanged and
   re-derived by `verify_artifacts.py`.
4. **Pilots** (`pilot-01`, `pilot-cua-01`, `P-p000*`, `P-p001*`) used separate prompts and are excluded. Their
   receipts are in the local mirror only.
5. **The executor model is also the Qwen baseline scorer** (qwen2.5:3b), as declared in PREREG.
6. **Erratum E1:** `PREREG.json` gives the hermes commit as `5d01f608975ab1d3…`. The actual commit is
   `5d01f60897373e67f7a3af5a9150439760be93f9`. Only the first 10 hex digits match; the rest was mis-expanded
   by hand. All 105 runs recorded that true head with a clean worktree, and `verify_artifacts.py` checks it.
   PREREG is left unmodified; MANIFEST and provenance carry the correct hash.
7. **NanoJev identity quirk:** its `decision.revision` reports the Qwen3-0.6B backbone (`c1899de2…`). The bundle
   pin `4a19595e…` and `best.safetensors` sha256 `fff62d14…` are in `dataset/MANIFEST.json` identities.

## Layout

- `PREREG.json`: hypotheses, rows, oracle, controls, metrics, gates and claim boundary.
- `workload/`: frozen tasks (`tasks.jsonl`, sha256 0e05d3c3…) and fixtures.
- `dataset/`: `MANIFEST.json`, `events.jsonl` (1154 observer rows, z0int.hermes_observer_event.v1) and
  `runs.jsonl` (per task: status, session, verdict, isolation receipt).
- `raw/collect/`: the driver's index and the oracle verdicts.
- `raw/runs/<run>/`: oracle inputs (final reply, produced files, GUI state) plus exit code, argv and mask receipt.
- `raw/examples/`: api and turn examples and join audits.
- `raw/scored/`, `raw/eval/`, `raw/analysis/`: scored rows, evaluations and analyses.
- `raw/scoring-logs/`, `raw/controls/`, `raw/quiet-lane-ledger.samples.jsonl`: scoring receipts.
- `harness/`:
  - `workload.py`: generator and oracle.
  - `oracle_selftest.py`.
  - `collect.sh`: driver.
  - `freeze.py`.
  - `build_turn_examples.py`: z0int adapter join glue.
  - `score_lane.py`.
  - `run_scoring.sh`.
  - `analyze.py`.
  - `make_summary.py`.
  - `build_packet.py`.
  - Sanitized launcher copies.
  - `vendor/`: the exact hermes lab scripts used.
- `summary.json`, `provenance.json`.

## Claim boundary

- One executor model (qwen2.5:3b Q4_K_M, CPU, 4096-token served context) on one shared machine, with synthetic
  fixture tasks and N = 105 turns / 235 attempts.
- verification_needed labels are the proxy "the unverified outcome failed the oracle", not the normative
  decision-capability-v1 gold.
- CUA rows reflect default approvals and default tool search, not Driver capability.
- Nothing here authorises active control or promotes a backend.
