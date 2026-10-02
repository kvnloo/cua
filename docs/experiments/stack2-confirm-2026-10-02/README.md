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
| 96e0eede | scoring outputs, analysis, summary, README, verifier | after scoring |
| this commit | correction round 1 (section 8): tool-result audit, rewritten finding, disclosures, verifier hardening | after independent verification; no re-collection, no re-scoring |

`python3 verify_artifacts.py` from this directory checks all of the above and prints `RESULT PASS`. Set `TMPDIR` (the
verifier otherwise uses a hidden scratch dir next to this packet and removes it).

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
  - Hermes runs as `hermes_cli.main chat -Q ... -q <prompt>` (single-query mode) with the SMOKE explicit per-action
    cua grants: `click`, `type`, `key`, `scroll` in background and foreground mode, `set_value` in background mode only;
  - any other computer_use action (`focus_app` in either mode, foreground `set_value`, ...) is refused by Hermes'
    approval gate before it reaches the Driver. This happened in 3 of the 42 CUA runs, all failures (section 2);
  - no `--yolo`, `approvals.single_query_mode` is not set to approve, no bypass variable;
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
- **Live-home stat.** The outer harness (`run_task.sh` `snap`) records `stat` metadata (name, mtime, size) of the
  live Hermes home directory and of its `state.db`, `state.db-wal`, `config.yaml`, `.env`, `auth.json` and `logs`
  before and after each run. It never opens or reads their contents. This carries over from ADDR.
  - The listed file entries were unchanged in 141/142 runs. In one run (c086), `auth.json`'s mtime moved to 19:50:22Z
    with no size change. It had already been rewritten at 19:05:23Z, before the PREREG commit and the first run.
  - The live home **directory** mtime moved in 140/142 runs. Across all 184 distinct recorded directory mtimes (19:29:45Z to
    20:00:50Z) every gap is a multiple of 5.0 s (181/183 within 0.02 s), i.e. an outside periodic writer on a 5 s
    cadence, not this lane's turn boundaries.
  - Hermes saw the live home only as an empty tmpfs in every run (`live_hermes_home_entries` 0 in 142/142). This
    matches the ADDR finding that long-running live Hermes processes write there. Disclosed, not attributed to this lane.

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
harness errors. The median turn took 6.0 s (a descriptive figure from unlocked collection, not a latency).

**Tool calls, classified from the raw tool results** (correction round 1; `harness/tool_audit.py` reads every
`role=tool` row of each run's private `state.db` read-only and joins it to its call by `tool_call_id`; per-call
classification in `raw/analysis/tool-calls.jsonl`, totals and per-run sequences in `raw/analysis/tool-audit.json`).
The original tally "computer_use 157 ok / 6 error" used the observer's Hermes-level tool status, which is `ok`
whenever the handler returned. It therefore counted Driver `ok: false` refusals and Hermes approval blocks as ok.
That tally is withdrawn.

