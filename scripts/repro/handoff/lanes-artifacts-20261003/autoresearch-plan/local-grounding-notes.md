# Autoresearch loop around the CUA kernel: local grounding notes (2026-10-01)

Read-only scan. Nothing was installed, built, run or launched. Paths: `<lanes>` = /mnt/zer0models/github/cua-lanes, `<tmp>` = /mnt/zer0models/cua-lane-tmp, `<base>` = `<lanes>`/r2-base (detached at upstream main 229b65b28, Driver 0.32.0). The upstream/main ref is now c4d0c6625. It is ahead of the tested base and needs a freshness re-check before the loop pins a base.

## 1. What autoresearch is, and how it has changed (web, fetched)

- **karpathy/autoresearch (early March 2026).** Three files. `prepare.py` is frozen (data and evaluation). `train.py` is the only file the agent edits. `program.md` holds the human-written instructions. Every run gets a fixed 5-minute wall-clock budget, and a run over 10 minutes is killed and counted as a crash. The metric is a single scalar, `val_bpb`. Each run gets a git commit on `autoresearch/<tag>`: the branch advances on an improvement, and `git reset` reverts anything equal or worse. `results.tsv` has the columns commit, val_bpb, memory_gb, status (keep|discard|crash) and description. There is a "simpler is better" rule. The agent never stops to ask whether to continue. The approach depends on a locked evaluator plus Goodhart discipline.
- **How it has developed since.**
  - Generalized loops for any metric:
    - pi-autoresearch: `.auto/measure.sh` prints `METRIC name=value`, `.auto/checks.sh` is the correctness backpressure, and `log.jsonl` is append-only. It reports a MAD-based confidence (|gain|/MAD, where at least 2x means the gain is likely real), but this is advisory only.
    - uditgoenka/autoresearch, a Claude Code plugin at v2.2.0. Install with `/plugin marketplace add uditgoenka/autoresearch` and `/plugin install autoresearch@autoresearch`, or `npx skills add uditgoenka/autoresearch`. A `Verify:` command produces the metric and a `Guard:` command protects existing behaviour. Guard and test files are never edited. It has iteration bounds, a TSV log, `experiment:` commits and auto-revert, and `/autoresearch:regression` runs a Mann-Whitney U test with 7 samples per side and a noise band.
    - chrisliu298/autoresearch, a plain skill installed by cloning it into `~/.claude/skills`.
  - Systems analogues:
    - AutoKernel: only `kernel.py` is editable. `bench.py` and `reference.py` are frozen. Every candidate must pass a 5-stage correctness check before any speedup counts. Kernels are ranked by Amdahl's law, and the loop runs about 40 experiments per hour.
  - Failure reports:
    - Cerebras ran 71 experiments. The agent drifted within hours whenever scope or gates were loose. Their fixes were isolated directories per experiment, accepting only results that are better or equal, and frequent re-steering checkpoints.
    - The awesome-autoresearch list collects "anti-autoresearch" and cheating audits.
- **Takeaway for us.** The loop machinery is a commodity: install a plugin, or write a 30-line program.md. The hard part is the frozen evaluator. Keep and discard must be computed by the evaluator, not judged by the agent, because the plugins leave that decision to the agent.

## 2. Benchmarks: what exists locally and what the kernel actually moves

**cua-bench** (`<base>/libs/cua-bench`, CLI `cb`):
- Adapters under `tasks/`: osworld (OSWorld-Verified, 369 tasks, upstream pinned at b138d348), osworld_g, screenspot_pro, miniwob, webvoyager, online_mind2web, webgym, winarena_adapter and wordpad_env.
- Datasets: cua-bench-basic (13 web-widget tasks on the bench-web image, each with a `solve()` oracle), cua-bench-kicad (25) and cua-bench-workflows.
- How a run works: tasks are Python modules (`@cb.tasks_config`, `setup_task`, `evaluate_task` returning a reward, `solve_task`). Each runs in a local gVisor/runc container or a QEMU VM, or in the cloud (KubeVirt), and is driven through **cua-spacesd** on port 3211.
- Results land in `~/.local/share/cua-bench/runs/<id>/` (`result.json` with per-phase timing for setup, agent and verifier; an ATIF `trajectory.json`; `summary.json` with pass@k).
- **The OSWorld adapter uses `action_mode="driver"`.** The agent acts through cua-driver inside the guest, because cua-spacesd links `platform-linux` and `cua-driver-core` as path dependencies (`libs/cua-spacesd/crates/*/Cargo.toml`). Testing a kernel candidate on OSWorld therefore means rebuilding cua-spacesd and overriding it in the `ghcr.io/trycua/bench-osworld:verified` image (pinned digest in `libs/images/bench/osworld/lock.json`). That costs much more per candidate than the host Driver path.
- The parity split's 4 oracles are shell commands sent through `/setup/execute`, so they never touch the kernel.

