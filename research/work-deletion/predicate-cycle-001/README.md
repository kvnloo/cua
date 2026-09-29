# Exact final-predicate audit — cycle 001

**Candidate findings, pending the parent's independent audit.** No product code, API, or policy changes. No push/upstream action. The authoritative completed run is `results-05/`; earlier attempts are retained, not added to its denominator.

## Findings

| Disposition | Finding and evidence limit |
|---|---|
| **KEEP (recipe-local, conditional)** | The exact opt-in fixture runner in both languages completes the normal form with one type and one submit, an independently read HTTP-state success, and one provider decision instead of two. Accepted telemetry has the fresh ref, same session, one actionable Submit match, null model scores, and zero provider-decision time. This is decision-count evidence, not a latency benchmark. |
| **NARROW** | The final producer is explicitly `browser-fixture-form` / `type-verification-value` / page `browser_type` only. Toggle→confirm, modal→act, and an honestly identified two-field/three-step task produce no plan. The newer toggle experiment's `plan_two_action` / `resolve_two_action` are different functions, not execution of the final predicate. |
| **NARROW** | Duplicate Submit targets decline the guard (`submit_not_unique`) but do not force the whole runner to stop: its normal mock-provider fallback selects the first task candidate and submits once. Likewise, `ref_reused` declines the guard; it is not a Driver-level stale-ref refusal certificate. The deliberately invalid-ref transport cell accepts the provider fallback and is NOT real stale-authority evidence. |
| **NARROW / admitted-state boundary** | A duplicate verification field whose *first* entry has the required value is admitted by both real producers/resolvers. Reversing field order declines. A disabled duplicate in `content_refs` is ignored. Thus proof establishes the task's first field summary and uniqueness within actionable `refs`, not uniqueness of every logical control. These resolver-only observations show missing conditions in broader claims, not a demonstrated wrong mutation. An extra second field is ignored by the unchanged fixture task; this is a recipe-extension limitation, not evidence of a general three-step detector. |
| **REVISE evidence claims** | Returned-action success plus a persistently unknown submission oracle causes **two submit POSTs** with a three-step budget in both baseline and guarded runners, ending `budget_exhausted`. The second guarded-run submit is provider-routed, with no carried guard. The guard therefore does not establish global at-most-once behavior on unknown verification. This behavior is shared with baseline; no optimization-attributable increase was observed. |
| **REVISE evidence claims** | HTTP verification failure after typing propagates as an exception before the next decision (Python `HTTPError`, TS CLI error), with no second dispatch and no synthesized final `unknown` event. A lost action response instead yields an actual runner `unknown` outcome and no replay of that action. These are different boundaries. |
| **KILL the evidentiary substitution, not the optimization** | Do not count historical/generalized-predicate successes or hand-fabricated accepted candidate/plan objects as proof of final-runner generalization. Forged candidate target/session/capture metadata is accepted by the pure resolver in some cases, but the real fixture candidate producer cannot create it. Changed snapshot targets violate the modeled Driver response binding, rather than being a demonstrated runner-admitted attack. |
| **BLOCKED** | Lossless final-predicate replay of the original trials: the packets omit full pre/post snapshots, exact task/candidate objects, and session-bound plans. Actual Rust session/ref/capture enforcement, GUI behavior, live-provider performance, and independent auditor acceptance are not established here. |

No optimization-attributable wrong or additional repeated mutation was found in the completed hermetic matrix. Zero wrong-value submissions were recorded by its state oracle. This does **not** certify arbitrary web applications or a real Driver transport.

### Important bootstrap incident / scope limitation

`results-01` stopped because inherited Python 3.14 `PYTHONPATH` contaminated the reused Python 3.12 venv. `results-02` stopped at the first TypeScript runner: the harness patched the SDK's CommonJS export rather than the ESM export used by `run.ts`. The failed receipt shows no recorded transport calls, zero oracle reads, and zero mutations. However, the erroneous mock could fall through to a real stdio connection, and its generic error capture did not retain enough detail to rule out a live transport attempt. **It is excluded and is not certified hermetic.** The parent was notified. No claim is made that every bootstrap attempt satisfied the no-live condition.

The successful `results-03` used the correct ESM export and a nonexistent Driver executable. `results-04` added desktop/session environment removal; `results-05` repeats that setup and corrects inventory discovery of the generalization directory (the earlier literal path-part filter missed it, although its 27 trials were already explicitly loaded and executed). The inventory coverage negative control is retained in `inventory-red.log`. The configured Driver path must not exist. Thus a broken mock in the authoritative run cannot launch Driver or a GUI. No live tests or performance measurements were intentionally run. Current safety constraint: no browser/computer-use GUI tools; any future live tests are parent-owned and require verified headless Sway, never native Hyprland or Xvfb fallback.

