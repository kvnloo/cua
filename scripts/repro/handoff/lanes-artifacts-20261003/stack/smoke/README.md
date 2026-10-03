# stack-smoke 2026-10-02: Hermes x cua-driver x z0int full-stack smoke and shadow-safety proof

Lane SMOKE of the CUA x Hermes x z0int stack track (kvnloo/hermes-agent#319 directive of 2026-10-01: no new
architecture, protocol, question family or active controller; shadow output must never change Hermes behaviour).

Hermes runs in an isolated runtime with a local model and performs CUA tasks through its `computer_use` tool, which
drives cua-driver inside a private Xvfb session. Two tasks were used: the jev-use loopback form (type a token, then
submit) in Chrome, and the GTK3 task-window "I agree" checkbox. The #385 observer writes metadata receipts. A shadow
sidecar scores the receipts with a z0int backend and writes `z0int.decision_receipt.v1` rows (`execution=shadow`).
Independent fixture oracles grade every run.

* Pre-registration: `PREREG.json` was committed (80174a1cf) before the first measured run. `verify_artifacts.py` checks the commit order.
* Follow-ups had their own pre-registrations, each committed before its runs:
  * `EXPLORATORY_PREREG.json`: a delay control.
  * `REPLICATION_PREREG.json`: a browser on/off replication.

## Verdicts

| # | Claim | Evidence | Result |
|---|---|---|---|
| H1 | The same trace_id and turn_id appear on the Hermes observer rows and on the z0int receipts, and join to the independent fixture outcome | REAL | **PASS**. 34/34 shadow-arm runs in the measured set (24 on, 6 outage, 4 compat), plus 24/24 supplementary runs (12 replication on, 12 onnowait). Each trace's oracle verdict was joined through `adapters.hermes_z0int.close_observation/join_outcome` and through `z0int.receipt.join_outcome` (`verification_source=fixture_oracle:*`, tier gold or negative). The one harness-failed run, m057, joins as `unknown`. |
| H2 | The complete candidate set, full distribution, confidence and latency are persisted where the backend supports it | REAL | **PASS**. 324/324 status-ok receipts (166 measured + 158 supplementary) each carry: candidates `["false","true"]`, probabilities over both labels (finite, summing to 1 ± 1e-5), confidence, backend `latency_ms`, and backend, model and revision. |
| H3a | No shadow field reaches prompts or tool choice (code path) | SOURCE + REAL | **PASS**. See the code-path section. Structural check: the sidecar output directory and the fixture state directory were empty tmpfs mounts inside Hermes' sandbox in all 106 runs. |
| H3b | Paired runs, shadow-on vs shadow-off | REAL | **SUPPORTED by the pre-registered rule.** All 24 pairs had identical system-prompt hashes. 11/24 pairs had identical tool sequences (gtk3 10/12, browser 1/12). Oracle verdicts were concordant in 21/24 pairs; the 3 discordant pairs all passed only in the off arm (sign test p=0.25). Every divergence falls into one of three causes: model nondeterminism with identical inputs (5), run-varying ids only (3), or environment content (5). The browser on-arm 0/12 was **not replicated**: in 12 fresh pairs on passed 3/12 and off 1/12, and pooled over 24 pairs on passed 3/24 and off 4/24 (p=1.0). |
| H4 | One backend outage fails open | REAL | **PASS**. The outage was injected by leaving the backend weights unreachable (residency miss, HF offline). In 6/6 runs Hermes completed with rc 0, and every one of the 33 opportunities was receipted `backend_unavailable` with the error. The oracles still graded these runs: gtk3 3/3 pass, browser 1/3 pass. |
| H5 | Cold and warm latency of each shadow backend call | BENCHMARK | **3 of 4 backends measured** under `quiet-timed` over 60 frozen real requests; see the latency table. decider_2b is **BLOCKED** because the GPU budget was taken by the shared resident chat model. Qwen/Ollama-logprob is NOT_RUN (owned by the z0int lane). JEV is NOT_RUN (paid). |

Secondary results:

