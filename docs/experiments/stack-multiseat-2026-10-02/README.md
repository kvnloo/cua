# MULTISEAT: concurrent Hermes + cua-driver agents on one machine (headless sway)

Lane `exp/stack-multiseat-20261002`. This is kvnloo/cua#36-relevant multi-session evidence for the CUA x Hermes x z0int stack (kvnloo/hermes-agent#319, #322). The compositor is **headless sway 1.12**, not Hyprland or Omarchy; kvnloo/cua#94 stays separate.

- Preregistration: `PREREG.json`, committed in `c9276c01` before any measured run.
- Measured window: 06:27Z to 07:59Z on 2026-10-02.
- Verify with `python3 verify_artifacts.py`.

## Answer in one paragraph

Four Hermes agents ran at the same time, each with its own cua-driver and its own private headless sway session. Across 74 agent runs and 74 fixture journals there were **0 cross-session landings**:

- no foreign windows appeared in any session;
- no session's focus moved to another agent's window;
- there were 0 stale-ref results.

This held even though every session's fixture had the **same title, the same pid (59) and the same X window id**.

Running the four agents concurrently instead of one at a time cut a round's makespan by a median of **2.38x**, with a range of 1.66 to 3.28. Concurrent was faster in 8 of 8 paired rounds.

Task success was low in both arms: 10/32 sequential and 7/32 concurrent. That is a limit of the local 7B executor on this stack, not of concurrency; the confidence intervals overlap.

**The isolation claim is bounded.** Agents only interfere if a client is given another session's addresses. On purpose, a same-uid client pointed at a sibling session's D-Bus/AT-SPI bus or Wayland socket **did** act in that session, 3/3 times each. Sibling sessions are isolated by environment scoping plus X11 enforcement. Path sockets are not fenced off.

Single-compositor multi-seat with the Driver is **BLOCKED**. Two Driver agents in a 2-seat sway both landed on seat1, in 2/2 reps.

## Topology and why

| Choice | Reason |
|---|---|
| One private headless sway per agent, N = 4 (`cua-sway-session.sh`, 1 seat, 1280x800, private AT-SPI) | The Driver cannot bind a seat. SOURCE: `primary_seat.rs` takes the last advertised `wl_seat`. REAL: the sway setup packet saw every Driver event on seat1, and this packet replicates that (SD below). The orchestrator's decision 4 is "one private session per agent". |
| sway, not Xvfb | The kit passed its isolation canary, and the spec names it. The Xvfb fallback was not needed: every session reached readiness. |
| Fixture: the upstream CuaTestHarness GTK3 `TaskWindow`, unmodified, as an X11 client of each session's private Xwayland | It is the Driver's X11 path. The native Wayland path mis-scales element frames (sway packet). `harness/journaled_fixture.py` only adds an app-side append-only journal. |
| Shared: one Ollama 0.35.0 on 127.0.0.1:11500 | Started by another stack lane. It serves 2 slots of 32768 context each, and other lanes' requests went to it in every round. |

Identities:

| Component | Identity |
|---|---|
| Hermes | `0d60437a`: fork main plus kvnloo/hermes-agent#385, #386 and #387. No lane code change; worktree clean. |
| cua-driver | 0.32.0 `r2-main-229b65b28`, sha256 `8b037961…` |
| Model | `qwen2.5:7b-instruct`, digest `845dbda0…` |
| Session script | sha256 `fed58de9…` |
| hostless | v2, sha256 `36738895…` |

`provenance.json` has the full hashes.

## Results (`summary.json`, `grade.json`)

### Per-arm results

Each arm is 8 rounds of 4 agents, so 32 agent runs per arm.

