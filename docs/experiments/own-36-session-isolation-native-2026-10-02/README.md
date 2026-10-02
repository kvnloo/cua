# OWN-36: native session isolation on Linux X11 / GTK3 (capture, element token, retirement)

Owner rows: kvnloo/cua#36 Linux native rows: capture ownership, native element-token / SnapshotStore ownership, session-end retirement. The browser rows are owned upstream by trycua/cua 4317 (merged 0ddf0f7a3) and were not re-run. The cross-session cancellation row belongs to kvnloo/cua#9 (OWN-09 R5) and is only referenced here. macOS and Windows native rows: **BLOCKED (hardware)**.

**Disposition: REVISE.** Capture ownership, replacement isolation, session-end retirement, same-label restart and content-free envelopes hold: **KEEP**. Native element-token ownership does **not** hold: **KILL**. A concurrent session that holds another session's `element_token` mutates the other session's window, landing **20/20 in T1 and 20/20 in T2**, verified on the fixture's own state file. Tokens are also not bound to the Driver runtime generation: **I5p KILL, 10/20**.

Revised claim, as measured on Linux X11/GTK3 at `352507b6c` with `cua-driver 0.32.0`:
- **Captures are owned by the session and its generation.** In one Driver runtime, session B cannot consume session A's `capture_id`: refused with `capture_generation_mismatch` 40/40, and A's capture stays live for A 40/40. A same-label restart retires A's old captures (`capture_not_found` 40/40), and so does a Driver process restart (20/20).
- **Element tokens are owned by the Driver runtime's per-target-pid snapshot store, not by the session.** B succeeds whenever it presents A's token with A's pid (40/40). B refuses it only when the pid does not match (40/40, `stale_element_token`).
- **Ending a session retires only that session's state.** After A ends, B's tokens keep working (40/40) and A's tokens are refused (80/80). Replacing A's snapshot of A's window leaves B's tokens on B's window working (40/40). The exception is a window both sessions observed: there the later observer retires the earlier observer's token (diagnostic I3s, 20/20 refusals, never a mutation).
- **Error envelopes are content-free** (0 hits in 550 scanned envelopes; the scanner's positive control found the marker 84/84). But a stale-token refusal names the target pid's live snapshot handles. From those, B built a working token for A's window without ever receiving one (diagnostic I2d, 40/40 landed).

E4 relevance: I2 and I2d are **cross-session mutations** in which authority came from another session's passive state (I2: A's token; I2d: A's snapshot handle in a refusal). This packet records them as measured falsifications and changes no Driver code. A fix is a reviewed product change (see Follow-ups).

## Provenance (all SHAs kept separate)

| item | value |
|---|---|
| tested source | upstream main `352507b6c03162ab286b21d5ed509125cc3daece` |
| Driver tree check | `git diff --quiet 229b65b28 352507b6c -- libs/cua-driver` exits 0 (re-verified before the worktree was created) |
| binary | existing loop binary `cua-driver-r2-main-229b65b28`, sha256 `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3`, `cua-driver 0.32.0`. Re-hashed and `--version` read inside the private session in every block (block headers) |
| Driver code changed | no (measurement-only harness; default Driver behaviour untouched) |
| fixture | `libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py` TaskWindow mode, sha256 `547b7bca…4059` |
| PREREG | `PREREG.json`, committed in `967dfc22d` at 2026-10-02T04:57:15Z, before the first counted attempt (first counted attempt 04:57:39Z) |
| live heads (read 04:59:50Z) | upstream main `091c6ee07` (1 commit after the tested source, images only; empty `libs/cua-driver` diff). trycua/cua 4317 merged as `0ddf0f7a3` |
| publication SHA | the branch tip carrying this packet (stated in the lane result) |
| provider | TypeSafe not used: **0 attempts, 0 reached** |

## STEP 0: who owns captures and tokens (SOURCE, file:line at the tested SHA)

Paths are under `libs/cua-driver/rust/crates/`.

**Element tokens / SnapshotStore: owned by the Driver runtime, keyed by target pid, not by session.**
- Token format `s<8 hex>:<index>` from one process-global counter that starts at 1 (`cua-driver-core/src/element_token.rs:8-20`). No session, runtime generation or process identity is in the token.
- `SnapshotStore.inner: HashMap<pid, Vec<Snapshot>>` (`cua-driver-core/src/snapshot_store.rs:120-123`). There is one store per Linux `ToolState`, registered per runtime scope (`platform-linux/src/tools/impl_.rs:213-216`). The runtime scope is the daemon generation (`cua-driver-core/src/tool.rs:1198`, `cua-driver-core/src/session_authorization.rs:201-203`), so every session served by one Driver process shares it.
- `publish_for_session` records the publishing session only as `screenshot_owner`. It replaces any snapshot of the same `(pid, window)` whatever its owner (`snapshot_store.rs:146-181`, replacement at `:161-163`).
- `resolve(pid, args)` looks up `(pid, snapshot id)` with **no session check** (`snapshot_store.rs:326-371`). Linux `click` calls it directly (`impl_.rs:6277`); so do type_text, press_key, hotkey, set_value, scroll, double_click and right_click (`impl_.rs:7199, 8086, 8496, 8890, 9291, 9811, 10090`). The session (`screenshot_owner`) gates only the pixel and zoom context (`snapshot_store.rs:34-43, 186-209, 275-295`).
- Session end retires every snapshot whose `screenshot_owner` is the ended session (`snapshot_store.rs:297-314`, hook at `impl_.rs:13957-13958`).
- A stale-token refusal lists the pid's current snapshot handles and window ids (`snapshot_store.rs:81-107`).

**Capture IDs: owned by (runtime generation, session id, session generation, target).**
- `CaptureBinding { runtime_generation, session_id, session_generation }` (`cua-driver-core/src/capture_registry.rs:279-311`). It is taken from the trusted `_session_id` (`capture_registry.rs:1123-1153`). Publication binds the capture to it and to `Window{pid, window_id}` (`platform-linux/src/capture_action_frame.rs:7-37`).
- Admission refuses `binding != capture.binding` as `capture_generation_mismatch`, and a different target as `capture_target_mismatch` (`capture_registry.rs:900-930`, codes at `:504-513`). Click admission happens before native dispatch (`impl_.rs:6690-6703`, `capture_action_frame.rs:120-140`).
- Session end retires the session's captures and bumps its generation (`cua-driver-core/src/tool.rs:733-735`, `capture_registry.rs:1213-1229`). Each registry has a random UUID namespace (`capture_registry.rs:687`), so another process never recognises the id.

**Session identity.** Direct stdio gives each connection a transport session `mcp-<uuid>`, and a non-empty public `session` label overrides it as `_session_id` (`cua-driver/src/proxy.rs:65, 167-187`). The daemon applies the same rule per request (`cua-driver/src/serve.rs:454`, `cua-driver-core/src/tool_args.rs:100-129`). Labels are public names inside one runtime scope, not credentials (`session_authorization.rs:206-211`). Two connections that send the same label share one session. That label-collision vector is a boundary of this packet, not a tested row.

**Topologies.**

| topology | what | run? |
|---|---|---|
| T1 | one `cua-driver mcp` process, sessions A and B = two public labels on one stdio connection | yes: shared store and capture service, distinct `_session_id` |
| T2 | one `cua-driver serve` daemon, two `cua-driver mcp --socket` MCP clients, A and B = each client's implicit transport session (I5 puts a label on A's calls) | yes: same shared stores, per-client transport sessions |
| T3 concurrent | two separate `cua-driver mcp` processes | **inapplicable** for I1-I6: separate stores make any refusal structural, and token strings collide across processes (X1). Inequality or refusal across processes is not isolation evidence |
| T3 sequential | Driver process gen1 exits, gen2 starts, same fixture pid | yes: row I5p (runtime-generation retirement) |
| same process, two windows | | **NOT_RUN**: the canonical fixture creates exactly one window per process (`main.py:509-513`) |