**Why OSWorld cannot be the inner-loop metric** (OSWorld-Human, arXiv 2506.16042, MLSys 2026):
- Planning, reflection and judging LLM calls take 76-96% of end-to-end latency. Screenshot, grounding and action execution are minor.
- Agents use 1.4-2.7x more steps than the human-optimal path.
- So an LLM-driven OSWorld score or latency barely responds to kernel changes, and model sampling noise would hide real kernel effects.
- What the kernel controls: the actuation, settle and verification floor of every step; how large and how accurate observations are (which drives prompt length and so LLM latency); and correctness (stale refs, duplicate effects, effects landing after the tool returns).

**Recommendation: three tiers.**
- **Tier A, the inner loop (val_bpb equivalent).** LLM-free scripted replays of fixed, optimal action sequences. These run through the real host Driver against fixtures that each have an independent oracle, inside `cua-x11-session.sh`. The metric is **whole-task verified time T**: from task start (first observation) until the independent oracle confirms the outcome. This is exactly the #73 END_CONDITION "whole task" definition. Because T ends at the oracle, deleting a settle the app actually needs only moves the time into bounded re-reads, or fails a later dependent step. It cannot win by returning early.
- **Tier B, comprehensive validation (milestones only).** OSWorld-Human-style replays of human-optimal trajectories for a subset of OSWorld-Verified tasks, run through cua-driver on the bench-osworld container (runc), scored by the OSWorld evaluator. It is LLM-free, kernel-sensitive and covers real apps (Chrome, LibreOffice Calc/Writer/Impress, VS Code, GIMP, Thunderbird, VLC). OSWorld-Human publishes the trajectories as coordinate actions in OSWorld's action space; its repo asks that they not be used for training, which this use is not. As an optional extra, run a fixed-model, temperature-0 LLM agent on `test_small` with the baseline and final kernels to report success rate plus per-step actuation share (paid, and needs internet egress).
- **Tier C, a held-out battery** the optimizing agent never sees. Examples: GTK3 density-24, other cursor start positions and window sizes, the trusted-input route. It catches overfitting to Tier A.

## 3. Machine capability (read-only)

| Item | Finding |
|---|---|
| /dev/kvm | **Absent.** The `kvm` group exists (gid 990) but kvn is not in it. `/proc/cpuinfo` shows **no vmx flag** on an i9-10900KF, and `systemd-detect-virt` reports `none` (bare metal). VT-x looks disabled in firmware. Without a BIOS change, the OSWorld VM variant (QEMU/KubeVirt) cannot run locally. |
| qemu | Not installed. |
| Docker | 29.7.2, daemon active, data root `/mnt/zer0models/docker-data`, kvn is in the `docker` group. Runtimes: runc only (no gVisor `runsc`), so cua-bench local needs `--runtime runc`. No container was run. |
| podman | Not installed. |
| OSWorld images | None found locally: no qcow2, no `~/.cache/cua-bench`, no `~/.cua/cbregistry`. `docker image ls` was not run, per the rules. An OSWorld mirror at `/mnt/zer0models/github-archive/kvnloo/mirrors/OSWorld.git` is from 2024-10-24 and **lacks** the pinned commit b138d348. |
| Disk | /mnt/zer0models has 1.6 TB free (58% used). **/ has only 14 GB free (90% used)**, so all temp, cargo and docker data must stay on /mnt/zer0models (it already does). |
| CPU/RAM | 10 cores, 23 GB RAM (14 GB available), 151 GB swap. Loadavg was 2.8 at scan time. |
| Session tooling | `~/.local/opt/cua-e2e-x11/root` provides Xvfb, xvfb-run and openbox. picom comes from /usr/bin. Chrome 151 and chromium are installed, as are system GTK3 PyGObject and the jev-use `.venv` in `<base>`. |
| Locks in use | `<tmp>/locks/quiet-lane.lock` and `cargo-build.lock`, shared with the running RFC loop (`<lanes>/artifacts/r2/loop/END_CONDITION.md`, `STATE.json`). |

