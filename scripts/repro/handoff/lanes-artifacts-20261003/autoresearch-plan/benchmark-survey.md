# Computer-use benchmark survey for optimizing the CUA kernel (as of 2026-10-01)

Scope: pick benchmarks that can drive an autoresearch-style loop over the cua-driver kernel
(Rust: cua_driver, cua_driver_core, cua_driver_contract, platform_linux) plus the jev-use
caller loop. The question for each benchmark is whether it measures **kernel properties with a
frozen model** (latency, whether actions land, observation fidelity) or mostly **model capability**.

## 0. Local facts that change the answer

- **No KVM on this box.** `/dev/kvm` is missing and the CPU flags show no `vmx`. The CPU is an
  i9-10900KF, which supports VT-x, so VT-x is most likely switched off in the BIOS. Turning it on
  is an owner action. Until then, nothing VM-based is practical locally: the OSWorld VM variant,
  WAA, the AndroidWorld emulator and macOSWorld are all out.
- Docker is installed. gVisor (`runsc`) is not, but cua-bench's default local runtime is gVisor,
  so locally use `--runtime runc` or install runsc first. Available: 10 CPUs and ~14 GB free RAM,
  with the existing lane loop already using some of both.
- **cua-bench upstream has moved past the local checkout.** `/mnt/zer0models/github/cua` main
  has the 0.2.x cua-bench, which still has the simulated Playwright provider. `upstream/main`
  (2026-10-01) is cua-bench **0.3.0**:
  - the simulated provider is removed;
  - local sandboxes run on gVisor/runc/qemu, with cloud Fleet pools;
  - `--attempts N` reports pass@k;
  - each run writes `result.json` (Harbor fields, coarse per-phase timing) and an ATIF-v1.8
    `trajectory.json`;
  - it adds adapters under `libs/cua-bench/tasks/`: **osworld** (OSWorld-Verified, 369 tasks),
    **miniwob** (130 tasks), osworld_g, screenspot_pro, online_mind2web, webvoyager, webgym and
    winarena.
- **Kernel linkage (verified in upstream Cargo.toml).** `cua-spacesd-desktop` depends on
  `cua-driver-core`, `cua-driver-contract`, `cursor-overlay` and `platform-linux`. Every
  cua-bench sandbox action (`sb.mouse` / `sb.keyboard`) therefore goes through the kernel's
  Linux input path. **Kernel changes propagate into cua-bench scores.**
- **Caveat: the scripted oracles bypass the GUI.** MiniWoB oracles are injected DOM JavaScript
  (`ORACLES` in tasks/miniwob/main.py). The OSWorld parity oracles are shell file writes; the
  parity set is only 4 tasks, all in the `os` domain. They check the environment, not the kernel.
  A kernel-only frozen policy needs a new **GUI-routed scripted policy** that acts only through
  the driver's observe, ref and act tools.
- cua-bench's per-phase timing is coarse (setup / agent / verify). Per-step kernel timing has to
  come from the driver or jev-use, which already has `semantic_observe_ms`, `action_ms`,
  `total_step_ms` and related fields per `timing-contract-v1.json`.

## 1. Comparison table

KVM column: "needs KVM" = needs hardware virtualization, which is currently unavailable here.