| Metric | SEQ (one at a time) | CONC (four at once) | Evidence |
|---|---|---|---|
| Task success, judged by the fixture journal | 10/32 = 31% (Wilson 95%: 18–49%) | 7/32 = 22% (11–39%) | REAL |
| Failure modes | never saved 11, saved an empty note 11 | never saved 11, saved an empty note 14 | REAL |
| Round makespan, median (min–max) | 85.9 s (75.2–123.7) | 40.2 s (30.2–45.7) | BENCHMARK (quiet-timed, 16/16 ledger receipts) |
| Agent wall time per run, median | 16.4 s | 28.9 s (agents queue at the 2-slot model) | BENCHMARK |
| Successes per minute, pooled | 0.84 | 1.35 | BENCHMARK |
| Agent runs per minute, pooled | 2.68 | 6.17 | BENCHMARK |
| Own model-call overlap per round, median | 0 s | 67 s | REAL (observer spans) |
| API calls per run, median / API errors | 8 / 0 | 8 / 0 | REAL |
| Max prompt_tokens, any request | 10,023 | 9,674 | REAL (all below the 32,768 served context) |
| Stale-ref results | 0 | 0 | REAL |
| Duplicate effects (Save pressed more than once) | 2 runs | 1 run | REAL |
| `element_index` refusals | 10 (in 7 runs) | 4 (in 3 runs) | REAL |
| Foreign windows in a session after a run | 0 | 0 | REAL |
| Focus not on own fixture after a run | 0 | 1 (see note) | REAL |
| Round process tree: CPU mean / peak RSS | 28% / 623 MiB | 71% / 2,228 MiB | BENCHMARK |
| Peak RSS per session | 607 MiB | 601 MiB | BENCHMARK |
| GPU memory used: peak / mean, and mean utilisation | 7,423 / 7,350 MiB, 33% | 7,427 / 7,362 MiB, 47% | BENCHMARK |
| Model server CPU mean / peak RSS | 209% / 2,846 MiB | 290% / 1,639 MiB | BENCHMARK; includes other lanes' traffic |
| Other lanes' requests on the shared model, per round | 76 total, all 8 rounds | 59 total, all 8 rounds | REAL |

CPU percentages are of one core. The host load average was 14–24 throughout, with other lanes running.

**Focus note.** In p8-conc A1 the agent clicked the fixture's own "Exit" button at (32, 207). The journal shows the app's own `exit` event, and the window closed. That is a self-inflicted failure, not interference: no other window was ever in that session. PREREG H2 counts focus only while the fixture is alive.

### Throughput pairs

The order alternated within each pair.

| Pair | p1 | p2 | p3 | p4 | p5 | p6 | p7 | p8 |
|---|---|---|---|---|---|---|---|---|
| Speedup (seq/conc) | 1.95 | 2.55 | 1.66 | 3.28 | 1.71 | 2.38 | 2.39 | 3.05 |

Every round carried other lanes' model requests, so no "clean" pair exists, and the preregistered sensitivity row is empty.

### Interference control L (look-alike windows)

5 rounds of 2 concurrent agents, with identical prompts except for the token. The windows were look-alikes in title, pid 59 and X window id.

- 0 landings across 10 journals.
- 0 foreign windows.
- 0 focus losses.
- 2/10 runs succeeded.

### Deliberate cross-session attempts X

3 reps. Session A acted against session B's idle look-alike fixture. Both journals are the oracle.

| Attempt | Lands in B | Note |
|---|---|---|
| C0 own fill (sanity) | 0/3, landed in A 3/3 | The oracle sees A's own effects. |
| X1 B's X display by number (abstract socket) | 0/3 | Blocked by the Landlock scope and the private /tmp. |
| X2 B's X socket path via the Driver | 0/3 | The Driver does not open path displays. |
| X3 B's X socket path via xdotool/libX11 | 0/3 | libX11 rejects the display name. |
| X4 raw X11 connection setup on B's socket path | no input sent; **accepted 3/3** | B's X server is reachable at protocol level. |
| D1 own X display plus B's D-Bus/AT-SPI bus | **3/3** | The Driver's AT-SPI path typed and saved into B's fixture. The same pid (59) names B's app on B's bus. |
| W1 B's Wayland socket (seatctl pointer and keyboard) | **3/3** | |
| S1 B's sway IPC (read-only) | reachable 3/3 | |

These are the preregistered predictions, and every prediction held. The oracle detected every landing that happened.

### Seat controls

- **SL**, one 2-seat sway, non-Driver (seatctl). Two seatprobe windows had the same title, and the seats typed concurrently, then swapped. 3/3 passed with 0 cross-seat landings: each window received exactly its own seat's tokens.
- **SD**, one 2-seat sway with two concurrent Driver agents, native Wayland arm. Both agents' clicks landed on **seat1** in 2/2 reps, so there is no per-agent seat binding. Single-compositor multi-seat Driver use is **BLOCKED**.

### Gates (PREREG)

| Gate | Result |
|---|---|
| H1, 0 cross-session landings | PASS (0/74) |
| H2, no foreign window or focus | PASS |
| H3, CONC faster in at least 6/8 pairs | PASS (8/8, median 2.38x) |
| H4, success parity | Descriptive, −9 points with overlapping CIs; no equivalence claim |
| H5, stale refs / duplicates | 0/0 stale; duplicates 2 vs 1 |
| HX | Predictions met, so the claim is bounded as stated above |
| HSL | 3/3 |
| HSD | 2/2 single seat, so BLOCKED |