## Method

- **Forced path.** Every attempt drives real MCP `tools/call` requests: `get_window_state`, `click` with `element_token` (accessibility route) or `click` with `capture_id` + x/y (capture admission, then the `x11_atspi` hit-test route), `end_session` and `start_session`. They go to the unmodified 0.32.0 binary over stdio (T1, T3) or through the daemon proxy (T2).
- **Actual route and refusal producer.** These are recorded per call from `structuredContent`: `route: accessibility`, `delivery.mode: background`, and the refusal `code`. Refusals come from `SnapshotStore::resolve` (`stale_element_token`, `invalid_element_token`), capture admission (`capture_generation_mismatch`, `capture_not_found`, `capture_id_invalid`, …) and session lifecycle (`session_ended`, `tool_invocation_failed`).
- **Independent target-owned oracle.** Each fixture instance (A, B) atomically rewrites its own JSON state file on every change (`main.py:488-506`). The harness reads **both** files before and after **every** call. The settle is 0.8 s for calls expected to change nothing. For calls expected to land it polls for 3.0 s plus one extra 0.2 s read. A Driver response is never the success oracle.
- **Isolation.** Every block ran as `hostless` → `flock -s quiet-lane.lock` → `cua-x11-session.sh`, with a private Xvfb, private dbus and AT-SPI. DISPLAY is recorded per block. Telemetry was disabled (no egress). At most 10 attempts per lock acquisition, with receipts in `raw/lock-ledger.jsonl`.
- **AB/BA.** Even attempt = AB, odd = BA. In most rows that is the order of the two sessions' initial observations. In P it is also the order of the actions. In I5 it decides whether B acts before or after A's restart. Blocks interleave T1 and T2 (`plan.txt`).
- **Markers for I6.** Each block first saves a unique note in each window (`ALPHA<hex>` / `BRAVO<hex>`), verified on the oracle.

