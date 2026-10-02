# stack2-addr 2026-10-02: element addressing between Hermes computer_use and cua-driver 0.32.0

Lane ADDR of the stack v2 track. Scope follows the kvnloo/hermes-agent#319 directive of 2026-10-01:

* no new architecture, protocol, question family or active controller;
* no Driver change, no new Driver service;
* fresh verification is kept and nothing is replayed blindly (kvnloo/cua#73/#93).

The fix is three small commits on the Hermes integration side; the branch head is d39e1175. Independent fixture oracles grade every run.

Pre-registration:

* `PREREG.json` was committed (ceaffa84) before the first measured run.
* `CONFIRM_PREREG.json` was committed (70b0a91d) before the confirmation runs.
* `CONFIRM2_PREREG.json` was committed (c446c74c) before the second confirmation runs. It is a disclosed extension after independent verification round 1; `PREREG.json` and `CONFIRM_PREREG.json` are unchanged.
* `verify_artifacts.py` checks all three commit orders.

## 1. The mismatch (SOURCE + UNIT + REAL)

* **Driver side.** trycua/cua#3873 (61f1c0ab, 2026-09-30, marked breaking) made the snapshot-bound `element_token` the only element target.
  * It removed `element_index` and `snapshot_id` from every action schema.
  * The Driver now refuses unknown argument names at dispatch.
  * The change ships in cua-driver 0.32.0 and is absent from 0.21.0.
  * trycua/cua main (989cc76c) keeps it, and adds the token pattern `^s[0-9a-f]{8}:[0-9]+$` to the schema.
* **Hermes side.** Hermes still sends `element_index`.
  * This is true of NousResearch/hermes-agent main and kvnloo/hermes-agent main (both 54bc5e50).
  * Their `tools/computer_use` is byte-identical to the stack base 0d60437a.
  * Hermes still pins cua-driver 0.21.0.
* **Verdict.** Hermes is the stale side. The Driver's contract preserves authority: tokens are bound to a snapshot, and a superseded token is refused. So the fix belongs in Hermes.

The table below compares, tool by tool, what Hermes sends at 0d60437a with what each Driver advertises in its live `tools/list` (`contract/tools_list_properties.json`).

| Hermes action | Hermes sends | 0.21.0 accepts | 0.32.0 accepts | 0.32.0 before the fix | After the fix |
|---|---|---|---|---|---|
| click (incl. right/middle) | `element_index`, plus `element_token` from the last capture | `element_index`, `element_token`, `snapshot_id` | `element_token` only (`additionalProperties: false`) | refused: `click: unknown argument element_index` | token only, dispatched |
| double_click | `element_index` (+ token), plus `button` | index and token; no `button` | token only; no `button` | refused on `element_index` | still refused: `double_click: unknown argument button` (residual, see 6) |
| scroll | `element_index` | index and token | token only | refused | token only (UNIT) |
| set_value | `element_index` (+ token) | index and token | token only | refused: `set_value: unknown argument element_index` | token only (UNIT) |
| drag | `from_element`, `to_element` | no element form | no element form | refused: `drag: unknown argument from_element` | unchanged: there is no Driver element drag, and Hermes must not substitute coordinates (see 6) |
| type / key | no element | n/a | n/a | n/a | n/a |

### Prior evidence, re-read

* SMOKE compat runs m055 and m057: every element click in the private state.db returned `click: unknown argument element_index`. The model's pixel fallback was "ok" but left the box unchecked.
* SMOKE probe: element click, set_value and the Chrome entry were each refused on 0.32.0. On 0.21.0 they worked.

## 2. The fix (kvnloo/hermes-agent `exp/stack-addr-20261002`, off `exp/stack-integration-20261002`)

**70cfc7a5: `CuaDriverBackend._action`, +11 lines.** This applies when the action's live schema advertises `element_token` but not `element_index`.

* Hermes sends the current snapshot's token alone.
* If the current snapshot has no token for that index, Hermes refuses locally with code `element_token_unavailable`. It never sends a bare index and never falls back to coordinates.
* Drivers that still advertise `element_index` (0.21.0) keep their current wire shape.

**c3d96b04: `_CuaDriverSession.call_tool`, follow-up (incomplete; superseded by d39e1175).** Hermes has a "session ended, so revive and replay once" path. After a revival, it no longer replays a call that carries `element_token`:

* The Driver retires an ended session's snapshots, so that token is dead.
* The backend's tokens and target are invalidated through the transport-reset callback.
* The call returns `element_token_session_ended`, which asks for a fresh capture.
* Token-free calls still replay once, as before.

Independent verification (round 1) found the gap. c3d96b04 dropped the tokens only when the call that noticed the ended session itself carried `element_token`. When a token-free call noticed it (`type_text`, `key`, a coordinate click), Hermes revived, replayed that call and kept the dead tokens. The next element action then sent one, and the Driver refused it as stale. So c3d96b04 still allowed stale-token reuse.

**d39e1175: `_CuaDriverSession.call_tool`, the complete fix (branch head).** The transport-reset callback now runs on every ended-session result, before the revive. Tokens and target are dropped whichever call noticed the end, and the next element action is refused locally until a fresh capture. Token-free calls still replay once, and `element_token` calls are still never replayed. The old test that asserted no reset after a token-free revival (`assert_not_called`) was flipped. A new test lets a token-free call trigger the revive and then clicks by element; it asserts that no token reaches the Driver.

**Unit tests (UNIT).** `tests/tools/test_computer_use_element_token_contract.py` runs against a strict fake Driver built from the frozen live schemas of both versions. The fake refuses unknown arguments, and a token must name the current snapshot.

| Run | Code | Result |
|---|---|---|
| red | 0d60437a | 7 failed / 5 passed. The failures say `click`, `set_value` or `scroll: unknown argument element_index`. |
| green | 70cfc7a5 | 12/12 |
| red (revive case) | 70cfc7a5 | 1 failed (the token was replayed) |
| green | c3d96b04 | 15/15 |
| red (token-free revive) | c3d96b04 code + the d39e1175 test file | 2 failed / 14 passed: the flipped assertion, and the new test, where `click` reached the Driver with the dead token |
| green | d39e1175 | 16/16 |
| computer_use suites | base / 70cfc7a5 / c3d96b04 / d39e1175 | 294 / 306 / 309 / 310 passed, 0 failed, 9 skipped |

The logs are in `raw/attempts/unit/`.

**Backend probes (REAL; private Xvfb; Driver 0.32.0; excluded from denominators; `raw/attempts/probes/`).**

| Probe | Build | Result |
|---|---|---|
| element actions | 0d60437a | every element click and set_value was refused |
| element actions | 70cfc7a5 | GTK checkbox checked through its token; Chrome entry click, type and Submit through tokens gave `submitted` = the probe token; index 999 was refused locally with 0 Driver calls |
| session revival: end the Driver session behind Hermes' back, then click by element | 70cfc7a5 | reproduced the full-stack refusal exactly (`element_token is stale ... no current snapshot`) |
| session revival | c3d96b04 | the call was not replayed, tokens were dropped, and the next capture and click checked the box |
| session revival, three triggers: element click, `type_text`, `key` (`probe_revive2.py`) | c3d96b04 | element click: correct (no replay, tokens 0). `type_text` and `key`: tokens kept (9), and the next element click sent the dead token, which the Driver refused (`element_token is stale ... pid has no current snapshot`). 2 stale tokens sent |
| session revival, three triggers | d39e1175 | all three triggers: tokens 0 after the trigger and 0 stale tokens sent. The old-index click was refused locally (`No active window — call capture() first.`, 0 Driver calls). The fresh capture and click toggled the box every time |

## 3. Full-stack runs (REAL)

The setup is the accepted SMOKE configuration, with these elements:

* **Hermes:** `python -m hermes_cli.main chat -Q -t computer_use --max-turns 12`, using the SMOKE prompts, config and allowlist verbatim.
* **Bridge and approvals:** `tool_search` off. No yolo and no approval bypass.
* **Observer:** the #385 observer is on (metadata only). No shadow sidecar runs.
* **Model:** qwen2.5:7b-instruct 845dbda0 via tag `qwen2.5:7b-instruct-smoke-t0`, digest 77a5de20. The tag was recreated byte-identical to the SMOKE tag: temperature 0, seed 42.
* **Model server:** shared user-local Ollama 0.35.0 on the GPU. Served context 32768; the peak prompt was 17,250 tokens, so nothing was truncated.
* **Sessions:** one private Xvfb session per run under hostless v2.
* **Fixtures and oracle:** identical to SMOKE. Fixture hashes are in `provenance.json`.
* **Driver:** "0.32.0" in this packet means a local build of trycua/cua 229b65b28, the version-bump commit after the cua-driver-rs-v0.32.0 tag (58aba84b); sha256 8b037961. The 0.21.0 Driver is Hermes' pinned release binary. See `provenance.json`.
* **Runs kept:** every run is reported. There were 0 harness errors and every Hermes exit code was 0.

### Measured set: Driver 0.32.0, 12 pairs per task, arm order randomised per pair (seed 20261002)

| Task | Arm (Hermes) | Oracle pass | Wilson 95% | Tool calls | Tool errors | `unknown argument element_index` | Element actions dispatched |
|---|---|---|---|---|---|---|---|
| gtk3 | before 0d60437a | **0/12** | 0.00-0.24 | 78 | 26 | 26 (12/12 runs) | 0/26 |
| gtk3 | after 70cfc7a5 | **12/12** | 0.76-1.00 | 39 | 0 | 0 | 12/12 |
| browser | before 0d60437a | **1/12** | 0.01-0.35 | 94 | 34 | 27 (12/12 runs) | 0/29 |
| browser | after 70cfc7a5 | **11/12** | 0.65-0.99 | 70 | 2 | 0 | 24/26 |

"Element actions dispatched" means the Driver accepted the action and dispatched it. Only the oracle grades success.

| Gate (PREREG) | Result |
|---|---|
| H1 contract: 0 addressing refusals after the fix | **PASS**. 0 after. Before: 53, in 24/24 runs that issued an element action. |
| H2 element reach: at least 90% of after-arm runs with an element action have at least 1 dispatched | **PASS**. 24/24 (Wilson 0.86-1.00). 36/38 element actions dispatched. Before: 0/55. |
| H3 task success, paired | **SUPPORTED** on both tasks. gtk3: 12 after-only vs 0 before-only discordant pairs, one-sided sign test p=0.00024. browser: 10 vs 0, p=0.00098 (1 pair passed both, 1 neither). |
| H4 authority: 0 stale and 0 invalid tokens after the fix | **FAIL for 70cfc7a5**. 2 `stale_token` refusals, both in m020-browser-after-p05 (see 4). 0 invalid tokens and 0 local `element_token_unavailable`. |
| H5 tool errors (descriptive) | Before: 60 errors in 172 calls, mean 2.5 per run (median 2), 24/24 runs had an error. After: 2 in 109, mean 0.08, 1/24 runs. |
| Legacy: the fix on the pinned 0.21.0, 0 addressing refusals | **PASS**. 0 refusals, 9/9 element actions dispatched. gtk3 3/3. browser 0/3: the model picked the wrong indices in Chrome's 122-element tree. First click: index 36 in l02, 46 in l04 and l06. Then all three clicked 56, which is the entry, as "Submit" (Submit is 57). This matches the SMOKE profile (0-4/12 per arm). |

Before-arm failures in detail (all kept):

* **gtk3:** after the refusals, the model fell back to pixel clicks at (736, 473) 8 times. The Driver answered `ok` (`x11_xsendevent`, "not verified"), but the checkbox stayed unchanged in 12/12 runs, according to fixture state.
* **browser:** 10 coordinate actions, 7 other errors, and 1 pass via a coordinate click and type (m028). The 7 other errors were:
  * 3 approval-gated calls (`drag`, `bring_to_front`) in `-q` mode, by design;
  * 4 local argument refusals (`coordinates` or `from_coordinate` passed to click).

### Confirmation set: c3d96b04, Driver 0.32.0, 24 runs (CONFIRM_PREREG)

| Task | Oracle pass | Wilson 95% | Tool errors | Element actions dispatched |
|---|---|---|---|---|
| gtk3 | 12/12 | 0.76-1.00 | 0 | 12/12 |
| browser | 12/12 | 0.76-1.00 | 0 | 24/24 |

* C1 contract: **PASS**, 0 addressing refusals.
* C4 authority: **PASS**, 0 stale, 0 invalid and 0 `element_token_unavailable`.
* Totals: 97 calls, 0 errors, 0 coordinate actions.
* The revive path itself was not triggered in these 24 runs. Its evidence is UNIT plus the REAL probe in section 2.
* c3d96b04 is no longer the branch head: it still allowed stale-token reuse after a token-free revive (section 2).

### Second confirmation set: branch head d39e1175, Driver 0.32.0, 24 runs (CONFIRM2_PREREG, disclosed extension)

| Task | Oracle pass | Wilson 95% | Tool calls | Tool errors | Element actions dispatched |
|---|---|---|---|---|---|
| gtk3 | 12/12 | 0.76-1.00 | 37 | 0 | 12/12 |
| browser | 12/12 | 0.76-1.00 | 61 | 3 (1 run) | 24/26 |

* D1 contract: **PASS**, 0 addressing refusals.
* D4 authority: **PASS**, 0 stale and 0 invalid tokens.
* Totals: 98 calls, 3 errors, 0 coordinate actions. The peak prompt was 8,032 tokens.
* **The 3 errors, all in d006-browser-after3-p303.** The run had already submitted the right value (oracle pass). The model then sent a capture with `bring_to_front` and no foreground mode, which Hermes refused locally (`bring_to_front_requires_foreground`). The page had re-rendered to 14 elements, but the model still clicked elements 15 and 16. Hermes refused both locally (`element_token_unavailable`, 0 Driver calls), because the new snapshot has no such indices. This is the authority-preserving refusal from 70cfc7a5, not the revive path.
* D5 revive path: triggered in 0/24 runs; no agent.log shows an ended session. The direct evidence for d39e1175 is still UNIT plus the REAL three-trigger probe (section 2).
* **Model tag.** The tag was recreated from blob 845dbda0 with the same recipe, and digest 77a5de20 was verified before any run. It was unloaded and deleted afterwards. The shared server was not started, stopped or reconfigured.
* **Aborted first launch, disclosed.** The first launch of this set started 18 s after the CONFIRM2_PREREG commit and aborted before any run. The local machine config lacked the `after3` arm, so `KeyError: 'after3'` hit while preparing each run dir. There were 0 sessions, 0 Hermes starts and 0 model calls. All 24 ledger lines are kept in `raw/drive-ledger.jsonl` as `harness_error`. The 24 empty run dirs were moved aside, and the set was relaunched with the same run ids and plan. The analyzer counts a run as executed by its id, so the relaunch is what `confirm2_summary.json` grades.


### Integrity

* 102/102 runs (54 measured and legacy, 24 confirm and 24 confirm2) had the live Hermes home, the real home and the fixture state as empty tmpfs inside Hermes.
* 0 host-display variables and 0 live-home references appeared in the Hermes environment.
* The system-prompt hash is identical in both arms (b62862ea...).
* **Live Hermes home stat (PREREG secondary report).** `harness/live_home_stat.py` reads `meta/live-home-stat.{before,after}` and writes `live_home_stat.json`.
  * The live home directory's mtime changed during every run (102/102: 78 main and confirmation runs plus 24 confirm2 runs).
  * `auth.json` was rewritten once during a run, at 12:35:28 -0500 during m020, and once more between two runs.
  * Nothing else changed: not `state.db`, its WAL, `config.yaml`, `.env` or `logs`.
  * **Attribution.** The directory mtime also changed in every gap between consecutive runs (101/101), when no lane run was active. Inside every run, Hermes saw the live home only as an empty tmpfs. The writer is therefore the live Hermes processes, which have run since Sep 29, not this lane. This is disclosed, not a breach.
* **Nit.** The committed `meta/env.inside` files contain the private session's ephemeral D-Bus socket path (`unix:path=/tmp/dbus-XXXXXXXXXX`). It is an absolute local path that identifies nothing. The accepted SMOKE packet has the same, and the scan in `verify_artifacts.py` ignores `/tmp`.

## 4. The H4 failure (m020-browser-after-p05)

The sources are `raw/runs/m020-browser-after-p05/tool_calls.jsonl` and `raw/attempts/m020-agent-log-excerpt.txt`.

* **Timeline:**
  * API call 2 took 424.7 s: the model emitted 29,224 tokens of 640 duplicate tool calls. Meanwhile the Driver ended the idle session.
  * Tool call seq 1 (click, element 15) noticed the ended session. agent.log shows one revive, during this click. Hermes revived the session and replayed the click verbatim, carrying a token minted under the ended session. The Driver refused it: `element_token is stale ... pid has no current snapshot`. This was the first refusal.
  * Seq 2 (type, no element) succeeded.
  * Seq 3 (click, element 16) was a new model call, not a replay. Hermes attached a token cached from the ended session, and the Driver refused it the same way. This was the second refusal.
  * Seqs 4-6 were captures. The model then chose two coordinate actions itself, before any element action: a type with `from_coordinate` [278, 434] and a coordinate click at [739, 434]. These are the only coordinate actions in the after arm. Hermes did not substitute them.
  * The model then re-captured and clicked elements 15 and 16 by fresh tokens. The oracle still failed: the submitted value was absent.
* **Cause.** The defect is reuse of cached tokens across an ended session; the replay is only one path to it. c3d96b04 closed only the replay path when the replayed call carried a token. That is why it was incomplete (section 2). d39e1175 drops the cached tokens on every ended-session result, which closes both paths.
* **Authority held.** No element was mis-hit, because the Driver refuses the dead token. Hermes replaced nothing with coordinates.
* **Status.** The gate result stays FAIL for the measured build 70cfc7a5. The confirmation sets on c3d96b04 and d39e1175 show no regression, but neither hit this path. The direct evidence for d39e1175 is UNIT plus the REAL three-trigger probe (section 2).

## 5. Claim boundaries and confounds

* **Browser difficulty differs by Driver.** The 0.32.0 Chrome AX tree had 19 indexed elements (entry 15, Submit 16), against 122 on 0.21.0 (entry 56, Submit 57). The browser success here (11/12, 12/12) is therefore not comparable with SMOKE's 0.21.0 browser rates. The before/after comparison is within 0.32.0 and is fair.
* **Determinism.** The model server is shared and not deterministic. Pairs share a token and the prompt; equivalence of first calls is not claimed.
* **Scope.** One 7B model and two fixtures. This is not a model benchmark. No timing is reported; wall times are incidental.
* **UNIT-only paths.** scroll and set_value by token are covered by unit tests only, because the tasks do not use them.

## 6. Findings recorded, not fixed (outside the addressing spec)

1. **Hermes `double_click` sends `button`.** Neither Driver's `double_click` advertises `button`. 0.32.0 refuses it (`double_click: unknown argument button`) for element and pixel double-clicks alike (REAL probe). The likely Hermes-side fix is `click` with `count: 2`.
2. **Element drag has no Driver counterpart.** Neither 0.21.0 nor 0.32.0 has one; 0.32.0 refuses `from_element`. Under the authority rule, Hermes must not translate elements to coordinates. Either Hermes refuses element drag explicitly, or the Driver adds a token-based drag. That is an owner decision; no Driver change was made.
3. **Right-click by element fired the button's default action.** In the GTK fixture, a right-click by element on "Increment" raised the counter from 0 to 1, on both 0.21.0 and 0.32.0. This is a Driver-side semantic finding for kvnloo/cua; the Driver was not changed.

## Files

| Path | Contents |
|---|---|
| `PREREG.json`, `CONFIRM_PREREG.json`, `CONFIRM2_PREREG.json` | pre-registrations |
| `plan.json`, `plan_confirm.json`, `plan_confirm2.json` | run plans |
| `summary.json` | measured and legacy gates and cells |
| `confirm_summary.json`, `confirm2_summary.json` | confirmation gates |
| `live_home_stat.json` | live Hermes home stat before/after, per run and between runs |
| `provenance.json` | exact identities |
| `contract/` | live `tools/list` property names of both Drivers, and the dump script |
| `raw/runs/<run_id>/` | sanitised `run.json`, `oracle.json`, `run_summary.json`, `tool_calls.jsonl` (every call, its result class and a message head), observer `events.jsonl`, fixture state before and after, and `meta/` |
| `raw/drive-ledger.jsonl` | every drive result, with start time and model-server residency |
| `raw/attempts/` | pilots, backend probes, unit logs and the m020 log excerpt (all excluded from denominators) |
| `harness/` | all code used |

Changes after pre-registration, all disclosed:

* `harness/sanitize_copy.py` gained one file entry (`tool_calls.jsonl`) after the PREREG commit.
* `harness/analyze_confirm.py` was committed with the results (61bc0729), not with CONFIRM_PREREG (70b0a91d). Its gates are simple counts, and an independent regrade matched.
* CONFIRM2_PREREG names `harness/analyze_confirm.py` as its analyzer, reused unchanged.
* `harness/live_home_stat.py` and the confirm2 checks in `verify_artifacts.py` were added after the confirm2 runs. They only read committed raw files.
* **Packet repair.** The repository's `*.log` ignore rule had kept 89 manifest-listed files out of the earlier commits: the unit logs and every run's `meta/timeline.log`. On a fresh clone the manifest check would have failed. They are force-added in the round-2 commit, unchanged; their hashes are the ones the earlier `SHA256SUMS` listed.

Verify with `python3 verify_artifacts.py` from this directory. It prints `RESULT PASS`.