| computer_use (163 calls) | Count |
|---|---|
| capture returned elements (incl. Hermes' byte-identical-result note on a repeat capture) | 67 |
| Driver `ok: true` (every one with `effect: unverifiable`: 64 click, 5 type, 1 key) | 70 |
| Driver `ok: false` `set_value` / `set_value_unavailable` (GTK check box / radio: no accessibility value route) | 12 |
| Driver `ok: false` `type_text` / `background_unavailable` (no focus-free input backend; retry in foreground) | 7 |
| Hermes approval gate, single-query mode: `set_value` foreground 2, `focus_app` background 1, foreground 1 | 4 |
| Hermes error: unknown action `capture_after` | 2 |
| Hermes repeated-call note on a click (no dispatch) | 1 |

File tools: 111 calls, 105 ok, 6 errors (5 `patch` refusals, 1 `write_file` overwrite refusal).

**Why the CUA input tasks failed: per-run mechanism from the raw tool results** (REAL; recorded, not fixed).

| Runs | What the tool results show | Fixture state |
|---|---|---|
| `cua_note` c006, c011, c054, c082, c084, c106 (6) | `type(element=6)` in background mode was refused by the Driver, `background_unavailable`. Nothing was typed. In c006 and c084 the model passed `keys` instead of `text`, so Hermes would have sent empty text anyway. The model then clicked Save note (`ok`, `effect: unverifiable`; c011 and c106 clicked it again in foreground) and never retried the `type` in foreground. | `note_saved` "" in all 6 |
| `browser_submit` c004, c026, c078, c087, c094 (5) | `type(element=15)` in foreground was delivered by the Driver as real key events (`route: global_input`, `focus_after=target`, `effect: unverifiable`), then the Submit click (e16) was delivered (`unverifiable`). | no submission |
| `browser_submit` c104 (1) | `type(element=15)` in background was refused, `background_unavailable` (Chromium); the following click was delivered. | no submission |
| `browser_submit` c009 (1) | `set_value(e15)` with `delivery_mode: foreground` was **blocked by Hermes' approval gate** (no foreground `set_value` grant in single-query mode) and never reached the Driver; the Submit click was delivered. | no submission |
| `browser_submit` c052 (1) | `focus_app` and then foreground `set_value(e15)` were both **blocked by Hermes' approval gate**; the run ended there. | no submission |

Other CUA failures, for completeness: `cua_size` c108 (`set_value(e3)` refused `set_value_unavailable`, then
`focus_app` **blocked by the approval gate**); `cua_agree` c044, c136 (`set_value(e34)` refused `set_value_unavailable`, then a
foreground click on e34; the oracle saw `agreed` false and one distractor action); `cua_increment` 7 runs (clicks only, wrong count or a click on another
element). Approval blocks occurred in 3 of the 42 CUA runs (c009, c052, c108), all failures, and in no passing run.

What this does and does not establish:

- **SOURCE fact:** Hermes' `type` action ignores `element` (`tools/computer_use/tool.py`: `backend.type_text(args.get("text", ""), ...)`);
  it also ignores `keys`. This is a fact about the code, not by itself a cause of these failures.
- **`cua_note`:** the cause is the Driver's background refusal plus the model never retrying in foreground; no keys
  were sent. `element` being dropped did not matter in these runs.
- **The 5 foreground browser runs:** keys were delivered to the focused widget of the Chrome window. The form's field is
  `required` and the fixture records any non-empty submission, so no submission means the field stayed empty or the
  Submit click did not submit. Which of the two is not determined from the receipts (no capture followed). That the
  keys missed the field because `element` was dropped is **consistent with the receipts but not shown**.
- **Approval blocks:** they stopped 4 actions in 3 failing runs. That does not show that granting them would have
  produced a pass (c108's `set_value` was already refused by the Driver; c009's value entry was the blocked step).
  This is not a basis for any approval bypass; none is requested, and grants stay an owner decision.
- **`element_token` on `type_text` as the fix is a HYPOTHESIS, not tested here.** cua-driver 0.32.0's `type_text`
  advertises `element_token`; whether a token-addressed `type_text` lands in background mode on these surfaces, or
  focuses the field in foreground mode, has not been probed. Wiring it, or refusing `element` on `type`, remains an
  owner decision for kvnloo/hermes-agent.

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

**Host load during the latency rows.** Besides the foreign GPU process, the CPU was not idle. The 1-minute loadavg
logged at the start of each scorer (`raw/scoring-logs/*.log`, `loadavg_before`) was 1.8 to 3.4 for every process
except the turn-lane decider_2b run, which started at 11.04 (the preceding api-lane nanojev scorer ended at 5.03, so
the extra load is not attributed). The CPU-heavy scorers raised the load themselves (laya_421m ended at 10.0 and
11.5, the api-lane decider_2b at 18.9). The turn-lane decider_2b cold start and its 183 s stall were measured under that load, so treat them as upper-side figures.

## 4. Evidence classes

- **REAL:** 142 Hermes turns and their oracle verdicts; the frozen dataset; the joins through
  `adapters.hermes_z0int.normalize_envelope`, `close_observation` and `join_outcome`.
- **BENCHMARK:** scorer latency under `quiet-timed`.
- **UNIT:**
  - The Ollama adapter's single-label refusal: red before b51c7a22 (2 failed), then `tests/lab` 29 passed.
  - The token-contract suite: 16 passed (`raw/unit/`).
- **SOURCE:**
  - Hermes runtime identical to d39e1175; no runtime z0int reference.
  - The `type` action ignores `element` (and `keys`).
- **REAL (post-hoc audit):** the per-run CUA failure mechanisms and tool tallies in section 2, from the raw tool
  results in the private `state.db` files.
- **HYPOTHESIS (not run):** that a token-addressed `type_text` would fix the `cua_note` or `browser_submit` failures.
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
- **Analysis code.** It was committed after collection began (about 3 minutes in) but before the freeze, as PREREG
  states. `drive.log` printed per-task verdicts during collection, so the earlier statement that the lane owner "saw
  only task counts" cannot be checked and is withdrawn. PREREG fully specifies the confirmatory analysis (metrics,
  reference, bootstrap, alpha, decision rule), so the room for outcome-dependent choices is small.
  - `make_summary.py`, `sanitize_copy.py` and `verify_artifacts.py` were written after scoring. They only read
    committed files.
  - `build_turn_examples.py` gained an observer session-id fallback (used once, counted) before the freeze.