| Benchmark | Tasks | Platform | Evaluator | Determinism / reset | Infra | Episode time / cost | Licence | SOTA (2026) | Runs here locally / parallel? | Measures the kernel with a frozen model? |
|---|---|---|---|---|---|---|---|---|---|---|
| **OSWorld-Verified** (Jul 2025) | 369 (361 without GDrive) | Ubuntu (+Win subset) | Execution-based scripts (134 eval funcs) | VM snapshot per task; some live-web tasks drift | Docker+KVM, VMware, VBox, AWS (50 envs, <1 h), Modal, Daytona; **via cua-bench 0.3: VM (QEMU/KubeVirt) or container (runc/gVisor)** | Tens of minutes per task for SOTA agents; GTA1 ≈ $2.43/task (OSWorld-Human) | Apache-2.0 | ~86% (Qwen3.8 Max, Claude Fable 5 85%; benchlm aggregator); human ~72% | Container variant: yes, no KVM, ~2-3 parallel by RAM. VM variant: needs KVM. | **Partly.** Success is mostly model capability. Wall-clock, steps and observation cost are kernel-sensitive. LibreOffice AX-tree build alone took 3-26 s (OSWorld-Human), which directly hits the AT-SPI path. |
| OSWorld-Human (MLSys 2026) | 369 human-optimal trajectories | OSWorld | Adds an efficiency metric (WES, 0 to 1, higher is better) on top of OSWorld | Same as OSWorld | Same as OSWorld | — | — | Best agents use 2.7-4.3x the human step count | Metric only | **Yes, as a metric.** WES and step ratio make efficiency first-class. Planner LLM calls are 75-94% of latency for S2/GTA1. Screenshot is 0.4-1.7% and action execution 0.7-1.6%. |
| **OSWorld 2.0 / 2.1** (Jun-Sep 2026) | 108 long-horizon workflows, ~27 checkpoints each | Ubuntu + 31 self-hosted sites | Scripted checkpoints: binary at 500 steps plus partial score | Pinned releases, mocked sites, gated HF tasks | Docker+KVM or AWS | Human median 1.6 h; Opus 4.7 averages 318 tool calls | Apache-2.0 | Paper: Opus 4.8 20.6% binary / 54.8% partial. benchlm: GPT-6 Astra 72.6% (aggregator, different harnesses) | Needs KVM and hours per task. Not loop-able. | No. Long-horizon capability and cost dominate. Kernel effects are drowned out. |
| OSWorld-MCP (Oct 2025) | OSWorld tasks + 158 MCP tools | Ubuntu | OSWorld evaluators + Tool Invocation Rate, Avg Completion Steps | Same as OSWorld | Same as OSWorld | — | — | o3 8.3→20.4% at 15 steps with tools | Same as OSWorld | Mostly model (tool choice). |
| WindowsAgentArena / WAA-V2 | 154 / 141 (11 apps) | Windows 11 | Execution-based (OSWorld-style). V2 fixes the evaluation dependence and infeasible-task hacking, and adds snapshot restore per task | Golden VM image, ~30 GB | Docker+KVM, Azure ML (~20-35 min with 40 VMs) | — | MIT | Navi 19.5% at release (2024); human 74.5% | Needs KVM and Windows. Exercises platform-windows, not platform_linux. | Wrong platform for this kernel target. |
| WindowsWorld (ACL 2026) | 181 tasks, 17 apps, ~5 checkpoints each | Windows | Process checkpoints | VMware snapshots | VMware Workstation + vmrun | — | Apache-2.0 | — | No (VMware/Windows) | Wrong platform. |
| macOSWorld | 202 tasks, 30 apps, 5 languages, safety subset | macOS | Scripted | Snapshot recovery (the bottleneck) | AWS EC2 Mac (or a VMware community variant) | ~15-20 min per task | — | >30% proprietary at release | No (macOS hardware) | Wrong platform. |
| AndroidWorld | 116 parameterized tasks, 20 apps | Android 13 emulator | System-state checks (adb/sqlite) | Seeds; the emulator is reset per task | AVD + KVM; Docker experimental | Step limit ≈ 2x human | Apache-2.0 | ~85% (llm-stats, self-reported) up to 97-100% (vendor claims): saturated | Needs KVM for the emulator; adb is present | Wrong platform. Saturated. |
| WebArena | 812 tasks, 6 sites | Web (Docker sites) | String / program / LLM fuzzy match | Container reset between runs | Docker or AWS AMI | Minutes per task | Apache-2.0 | — | Yes, but the site containers are heavy (GitLab and others) | Mostly model. Browser path only. |
| **WebArena-Verified** (Dec 2025) | 812, plus a 258-task hard subset | Web | **Deterministic**: agent JSON + HAR network trace, no LLM judge, offline re-scoring | Per-site Docker images, reset API | Docker | Minutes per task | Apache-2.0 | — | Yes. RAM heavy, 1-2 parallel stacks next to the lane loop. | Mostly model. Useful as a deterministic holdout for the CDP browser path. |
| VisualWebArena | 910 tasks, 3 sites | Web | Execution + VQA/LLM evaluators | Docker reset token | Docker | — | MIT | Human ~89% | Yes, but heavy | Mostly model (visual reasoning). |
| Mind2Web | 2,350 tasks, 137 sites | Static snapshots (MHTML/HAR) | Offline step/element accuracy | Fully static | None | — | Research-only | — | Yes | No: no live environment, no kernel. |
| Online-Mind2Web | 300 tasks, 136 live sites | Live web | **LLM judge** (WebJudge, ~85.7% agreement with humans) | Non-deterministic (live) | Browser + LLM key (cua-bench adapter) | — | MIT / CC-BY-4.0, gated | — | Yes (cua-bench) | No: judge noise and site drift swamp kernel effects. |
| WebVoyager | 643 tasks, 15 live sites | Live web | GPT-4V auto-eval or human | Non-deterministic | Browser + LLM (cua-bench adapter) | — | Apache-2.0 | — | Yes (cua-bench) | No (same reasons). |
| WebGym (cua-bench adapter) | 1,167 test tasks | Live web | Rubric LLM judge | Non-deterministic | Browser + OPENAI key | — | MIT / CDLA | — | Yes | No. |
| **MiniWoB++** (via cua-bench 0.3) | 130 tasks × seeds | Chromium in the bench-web container | **Page JavaScript computes the reward**, deterministic per seed | Seeded RNG, no network | Docker container, no KVM | Seconds to ~1 min per episode | MIT (maintenance mode) | Saturated for frontier models | **Yes, cheap, 4-6+ parallel** | **Yes, if the policy is frozen and GUI-routed.** Its short episodes are dominated by observe/act/settle time and whether clicks land, including drags, sliders and dropdowns. |
| WARC-Bench (Oct 2025) | 438 GUI subtasks | Web-archive replay | Deterministic subtask checks | WARC replay | Browser | Short | — | 64.8% frontier | Plausible | Partly: short subtasks make action reliability visible. |
| ScreenSpot-Pro | ~1,581 screenshots, 23-26 pro apps, 3 OSes | Static | Click inside bbox | Static | None (cua-bench `provider: dataset`, no sandbox) | — | MIT (HF) | GPT-6 Astra 92.7%, Opus 4.8 87.9% (benchlm) | Yes | **No.** Pure model grounding; the kernel is not in the loop. |
| OSWorld-G | 564 screenshots | Static | Click in bbox/polygon + refusal items | Static | None | — | Apache-2.0 | — | Yes | No. |
| Desktop-Delta Bench (Jul 2026) | 2,013 before/after and ordering items, ~15 Linux apps | Static frames | Exact-match labels | Static | None | — | — | ~65% ordering | Yes | No as a loop target. It is a design reference for stale-observation and effect-landed checks. |
| OSUniverse | 160 tasks (11 paper / 58 wood / 48 bronze / 32 silver / 11 gold) | Linux desktop (AgentDesk Docker) | **Gemini LLM validator**, <2% disagreement with humans | Docker desktop | Docker + Gemini key | Full run 7.4-15.5 h, $73-124 | MIT | <50% SOTA at release | Yes (Docker) | Mostly model, and the LLM-judge noise is non-zero. |
| TheAgentCompany | 175 tasks | Self-hosted GitLab / Plane / ownCloud / RocketChat | Checkpoints; deterministic + LLM evaluators | Reset in minutes | Docker, 30+ GB disk | Long | MIT | 30% at release | Heavy | No: workplace capability. |
| AgentBench-OS | OS bash tasks (dev/test) | Docker bash | Check scripts | Container per task | Docker, <500 MB per worker | Seconds | Apache-2.0 | — | Yes | **No GUI at all**, so it never touches the kernel. |
| UI-CUBE (UiPath, Nov 2025) | 226 tasks, 2 tiers | Enterprise UI | Success across interface variants and resolutions | — | — | — | — | Simple 67-85%, complex 9-19% | Unclear | Its multi-resolution and robustness axes are relevant ideas. |
| OS-Marathon (EMNLP 2026) | 100 vast-horizon repetitive tasks | Desktop | — | — | — | Long | — | SOTA struggles | — | No (horizon capability). |
| MyPCBench (Jun 2026) | 184 personal-assistant tasks | Linux + 17 simulated web apps | — | — | — | — | — | Opus 4.6 best | — | No. |
| Agents' Last Exam | 1,500+ tasks (target 5,000), 55 subdomains | GUI + CLI professional software | Verifiable deliverables (FPR / mean score) | — | — (cua-bench has an ALE compat check) | Long | CC-BY-4.0 / Apache-2.0 | Opus 5.5 34.3% FPR | Heavy, pro software | No (capability). |
| **cua-bench (trycua)** | basic (13 tasks × variants), KiCad (25), workflows, adapters above | Linux / Win / macOS / Android sandboxes | Task `evaluate()` reads state. Optional `solve()` oracle. pass@k | Fresh sandbox per variant, images pinned by digest | Docker (runc/gVisor), QEMU, Lume, cloud Fleet | Depends on dataset | MIT | KiCad: best frontier agent 6/25 | Yes, after syncing to upstream 0.3 and with `--runtime runc` | **It is the harness, not the metric.** Actions run through cua-driver, so it is the natural runner. It needs a jev-use / driver-tool agent adapter (`--agent-import-path`) and per-step kernel timing. |