## 4. Kernel knobs and where time goes (source, `<base>`)

Runtime env knobs:
- `CUA_DRIVER_WINDOW_CHANGE_TIMEOUT_MS` and `CUA_DRIVER_WINDOW_CHANGE_POLL_MS` (`cua-driver-core/src/window_observation.rs`)
- `CUA_MPX_PRESS_MS` (default 12) and `CUA_MPX_CLICK_GAP_MS` (`platform-linux/src/input/mod.rs:2249`)
- `CUA_DRIVER_CDP_PORT`
- Debug only: `CUA_ATSPI_DEBUG`, `CUA_OVERLAY_DEBUG`

Tool-level knobs:
- `set_agent_cursor_enabled`
- `set_agent_cursor_motion`, backed by `cursor-overlay/src/motion.rs::MotionConfig`. Defaults: `glide_duration_ms` 0 (speed-based), `peak_speed` 900, `min_start_speed` 300, `min_end_speed` 200, `dwell_after_click_ms` 80, `press_duration_ms` 120, `turn_radius` 80, `spring` 0.72.

Hard-coded waits that are candidate targets:
- `overlay.rs`: the arrival wait, capped near 5.5 s. R2-01 measured a median of 1517 ms of the 1541 ms browser click.
- `input/focus_guard.rs`:
  - `SETTLE_WATCH` 220 ms
  - `SETTLE_WATCH_NEW_WINDOW` 900 ms
  - `SETTLE_POLL` 30 ms
- `input/foreground.rs`: settle 800 or 1500 ms.
- `input/mod.rs`: `EFFECT_SETTLE` 250 ms.
- `input/targeted.rs`:
  - `OCCLUSION_SETTLE` 300 ms
  - 20 ms and 50 ms sleeps
- `atspi/native.rs`: 50 ms post-`DoAction` sleeps at lines 3535, 3654, 4207 and 4319.
- `atspi/native.rs:3768`: a 500 ms settle deadline.
- `tools/impl_.rs::reveal_pointer_action_for`, the native cursor reveal. R2-04 measured 255-1416 ms.
- `mpx_keyboard.rs`: `KEY_DELAY_MS` plus 120 ms and 30 ms sleeps.
- `x11/mod.rs`: a 40 ms sleep.
- `overlay_capture.rs`: `HIDE_SETTLE` 50 ms.
- The caller completion loop: a 0.1 s poll, 20 times.

Per-phase timing sources:
- **Upstream, caller side.** #4052 (46a75b1b8): jev-use `decision_timing_fields` reports `decision_ms`, `semantic_observe_ms`, `visual_observe_ms`, `candidate_build_ms`, `provider_decision_ms`, `action_ms` and `total_step_ms` in the runner JSONL.
- **Driver internals, branches only.** The default-off `CUA_DRIVER_PHASE_TRACE_FILE` JSONL marks exist on the R2 branches only. There are **two divergent implementations**:
  - `exp/r2-01` 7d3a28b66 uses CLOCK_MONOTONIC ns and marks dispatch, browser click and viz phases.
  - `exp/r2-04` 28b915ae9 uses `{scope, mark, wall_ns, mono_ns}` and marks the AX route, focus guard and DoAction.
  - The loop needs one merged, measurement-only `phase_trace.rs` committed as a frozen base commit.
- **cua-bench.** Its `result.json` timing covers only setup, agent and verifier.

## 5. Reusable harness pieces (R2 packets and lanes)