## Exact pins and execution boundary

- Final resolver/runner pin: **`c78f50efed1ee7b289ab8947ec997904ea18fd72`**.
- Assigned branch: `research/guarded-predicate-audit-20260929`.
- Python imports the assigned checkout's actual `guarded_completion.py`, `tasks.py`, `sources.py`, and `run.py`.
- TypeScript imports the dependency checkout's actual source at `/mnt/zer0models/github/cua-lanes/c4316/libs/cua-driver/examples/jev-use/typescript/`. Before execution, all relevant tracked Python/TS/JSON/lock sources in **both** checkouts are compared byte-for-byte with `git show` at the final pin. `results-05/pins.json` records Git blob IDs, SHA-256s, import paths, dependency lock hash, and runtime versions.
- TypeScript's private runner is exercised through its existing CLI main guard, not an exported imitation. Only external MCP/provider I/O is intercepted. The planner, resolver, candidates, choice validation, task summary, runner control flow, classification, and telemetry writing remain unmodified.
- Tokens are generated per trial, remain in process/HTTP memory, and never persist in receipts. The actual runner logs are checked for token absence. Corpus normalization persists statuses, booleans, counts, refs, source locations and hashes, not recorded field values.
- The independent **state oracle** is an owned loopback HTTP server, read separately after each child. It counts actual adapter-originated `/type` and `/submit` POSTs and compares the submitted value in memory. It does not derive success from proof/events. It is independent of runner telemetry but **not** independent of the harness author, nor a real browser/Driver oracle.

## Corpus discovery and deduplication

Original root: `/mnt/zer0models/github/cua-lanes/evidence/scripts/repro/handoff/`.

| Completed source | Trials | Cells |
|---|---:|---:|
| `issue-24-live-battery.json` | 150 | 15 |
| `issue-33-replay.json` | 63 | 45 |
| `rfc-3963-guarded-generalization/results/trials.json` | 27 | 9 |
| **Total** | **240** | **69** |

A cell retains task, arm/policy, and injection/variant; a trial adds the recorded repetition (or uniquely named negative-control trial). Equal trial keys must have equal source-row hashes; conflicting duplicates fail. No duplicate trial keys existed in these completed sources. Negative controls count as *completed*, not necessarily successful. `issue-24-battery.json` is theoretical (`live_success: null`), `issue-33-dispatch.json` and `issue-33-injections.json` lack replay identity/input state, and visual-only is explicitly pending; these are inventoried but excluded from the completed denominator.

`results-05/corpus.jsonl` preserves stable keys, source-row indices, original source-file/row hashes, and redacted original results. #24 state success and #33 journal invariants are recomputed in code. `corpus-lineage.json` hashes the original generators and nonfinal rule modules; its recorded old rule/Driver pins are not claimed to have been reexecuted.

### What “replay” means in this packet

All 69 deduplicated cells are exercised through the exact final producer/resolver in both languages, using **explicitly labeled structural adaptations**. Known recorded refs are reused where available; missing initial state/field proof is reconstructed with ephemeral test values. Nonfixture task adapters keep distinct task IDs instead of pretending to be the fixture. Every original trial links to its executed cell in `corpus-links.jsonl`. These runs demonstrate interface/scope behavior only. They do not turn omitted original observations into new ground truth, replay the #33 uncertainty history, or add 240 fresh independent trials.

## Executed matrix

The authoritative run has **270 receipts**:

- **76** boundary resolver receipts: 38 cases × Python/TypeScript.
- **138** structural corpus-adaptation resolver receipts: 69 cells × Python/TypeScript.
- **56** full runner receipts: 14 scenarios × baseline/guarded × Python/TypeScript.

The 38 direct cases cover fill, distinct toggle/modal/two-field task IDs, extra-field recipe extension, initial/late duplicate targets, missing targets, renamed targets, all eight final decline reasons, duplicate candidates, candidate ref/tool/source/identity, missing/unavailable/other-valued fields, empty/cross sessions, ref reuse, malformed refs, forged target/session/capture metadata, snapshot-target mismatch, duplicated verification fields and disabled content duplicates. Reachability is per receipt (`producer`, `other-task`, `injected-candidate`, `impossible-runner`, `invalid-driver-snapshot`, `recipe-extension`), not inferred from acceptance alone.

The runner scenarios are accepted fill, duplicate-after, ref-reused, reobserve, field-unavailable, provider-failure, first/second response-lost, first/second refusal, session refusal, verification unavailable, verification unknown, and capture mismatch. Each has actual events, transport dispatches, state-oracle readback, CLI exit, and observed proof/decline. Capture mismatch uses the real visual parser and yields `capture_mismatch`, zero clicks/submits. Refusal cases test the real runner's handling of an injected refusal envelope, not the real Driver's enforcement.