## 2. Core finding

With a frozen model, success rate on capability benchmarks is a weak and noisy signal for
kernel changes:

- OSWorld-Human attributes 75-94% of latency to planner LLM calls when big planners are used.
- At ~361 tasks, run-to-run sampling noise is a few percentage points.

Kernel quality shows up as:

1. **Non-model wall-clock per step and per success.** Examples: observe, snapshot build, act,
   cursor glide, settle. Measured kernel numbers: the ~1.5 s glide; GTK native actions spending
   255-1416 ms in cursor reveal, plus a fixed 50 ms post-DoAction sleep and a ~241 ms settle.
2. **Effect-landed rate** and **false-success rate**: the tool reported success but the
   independent oracle shows no change, or shows a double apply.
3. **Observation fidelity**: is the target ref present, is the snapshot stale, its size in
   bytes/tokens, and AX build time (3-26 s on LibreOffice in OSWorld-Human).
4. **Steps and provider calls per success**, for example guarded completion removing 1 of 2
   provider calls; WES / human step ratio.

The loop should optimize (1)+(4) under hard constraints on (2)+(3) and on the invariants. Success
rate on a frozen-model benchmark is used only as a **non-inferiority guardrail**.

## 3. Recommended optimization suite

### Inner loop (every candidate, minutes, no LLM): micro-fixtures with independent oracles