- `<lanes>/cua-x11-session.sh`: an isolated rootless Xvfb at 1920x1080 with private dbus, openbox and picom, an `env -i` scrub, and an optional private AT-SPI bus (`CUA_SESSION_ATSPI=1` plus `CUA_SESSION_EXTRA_ENV`).
- `build-driver.sh`: the exact CI release build (`--locked --release -p cua-driver --features portal-input`) into `<lanes>/bin/cua-driver-<label>`, with sha256 and Fresh-unit checks. Measured build time is **79-239 s**.
- `run-unit.sh` runs the jev-use Python/TS CI steps. `validate-contract-gates.sh` runs the schema, compatibility and embedded-SDK contract tests. `lane-deps.sh` handles dependencies.
- **R2-01** `docs/experiments/r2-01-2026-10-01/run_feedback_ab.py` and `verify_artifacts.py`: the browser fill-and-submit AB/BA harness. It starts a fresh Driver per trial, uses the fixture `/state` plus journal oracle, keeps all timestamps on one clock, and includes no-submit and stale-ref controls and a bootstrap CI.
- **R2-04** `profile_atspi.py`, `run_in_session.sh` (refuses to run outside the isolated session), `run_batch.sh` (an M,P,P,M,P,M,M,P session order under the quiet-lane flock with per-trial loadavg) and `analyze.py`. Covers GTK3 checkbox, button and text plus stale-token negatives, with the app's own state file as oracle (`libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py`, `CUA_GTK3_TASK_STATE`).
- **R2-03** guarded completion (`python/guarded_completion.py`, `--guarded-completion`), plus R2-05 reconcile-before-replay and R2-06 bounded re-read. These are correctness requirements in every arm.
- jev-use `fixture_server.py` (loopback form with an independent `/state`, and a visual-only variant), `verify_native.py` (harness state-file oracle, density 12/24), `measure_native.py` (decision accuracy by candidate-set size) and `fixtures/native/*` (captured `get_window_state`).
- **Gap:** only fill-and-submit exists as a browser fixture. The #24 classes toggle-and-confirm and modal-and-act are not present on the base and would have to be added as new frozen fixtures before the loop starts.

## 6. Editable surface vs frozen harness

See `editable_vs_frozen` in the structured result. The same text is reproduced at the end of this file.

## 7. One evaluation episode (proposed `ar-eval`, which lives outside the editable tree)

1. **Candidate.** The agent commits on `autoresearch/<tag>` in the lane worktree `<lanes>/ar-<tag>`. The base is pinned upstream main plus the frozen measurement commit (merged phase_trace and the new fixtures).
2. **Static gates (seconds).**
   - The diff touches only allowlisted paths.
   - Cargo.lock, Cargo.toml dependencies and rust-toolchain are unchanged.
   - Nothing frozen changed, checked by sha256 manifest.
   - No existing test was modified or deleted.
   - Added lines that spawn threads or tasks, open listeners or sockets, or add new modules or crates are flagged to an invariant judge. This enforces "no new services".
   - `cargo fmt --check`.
3. **Build** under `flock cargo-build.lock`, into a lane-private `CARGO_TARGET_DIR` (`cua-release-ar-<tag>`). Run it nice -n 19 and pinned to a CPU set away from the timed lane. Incremental builds are about 80-180 s. Release builds stay CI-identical.
4. **Unit guard (about 2-3 min).**
   - `cargo test -p cua-driver-core --lib`: 815 tests, about 12 s plus compile.
   - `cargo test -p platform-linux --lib` inside the session: 599 tests, about 19 s plus about 73 s compile.
   - `run-unit.sh` if caller files changed.
5. **Timed battery** under `flock <tmp>/locks/quiet-lane.lock`, in **one** `cua-x11-session.sh` with `CUA_SESSION_ATSPI=1`.
   - Champion binary B and candidate C run interleaved AB/BA, with a fresh Driver (and browser) per trial. Per-trial loadavg is recorded, and the trace env is set to a per-trial file.
   - Tasks:
     - browser fill-and-submit on the dom_event and trusted routes (plus toggle-and-confirm and modal-and-act once frozen)
     - GTK3 checkbox, button, and text-plus-save
   - Profiles: **feedback ON (product default)** and feedback OFF (host opt-in).
   - Controls: stale-ref refusal, no-submit, and an ack-loss reconcile case. Every control must discriminate.
