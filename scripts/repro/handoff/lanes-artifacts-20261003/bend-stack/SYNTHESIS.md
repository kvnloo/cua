# Hermes x CUA x z0 x Bend: bend-native integration run (2026-10-02/03)

Scope: kvnloo/hermes-agent#324 (Bend boundary) with its RFC waves #388, #389 and #390, and kvnloo/hermes-agent#319 (z0 shadow
decisions). The 2026-10-01 meta triage on #324 applies: no broad semantic matrix; focus on kernel provenance, release
qualification and dependency provenance. No plugin code, Hermes core or z0 code was changed by any lane. All five lanes were
independently re-verified and **accepted**, with **no hard-rule breach**. One cross-workflow escalation (section 9) is open.

## 1. What bend-native is in this integration

kvnloo/bend-native @ e85e65e5 (v0.4.0) is the **packaging seam**: a standalone, opt-in native Hermes plugin, extracted from
kvnloo/hermes-agent#325, that needs no Hermes core change. It ships:

- the `bend_verify` model tool, `hermes bend` (doctor, verify, replay, last-receipt) and the `bend:workflow` skill;
- the stack pieces copied unchanged with digests in `stack/sources.json`: the observer (kvnloo/hermes-agent#385), the
  API-attempt shadow scorer and evaluator (#386/#387), and z0's State Packet and DecisionOpportunity builders;
- `hermes z0` (state, opportunity, report, score, evaluate), the `bend:z0-stack` skill, opt-in shadow observation
  (default off) and a runtime bridge to a z0int service.

Ownership (README + `stack/STACK.md`), which held in every lane:

| Owner | Owns | Does not |
|---|---|---|
| Hermes | orchestrates and executes tools | grade its own outcomes |
| Bend (via plugin) | proof evidence over the **emitted book** (`source_semantics_attested: false`, `label_kind: scoped_proof_evidence_not_task_success`) | attest source semantics; a proof PASS is never task success |
| z0intelligence | admission and outcome decisions, typed functions, backends, dispatch authority/ledger | get a second receipt protocol or scheduler from the plugin |
| AODL | intent and authority | (Python `aodl_contract` validator stays canonical; the Bend gate is an experimental fail-closed filter) |
| Plugin | observation, projection, receipts | grant authority, mint task success; shadow hooks always return None |
| Independent oracles | outcome grading (fixture state files, fresh Bend runs outside Hermes, git facts) | — no observer self-credits |

## 2. What was installed and validated (setup, SETUP.json)

| Item | Identity | Result |
|---|---|---|
| Bend 2.0.34 official | bin 7fafb749, base.bend c742fae9, bendtt.lean 61e0d2d9, kernel a7e5203d | release sha256 matched; rebuilt byte-identical from tag v2.0.34 (Bun 1.3.14) |
| Bend patched candidate kvnloo/bend@17db447a | bin b8473e16, bendtt.lean e1504243, kernel 72e11a86 | = v2.0.34 + 6 later upstream commits + the 2-line patch; still reports `bend 2.0.34` (hash-only identification) |
| Lean 4.34.0 | lean e8baaa71, leanc 68a45f83 | release sha256 matched |
| Hermes kvnloo/hermes-agent `exp/bend-stack-integration-20261002` | ad31bbf0 on CI pin 50a6abca + 3 element_token fix commits | new tests 10 fail on base / 16/16 on head; computer-use suite 256 pass, 0 fail, 8 skip |
| Plugin bend-native e85e65e5 | installed via `hermes plugins install --ref` | validate PASS; doctor available; tests 6/6; smoke 7/7 (official); AODL smoke 8/8 per build; one local-model turn called `bend_verify` |
| Model | qwen2.5:7b-instruct 845dbda0 on user-local Ollama 0.35.0 (127.0.0.1:11500) | served context 32,768/request (see blockers) |
| Driver | cua-driver 0.32.0, sha256 8b037961 | used in CONTRACT and E2E GUI rows |
| z0 | scoring stack-z0 @ 6764ae78 (offline, HF_HUB_OFFLINE=1); AODL gate z0intelligence `exp/bend-aodl-gate` @ a0e95785; private service on 127.0.0.1:11521/11523 from dev 6764ae78 | live service 11501 never contacted |

Safety change made in setup: the plugin profile pins `stack_service_port` to the private port, because the bridge bypasses
the proxy and its default 11501 would reach the user's live z0 service (plugin finding P-1 below).

## 3. Lane results and dispositions

| Lane | Branch @ head (pushed) | Evidence | Verdict | Disposition |
|---|---|---|---|---|
| CONTRACT (shadow safety) | kvnloo/bend-native `exp/contract-20261002` @ 15ddac2 | REAL 108+6 runs, FIXTURE, BENCHMARK (quiet-timed) | H1, H2, H4, H5, H6 PASS; **H3 PARTIAL (unload FAIL)** | KEEP (finding F2 -> plugin REVISE) |
| B389 (release qualification) | kvnloo/bend-native `exp/b389-20261002` @ 0d434457; control kvnloo/bend `exp/b389-patchonly-20261002` @ 6e940a0b | REAL (direct, plugin, CLI) | candidate 17db447a PROMOTABLE; stock 2.0.34 NOT promotable | KEEP |
| B390 (dependency provenance) | kvnloo/bend-native `exp/b390-20261002` @ e79cfe72 | REAL + FIXTURE (private hub) | all 5 acceptance criteria hold: accept | KEEP |
| E2E (full stack) | kvnloo/bend-native `exp/e2e-20261002` @ a7a041f8 | REAL 60 measured runs, BENCHMARK (quiet-timed) | stack works end to end; 0 forged passes, 0 false claims | KEEP |
| AODL (gate receipts) | kvnloo/bend-native `exp/aodl-20261002` @ 9477f918 | REAL 20 preregistered runs | 20/20 predictions held | KEEP |
| Plugin bend-native e85e65e5 | (unchanged) | findings from all lanes | integration works; 12 bugs/limits | REVISE |

Every packet has PREREG committed before its first measured run (reflog-checked by the verifiers), README, raw/, summary,
provenance and a verify_artifacts.py that passes from a clean clone and fails on tamper.

## 4. Shadow-safety result (CONTRACT)

- **H1 (REAL):** 12 pair blocks x 3 tasks (GTK3 computer-use in private Xvfb, `bend_verify` with real Bend, repo question) x
  3 arms (off / shadow+opportunities / aa). The loopback capture proxy stored Hermes's exact request bytes. First request:
  one hash per task across all 36 runs. Off-vs-shadow: 26 identical, 10 model-originated, **0 Hermes-built** divergences;
  off-vs-aa control: 26/10/0 (Fisher p 1.0). Oracle passes 108/108. Peak prompt 6,458 tokens.
- **H2:** inventory is exactly 12 hooks, `bend_verify`, CLIs `bend`/`z0`, 2 skills, 2 on_unload; 26 normal+hostile
  invoke_hook calls returned []; 0 block directives in 122 chat runs.
- **H3 PARTIAL:** queue bound (<=256), accounting (3,400 = 276 written + 3,124 dropped) and non-blocking (callback p99
  3.65 ms) PASS; **`Stack.close()` misses the preregistered 2.0 s** (returns only at join timeout, 2.0001 s), and the worker
  keeps writing 256 rows + ~70 opportunity records for 3.0-3.25 s afterwards.
- **H4** profile isolation PASS; **H5** no raw tool/reply/source/AX content in plugin data (prompt canary only in shadow
  `opportunities.jsonl`, as configured); **H6** disabled plugin leaves zero footprint. `stack_mode: off` still costs
  p50 18 -> 162 us per invoke_hook dispatch (EXPLORATORY).

## 5. #389 and #390 acceptance verdicts

**kvnloo/hermes-agent#389 (B389): candidate kvnloo/bend@17db447a PROMOTABLE; stock 2.0.34 fails the gate.**
- Stock 2.0.34 returns PASS via `bend_verify` (3/3) and `hermes bend verify` on the bendlang/bend issue 1212 fb3 layout while
  the certified book computes True and the source computes False (1 translation mismatch). The verifier re-checked this
  cross-kernel: both kernels certify stock's book as True.
- Candidate B: 3/3 primary oracles certify the source value (direct and plugin); 79/79 derived value oracles agree; 0 stable
  new failures vs stock over 1,526 tests + 70 examples; 0 plugin false passes over 1,580 cases; CLI 30/30 matches.
- Per release, agree counts (tests of 1,526 / proof of 86 / examples of 70 / plugin pass of 1,580): A 969/51/43/1004,
  B 973/52/43/1014. B gains 4 cases (3 from the 6 upstream commits, 1 from the patch), loses 0.
- C2 control (v2.0.34 + only the 2 safe.ts lines, official kernel) also meets every condition (informational).
- Upstream closed bendlang/bend issue 1212 with a different fix (bendlang/bend PR 1215, e1ed2435), **unreleased**; v2.0.34
  is still the latest release. Its regression test passes on B and C2, fails closed on A and C1.
- Claim scope: "agrees on every oracle" means the preregistered oracle set (3 primary + 75-79 derived); ~937 certified
  files per arm have a non-Bool/Nat/U32 `main` and no value oracle. The issue's 25-verdict adapter matrix was replaced by
  3 reps + 1 CLI run per special case (per the meta triage).

**kvnloo/hermes-agent#390 (B390): accept for the packaged plugin** (strategies 2+3+4 combined: content-hash identity,
name->hash resolution from the local binding with no network, private BEND_LIB snapshot re-checked after the verdict).
- A1 181/181 success receipts carry exactly the identities re-derived from fixture bytes.
- A2 0 successes in 35 replays with differing package/verifier (receipt_stale / replay_mismatch as expected).
- A3 0 plugin successes on 105 mutated-cache rows, while raw `bend --verdict` accepted the same caches (40/40; 20 forged
  fail->pass). Mid-verdict mutation: 30/30 unstable.
- A4 offline replay 10/10 (matrix) + 10/10 (`hermes bend replay`, new process, no network).
- A5 0 hub requests attributable to 125 sequential online plugin calls (all 632 hub-log requests fall inside Bend-fetch
  windows); the 980 racing attempts are covered by SOURCE only.
- Concurrency: 980 racing verifies fail closed except 26 exact-identity passes; 3 concurrent Hermes processes 30/30.
- Scope: the four strategies of #390 were **not** compared as separate arms; strategy 1 is not a plugin mode.

## 6. Full-stack E2E (REAL, 10 measured runs per task, every run in the denominator)

Integration Hermes ad31bbf0 + qwen2.5:7b-instruct + bend-native in shadow mode, fresh private sessions, private z0 service.

| Task | Layer | Independent oracle | Result |
|---|---|---|---|
| cua_browser fill -> submit | CUA (Driver 0.32.0) | fixture `/state.submitted == token` | 9/10 |
| cua_gtk3 check "I agree" | CUA | GTK3 task-state file, no collateral | 9/10 |
| bend_fix repair impl.bend | Bend | fresh `bend ./PROOF.bend --verdict` outside Hermes + LAWS hash | 2/10 (7B model weak at Bend; untuned) |
| bend_contra unprovable law | Bend | honest non-success: no VERIFIED claim, LAWS unchanged, no passing receipt | 10/10; 0 forged passes, 0 false claims |
| z0_state pinned repo | z0 | git facts checked outside Hermes | 10/10; packet_id 5e108208 identical |
| z0_opp current branch | z0 | same + read-only authority/effects | 10/10; semantic_id b34cfee8 identical, grants `["read"]` |

- Joins: receipt -> observer trace 17/17; opportunity records 40/40, all read-only; both pass receipts replay
  (`replay_match: true`); 14 fail receipts refused fail-closed (F4). LAWS.bend and PROOF.bend unchanged 20/20.
- Kernel latency (quiet-timed, 10 processes, kernel a7e5203d): bootstrap median 22.6 s; warm p50 140 ms, p90 152 ms.
- z0 scoring (offline): `api.attempt_will_fail` degenerate (0 positives / 178); `verification_needed` (n=40, 10 positive,
  bend_contra honest non-success counted as success): base rate Brier 0.1875; laya_421m 0.2035, nanojev 0.2060,
  julia_1 0.2453 — **no backend beats the base rate**; promotion_ready never true. GPU peak 10,903/12,288 MiB.
- Fail-open on the private z0 service: held in the 2 exercised stops (the preregistered in-run stop was refused by
  Landlock; amendment 1 committed before a 3-run supplement; 1 stop landed after Hermes exited).
- 0 API errors / 178; all 40 chat runs rc 0 with session_end completed.

## 7. AODL gate receipts

z0 AODL gate proof project (z0intelligence `exp/bend-aodl-gate` @ a0e95785, 6-file closure, manifest 04e7c7c5, PROOF
88b17baf) through `hermes bend verify`: pass 3/3 on official (kernel a7e5203d) and 3/3 on patched (72e11a86); offline
replay match 2/2 in a netns with only lo; one-byte mutants of LAWS.bend and transition.bend -> fail 4/4; pristine receipts
against mutants -> receipt_stale 4/4 without running Bend; out-of-closure README byte still replays to match; cross-build
replay -> receipt_stale. Kernel hash identical across 5 cold bootstraps per build. The mutant rejections came from Bend's
front-end checker, not the BendTT kernel (F2). Restated (SOURCE): parity 22,079 cases, 0 false allows, 1 false deny;
Python validator stays authoritative; Bend gate 4-25x slower, not for the hot path.

## 8. Plugin findings for kvnloo/bend-native (no fixes applied)

| ID | Source lane | Severity | Finding |
|---|---|---|---|
| P-1 | setup | high (safety) | `stack_service_port` defaults to 11501 and the bridge bypasses the proxy, so an unpinned profile talks to the user's live z0 service |
| P-2 | CONTRACT F2 | medium | `Stack.close()` cannot enqueue its stop sentinel into a full queue; worker writes after unload; README's 30 s bound is really 256 x 30 s |
| P-3 | CONTRACT F1 | medium | drops are not persisted; a fresh-process `hermes z0 report` shows rows_dropped 0 |
| P-4 | AODL F1 / E2E F4 | medium | FAIL receipts (kernel_sha256_after null, schema-legal) are rejected by `read_receipt` as invalid_receipt: negative verdicts cannot be replayed |
| P-5 | E2E F2/F2b | medium | `hermes z0 score` strips HF_HUB_OFFLINE and z0 checkpoint/device env from the child; failures hide the backend traceback |
| P-6 | E2E F3 | medium | `hermes z0 evaluate` is hard-wired to api.attempt_will_fail; on other question ids returns n=0 and omits promotion_ready |
| P-7 | E2E F5 | medium | shadow opportunity projection uses process cwd, not the task repo; gate says ACT with every git fact unknown |
| P-8 | B390 F1 | low | missing name binding returns input_capture_failed; the dependency_missing branch is unreachable (still fail closed) |
| P-9 | CONTRACT F4 | low (disclosure) | State Packet persists README open-item text, commit subjects, branch names (latest.json, opportunities.jsonl) undocumented |
| P-10 | CONTRACT F3, H6 | low | delivery counters shared within one manager; hooks registered in `stack_mode: off` cost dispatch time and put every tool call through the fail-closed pre_tool_call gate |
| P-11 | CONTRACT verifier | low | `Stack.callback.record` calls `enabled()` (config load) outside its try; reducer subprocess writes `__pycache__` into the installed plugin tree |
| P-12 | B390 / AODL F3 | low (docs) | receipt schema does not require dependency_* fields; replay briefly stores a success `last_receipt` before replay_mismatch; receipt excludes main.bend (runtime gate shell) |

Setup/harness findings: Hermes PM boots the profile's PM environment, which lacks the computer-use extra, so the first
`computer_use` call does a networked `uv sync` (F-PM; fixed per lane by a provisioned template copy or by masking
HERMES_HOME/installs; the shared template is unchanged). A hostless driver cannot signal a service started outside hostless.

## 9. Blockers, near-misses and escalation

- **Escalation (cross-workflow, not an enumerated breach):** B389's unlocked pilots ran inside other workflows' exclusive
  quiet-timed windows: b389-pilot-direct-A-01 (03:21:41-03:22:55Z) and b389-pilot-plugin-A-01 (03:23:38-03:24:37Z), each
  with a cold kernel build, inside **b04a2-measured-r20-30** (03:19:23.969-03:25:52.269Z); two control Bun builds ending
  03:15:26Z inside **n03a2-a1** (03:13:48.014-03:16:53.839Z). The B389 verifier's own few seconds of single-core Python
  (~05:52:45-05:53:32Z) fell inside **r2-10r-a2-nm2** (05:51:37.630-05:54:27.287Z). Owners of those blocks should flag or
  rerun them. No bend-stack timing is affected (B389 reports no timings).
- Served context: Ollama 0.35.0 serves qwen2.5:7b-instruct at 32,768 tokens/request (owner decision to change model);
  peak prompts were 6,458 (CONTRACT) and 7,635 (E2E), so nothing was truncated.
- The private z0 service ran dev 6764ae78, not the plugin's tested 0563ed7a (which hardwires the system Ollama on 11434).
- Quiet-lane writer starvation (shared-mode back-to-back holders made exclusive blocks wait 15-30 min).
- Disclosed near-misses (all without effect): plain-host empty `python3 -` heredocs and JSON reads; `git config` in a
  worktree briefly wrote a [user] section to the shared bend-native clone's .git/config (removed within a minute, twice);
  networked but lock-pinned/hash-checked provisioning steps inside hostless (PM runtime, computer-use extra); live
  auth.json mtime refreshes at a 44 min 58 s cadence attributed to the owner's own services (masked in every run).

## 10. Errata carried forward (verifier NON-BLOCKING items; packets published as verified, not rewritten)

- CONTRACT: lane Result text said "all six PASS" at 93d91ce; the published head 15ddac2 (D7) has H3 PARTIAL. "aa
  byte-identical to off" means identical settings (config comment line differs). H2 "record cannot raise" overstates
  (P-11). F4 text: history.jsonl holds only claim digests.
- B389: README Deviations omit the unlocked pilots/builds (section 9). Cross-kernel check covers the primary oracle only.
- B390: commit message on e79cfe72 says "0 hub requests from any plugin call"; measured scope is 125 sequential online
  calls. "Unconfigured lo" wording; crashed pilot b390-pilot-online-01 not named; O5/F5 fail baseline is the plugin's own
  run (Bend `--check-only` rc=1 10/10 corroborates).
- E2E: README section 8 "0 real-home entries in every process" is false for 96 scoring runs (two read-only julia dirs
  bound in; no secrets). Live-home stat excludes the directory's own mtime (5 s cadence). Amendment written_at field is
  wrong (commit 03:57:16Z is authoritative). verify_artifacts.py does not re-derive joins/replays/opportunities (verifier
  re-derived them; they hold). 8 tool errors = 7 no-match + 1 multi-match. F5 "no effect on Hermes" is UNIT+SOURCE.
  summary.json scoring latencies are incidental. Failed S2-vn-julia_1-000..003 and aborted S-api-laya_421m-006 not
  listed in failed-attempts.
- AODL: verify_artifacts.py always exits 0 (prints FAILED invariants but OK); a missing live-home-stat counts as
  unchanged; meta/cwd.sha256 was written post hoc by collect.py; PREREG written_at wrong (commit time authoritative).

## 11. Ranked next steps

1. **Plugin fix PR on kvnloo/bend-native (REVISE):** P-1 (default bridge port must not be the live service, or require
   explicit opt-in), P-2 (bounded close), P-4 (replayable FAIL receipts), P-5/P-6 (score env passthrough, evaluate by
   question id with explicit promotion_ready false), P-7 (task-repo cwd; no ACT on unknown facts); then P-3, P-8..P-12.
   Each with the lane's packet as the regression fixture.
2. **#389 owner decision:** promote candidate B (17db447a) or the minimal C2 (6e940a0b), or wait for the next upstream
   release carrying bendlang/bend PR 1215 and gate it with the same corpus (identify by binary/kernel hash, not version).
3. **#390:** close as accepted for the packaged plugin, noting the strategy comparison was not run as separate arms.
4. **Packet errata commits** (section 10) on each exp branch as new commits (no history rewrite).
5. **Cross-workflow:** owners of b04a2-measured-r20-30, n03a2-a1 and r2-10r-a2-nm2 flag or rerun those blocks.
6. **Shared template:** provision the computer-use extra in the bend-stack PM environment once (F-PM).
7. **Model/context owner decision** (32,768 served) and z0 service revision alignment (6764ae78 vs 0563ed7a).
8. Bend tasks need a stronger local model or tuned prompting before any bend_fix rate is meaningful (2/10 is a
   capability floor, not a plugin result); keep `verification_needed` descriptive until a backend beats the base rate.
9. Hermes upstream main is 356 commits ahead of the CI pin 50a6abca; rebase the integration branch and re-run H1/E2E.

## 12. Published (kvnloo only, new branches, --no-follow-tags, no force)

- kvnloo/bend-native: `exp/contract-20261002` 15ddac2b, `exp/b389-20261002` 0d434457, `exp/b390-20261002` e79cfe72,
  `exp/e2e-20261002` a7a041f8, `exp/aodl-20261002` 9477f918.
- kvnloo/hermes-agent: `exp/bend-stack-integration-20261002` ad31bbf0 (setup branch).
- kvnloo/bend: `exp/b389-patchonly-20261002` 6e940a0b (B389 C2 control).
- kvnloo/z0intelligence: nothing to push (lanes used existing `exp/bend-aodl-gate` a0e95785 and `dev` 6764ae78 unchanged).
- Commit scan (every commit since merge-base, messages and added lines): noreply identity + Co-Authored-By trailer on all
  19 commits; no absolute local paths, host name or secrets; no upstream owner/repo#N or upstream issue URLs in messages.
  Added file content contains the plugin's own limitation string with the upstream bendlang/bend issue 1212 URL in raw
  receipts (from verify_core.py at e85e65e5) and, in the Hermes branch, a code comment naming trycua/cua PR 3873 in
  owner/repo#N form; file content creates no upstream backlinks. Comments are listed in PUBLISH.md.