All Python/TypeScript pure-resolver branch, proof and selected-candidate records agree. Normal fill routes are `provider → guarded-completion`; first lost response has no pending guard attempt; second lost response retains accepted proof but terminates `unknown`; a declined plan followed by reobserve is not carried into the later submit. A fresh provider-selected retype may create a new plan, as the field-unavailable case demonstrates.

## Checker, invariants, and independent audit

`checker.py` checks identity/pin consistency, unique trial keys, expected actual branches, nonreused proof refs, proof/candidate alignment, page-click acceptance, field and target proof, plan existence, transport cleanup/session binding, correct-oracle requirements for verified outcomes, default-off guard absence, no model calibration/provider work on guarded steps, and lost-response nonreplay. It is an invariant checker, not a second implementation of the product predicate.

The checker was developed RED→GREEN. Four retained RED logs fail with assertion failures (not import/syntax errors), then GREEN logs pass. A corruption of a genuinely executed receipt is retained as `negative-control.jsonl`: making its fresh ref equal its prior ref produces exit **1**, `fresh_ref_reused` and `proof_candidate_mismatch` (`negative-control.log`). The uncorrupted final 270 receipts pass (`checker-05.json`).

`verify_packet.py` reloads exact child artifacts, checks counts/keys/coverage, rechecks source and original corpus hashes, compares languages, checks real HTTP-state readbacks and unknown-oracle differential behavior, and verifies `SHA256SUMS` when present. These checks do not replace the required independent parent audit.

Additional untouched final-pin tests passed: **15 Python guarded tests**, **61 TypeScript resolver/core tests**, **20 TypeScript runner tests**. The checker has four test methods with multiple corruption subcases; full packet verification has nine methods. Logs are retained. No wall-clock performance conclusion is drawn from any hermetic timings.

## Reproduce (no installs; dependencies read-only)

From `/mnt/zer0models/github/cua-lanes/speed-predicate/research/work-deletion/predicate-cycle-001`:

```sh
# Choose a new output dir: existing results are never overwritten.
PYTHONDONTWRITEBYTECODE=1 python run_experiments.py --out results-repro-01
PYTHONDONTWRITEBYTECODE=1 python checker.py results-repro-01/receipts.jsonl

# Audit the committed canonical packet.
PYTHONDONTWRITEBYTECODE=1 python -m unittest test_checker -v
PYTHONDONTWRITEBYTECODE=1 python verify_packet.py
python checker.py negative-control.jsonl  # MUST exit 1
sha256sum -c SHA256SUMS
```

`results-05/commands.json` lists every executed child argv and exit. `hermetic-setup.json` pins the harness inputs and no-live setup; exact runtime paths are in `pins.json`. The system `python` only orchestrates stdlib HTTP/subprocess work; actual Python resolver/runner calls use the specified installed Python 3.12 venv. Both `PYTHONPATH` and `PYTHONHOME` are scrubbed for children. Node 22 and the existing `tsx` loader are used without installation or dependency mutation.

Original-suite reproduce commands (write any new logs under this packet):

```sh
ROOT=/mnt/zer0models/github/cua-lanes/speed-predicate
EX=/mnt/zer0models/github/cua-lanes/c4316/libs/cua-driver/examples/jev-use
NODE=/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin/node
TMPDIR="$ROOT/research/work-deletion/predicate-cycle-001/results-05/tmp" \
  env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV PYTHONDONTWRITEBYTECODE=1 \
  "$EX/.venv/bin/python" -m unittest discover \
  -s "$ROOT/libs/cua-driver/examples/jev-use/python/tests" -p 'test_guarded*.py' -v
TSX_DISABLE_CACHE=1 "$NODE" --import "$EX/node_modules/tsx/dist/loader.mjs" --test \
  "$EX/typescript/guarded_completion.test.ts" "$EX/typescript/core.test.ts"
# run_guarded_completion.test.ts spawns children with --import tsx, so its cwd
# must resolve the existing dependency installation; the test only writes TMPDIR.
(cd "$EX" && TSX_DISABLE_CACHE=1 \
  TMPDIR="$ROOT/research/work-deletion/predicate-cycle-001/results-05/tmp" \
  CUA_DRIVER_BIN="$ROOT/research/work-deletion/predicate-cycle-001/NO_LIVE_DRIVER_ALLOWED" \
  "$NODE" --import tsx --test typescript/run_guarded_completion.test.ts)
```

Remaining action: parent independently audit `results-05`, reachability labels, corruption control and the excluded bootstrap incident. Any generalized policy or live testing requires a separate decision; none is proposed as a product change here.