6. **Scoring, computed by the evaluator, not the agent.**
   - Gates:
     - 100% oracle-verified
     - 0 duplicate mutations
     - 0 stale-ref dispatches
     - 0 unverified successes
     - refusals stay `effect=refused`
     - route unchanged, or a declared change
     - in the ON profile, the trace shows that the overlay ran and arrived before dispatch, so a candidate cannot win by silently dropping feedback
   - Primary metric: the geometric mean over tasks of the median paired ratio T_C/T_B, per profile, with a bootstrap CI.
   - Secondary metrics: p95, tool span, Driver CPU time, observation bytes/elements per step (proxies for LLM prompt cost), and LOC delta.
   - **KEEP** requires all gates, the upper CI bound of the primary below 0.98 (or a gain of at least 3x the A/A MAD), and no task whose ratio CI lies entirely above 1.02. The evaluator prints `METRIC` lines and a verdict, and appends to results.tsv/jsonl.
7. **Confirmation, before the branch advances.**
   - A fresh session with 30 pairs per browser task and 20 per native task (the END_CONDITION E3 sizes).
   - Tier C held-out tasks and contract gates.
   - Only then does the candidate become champion B.
   - Every 5 candidates, run an A/A control (B vs B) to measure drift and the false-keep rate.
   - Re-measure the champion at the start of each session.

## 8. Episode time and parallelism on this host

- **Per-trial costs (measured).**
  - Browser: R2-01 ran 56 trials in 169 s, about 3 s per trial including Driver and Chrome start. The trial wall was 4.06 s with feedback ON and 1.05 s with it OFF.
  - Native: R2-04 trial start to verified was 0.58 s (checkbox), 0.71 s (button) and 3.05 s (text), plus about 26 ms per observation.
  - Session start is about 3-5 s (two fixed sleeps plus AT-SPI startup).
- **Screening episode.** 6 tasks x 6-8 pairs x 2 arms x 2 profiles is about 150-190 trials, roughly **7-10 min**. Add build at about 1.5-3 min and unit tests at about 2-3 min, for **about 12-15 min per candidate, or about 4 per hour**.
  - Default-profile-only screening with sequential early stopping is about 8-10 min per candidate, or about 6 per hour.
  - Effects on the order of 1.5 s are decisive with n=5 pairs: R2-01's CI was about ±1.5 ms at n=24. Effects of 10-50 ms need 20-30 pairs.
- **Confirmation** takes about 15-20 min and happens only on a keep.
- **Overnight (10 h)** that is about 30-50 screened candidates, as long as the RFC loop is not holding the quiet lock.
- **Timed parallelism: 1.**
  - Timing must stay serialized machine-wide under the shared quiet-lane.lock, which the running RFC loop also takes.
  - Glide arrival is frame-paced on CPU-rendered Xvfb/picom, so concurrent sessions would perturb it.
  - Builds, unit tests and agent thinking can run in **2-3 parallel untimed lanes** (each its own worktree and target dir, with `-j 3-4`, nice 19 and a cpuset excluding the timed cores). Memory is not the limit: about 1-2 GB per Chrome session, 14 GB free.
  - Before trusting this layout, run an A/A calibration with a build running concurrently. The CI must contain 1.0 and the median must stay within 1%. If it fails, fall back to pausing builds during battery windows.
- **Tier B** is container-only locally (no KVM). Expect minutes per task plus a cua-spacesd rebuild and image overlay per kernel build. Run it at milestones, not per candidate, or `--on cloud` (paid, needs owner approval).

## 9. Seed hypotheses (from the R2 evidence; the agent may add its own)

1. A non-blocking or capped overlay arrival wait that keeps visible feedback (ON profile). This is an OWNER_DECISION boundary: the minimum visible glide or dwell must be fixed by the owner before the loop starts.
2. Native cursor reveal cost that grows with distance. Cap it, or overlap it with the AX route.
3. Replace the fixed 50 ms post-DoAction sleep with a bounded readback.
4. Exit the focus-guard `SETTLE_WATCH` early once focus is stable.
5. `EFFECT_SETTLE` 250 ms and `OCCLUSION_SETTLE` 300 ms.
6. Browser-click `revalidate` (11 ms, the largest non-visual phase).
7. Caller side: shrink the completion poll from 100 ms to 4-10 ms with a bounded re-read, and keep guarded completion.

