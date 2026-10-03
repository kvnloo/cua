# Full-stack track synthesis: CUA x Hermes x z0int (2026-10-02)

Scope: kvnloo/hermes-agent#319 directive (2026-10-01). No new integration architecture, protocol, question family
or active controller was added. Hermes is the executor, z0intelligence owns the cognition schema, independent
fixture oracles grade outcomes, and shadow output never reaches Hermes. CUA invariants (kvnloo/cua#73/#93) hold:
no new Driver services, fresh verification kept, no blind replay.

Lane verdicts: SMOKE accepted, MULTISEAT accepted, **SAMPLES not accepted** (one blocking claim-honesty problem; a
text-only erratum fixes it, and the verifier says the data, labels and metrics are unaffected). Setup lanes (sway,
hermes, z0int) were inputs, not verified lanes.

## 1. What the stack does end to end

```
fixture task (seeded, independent oracle)
  -> hostless v2 (env stripped, private XDG_RUNTIME_DIR, Landlock scope)
     -> private desktop session per agent (cua-x11-session.sh = Xvfb, or cua-sway-session.sh = headless sway)
        -> Hermes (isolated worktree exp/stack-integration-20261002 = fork main 4d3555e5 + #385 + #386 + #387,
           own venv, private HOME/HERMES_HOME, live home masked by bwrap, egress to a dead proxy except loopback)
           -> local model on Ollama (qwen2.5:7b-instruct 845dbda0 on user-local 0.35.0 at 127.0.0.1:11500, GPU,
              32K served; or qwen2.5:3b 357c53fb on system 11434, CPU, 4K served)
           -> computer_use tool -> cua-driver (Hermes-pinned 0.21.0; 0.32.0 for compat/sway)
           -> #385 observer plugin: z0int.hermes_observer_event.v1, metadata only, every hook returns None
  -> offline or sidecar z0int scoring (laya_421m / julia_1 / decider_2b / nanojev / Qwen logprob adapter)
     on two existing lanes: api.attempt_will_fail (#386) and the verbatim decision-capability-v1
     verification_needed question
  -> outcome join: fixture-oracle verdict via adapters.hermes_z0int close_observation/join_outcome and
     z0int.receipt.join_outcome (execution_completed kept separate from verified_success)
  -> #387 evaluation (Brier / log-loss / ECE / coverage), with explicit denominators
```

Joined identity is (trace_id = sha256(session_id, turn_id), turn_id); the api-lane attempt key is
(api_request_id, retry_count).

## 2. Sway kit status and isolation canary

- Kit: sway 1.12, wlroots0.20 0.20.2, libliftoff 0.5.0, wtype 0.4, installed user-local without root under
  ~/.local/opt/cua-sway. All packages sha256-match the sync db. wlrctl (AUR only) was replaced by two small
  tools: `seatctl` (virtual pointer and keyboard on a named seat) and `seatprobe` (logs the seat of every event).
- Session script: cua-sway-session.sh (sha256 c3e54bc4...). It supports N seats, readiness waits and clean
  teardown (0 leftover processes). It refuses to run outside hostless or when SWAYSOCK is set (both verified
  rc 97). The WAYLAND_DISPLAY/HYPRLAND_* refusal is SOURCE only. It adds a nested bwrap (private /tmp and PID
  namespace), a Landlock scope (no abstract-socket connects or signals outside the session) and X display lock
  seeding.
- Isolation canary (REAL): PASS 3/3 after a fix; 1 earlier FAIL (display shadowing) is kept. From inside, the host
  Hyprland sockets, host Wayland sockets, session and AT-SPI buses and X11 path sockets are all ENOENT. Host
  abstract X11 sockets give EPERM or ECONNREFUSED, and the host PID is ESRCH. The private Wayland and X11 clients
  map in the private tree. Decoy checks show the probe can detect a reachable socket.
- Multi-seat (REAL): PASS 5/5 reps, 16/16 checks each. Each seat has its own cursor and focus, and concurrent
  typing lands only in that seat's focused window.
- Near miss, fixed: before lock seeding, 13 sessions took the private display :1 (about 2 min in total), which
  could have caught a host X11 client. No traffic went from the session to the host.
- Shared-infra findings: plain hostless still reaches host abstract sockets (shown with a decoy only).
  cua-x11-session.sh writes its X lock and D-Bus socket into the host /tmp.

## 3. Driver capability matrix under sway (cua-driver 0.32.0)

| Capability | Verdict | Evidence |
|---|---|---|
| Native Wayland | PARTIAL | Opt-in (`CUA_DRIVER_RS_ENABLE_WAYLAND=1`). list_windows, capture and the AT-SPI tree work. Foreground click and type arrive. Background input is refused (no libei/RemoteDesktop on sway). GTK3 task 0/3: element frames are scaled by 1.326 (original_width/screenshot_width), so clicks overshoot. Native titles get a " [app_id]" suffix, which breaks the exact-title jev-use smoke. |
| X11 apps via Xwayland | PARTIAL | AT-SPI smoke PASS (18 elements). Foreground XTEST: 1/3 full pass, and the first click into a fresh Xwayland was lost in 2/3 runs. Background pointer and keyboard need uinput. |
| Seat binding | NO | SOURCE: primary_seat.rs takes the last-advertised seat, and no parameter selects one. REAL: every Driver event landed on seat1 (setup), and 2/2 MULTISEAT reps had both agents on seat1. |
| Multicursor | PARTIAL | One Driver drew 3 per-session cursors at once. Input still goes through one seat. Session B was refused until it took its own snapshot (per-session capture ownership). |
| Portal input (libei) | NO | Structured "no focus-free input backend" refusal. |

The browser smoke was BLOCKED under hostless v1 because the user namespace hid root ownership of Chrome. Orchestrator
decision 1 (hostless v2, no user namespace) resolved that for Xvfb sessions.

## 4. Smoke results (SMOKE, accepted; kvnloo/cua exp/stack-smoke-20261002 @ c9604fb3)

106 REAL computer-use runs, each in its own private Xvfb session under hostless v2: 58 measured plus compat, 24
exploratory and 24 replication. 12 pilots are kept separately and excluded from denominators. Model
qwen2.5:7b-instruct 845dbda0 (temperature 0, seed 42 tag, deleted afterwards). Peak prompt 23,637 of 32,768 tokens,
so nothing was truncated. Driver 0.21.0, as pinned by Hermes.

- H1 join: PASS. 34/34 measured shadow-arm runs plus 24/24 supplementary runs have the same trace_id/turn_id on
  observer rows and z0int receipts. The oracle verdict is joined through close_observation/join_outcome.
- H2 persistence: PASS. 324/324 ok receipts carry the candidate set, the full distribution, confidence, latency
  and backend/model/revision.
- H3a code path: PASS. No core Hermes file references z0int. Hooks return None, 0/333 tool results were blocked,
  and the shadow directory was an empty tmpfs inside Hermes in 106/106 runs.
- H3b paired on/off: supported by the preregistered rule. The system-prompt hash was identical in 24/24 pairs. 3
  discordant pairs, all off-only passes (sign test p=0.25). The browser on-arm 0/12 did not replicate: on 3/12 vs
  off 1/12 on fresh pairs, and pooled 3/24 vs 4/24 (p=1.0). The verifier corrected the mechanism of the first-call
  divergences: it is Ollama prompt-cache state, not cross-lane batching.
- H4 fail-open: PASS. 6/6 outage runs exited 0, and 33/33 opportunities were receipted backend_unavailable. The
  check is structural because the sidecar is out of process.
- H5 latency (BENCHMARK, quiet-timed, 60 frozen real requests):

| Backend | Cold ms | Warm p50 ms | Warm p90 ms |
|---|---|---|---|
| laya_421m (CPU) | 17,899 | 555 | 660 |
| julia_1 (CPU) | 17,793 | 77 | 91 |
| nanojev (GPU, chat model resident, peak 10.8 GB) | 23,311 | 28.6 | 29.5 |
| decider_2b | BLOCKED (GPU budget) | | |
| Qwen logprob | NOT_RUN here (z0int lane) | | |
| JEV | NOT_RUN (paid) | | |

- Outcomes: gtk3 12/12 on, 12/12 off, 3/3 outage. The browser task had 0-4 passes out of 12 per arm (the model
  picks the wrong index in Chrome's 122-element AX tree). api.attempt_will_fail is DEGENERATE (0 positives in 299
  joined attempts, plus 2 counted orphans). verification_needed: 35 of 58 traces true, 1 unknown.
- Driver contract finding: Hermes computer_use sends `element_index`. cua-driver 0.32.0 refuses it ("unknown
  argument element_index"). Compat runs on 0.32.0 passed 0 of 4.

## 5. Multi-seat interference and throughput (MULTISEAT, accepted; kvnloo/cua exp/stack-multiseat-20261002 @ 8502fe3e)

Topology: N=4 concurrent Hermes + cua-driver 0.32.0 agents, each in its own private headless sway (not one
compositor with N seats). The fixture is the upstream GTK3 TaskWindow with an app-written journal as the oracle.
The windows were deliberate look-alikes: same title, same pid and same X window id in every session.

| Gate | Result |
|---|---|
| H1 cross-session landings | PASS, 0/74 journals |
| H2 foreign window or focus | PASS, 0 foreign. 1 run lost its own window: the agent clicked the fixture's Exit button, which the journal records |
| H3 concurrent faster in >=6/8 pairs | PASS, 8/8, median 2.38x (range 1.66-3.28) |
| H4 success parity | Descriptive only: SEQ 10/32 vs CONC 7/32, confidence intervals overlap |
| HSL non-Driver seat look-alike | 3/3, 0 cross-seat landings |
| HSD Driver multi-seat in one compositor | BLOCKED: 2/2 reps both on seat1, and half the presses were absorbed |

Throughput (BENCHMARK, 16/16 quiet-lane ledger receipts, model server shared with other lanes in every round):
median round makespan 85.9 s SEQ vs 40.2 s CONC, 0.84 vs 1.35 successes per minute, 2.68 vs 6.17 agent runs per
minute. CPU mean was 28% vs 71% (lower bound). Peak RSS was about 600 MiB per session. GPU peak was about 7.4 GB
device-wide (the model runner held a constant 6.6 GB).

Deliberate cross-wire control (3 reps): X11 by display number, by X11 socket path through the Driver, and through
xdotool all gave 0/3. **D-Bus/AT-SPI through the Driver landed in B 3/3, and Wayland through seatctl landed in B
3/3.** Sway IPC was reachable 3/3. Isolation therefore holds between agents that only know their own addresses.
Same-uid sibling sessions are not isolated against a deliberately cross-wired client, because Landlock fences only
abstract sockets, not path sockets.

Verifier corrections (non-blocking): withdraw "limit of the 7B executor, not concurrency". At least 4 runs show a
stack-side loss of the first click (Driver ok, typed text never journalled). The D1 pid was 52, not 59. kvnloo/cua#36's
remaining rows (capture ownership inside one Driver process, native token ownership, cancellation) were not
exercised.

## 6. Frozen dataset and backend evaluation (SAMPLES, NOT accepted; local only, not pushed)

Packet: kvnloo/cua exp/stack-samples-20261002 @ 4c1a4a95 plus kvnloo/hermes-agent exp/stack-samples-20261002 @
5d01f608 (harness hygiene: question-id parameter, explicit denominators, thin Ollama-logprob adapter). Both are held
locally until the erratum lands.

- 112 preregistered tasks (100 file-tool, 12 CUA on GTK3 in private Xvfb). 105 ran and 7 are NOT_RUN (deadline).
  Executor qwen2.5:3b on system 11434 (CPU, 4K served context; 0/235 attempts truncated). MANIFEST 648e418e...,
  1154 observer rows, 0 dropped. Oracle: 48 pass, 57 fail.
- api.attempt_will_fail: DEGENERATE, 0/235 positives (one-sided 95% upper bound 1.27%), 0 orphans. Kept as a
  registered row with no ranking.
- verification_needed (57/105 positives; G3 = paired-bootstrap Brier difference vs the preregistered
  leave-one-family-out prior):

| Row | Brier | log-loss | ECE | acc@0.5 | G3 diff [95% CI] | First call ms | Warm p50/p95 ms |
|---|---|---|---|---|---|---|---|
| base rate in-sample (optimistic ref) | 0.2482 | | | | | | |
| constant 0.5 | 0.2500 | 0.693 | 0.043 | 0.543 | -0.021 [-0.032, -0.011] | | |
| LOO-family prior (reference) | 0.2709 | 0.735 | 0.000 | 0.352 | ref | | |
| julia_1 (CPU) | 0.2466 | 0.852 | 0.113 | 0.667 | -0.024 [-0.074, 0.031] | 10,815 | 68.5 / 87.8 |
| laya_421m (CPU) | 0.2513 | 0.696 | 0.096 | 0.505 | -0.020 [-0.042, 0.001] | 16,963 | 433.8 / 465.4 |
| nanojev (GPU, comparison only) | 0.2906 | 0.779 | 0.212 | 0.457 | +0.020 [-0.022, 0.063] | 17,169 | 28.4 / 34.5 |
| decider_2b (GPU) | 0.4348 | 1.280 | 0.439 | 0.457 | +0.164 [0.081, 0.250] worse | 197,540 | 24.3 / 24.6 (one 180 s stall at call 3 not shown) |
| qwen_3b logprob (CPU Ollama) | 0.5426 | 4.630 | 0.543 | 0.457 | +0.272 [0.170, 0.378] worse | 9,356 | 2,057.8 / 2,290.6 |
| JEV reference | NOT_RUN (paid) | | | | | | |
| fail-open control (dead-port adapter) | coverage 0, 105/105 backend_error, scorer exit 0 | | | | | | |

  No backend beats the prior (H3 not supported). julia_1 is the only row that separates classes. Decider, NanoJev
  and Qwen always answer "safe to respond".
- Blocking fix: the README blames default approvals for the CUA input failures. The receipts show 0/12 CUA runs
  reached the Driver at all: every failure was tool_call bridge misuse by the 3B model, with no approval lines. The
  2 button_present passes are unassisted yes/no answers. The approval-bypass owner question should be withdrawn.
  Other fixes: decider stall disclosure, the 92 s wall-time label, the t096 exit reason, plainer E1 wording, a
  one-hot edge case in the adapter, and saving the unit log.

## 7. Blockers

1. **Hermes vs cua-driver element addressing** (owner decision): Hermes always sends `element_index` (fork and
   upstream main). cua-driver 0.32.0 and upstream main refuse it. Hermes still pins 0.21.0. With current Drivers,
   element clicks always fail.
2. **Single-compositor multi-seat Driver use is BLOCKED.** There is no seat selection (primary_seat.rs).
3. **Sibling-session path sockets are reachable** (Wayland, sway IPC, D-Bus/AT-SPI, X11 path). The owner must
   decide whether to fence them with Landlock filesystem rules or accept environment-scoped isolation.
4. **decider_2b latency is BLOCKED by the GPU budget** while the 11500 chat model is resident (7.3 GB).
5. **SAMPLES not accepted** until the text-only erratum lands. After that it needs re-verification, then a push.
6. Shared Ollama on 11500 (pid 3782390): no lane claims to have started it, and users.d/samples.json is stale.
   The orchestrator must assign who stops it.
7. With the default tool_search bridge, small models call `tool_call` with malformed arguments, so CUA runs need
   tool_search off.
8. Shared GPU Ollama output is not deterministic at temperature 0 (prompt-cache state). On/off equivalence claims
   are observational only.
9. Evidence gaps: drive.py does not record CUA_HOSTLESS. The derived t0 tag has no /api/show receipt.

## 8. Ranked next experiments

1. **Element-addressing contract (highest leverage).** After the owner decides which side changes, re-run the
   SMOKE 0.32.0 compat arm and the MULTISEAT task with element clicks. This removes the coordinate workaround and
   the pin to 0.21.0.
2. **Publish SAMPLES** after the erratum and a re-verify. Then preregister a confirmation of julia_1 on
   verification_needed on a fresh frozen set (it is the only row that separates classes), using the 7B executor on
   11500 for larger N and more CUA tasks with tool_search off.
3. **Driver delivery bugs under sway**, each with a frozen fixture and a fresh-verification oracle (kvnloo/cua#73):
   the native element-frame scale of 1.326; the first XTEST click lost in a fresh Xwayland (seen again in
   MULTISEAT); the title-bar offset of (+2, +27) px; the " [app_id]" title suffix.
4. **Sibling path-socket fencing** in cua-sway-session.sh (Landlock filesystem deny on other sessions' run dirs),
   then re-run the D1/W1/S1 cross-wire control. Expected result: 0/3 everywhere.
5. **decider_2b latency slot** with the 11500 chat model unloaded. Record the warm series max to catch the
   compile stall.
6. **kvnloo/cua#36 remaining rows** inside an existing fixture: two sessions in one Driver process for capture
   ownership (the sway multicursor observation already shows a per-session snapshot refusal), native token
   ownership and cancellation.
7. Seat selection (feeds kvnloo/cua#100 seat lifetime). This is a parameter, not a service, and needs an owner
   decision before any code.

Kernel and autoresearch targets the stack now exposes (measured, frozen inputs exist; not acted on here):
- laya_421m CPU warm p50 of 434-555 ms (ModernBERT-large decision head). It is the slowest local backend on the
  default-candidate path, and a CPU inference kernel and batching target over the 60-request frozen set.
- decider_2b cold start of 197-303 s, almost all torch.compile/inductor. Targets: compile-cache persistence and
  the stall at call 3.
- julia_1 worker IPC: 241 ms through the worker at setup vs 69-77 ms later vs the documented in-process 28.6 ms.
  Target: the JSON IPC overhead.
- Qwen logprob via CPU Ollama at about 2 s warm. Target: GPU serving or prompt-cache reuse.
- Hermes prompt size: peak 23.6K tokens, dominated by Chrome's 122-element AX tree. Target: AX-tree
  serialization or compaction, measured against the existing browser fixture.
- Multi-agent throughput: 2.38x at N=4, bounded by 2 model-server slots. Target: a slots/N scaling sweep under
  quiet-timed.

## 9. Publish log (2026-10-02)

Pushed with --no-follow-tags, new branches only, no force. Every commit since the merge base was scanned: no
/home or /mnt paths, no host name, no secrets, emails are noreply only, and every lane commit carries the
Co-Authored-By trailer. The sway canary receipts contain the generic XDG runtime path /run/user/1000/... as probe
targets, with the Hyprland signature masked. That is accepted as a generic system path.

- kvnloo/cua: exp/stack-sway-20261002 d7317fd2, exp/stack-smoke-20261002 c9604fb3,
  exp/stack-multiseat-20261002 8502fe3e.
- kvnloo/hermes-agent: exp/stack-integration-20261002, exp/stack-smoke-20261002 and exp/stack-multiseat-20261002,
  all at 0d60437a.
- Not pushed: exp/stack-samples-20261002 on both repos (lane not accepted). No z0intelligence branch exists (the
  setup used a detached worktree at origin/dev 6764ae78 with no changes).
- Comments posted (no write was refused, so there is no PUBLISH.md):
  - kvnloo/hermes-agent#319 issuecomment-5950027640
  - kvnloo/hermes-agent#322 issuecomment-5950028031
  - kvnloo/cua#36 issuecomment-5950028298
  - kvnloo/cua#94 issuecomment-5950028560
- kvnloo/z0intelligence#14 was skipped because its eval rows come from the unaccepted SAMPLES lane.

---

# Stack v2 (2026-10-02, second pass)

Lanes: SAMPLESFIX, ADDR and CONFIRM. All three were independently verified and **accepted**, with
hard_rule_breach none. Self-reported near_misses (plain-host `python3` JSON one-liners, one `bash -n`, one
own-pattern `pkill`, loopback curl to the shared 11500 Ollama) could not have reached the host session. The scope
directive still holds: no new architecture, protocol, question family or active controller, no Driver change, and
shadow output never reaches Hermes.

## v2.1 SAMPLES: corrected disposition (SAMPLESFIX, accepted)

- Packet: kvnloo/cua `exp/stack-samplesfix-20261002` @ 0e50faeb. It contains the SAMPLES history (4c1a4a95) plus the
  repair: PREREG c26ac540, packet repair 6baeb7a6, lane packet 5a6cb529 and receipts 0e50faeb. No new data,
  labels or scores. Dataset, scored rows, eval, workload and PREREG are byte-identical to 4c1a4a95.
- **CUA attribution corrected.** In the 12 CUA runs of SAMPLES, every failure happened at Hermes' `tool_call` bridge
  (tool_search on, qwen2.5:3b). There were 35 API calls and 27 tool calls, all refused before dispatch: 23 "requires
  'calls'", 3 unknown tool names and 1 "cannot invoke tool_search". That is 0 completed, 0 computer_use dispatches,
  0 approval lines, and GUI state unchanged in 12/12. The earlier figure of 23 counted only the largest class. The
  observer's 27 pre_tool_call and 27 post_tool_call rows match run by run. As a positive control, SMOKE's logs from
  the same logger hold 481 "tool computer_use completed" lines. The 2 button_present passes are a constant "No"
  that matches the 2 tasks whose expected answer is no.
- **The approval-bypass request is withdrawn.** It had no basis in the receipts.
- Other errata: E1 (30 of 40 hex digits of a hermes hash had been invented), E3 (decider stall at warm call 3,
  180.1 s, disclosed), E4 (the 92 s median wall time is descriptive), E5 (t096 exited with pending_tool_result) and
  E6 (header mislabel: the warm columns are the scorer wall-clock series; no value changed).
- Every headline number reproduced independently. Oracle 48 pass / 57 fail. verification_needed Brier: julia_1
  0.2466, laya 0.2513, nanojev 0.2906, decider 0.4348, qwen_3b 0.5426, constant 0.2500, LOO prior 0.2709, base rate
  0.2482. api.attempt_will_fail 0/235 (Clopper-Pearson upper bound 1.27%). verify_artifacts.py passes (14 groups),
  and the tamper copies fail.

Corrected verification_needed table (SAMPLES, n=105, 57 positive; G3 = paired-bootstrap Brier difference vs the
LOO-family prior):

| Row | Brier | log-loss | ECE | acc@0.5 | G3 diff [95% CI] |
|---|---|---|---|---|---|
| base rate in-sample (optimistic) | 0.2482 | | | | |
| constant 0.5 | 0.2500 | 0.693 | 0.043 | 0.543 | -0.021 [-0.032, -0.011] |
| LOO-family prior (ref) | 0.2709 | 0.735 | 0.000 | 0.352 | ref |
| julia_1 | 0.2466 | 0.852 | 0.113 | 0.667 | -0.024 [-0.074, +0.031] |
| laya_421m | 0.2513 | 0.696 | 0.096 | 0.505 | -0.020 [-0.042, +0.001] |
| nanojev | 0.2906 | 0.779 | 0.212 | 0.457 | +0.020 [-0.022, +0.063] |
| decider_2b | 0.4348 | 1.280 | 0.439 | 0.457 | +0.164 [+0.081, +0.250] worse |
| qwen_3b logprob | 0.5426 | 4.630 | 0.543 | 0.457 | +0.272 [+0.170, +0.378] worse |

## v2.2 Element addressing: mismatch and fix (ADDR, accepted)

- **Mismatch (SOURCE, UNIT, REAL).** trycua/cua PR 3873 (61f1c0ab, 2026-09-30, breaking) made the snapshot-bound
  `element_token` the only element target. It removed element_index and snapshot_id from every action schema, and
  unknown arguments are refused at dispatch. The change is in 0.32.0 (local build of trycua 229b65b28) and is absent
  from 0.21.0. Hermes (NousResearch main and fork main, both 54bc5e50, byte-identical in tools/computer_use to the
  stack base 0d60437a) still sends element_index. **Hermes is the stale side.** The Driver contract preserves
  authority, so no Driver change was made.
- **Fix** (kvnloo/hermes-agent `exp/stack-addr-20261002`, head d39e1175):
  - 70cfc7a5 (+11 lines, the measured build): when the live schema lists element_token but not element_index,
    Hermes sends the current snapshot's token alone. With no token for that index it refuses locally with
    `element_token_unavailable`. It never sends a bare index and never falls back to coordinates. 0.21.0 keeps its
    old wire shape.
  - c3d96b04: an element_token call is never replayed after a session revive. This was incomplete: a token-free call
    that noticed the ended session left dead tokens cached.
  - d39e1175: cached tokens and the target are dropped on every ended-session result, before the revive.
  - UNIT: base 7 red, then 12/12, 15/15 and 16/16. computer_use suites 294 / 306 / 309 / 310 passed, 0 failed.
- **Before/after on 0.32.0** (REAL, 12 pairs per task, private Xvfb under hostless v2, qwen2.5:7b-instruct
  845dbda0 at temperature 0, seed 42):

| Task | Before 0d60437a | After 70cfc7a5 | Paired sign test |
|---|---|---|---|
| gtk3 | 0/12 | 12/12 | p=0.00024 |
| browser (jev-use form) | 1/12 | 11/12 | p=0.00098 |
| addressing refusals | 53 | 0 | |
| tool errors / calls | 60/172 | 2/109 | |
| element actions dispatched | 0/55 | 36/38 | |

  - Confirmation on c3d96b04: 24/24, 0 errors in 97 calls. Second confirmation on the head d39e1175: 24/24, 3 errors
    in 98 calls, all in one run after its pass (bring_to_front_requires_foreground, plus 2 local
    element_token_unavailable, which is the authority-preserving refusal).
  - Legacy on 0.21.0: 0 refusals; gtk3 3/3 and browser 0/3 (wrong index in Chrome's 122-element tree).
  - 106 executed runs, 0 harness errors, isolation held in 102/102 runs.
  - **H4 authority FAILED for 70cfc7a5.** In m020, a 425 s degenerate model call (640 duplicate tool calls, 34.6K
    tokens, which overflowed the 32K served window) outlived the Driver session. Hermes then reused cached dead
    tokens twice, and the Driver refused both as stale. No element was mis-hit and nothing was replaced by
    coordinates. d39e1175 closes both paths. Its direct evidence is UNIT plus a REAL three-trigger probe: the
    confirmation runs never triggered the revive path.
  - Confound: Chrome's AX tree has 19 elements on 0.32.0 and 122 on 0.21.0, so the browser rates cannot be compared
    with SMOKE. The within-0.32.0 comparison is fair.
  - Claim boundary: X11/Xvfb + AT-SPI only, n=12 per cell, one local 7B model.
- Recorded, not fixed: Hermes `double_click` sends `button`, which 0.32.0 refuses. Element drag has no Driver
  counterpart (an owner decision; it must never be mapped to coordinates). A right-click by element fired the GTK
  button's default action on both Driver versions (a Driver finding for kvnloo/cua).

## v2.3 Fresh frozen set and julia_1 confirmation (CONFIRM, accepted)

- Packet: kvnloo/cua `exp/stack-confirm-20261002` @ 62034ca4 (correction round 1 on top of 96e0eede). Hermes
  `exp/stack-confirm-20261002` @ b51c7a22: a cherry-pick of the SAMPLES hygiene plus the adapter's single-label
  refusal (no one-hot output). Runtime byte-identical to d39e1175.
- Order: PREREG f11cd9d8 (before the first run), analysis harness 821d895a (before the freeze), freeze fa8399e1
  (MANIFEST content 281a20e4, 2039 observer rows, 0 dropped, before any scorer), results 96e0eede, correction
  62034ca4. verify_artifacts.py passes.
- Collection (REAL): 142/142 tasks, 0 NOT_RUN, 0 harness errors, 1 Hermes timeout kept. 100 file-tool turns and 42
  computer-use turns on cua-driver 0.32.0 with ADDR addressing and tool_search off. Ordinary sampling (no
  temperature-0 tag), each CUA turn in a fresh private Xvfb session. Isolation ok in 142/142 runs. Oracle 94 pass /
  48 fail (file 76/24, CUA 18/24). The oracle re-run reproduces 142/142.
- **Confirmatory test: NOT_CONFIRMED** (preregistered paired bootstrap, B=10000, one-sided, alpha 0.05,
  intersection-union over Brier and log-loss). julia_1 vs the LOO-family prior: Brier 0.2563 vs 0.2468 (+0.0094,
  upper bound +0.045, p=0.67); log-loss 0.744 vs 0.692 (+0.052, upper bound +0.150, p=0.81). The SAMPLES lead did
  not replicate.

| Row (n=142, 48 positive) | Brier | log-loss | ECE | Brier diff vs ref [95% CI, descriptive] |
|---|---|---|---|---|
| LOO-family prior (ref) | 0.2468 | 0.692 | 0.002 | ref |
| julia_1 (confirmatory) | 0.2563 | 0.744 | 0.186 | +0.0094 [-0.034, +0.053] |
| laya_421m | 0.2281 | 0.649 | 0.056 | -0.0188 [-0.030, -0.008] |
| nanojev | 0.2231 | 0.638 | 0.012 | -0.0237 [-0.030, -0.018] |
| decider_2b | 0.2841 | 0.875 | 0.247 | +0.0373 [+0.002, +0.075] |
| qwen_7b_logprob | 0.3380 | 3.754 | 0.338 | +0.0912 [+0.043, +0.139] |
| constant 0.5 | 0.2500 | 0.693 | 0.162 | +0.0032 |
| SAMPLES prior 57/105 | 0.2657 | 0.725 | 0.205 | +0.0189 |
| base rate in-sample (optimistic) | 0.2238 | | | |
| fail-open control (dead port) | coverage 0, 142/142 backend_error, rc 0, no row dropped | | | |
| JEV | NOT_RUN (paid) | | | |

  - nanojev, laya, decider and Qwen answer "safe" on every turn. nanojev and laya beat the reference only because
    they are calibrated near the base rate, which the LOO prior is not here; neither separates the classes.
    julia_1 is the only row that ever says "verify" (40/142), and it is poorly calibrated.
- api.attempt_will_fail: DEGENERATE again, 0/418 joined attempts (upper bound 0.71%), 1 counted orphan. It stays a
  registered row with no ranking.
- **CUA failure causes (corrected from raw tool results).** The 6 cua_note runs: background `type` was refused by
  the Driver (background_unavailable), so nothing was typed, and the model never retried in foreground. 5 foreground
  browser runs: keys were delivered but nothing was submitted, and the receipts cannot say why. 1 browser run: a
  background refusal. 2 browser runs: Hermes' single-query approval gate blocked foreground set_value or focus_app.
  Hermes `type` ignores `element` (SOURCE). That element_token on type_text would fix these failures is an untested
  HYPOTHESIS. No approval bypass is requested.

## v2.4 decider_2b latency (BENCHMARK, quiet-timed, GPU slot with the chat model unloaded)

| Backend | Cold ms | Warm p50 | Warm p95 | Warm max |
|---|---|---|---|---|
| decider_2b (first process) | 240,712 | 28.4 | 28.9 | 183,222 (warm call 13) |
| decider_2b (second process, same TMPDIR) | 35,200 | 22.7 | | 30.8 |
| nanojev (GPU, alone) | 17,262 | 27.8 | 29.6 | 36.8 |
| julia_1 (CPU worker) | 10,803 | 69.2 | 105.0 | 109.6 |
| laya_421m (CPU) | 13,452 | 420.6 | 451.4 | 695.4 |
| qwen_7b_logprob (GPU Ollama, resident) | 537 | 52.4 | 57.6 | 79.1 |

The cold start is torch.compile/inductor. A persisted compile cache removes most of it (240.7 s to 35.2 s). The
large warm stall reproduces (SAMPLES: 180 s at call 3; here: 183 s at call 13). Caveats: a foreign GPU process held
about 0.9 GB at up to about 55% utilisation, and the CPU loadavg was 1.8-11 during the scorers. The decider figures
are upper-side, small-cohort numbers.

## v2.5 Blockers (v2)

1. **Publish holds on ADDR and CONFIRM** (see v2.7). Two commit messages contain an autolinking upstream reference
   (`trycua/cua#3873`): kvnloo/cua 61bc0729 (ADDR results) and kvnloo/hermes-agent 70cfc7a5 (the fix). Every ADDR
   and CONFIRM branch descends from one of them. Pushing kvnloo commits that name trycua issues has already put
   "referenced" events on upstream timelines (seen read-only on trycua/cua 4052 and 3963, from commit 320451280).
   So pushing these branches would write to upstream. Rewording changes the commit hashes the packets and their
   verifiers cite (PREREG order checks, measured-build identities), which is an orchestrator decision.
2. **The hermes fork push was refused** by the permission classifier (External System Writes), including the clean
   SAMPLES branch.
3. Hermes `type` ignores `element`, and background `type_text` is refused on GTK and Chromium surfaces. That blocks
   the CUA text-entry families (cua_note 0/6, browser_submit 0/8).
4. Owner decisions still open: double_click (send click with count 2), element drag (refuse it in Hermes, or add a
   token drag to the Driver), bumping Hermes' pinned cua-driver from 0.21.0 once the fix lands, the right-click
   semantics finding, and single-query approval grants.
5. Isolation gap in older harnesses: the ADDR and SMOKE `run_one.sh` left the host /run/user/<uid> and
   /tmp/.X11-unix visible inside the Hermes sandbox. Hermes connected only to the private display. CONFIRM masks
   both, and that fix must be ported. CONFIRM's run_scoring.sh parses /api/ps with a plain-host python3.
6. The verification_needed reference is weak: on CONFIRM, the LOO-family prior loses to the in-sample base-rate
   constant. No backend discriminates.
7. The shared Ollama on 127.0.0.1:11500 (pid 3782390, running about 16 h) is still unclaimed. No v2 lane started
   it, and the orchestrator must assign who stops it. All v1 blockers on sway, seat binding and sibling path
   sockets carry over unchanged.

## v2.6 Ranked next steps

1. **Unblock publication.** Either (a) the owner accepts an upstream "referenced" event, or (b) reword 61bc0729
   and 70cfc7a5 to plain text, with committer dates preserved and trees identical. Option (b) needs an
   identity-mapping erratum in both packets and a verify_artifacts re-run on the new heads. Also grant the
   hermes-fork push.
2. **Probe the `type` contract on 0.32.0.** Run a REAL backend probe of a token-addressed type_text in background and
   foreground on the GTK entry and the Chrome field, before any Hermes change. Then, if it lands, make a minimal
   Hermes fix (wire element_token into `type`, or refuse `element`) and re-run cua_note and browser_submit paired.
3. **Owner decisions** listed in blocker 4. The Driver right-click finding goes to kvnloo/cua#94.
4. **Harness hygiene:** port CONFIRM's /run/user and X11 masks into run_one.sh, move every JSON parse under
   hostless, and set TMPDIR for verifiers.
5. **verification_needed v3 PREREG:** use the base-rate constant (LOO-estimated) as the reference and add a
   discrimination metric (AUC or paired rank), alongside Brier and log-loss. Increase the CUA share now that
   addressing works. Keep api.attempt_will_fail registered: 0/653 across two sets. A positive class would need a
   fault-injection workload, which counts as a new workload decision.
6. decider_2b: persist the inductor cache across processes, and isolate the warm stall (call 3 and call 13) under
   quiet-timed.
7. Carry-over from v1: sway Driver delivery bugs, sibling path-socket fencing, kvnloo/cua#36 remaining rows (no
   new multi-session evidence in v2), and seat selection.

**What the stack exposes for the kernel and autoresearch loop.** Measured, with frozen inputs and sealed oracles;
not acted on here.
- Two frozen, hash-pinned sets with independent oracles and verify_artifacts.py: SAMPLES (105) and CONFIRM (142).
  They are ready as a sealed evaluation for any candidate backend. The loop's objective should be discrimination
  over the base rate, because Brier against the LOO prior rewards base-rate calibration.
- decider_2b compile cost (240.7 s cold; 35.2 s with a warm cache) and the reproducible approximately 180 s warm
  stall. These are a compile-cache and recompilation-trigger target.
- laya_421m CPU warm p50 of 421 ms is the slowest default-path backend, a CPU kernel and batching target. julia_1 is
  69 ms through worker IPC against 28.6 ms in-process, so the target there is IPC.
- Qwen 7B logprob on the GPU (52 ms warm) against the 3B on CPU (2.06 s). Serving placement matters more than model
  size for the baseline.
- Hermes prompt size: peak 12.8-17.3K tokens on 0.32.0, where the 19-element Chrome tree is smaller. One
  degenerate 29K-token generation overflowed 32K. Targets: a duplicate-tool-call guard (owner decision) and
  AX-tree compaction.

## v2.7 Publish log (v2)

- Pushed (new branch, --no-follow-tags, no force): kvnloo/cua `exp/stack-samplesfix-20261002` @ 0e50faeb. All 7
  commits since the pushed base were scanned: no absolute /home, /mnt, /workspace or /tmp/claude paths, no host
  name, no secrets, no binaries, noreply author and committer, and the trailer on each. No upstream refs autolink.
- Refused: the kvnloo/hermes-agent `exp/stack-samples-20261002` @ 5d01f608 push (classifier). It was not retried.
- Held (not attempted): kvnloo/cua `exp/stack-addr-20261002` @ 2013aa36 and `exp/stack-confirm-20261002` @
  62034ca4; kvnloo/hermes-agent `exp/stack-addr-20261002` @ d39e1175 and `exp/stack-confirm-20261002` @ b51c7a22.
  Both repos' scans were otherwise clean.
- Local-only side effect: `git fetch origin` in the shared cua clone pruned 59 local upstream tags (global
  fetch.pruneTags). They were restored with a no-prune tag fetch from upstream (884 tags). Nothing was written
  remotely.
- No z0intelligence branch exists. Comments: kvnloo/hermes-agent#319 issuecomment-5961784610, kvnloo/z0intelligence#14 issuecomment-5961789232; kvnloo/cua#36 skipped (no new multi-session evidence). Refusal and holds recorded in PUBLISH.md.