## Results (N of M per row; every attempt kept)

410 counted attempts in 46 complete blocks, plus 2 failed blocks with 0 attempts that were re-run under new ids (see Deviations). Every block header shows sha256 `8b037961…cd3` and `cua-driver 0.32.0`. Displays: `:99` (27 blocks), `:100` (16), `:101` (5), each a private Xvfb. Recomputed by `analyze.py` into `own-36-summary.json` and independently by `verify_artifacts.py`.

"Cross-session mutations" counts calls in which one session's artifact (token or capture), or an old-generation token, changed a fixture.

| topology | row | gating result | cross-session mutations | refusal codes | evidence | verdict |
|---|---|---|---|---|---|---|
| T1 | P | 20/20 attempts, both own-token uses verified (40 uses) | 0 | none | REAL | CONTROL_PASS |
| T2 | P | 20/20 attempts, both own-token uses verified (40 uses) | 0 | none | REAL | CONTROL_PASS |
| T1 | I1 | 20/20: B's use of A's capture refused with 0 mutation, and A's own capture tail verified | 0 | `capture_generation_mismatch` 20 | REAL | KEEP |
| T2 | I1 | 20/20: B's use of A's capture refused with 0 mutation, and A's own capture tail verified | 0 | `capture_generation_mismatch` 20 | REAL | KEEP |
| T1 | I2 | 0/20: B + A's token on pid_B refused 20/20 (`stale_element_token`), but on pid_A it landed 20/20 (A toggled, verified on A's state file, B unchanged) | 20 | pid_A: none (success, `route: accessibility`) | REAL | KILL |
| T2 | I2 | 0/20: same pattern; on pid_A it landed 20/20 | 20 | pid_A: none (success) | REAL | KILL |
| T1 | I3 | 20/20: B's pre-replacement token verified on B, A unchanged, and A's superseded token refused | 0 | A superseded: `stale_element_token` 20 | REAL | KEEP |
| T2 | I3 | 20/20: same | 0 | `stale_element_token` 20 | REAL | KEEP |
| T1 | I4 | 20/20: after A's end, B's own token verified, B + A's token refused, A + its own token refused | 0 | B: `stale_element_token` 20 (pid has no current snapshot); A: `session_ended` 20 | REAL | KEEP |
| T2 | I4 | 20/20: same | 0 | B: `stale_element_token` 20; A: `tool_invocation_failed` 20 (session has ended) | REAL | KEEP |
| T1 | I5 | 20/20: same-label restart refused the old token and old capture, the new token verified, and B verified | 0 | old token `stale_element_token` 20; old capture `capture_not_found` 20 | REAL | KEEP |
| T2 | I5 | 20/20: same | 0 | same | REAL | KEEP |
| T3 | I5p | 10/20: gen1 capture refused 20/20 (`capture_not_found`), but the gen1 token was accepted by gen2 in 10/10 'same'-order attempts (identical string `s00000001:2`, A toggled) and refused in 10/10 'swapped' attempts | 10 | 'same': none (success); 'swapped': `stale_element_token` 10 | REAL | KILL |
| T1 | N | 10/10: stale token on the recreated window's pid refused with 0 mutation | 0 | `stale_element_token` 10 | REAL | CONTROL_PASS |
| T2 | N | 10/10: same | 0 | `stale_element_token` 10 | REAL | CONTROL_PASS |
| T1 | I1 forged | 5/5 refused with 0 mutation, and A's tail verified | 0 | `capture_id_invalid` 2, `capture_not_found` 3 | REAL | CONTROL_PASS |
| T2 | I1 forged | 5/5 | 0 | `capture_id_invalid` 2, `capture_not_found` 3 | REAL | CONTROL_PASS |
| T1 | I2 forged | 5/5 (both B calls refused) | 0 | `invalid_element_token` / `stale_element_token` | REAL | CONTROL_PASS |
| T2 | I2 forged | 5/5 | 0 | same | REAL | CONTROL_PASS |
| T1 | I3 forged | 5/5 | 0 | same | REAL | CONTROL_PASS |
| T2 | I3 forged | 5/5 | 0 | same | REAL | CONTROL_PASS |
| T1 | I4 forged | 5/5 | 0 | same | REAL | CONTROL_PASS |
| T2 | I4 forged | 5/5 | 0 | same | REAL | CONTROL_PASS |
| T1 | I5 forged | 5/5 | 0 | same | REAL | CONTROL_PASS |
| T2 | I5 forged | 5/5 | 0 | same | REAL | CONTROL_PASS |