* **api.attempt_will_fail is DEGENERATE.** There were 0 positives in 299 joined physical attempts across all shadow runs (165 measured + 134 supplementary). Two unmatched attempts (orphan pre rows from the two compat-run timeouts) are counted separately.
* **verification_needed has signal.** Under the proxy label "the unverified outcome failed the oracle", 35 of 58 shadow-arm traces are labelled true (17/34 measured, 18/24 supplementary), and 1 is unknown (m057).
* **Laya readings are uninformative.** laya_421m read p(true) for verification_needed between 0.48 and 0.54 whatever the outcome, and p(fail) for api.attempt_will_fail between 0.57 and 0.61 on all 114 negative attempts. These are descriptive only; no ranking is claimed.

## What was run

* **Hermes:** worktree `exp/stack-smoke-20261002` is identical to `exp/stack-integration-20261002` at 0d60437a (#385, #386 and #387 merged on fork main). **No Hermes source change was needed.**
* **Hermes runtime:** dedicated venv, and a private HOME/HERMES_HOME per run. bwrap masks the live Hermes home, the real home, the shadow output and the fixture state with empty tmpfs. Run directories are bind-mounted at constant paths, so the system prompt is byte-identical across runs (24/24 pairs).
* **Command:** `python -m hermes_cli.main chat -Q -t computer_use --max-turns 12 -q <prompt>`. The prompts are frozen in `harness/drive.py`.
* **Hermes config:**
  * `tools.tool_search.enabled: off`. With it on, the local model called the `tool_call` bridge with malformed arguments (pilot-01).
  * `capture_after_mode: ax`.
  * Explicit `command_allowlist` grants for `cua:{click,type,key,scroll}:{background,foreground}` and `cua:set_value:background`.
  * Not used: `--yolo`, `approvals.mode off`, or any Driver bypass variable. The Driver stays in `standard` mode.
* **Model:**
  * Weights: `qwen2.5:7b-instruct`, digest 845dbda0ea48 (Q4_K_M), on a user-local Ollama 0.35.0 at 127.0.0.1:11500 on the GPU. Another stack lane started the server; this lane pulled the model.
  * Runs used the tag `qwen2.5:7b-instruct-smoke-t0`: the same weights plus temperature 0 and seed 42.
  * Context: served at 32768, the model maximum; Hermes is configured for 65536. The peak prompt was 19015 tokens (23637 in the supplementary runs), so no prompt was truncated.
* **Driver:** **cua-driver 0.21.0**, the official release that Hermes pins in `pm/lock.json`; tarball sha256 matches.
  * Hermes' backend sends `element_index`, and cua-driver 0.32.0 (upstream main) refuses it: `click: unknown argument element_index`, likewise for `set_value`.
  * The compat set confirms this at full-stack level on 0.32.0: gtk3 had 0 passes. In one run the coordinate fallback reported "ok" while the checkbox was unchanged. The browser compat runs both hit the 600 s harness timeout.
* **Sessions:** one private Xvfb session per run (`cua-x11-session.sh` under hostless v2) with a private D-Bus and AT-SPI bus. The sway kit was not used, because seat binding is NO there and this lane needs no multi-seat.
* **Shadow:** `harness/shadow_sidecar.py` runs as a separate process with laya_421m on the CPU.
  * It reads only the observer spool.
  * Decision lanes: `api.attempt_will_fail`, built by the #386 `request_for`, and `verification_needed`, the decision-capability-v1 question verbatim, asked at the turn's final response.
  * It writes z0int receipts into a private Z0INT_HOME.
  * Fail-open: a backend error yields a `backend_unavailable` receipt.
* **Oracles** (`harness/oracle.py`), reading app-owned state after Hermes exits:
  * gtk3 passes iff `agreed` is true and nothing else changed.
  * browser passes iff the fixture's `/state` shows `submitted` equal to the run token.

### Run sets and outcomes (oracle pass / n; Wilson 95%)

| set | task | arm | driver | pass/n | CI |
|---|---|---|---|---|---|
| measured | gtk3 | on | 0.21.0 | 12/12 | 0.76-1.00 |
| measured | gtk3 | off | 0.21.0 | 12/12 | 0.76-1.00 |
| measured | gtk3 | outage | 0.21.0 | 3/3 | 0.44-1.00 |
| measured | browser | on | 0.21.0 | 0/12 | 0.00-0.24 |
| measured | browser | off | 0.21.0 | 3/12 | 0.09-0.53 |
| measured | browser | outage | 0.21.0 | 1/3 | 0.06-0.79 |
| compat | gtk3 | on | 0.32.0 | 0/2 (1 fail, 1 unknown) | |
| compat | browser | on | 0.32.0 | 0/2 (both rc 124) | |
| exploratory | browser | offdelay | 0.21.0 | 4/12 | 0.14-0.61 |
| exploratory | browser | onnowait | 0.21.0 | 3/12 | 0.09-0.53 |
| replication | browser | on | 0.21.0 | 3/12 | 0.09-0.53 |
| replication | browser | off | 0.21.0 | 1/12 | 0.01-0.35 |

Totals: **106 planned runs (58 measured+compat, 24 exploratory, 24 replication), 106 executed, none dropped.** The 12
pilot runs (pilot-01 to pilot-12, harness debugging before the PREREG commit) are kept under `raw/attempts/` and are
excluded from every denominator.

Hermes exit codes were 0 in every run except three:

* the two browser compat runs (rc 124, harness timeout);
* m057, where the harness failed.

### Browser task difficulty

The browser task is hard for this model. Chrome's accessibility tree has 122 elements. The model often clicked a
wrong index (36 or 46) for the entry; the correct indices are 56 for the entry and 57 for Submit. With temperature 0,
the first call still differed inside 5 pairs whose inputs were identical. The shared GPU server batches requests from
other lanes (NUM_PARALLEL=2), so its output is not deterministic. That is the dominant source of divergence, not the
arm.

### Exploratory delay control (post hoc, pre-registered before its runs)

Waiting for the warm sidecar delays Hermes' start by a median of 17.5 s after the fixture is ready; the off arm has no
wait. Two controls test whether this explains the on arm's 0/12:

* `offdelay`: no shadow stack, plus the same 17.5 s wait. It passed 4/12 (paired with off: 3 vs 2 discordant, p=1.0).
* `onnowait`: shadow stack running, no wait. It passed 3/12 (paired with on: 3 vs 0, p=0.25).

Pooled: shadow present 4/27, shadow absent 7/24, Fisher p=0.31. Neither single factor reproduces 0/12.

An unadjusted post-hoc comparison of on against all other browser arms gave p=0.048. The replication that followed
did not support it (R1 not supported). The 0/12 cell is therefore treated as variance.

## Code path: why shadow output cannot reach Hermes (H3a)

1. **Separate process, invisible output.**
   * The sidecar is not part of Hermes and talks to it through no IPC.
   * It reads the observer spool and writes only under `<run>/shadow`.
   * `run_one.sh` mounts an empty tmpfs over that directory (and the fixture state directory) inside Hermes' bwrap view. `mask.inside` shows `shadow_dir_entries=0` in all 106 runs.
2. **No Hermes code reads z0int artefacts.**
   * Outside `lab/` and `tests/`, no Hermes Python file mentions `z0int`, `Z0INT` or the observer id (grep at 0d60437a).
   * The lab modules `shadow_api_failure.py` and `evaluate_shadow.py` are offline scripts. The plugin imports neither.
3. **Observer callbacks return None.**
   * `lab/z0_hermes_observer/__init__.py` `observe()` catches every exception and returns None.
   * `hermes_cli/plugins_dispatch.py::invoke_hook` returns only non-None results.
   * So the hooks that consume return values receive nothing from the observer:
     * `pre_llm_call` context injection (`agent/turn_context.py`);
     * `pre_tool_call` block/approve/modify directives (`hermes_cli/plugins.py::_get_pre_tool_call_directive_details`);
     * `transform_*` (not registered).
4. **Residual path.**
   * `pre_tool_call` fails closed if a callback exceeds `plugins.hook_callback_timeout` (default 30 s) or raises.
   * The observer only enqueues the row (no I/O on the hook thread) and swallows exceptions.
   * Observed: 0 of 333 tool results in the measured and exploratory runs carry a `pre_tool_call` block message.
5. **Resource path (not an information path).** The sidecar uses CPU while Hermes runs. The browser data show no arm effect that survived replication.

## Latency of shadow backend calls (H5, BENCHMARK)

Each backend ran as one `quiet-timed` phase. The ledger lines are in `bench/quiet-lane-ledger.stack-smoke.jsonl`.

* **Input:** the frozen set of 60 deduplicated real requests (33 api.attempt_will_fail, 27 verification_needed) from the measured shadow runs; sha256 47d176fa…
* **Cold:** from the shell timestamp just before the interpreter starts to the first answer. This includes imports, model load and the first evaluate.
* **Warm:** the backend-reported `latency_ms` of the next 59 calls.

| backend | device | cold ms | warm p50 ms | warm p90 ms | warm max ms | errors |
|---|---|---|---|---|---|---|
| laya_421m | CPU | 17899 | 555.0 | 660.4 | 870.4 | 0/60 |
| julia_1 | CPU (worker) | 17793 | 77.1 | 91.4 | 147.3 | 0/60 |
| nanojev | GPU | 23311 | 28.6 | 29.5 | 68.8 | 0/60 |
| decider_2b | GPU | BLOCKED | | | | |

Conditions and caveats:

* **Machine load:** loadavg was 12-15 from other lanes. The quiet lock serialises timing phases, not the whole machine.
* **GPU state:**
  * The 6.5 GB chat model stayed resident throughout.
  * nanojev ran next to it; the GPU peaked at 10.8 of 12.3 GB.
  * decider_2b was gated off at 7.3 GB in use (twice), because it would exceed the 12 GB budget while other lanes kept the chat model loaded.
* **Identity:** NanoJev's reported revision is the backbone revision; its bundle pin is recorded in `provenance.json`.

## Incidents, failures and limits (all kept in the denominators)

* **m057 (compat gtk3):** I edited `run_one.sh` while m057 was executing it. bash re-read the rewritten file and died after Hermes ended (session rc 2), so no oracle ran.
  * Verdict `unknown`; see `raw/runs/m057.../HARNESS_INCIDENT.txt`.
  * The orphaned sidecar was stopped through its stop file. Its receipts are kept.
  * m058 ran on the edited script, which is identical for arm on.
* **m056 and m058 (browser on 0.32.0):** Hermes was still inside API call 3 when the 600 s harness timeout fired: a pre row with no post row, counted as orphan pre. The cause is undetermined because content is not captured by design. No verification_needed decision exists for those turns, a coverage gap of 2 turns.
* **Live Hermes home:** the stat of `auth.json` in the live Hermes home changed while m056 was running.
  * Metadata only; its contents were never read.
  * Hermes saw that directory as an empty tmpfs in every run, so the change came from the concurrently running live Hermes.
  * Nothing else in the live home changed, apart from the directory's own mtime, which also moves between runs.
* **Driver choice:**
  * The primary results use Hermes' pinned 0.21.0, not upstream main 0.32.0; 0.32.0 is not usable from this Hermes backend.
  * This is a compatibility finding for the CUA side, recorded rather than worked around.
  * No Driver service was added and fresh verification was kept (kvnloo/cua#73/#93).
* **Not covered:** multi-seat, Wayland, model capability claims, backend ranking, and Hermes turn latency (wall times are not reported as results).

## Files

* `PREREG.json`, `EXPLORATORY_PREREG.json`, `REPLICATION_PREREG.json`: pre-registrations.
* `plan.json`, `plan_exploratory.json`, `plan_replication.json`: run plans.
* `summary.json`: measured-set gates H1-H4 and secondary results.
* `supplementary_summary.json`: H1 and H2 over the exploratory and replication runs.
* `exploratory_summary.json`, `replication_summary.json`: follow-up analyses.
* `bench/`: H5. Contains `bench_summary.json`, `raw/*.json`, `frozen_requests.jsonl`, the quiet-lane ledger excerpt and `bench.log`.
* `raw/runs/<run_id>/`, sanitised per run:
  * observer `events.jsonl`;
  * shadow `decisions.full.jsonl` and z0int `receipts/{decisions,outcomes}.jsonl`;
  * `join/`, `oracle.json`, fixture state before and after;
  * `run_summary.json`, with the tool sequence from Hermes' own state.db;
  * meta: timeline, rc, `mask.inside`, `env.inside`, live-home stat, stdout and stderr.
* `raw/attempts/`: pilots. `raw/drive-ledger.jsonl`: every drive result, with start times.
* `harness/`: all code used. `provenance.json`: exact identities.
* `verify_artifacts.py`: re-checks the manifest, the PREREG order, oracles re-derived from fixture state, the summary regrade, the bench regrade, and a path, host and secret scan.

Verify with `python3 verify_artifacts.py` from this directory; it prints `RESULT PASS`.