- **jev-use FixtureFormTask** (browser/CDP path; loopback fixture, independent `/state` oracle).
- **jev-use native GTK3 fixtures** on the AT-SPI path:
  - `gtk3-choose-size` and `gtk3-save-note`, whose oracle is the state file / journal;
  - captured window states at density 12 and 24, replayed through `measure_native.py replay`
    for observation fidelity, with no live GUI.
- **cua-driver-fixtures HTML**:
  - `interactive.html`: the `#counter` is an exact double-apply / never-blind-replay detector;
  - `form_all_inputs.html`;
  - `gesture_panels.html`: hotkeys/modifiers, pixel accuracy, drag sequence, scroll.
- **timing-contract-v1** with `fake_native_driver.py`, so the timing fields stay honest.
- Policy: **scripted and GUI-routed**. It acts only via driver observe → ref → act, never DOM
  injection. Run 20-30 reps per fixture and report p50/p95 distributions.
- Run in isolated Xvfb sessions that do not reuse the existing lane names or locks, and never
  touch the Hyprland host.
- Metrics: non-model ms per action (tool return **and** oracle-observed effect time),
  effect-landed-before-next-observe rate, false-success, double-apply count, ref-hit rate,
  observation size.

### Dev split (per accepted candidate, ~30-60 min, local Docker, no KVM)