**I6, content-free envelopes: KEEP** (REAL for envelopes; SOURCE for telemetry). The scan covered 550 envelopes: every response returned to a session for a call that carried the other session's token or capture, plus every refusal in every T1/T2 row. It found **0** occurrences of the other session's note marker, of the PNG base64 signature, of image items, or of base64 runs of 256 characters or more. The scanner's positive control found each session's own marker in its own observation envelope in **84/84** block-sessions, and the marker was saved on the oracle 84/84. The 192 Driver, proxy and daemon stderr files of the campaign also carried no marker (local scratch, mirrored outside the packet). Telemetry: the tool and session events use a bounded property schema (`cua-driver/src/telemetry.rs:340-420, 1024-1041, 2108-2145`) that is posted only to the network (`:2220-2237`). Runtime telemetry was disabled here, so REAL telemetry inspection is NOT_RUN. **Non-gating disclosure:** 52 refusals returned to B listed A's live snapshot handle and window id (`current_snapshots`): 40 I2d probes, 10 I3s, 2 forged I2. The I6 definition treats these as identifiers, not content, but I2d shows they are enough to mint a working token.

**Diagnostics (non-gating, pre-registered):**
- **I2d** (T1 20, T2 20): B never received A's token. Its stale probe on pid_A was refused 40/40 with A's handle listed. The derived `<handle>:<B's own checkbox index>` equalled A's token 40/40 and **landed on A 40/40** (verified).
- **I3s** (T1 10, T2 10): both sessions observed A's window. The earlier observer's token was refused 20/20 (`stale_element_token`) and the later observer's token verified 20/20. Retirement is per (pid, window), regardless of session (`snapshot_store.rs:161-163`), so it only refuses and never mutates.
- **X1** (20 pairs): two concurrent Driver processes each minted `s00000001:2` for their own window in 20/20 pairs. Cross-process token inequality cannot be assumed, and cross-process refusal is not isolation evidence.
- **N, dead pid** (20): the old token on the dead pid resolved in the store. The action-time AT-SPI identity check then refused it (`stale_element_token: observed AT-SPI object … is no longer …`) with 0 mutation, 20/20.

## Row dispositions for kvnloo/cua#36 (Linux X11 / GTK3)

| #36 row | rows | disposition |
|---|---|---|
| capture ownership across concurrent sessions | I1 (T1, T2), I5 capture sub-check, I5p capture | **KEEP** |
| native element-token / SnapshotStore ownership across concurrent sessions | I2 (T1, T2) | **KILL**: 40/40 cross-session mutations |
| snapshot replacement does not retire another session's state | I3 (T1, T2) | **KEEP** for separate windows. A shared window is excepted (I3s) |
| session-end retirement | I4 (T1, T2) | **KEEP** |
| same-label restart (session generation) | I5 (T1, T2) | **KEEP** |
| Driver process restart (runtime generation) | I5p (T3) | **KILL**: tokens carry no runtime generation; gen1 token accepted 10/10 when gen2 re-observes in the same order |
| content-free envelopes and telemetry | I6 | **KEEP**, with the identifier disclosure above. Telemetry is SOURCE only |
| same process, two windows | | **NOT_RUN**: fixture makes one window per process |
| concurrent separate processes | | **inapplicable** (structural; X1) |
| macOS, Windows native rows | | **BLOCKED** (hardware) |
| cross-session cancellation | | owned by kvnloo/cua#9 (OWN-09 R5) |
| browser rows | | owned upstream (trycua/cua 4317) |