Known dead ends from R2: CDP commit-event wake (R2-02 KILL) and AT-SPI bulk/cache on small trees (R2-04 H_A KILL, scoped to the 9-element tree).

## 10. Open owner decisions before the loop starts

1. The ON-profile feedback contract: the minimum visible glide or dwell, and whether arrival must precede dispatch.
2. Whether caller (jev-use) files are in scope, or only the Rust kernel.
3. Whether the TS runner must mirror Python changes.
4. Whether Tier B may use cloud (KubeVirt) or a paid LLM.
5. Whether to enable VT-x in BIOS for local OSWorld VMs.
6. Which loop driver to use: the uditgoenka plugin, a plain program.md plus `ar-eval`, or a Workflow script. Whichever is chosen, the evaluator owns the keep/discard verdict.

## Appendix: editable vs frozen

**Editable by the optimizing agent.** All paths are under libs/cua-driver/. The allowlist is enforced by a diff check.

- rust/crates/platform-linux/src/:
  - overlay.rs: the arrival wait and the glide-await semantics
  - input/focus_guard.rs (SETTLE_WATCH, SETTLE_POLL)
  - input/foreground.rs
  - input/targeted.rs (OCCLUSION_SETTLE and its sleeps)
  - input/mod.rs (EFFECT_SETTLE, click cadence)
  - input/mpx_keyboard.rs
  - atspi/native.rs: the post-DoAction sleeps and the settle deadline
  - tools/impl_.rs: reveal_pointer_action_for and the click/set_value paths
  - snapshot_queries.rs
  - x11/mod.rs
  - capture.rs
- rust/crates/cua-driver-core/src/:
  - browser/tools.rs
  - browser/engine.rs (visualize_browser_action)
  - browser/cdp_ws.rs
  - window_observation.rs, timing defaults only
- rust/crates/cursor-overlay/src/motion.rs and render_state.rs. Pacing only; the minimum visible feedback is the owner's call.
- Optional, if the owner puts the caller in scope: examples/jev-use/python/run.py, guarded_completion.py and run_native.py, plus the TS mirrors when parity is required.
- New unit tests may be added. Existing tests may not be modified or deleted.

**Frozen.** These paths are read-only to the agent, sha256-manifested and checked before every episode. The harness lives outside the agent's worktree, for example `<lanes>/autoresearch-harness`, chmod a-w.

- Cargo.lock, every Cargo.toml (no new deps or crates), rust-toolchain.toml.
- The public contract and safety code:
  - crates/cua-driver-contract/**
  - cua-driver-core/src/tool_schema.rs
  - cua-driver-core/src/authorization.rs
  - cua-driver-core/src/mcp_result.rs (envelope shape)
  - permission and policy code
  - crates/cua-driver-sdk
- Measurement: the merged phase_trace.rs and its call sites, the R2-01/R2-04 marks as a frozen base commit.
- Every fixture and oracle:
  - examples/jev-use/fixture_server.py
  - examples/jev-use/fixtures/**
  - python/tasks.py expected states
  - verify_*.py
  - measure_native.py
  - tests/fixtures/apps/linux/gtk3/** and the other fixture apps
  - the new toggle-and-confirm and modal-and-act fixtures
- Every existing test file: rust tests, python/tests and the typescript *.test.ts files.
- The evaluator: ar-eval (the battery definition, interleave plan and seeds, stats and bootstrap, gates, the profile definitions, A/A schedule and decision thresholds), plus results.tsv/jsonl written only by the evaluator.
- The lane scripts: cua-x11-session.sh, build-driver.sh, run-unit.sh, validate-contract-gates.sh and lane-deps.sh. Also the R2 packet harnesses that are reused (run_feedback_ab.py, profile_atspi.py, run_in_session.sh, run_batch.sh, verify_artifacts.py).
- The Tier C held-out battery. The agent cannot see it, and it is stored outside its worktree.
- program.md, the loop instructions, which only the human edits.