## Findings outside the hypotheses (from the shakedown, kept in `raw/shakedown/`)

1. **Hermes and Driver element-click mismatch.** Hermes always sends `element_index`, and cua-driver 0.32.0 refuses it with `click: unknown argument element_index` (`invalid_arguments`). This is SOURCE on the stack, on upstream Hermes main `5bba024d`, and on upstream Driver main `352507b6`, and REAL in the runs. Every element-index click fails, which leaves only coordinate clicks. The runs still show 14 such refusals despite the prompt.
2. **sway decoration offset.** With sway's title bar, the Driver's AT-SPI element bounds and its window-local click frame differ by (+2, +27) px, so clicks at element centres miss. The measured runs remove the fixture's border with a per-window `swaymsg` command.
3. **First XTEST click lost** in a fresh Xwayland. Three clicks gave counter 2. With a motion-only `xdotool` warm-up they gave 3. This explains the sway setup's "first click lost 2/3" (`fgtype-3`/`fgtype-4`).
4. **Hermes defers `computer_use`** behind the tool_search/tool_call bridge by default. Small local models failed it (5/5 malformed bridge calls), so the lane config makes the tool eager.
5. **Served context is smaller than Hermes assumes.** The server serves 32,768 per slot while Hermes is configured for 65,536. No request came close: the maximum was 10,023 prompt tokens.
6. **Sibling-session reachability** (X runs above). Each session's run directory holds path sockets for Wayland, sway IPC, D-Bus/AT-SPI and the backing X socket, and any same-uid process can reach them. PID namespaces make pids collide across sessions, so a cross-wired AT-SPI client acts on the wrong app with a "valid" pid.

## Declared configuration and harness choices (PREREG)

These are config only, with no code change:

- Private Hermes home per agent.
- `tools.tool_search.defer` set to the default list minus `computer_use`.
- `command_allowlist` holding the exact `cua:*` scopes. These are the product's permanent grants. There is no `--yolo`, no `approvals.mode` change and no bypass variable.
- The border removal and pointer warm-up described above.
- A fixed 6-step prompt using coordinate clicks.
- The task: type your token into Note and click Save note once.

## Claim boundary

**Covered:**

- Headless sway 1.12 with X11 fixtures via Xwayland.
- One fixture and one task.
- A text-only AX capture, with one shared local 7B executor.
- Success rates measure this executor plus stack, not the Driver alone.

**Not covered:**

- Hyprland/Omarchy (#94), physical seats, and browser sessions. #36's browser row is covered upstream by trycua/cua#4317.

**Qualifications:**

- Throughput was measured on a loaded shared machine with a 2-slot model server that other lanes also used. It is not a capacity benchmark.
- Isolation holds for agents that only know their own session. It does not hold against a deliberately cross-wired same-uid client.

## Denominators and deviations

- Every launched run is counted: 64 main runs, 10 look-alike runs, 3 X reps, 3 SL reps and 2 SD reps. There were no timeouts, no Hermes non-zero exits and no missing transcripts.
- Launch 1 was aborted while queued for the quiet-lane lock, before any round started. It was relaunched detached so it would outlive the tool timeout (`raw/attempts/`).
- After PREREG, `grade.py` gained one fallback: it reads the exported `hermes/messages.jsonl` when `state.db` is not shipped. The scoring rules are unchanged. The packet regrade is identical to the grade computed from the full local receipts, which include `state.db` and the full server log.
- `harness/collect.py`, `export_messages.py`, `summarize.py` and `provenance.py` were added after PREREG for packaging. `harness/SHA256SUMS` lists the files as preregistered.

## Layout

| Path | Contents |
|---|---|
| `PREREG.json` | The preregistration |
| `summary.json`, `grade.json` | Aggregates and per-run grades (`harness/summarize.py`, `harness/grade.py`) |
| `provenance.json` | Identities, ledger reference and prereg commit |
| `raw/measured/` | Main rounds (`main/`), look-alike rounds (`lookalike/`), `crosswire/`, `seat-lookalike/`, `seat-driver/`, `server-requests.log` (request lines only, for the contamination count) and `quiet-lane-ledger.ms-main.jsonl` |
| `raw/shakedown/` | Every pre-PREREG run, including failed ones |
| `raw/attempts/` | The aborted launch |
| `harness/` | Everything that produced the receipts. The lane-local environment points it at the session kit, the Hermes venv and the Driver. |

Local paths are masked (`<TMP>`, `<MNT>`, `<HOME>`, `<WORKSPACE>`). The private sqlite files are not shipped; their messages tables are exported.