## Controls

- **Positive.** Same-session token use verified 80/80 (row P), plus every verified tail: I1 40/40, I2 40/40, I2d 40/40, I3 B 40/40, I5 new token 40/40.
- **Forged or garbled.** 5 per row per topology, 50/50 refused with 0 mutation.
- **Discriminating in-session negative.** A stale token after the window was destroyed and recreated was refused 20/20 (row N). I3's own superseded token was refused 40/40.
- **The I2 KILL itself discriminates I4.** The same call (B + A's token on pid_A) that lands 40/40 in I2 is refused 40/40 once A has ended (I4).

## Work deleted vs wall-clock saved

None claimed. This is a correctness and isolation lane: no timing claims, counts only, and no component time is attributed.

## Deviations

1. **Two failed blocks, re-run under new ids** (`plan-reruns.txt`). `T2 I1 04` hit a setup crash: the private AT-SPI registry failed to activate, so the Note element was missing. `T2 I2d 08`: GTK init failed because the private Xvfb on `:99` had already exited. Both crashed before any gating call with 0 attempts. Their header-only raw files and rc=1 receipts are kept, and the re-runs (`04R`, `08R`) completed. All 46 complete blocks have rc=0. A pilot block once returned rc=1 from `xvfb-run` teardown after a complete `block_end`, so verification keys completion on `block_end`, not on rc.
2. **"Window destroyed and recreated" (row N)** is a fixture process restart (new pid), because the fixture cannot recreate its window in-process.
3. **Pilots before PREREG.** 5 runs (~32 attempts, outside the packet) already showed I2 landing and the I5p 'same' arm being accepted. The gates are the lane spec's and were not changed. The pilots fixed harness mechanics only.
4. **T2 I5** puts a public label on client A's calls, because a same-label restart needs a label. The other T2 rows use each client's implicit transport session.

## Limits and claim boundary

- **Applies to:** Linux X11 (private Xvfb, openbox) with the GTK3 TaskWindow fixture, `cua-driver 0.32.0` built from `229b65b28` (Driver tree = tested `352507b6c` = live main `091c6ee07`). Topologies T1, T2 and T3-sequential as defined in STEP 0. Checkbox clicks via `element_token` (accessibility route) and capture-bound coordinate clicks.
- **Not tested:** Wayland/Hyprland; other token-consuming tools (they call the same `resolve`, `impl_.rs:7199-10090`; SOURCE only); label collision between connections (SOURCE boundary); concurrent separate processes beyond X1; trees that differ between Driver generations (I5p shows token acceptance, not a wrong-element dispatch, because the fixture tree is static); REAL telemetry payloads.
- **Nothing here covers** browser (trycua/cua 4317), macOS or Windows.

## Follow-ups (staged, not done here)

1. **Reviewed product fix for I2 (and I2d).** `SnapshotStore::resolve` should refuse a token whose snapshot `screenshot_owner` differs from the caller's `_session_id`, and anonymous snapshots should not resolve for named sessions. Re-run I2/I2d. That also turns the `current_snapshots` disclosure into a harmless hint.
2. **I5p.** Bind tokens to the runtime generation, for example by seeding the snapshot counter randomly per runtime or putting the runtime scope in the handle. Re-run I5p with a fixture whose tree differs between generations to test for wrong-element dispatch.
3. **Decide whether I3s is intended** (latest observation per window is authoritative across sessions). If so, document it as a #36 boundary.

## Files

- `PREREG.json` (committed first), `plan.txt`, `plan-reruns.txt`
- `harness/` (MCP client, block runner, lock wrapper, campaign)
- `raw/T{1,2,3}/<row>/b<block>.jsonl`: every call with both fixtures' pre/post states. Image data is replaced by its length. Local path prefixes are scrubbed.
- `raw/lock-ledger.jsonl`: one shared-lock receipt per block.
- `analyze.py` → `own-36-summary.json`
- `provenance.json`
- `verify_artifacts.py`: independent recomputation of every gating row, the I6 scan, the plan and ledger coverage, the lock windows, PREREG-before-first-attempt, binary identity and a privacy scan.