- **Sanitization.** Local path prefixes in raw receipts were replaced by placeholders (`raw/runs/sanitized.json`
  lists the 639 files). Oracle verdicts are unaffected: the re-run on the sanitized copies matches 142/142.
  `state.db`, configs and screenshots are not committed.
- **The 11500 server** is shared and was not started by this lane, so this lane did not stop it. The chat model is
  left unloaded, and `users.d/stack2-confirm.json` is marked DONE.
- **Plain-host interpreter (near_miss, found in verification).** `harness/run_scoring.sh` waits for a free GPU by
  piping the Ollama `/api/ps` JSON into a plain-host `python3 -c` count, outside hostless. It is a JSON parse only:
  no GUI library, no socket, no effect. It contradicts the earlier statement that every interpreter ran under
  hostless, which is corrected here. The script is left as it ran (it is the executed harness); a later lane should
  move that parse under hostless.

## 7. Claim boundary

- One executor (qwen2.5:7b-instruct Q4_K_M, GPU, 32K context), one machine, synthetic fixture tasks, 142 turns.
- `verification_needed` labels use the proxy "the unverified outcome failed the oracle".
- The reference is the SAMPLES LOO-family prior. Here it is weaker than the in-sample base-rate constant.
- Descriptive differences for other rows are not tests.
- Latency is small-cohort grade on a shared GPU and a CPU that was not idle (section 3).
- The CUA failure mechanisms in section 2 are what the tool results show; where the receipts cannot separate two
  causes (the 5 foreground browser runs) the README says so. No fix for them was tested.
- No backend is promoted (`promotion_ready: false`), and nothing here enables active control.

## 8. Correction round 1 (after independent verification)

The verifier found that the section 2 finding gave wrong failure causes for 9 of the 14 runs it covered, and that the
tool tally counted Driver refusals and approval blocks as ok. Changes, with no re-collection and no re-scoring (the
confirmatory result, the frozen set and every scored row are unchanged):

- Added `harness/tool_audit.py` (post-hoc, written after verification, not in PREREG). It reads the raw tool results
  read-only from the private `state.db` files (not committed) and writes `raw/analysis/tool-calls.jsonl` (one row per
  tool call: argument shape and result class, no result text, paths or typed strings) and `raw/analysis/tool-audit.json`.
  `verify_artifacts.py` recomputes the audit from the per-call file and the frozen `runs.jsonl`.
- Rewrote the section 2 tool tallies and the finding from those results: Driver refusals by code, approval blocks by
  action and mode, `keys` vs `text`, per-run mechanism. "type ignores element" is kept only as a SOURCE fact; the
  `element_token` fix is labelled a hypothesis.
- Section 1: stated that Hermes runs in single-query mode with explicit grants, and that the approval gate blocked 4
  actions in 3 failing CUA runs. Expanded the live-home stat disclosure (directory mtime, 5 s cadence, the earlier
  `auth.json` rewrite, metadata-only stat).
- Section 3: host load during the latency rows. Section 6: analysis-timing claim withdrawn; the plain-host `python3`
  near_miss.
- `verify_artifacts.py`: temp files go to `TMPDIR` or a hidden dir next to the packet (never the system default);
  the host-name hash check now covers every token of every length in every committed file, including itself.

## Layout

- `PREREG.json`, `README.md`, `summary.json` (from `harness/make_summary.py`), `provenance.json`, `verify_artifacts.py`,
  `SHA256SUMS`.
- `workload/`: tasks and fixtures.
- `dataset/`: the frozen set.
- `harness/`:
  - collection: `drive.py`, `run_task.sh`, `workload.py`, `oracle_selftest.py`, `fixture_serve.py`;
  - freeze, examples and scoring: `freeze.py`, `build_turn_examples.py`, `score_lane.py`, `run_scoring.sh`;
  - analysis and summary: `analyze.py`, `make_summary.py`, `sanitize_copy.py`;
  - correction round 1: `tool_audit.py` (post-hoc tool-result audit);
  - `vendor/lab/z0_hermes_observer/`: the offline scorer scripts at b51c7a22, which the verifier uses.
- `raw/`:
  - `collect/`, `runs/<run_id>/` (sanitized per-run receipts), `pilots/`;
  - `examples/`, `scored/`, `eval/`, `analysis/` (incl. `tool-calls.jsonl`, `tool-audit.json`), `scoring-logs/`,
    `controls/`, `gpu/`;
  - `quiet-lane-ledger.confirm.jsonl`, `unit/`, `run_scoring.log`, `freeze_commit.txt`.