- **MiniWoB++ through cua-bench 0.3 (bench-web container)**:
  - deterministic JavaScript reward, seeded, no network, exercises Chromium through cua-driver;
  - choose ~40 tasks × 3 seeds, weighted toward the action-reliability tasks: drag, slider,
    dropdown, typing, scroll, menus;
  - run (a) the scripted GUI-routed policy (kernel-only) and (b) one **frozen** cheap model
    (pinned id, temperature 0, fixed prompt) for end-to-end non-inferiority.
- **OSWorld-Verified via the cua-bench container variant**, restricted to tasks with
  `container_fidelity == "full"`, no live web and no GDrive:
  - a fixed ~30-40-task dev subset biased to LibreOffice (stresses the AT-SPI build) and Chrome
    (CDP), with the frozen model;
  - report success, WES (OSWorld-Human references), non-model seconds per step and provider
    calls per success.

### Holdout (only for promotion candidates, e.g. every K accepted changes)

- A **disjoint** OSWorld-Verified subset of ~60-100 tasks, never seen by the optimizer. Run it in
  the container variant locally, or the VM variant once VT-x is enabled or on cua cloud KubeVirt.
- Optional: the WebArena-Verified hard subset (258 tasks, deterministic HAR scoring) as a browser
  holdout, if the RAM budget allows next to the lane loop.

### Acceptance rule (paired A/B)

- Run baseline and candidate on the same tasks and seeds, interleaved, with bootstrap CIs.
- Accept only if all of these hold:
  - the CI for non-model latency or steps excludes 0;
  - effect-landed rate and false-success stay ≥ baseline, with zero double-applies;
  - success is non-inferior on the dev set (McNemar on discordant pairs, margin δ);
  - the invariant tests pass: no new services, events are hints only, no blind replay,
    refs are not durable authority, fresh verification.

### Excluded as optimization targets, and why

| Benchmark(s) | Why excluded |
|---|---|
| ScreenSpot-Pro, OSWorld-G, Mind2Web | Static; no kernel in the loop |
| Online-Mind2Web, WebVoyager, WebGym | Live web plus LLM judge; drift and judge noise |
| OSUniverse | LLM validator; hours per run |
| WAA, WindowsWorld, macOSWorld, AndroidWorld | Wrong platform crate, need KVM or Apple hardware; AndroidWorld is saturated |
| OSWorld 2.0, ALE, TheAgentCompany, OS-Marathon | Hours per task; capability-dominated |
| AgentBench-OS | No GUI |

OSWorld 2.0 is worth an occasional sanity run on cloud, but it is not a loop target.

## 4. Prerequisites and owner decisions surfaced

1. Enable VT-x in the BIOS if VM variants should run locally. Until then, use containers or cua
   cloud.
2. Sync the fork's cua-bench to upstream 0.3.0, which holds the adapters and ATIF output.
3. Build a cua-bench agent adapter that drives cua-driver's tool surface, jev-use style, plus a
   GUI-routed scripted policy for MiniWoB and the fixtures.
4. Add per-step kernel phase timing to the trajectory.
5. Decide whether agent-cursor feedback is a fixed UX requirement or a tunable. It is worth
   ~1.5 s per browser click, and the loop must not "win" just by turning it off unless allowed.
6. Pin the model id and budget for the frozen-model runs.
