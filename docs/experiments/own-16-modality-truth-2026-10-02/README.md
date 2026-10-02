# OWN-16: Linux observation-modality selector truth table (GTK3, AT-SPI)

Owner: kvnloo/cua#16 (Linux row). Consumers: kvnloo/cua#10 (accounting), kvnloo/cua#73 (invariants).
Branch `exp/own-16-modality-truth-20261002`. Provider: none (0 attempts, 0 reached).

## Disposition

**KEEP** for the Linux row of kvnloo/cua#16, inside the claim boundary below. On this fixture, an
omitted modality's producer did not run in 42 of 42 cold and warm calls per omission row. The other
modality stayed complete and truthful. The two omission selectors are latency-real. Contract-invalid
selectors are refused before any producer runs.

The macOS and Windows rows of #16 are **BLOCKED** (hardware). Wayland is **NOT_RUN**.

One supplementary finding is outside the pre-registered matrix, so it does not change the
disposition. It is a real silent accept-and-ignore: `include_screenshot: "false"` (a string, where the
contract says boolean) is accepted, the screenshot producer runs, and the screenshot is returned, with
nothing in the response saying so. See "Supplementary finding".

| row | forced selector | class | capture count (S1, S2) | walk count (S1, S2) | warm median ms | warm diff vs `both`, ms [95% CI] | evidence |
|---|---|---|---|---|---|---|---|
| `both` | tree:true, screenshot:true | positive_control_pass | 1 in 21/21, 21/21 | 1 in 21/21, 21/21 | 27.66 (p95 38.26) | n/a | REAL+BENCHMARK |
| `screenshot_only` | include_accessibility_tree:false | latency_real_selector | 1 in 21/21, 21/21 | **0** in 21/21, 21/21 | 20.30 (p95 30.25) | **-7.36 [-8.46, -6.52]** | REAL+BENCHMARK |
| `accessibility_only` | include_screenshot:false | latency_real_selector | **0** in 21/21, 21/21 | 1 in 21/21, 21/21 | 24.68 (p95 33.12) | **-2.98 [-4.28, -1.81]** | REAL+BENCHMARK |
| `neither` | both false | rejected_explicit | 0 in 21/21, 21/21 | 0 in 21/21, 21/21 | 3.08 (error) | -24.57 [-25.64, -24.04] | REAL |
| `legacy_omitted` | no selector field (older schema) | default_honored | 1 in 21/21, 21/21 | 1 in 21/21, 21/21 | 28.04 | +0.38 [-1.68, 1.78] | REAL+BENCHMARK |
| `unknown_field` | include_tree:false (undefined name) | rejected_explicit | 0 in 21/21, 21/21 | 0 in 21/21, 21/21 | 2.45 (error) | -25.21 [-26.26, -24.68] | REAL |
| `wrong_type_supplementary` | include_screenshot:"false" (string) | silently_ignored (supplementary) | 1 in 21/21, 21/21 | 1 in 21/21, 21/21 | 27.26 | -0.40 [-1.76, 1.25] | REAL |
| macOS / Windows rows | n/a | BLOCKED (hardware) | | | | | BLOCKED |
| Wayland | n/a | not attempted, outside the boundary | | | | | NOT_RUN |

How to read the table: "1 in 21/21" means the count was 1 in all 21 cold and warm calls of that
session. The warm median pools 40 warm calls (20 per session). The difference CI is a seeded,
stratified bootstrap of the difference of medians: 10000 resamples, resampling within each session,
seed 1616. Evidence classes: REAL means the real Driver on a real GTK3 app in a private Xvfb session.
BENCHMARK means the timed warm block under the EXCLUSIVE quiet-lane lock. The unit tests are UNIT and
the contract reading is SOURCE.

## Hypothesis (#16 gate) and verdict per clause

1. **Omitted modality means its producer did not run.** Holds.
   - `screenshot_only`: AT-SPI walk count 0 in 42/42 calls.
   - `accessibility_only`: capture count 0 in 42/42 calls.
   - The independent oracle agrees on all 6 oracle calls per row (details under "Controls").
2. **The remaining modality stays truthful and usable.** Holds.
   - `accessibility_only` returned 9 elements with `elements_complete: true`, `truncated: false` and
     no `degraded`, in 42/42 calls. Its element digest (index, role, label, value, frame) is identical
     to the `both` row's digest (`3d9d293d57058dce`). 0 frames fall outside the window bounds.
   - Usability: in each session, an `element_token` from an accessibility-only snapshot was clicked
     (background, AT-SPI route). The fixture's own state file recorded counter 0 to 1 and seq 1 to 2
     (oracle_verified in 2/2 sessions).
   - `screenshot_only` returned a 480x320 PNG in 42/42 calls. The PNG header dims equal the reported
     `screenshot_width`/`screenshot_height`, which equal `window_bounds` (`frame_scale` absent, so
     1.0). `screenshot_frame_valid` is true. The PNG bytes are identical to the `both` row's PNG
     (sha256 prefix `e37d40b2cff85036`), and a capture_id is present.
3. **No silent accept-and-ignore.** Holds for every pre-registered matrix row.
   - `neither` is refused with a message naming both fields.
   - `unknown_field` is refused (`invalid_arguments`) before the tool runs.
   - Neither row runs any producer.
   - It does **not** hold for the supplementary wrong-type value (see below).
4. **Metadata distinguishes omitted from failed or unavailable, where the contract supports it.**
   Holds, but only implicitly.
   - Omission is signalled by **absence**. A tree-omitted response has no `elements`,
     `tree_markdown`, `elements_complete` or `degraded`. A screenshot-omitted response has no
     `screenshot_*` fields, no `screenshot_error` and no image part.
   - Failure is signalled **explicitly**. With accessibility requested and no AT-SPI registry (N1),
     every call returns `degraded: true`, `degraded_reason: "atspi_walk_failed: AT-SPI connect
     failed: ... Could not activate remote peer 'org.a11y.atspi.Registry' ..."`,
     `elements_complete: false`, and an X11-property fallback tree of 1 element. The walk count is 1
     (the attempt is counted).
   - Capture failure is also explicit in source. On X11 the call errors ("window screenshot failed"
     or a stale-target error). On Wayland the response carries `screenshot_error` +
     `screenshot_frame_valid: false` (SOURCE only here; Wayland NOT_RUN).
   - The contract has no explicit "omitted" marker. This is reported as a contract observation, not
     a failure.

## Method

- **Forced path.** The selector rows above are sent as `get_window_state` arguments, with `pid` and
  `window_id` of the fixture's task window, over one MCP stdio session per isolated X11 session.
- **Actual producer invocation.** This comes from the lane binary's measurement-only marks
  (`CUA_DRIVER_PHASE_TRACE_FILE`, commit cd9d6d169):
  - `capture_window` enter/exit around `screenshot_dispatch_for_pid`, the function get_window_state
    calls to capture;
  - `capture_root_region` around `screenshot_root_region_png`, the overlay path (never invoked here);
  - `atspi_walk` around `walk_tree_bounded_within`.

  Each mark carries `n`, that producer's 1-based invocation ordinal. Per call, the harness drains the
  trace before and after the call. The count is the number of `enter` marks.
- **Full-trace audit.** From `raw/S*/phase-m.jsonl`, every producer invocation lies inside a
  `get_window_state` dispatch window. There are 0 outside any dispatch. Ordinals are gap-free per
  scope: 98 walks and 96 window captures per session, which equals 4 walk rows x 24 calls + 2
  usability observations, and 4 capture rows x 24 calls. The usability click and `list_windows`
  invoked no producer.
- **Independent producer-boundary oracle** (separate oracle block, never timed):
  - An X server RECORD client (`xrecord_capture.py`, python-xlib) intercepts core `GetImage` and
    MIT-SHM `ShmGetImage` from ALL X clients.
  - `dbus-monitor --monitor` runs on the private AT-SPI bus. Destination and sender unique names are
    mapped to the fixture and Driver pids via `GetConnectionUnixProcessID`.
  - It runs 3 rounds of every row with 250 ms gaps, plus a 1 s idle window.
- **Matrix.** There are 2 measured sessions, S1 (rotation 0) and S2 (rotation 3), run in the order
  S1, N1, S2, D1.
  - Per session, the cold block is 1 call per row in rotated order. Only the first call is
    process-cold: S1's `both` at 136.4 ms and S2's `neither` at 3.3 ms. The rest are first-of-row.
  - Next is the warm block: 20 rounds, with row order rotated by (rotation + round), under the
    EXCLUSIVE quiet-lane lock. The waits for the exclusive lock were 255.2 s (S1) and 139.1 s (S2),
    because other lanes held it shared.
  - Then come the oracle block and the usability action. Every call is kept, loadavg is recorded per
    call, and there were 0 exceptions in 168 calls per measured session.
- **Per call** the harness records: capture and walk counts with exit outcomes, producer and dispatch
  spans, the response key set, content parts (type, bytes, PNG sha256 prefix and IHDR dims), the
  completeness/degraded/error metadata verbatim, element/coordinate integrity, client wall time
  (monotonic, around `call_tool`) and MCP response bytes. Response bytes are the client's compact
  re-serialization of the CallToolResult, not wire bytes.
- PREREG.json was committed (777149eae, 02:07:48Z) before the first measured call (batch start
  02:07:55Z). `verify_artifacts.py` checks this against the raw timestamps.

## Controls

- **Positive (`both`):** capture = 1 and walk = 1 in 42/42 cold and warm calls. PASS, so the counters
  work.
- **Oracle corroboration:** 21/21 oracle calls agree in each session.
  - X image reads per call: exactly 1 for every capture row and 0 for `accessibility_only`,
    `neither` and `unknown_field`.
  - AT-SPI method calls to the fixture per call: 142 for every walk row and 0 for `screenshot_only`,
    `neither` and `unknown_field`.
  - The idle window saw 0 of both.
  - Windows recomputed from the raw oracle logs: 22/22 per session.
- **Negative / distinguishability (N1, a session without CUA_SESSION_ATSPI):** PASS.
  - 12/12 accessibility-requesting calls (`both`, `accessibility_only`) show walk = 1, `degraded:
    true`, a non-empty `degraded_reason`, `elements_complete: false` and element_count 1 (the X11
    fallback). That is degraded/unavailable, never the omission shape.
  - `screenshot_only` in N1 shows walk 0 and capture 1 in 6/6, and `accessibility_only` capture 0 in
    6/6.
  - Warm medians in N1: both 477.4 ms, accessibility_only 475.6 ms, screenshot_only 20.1 ms. The
    failed registry activation costs about 455 ms per walk attempt. This is reported only, never
    compared with S1/S2.
  - Note: the session bus auto-activates `org.a11y.Bus` when the GTK app starts, even without
    CUA_SESSION_ATSPI. What is missing is the registry, whose activation fails.
- **Default-off smoke (D1):** PASS.
  - With the marks unset, or set to an empty string, the lane binary created no trace file and no new
    file. The unmodified main binary (229b65b28) created none either.
  - Per row, the response shape (structured key set, content part types, is_error) is identical
    across lane-unset, lane-empty, lane-on and main (7/7 rows, 84 calls).

## Component timings and work accounting (warm medians, S1 / S2)

| component (from marks) | both | screenshot_only | accessibility_only |
|---|---|---|---|
| client wall per call | 26.26 / 28.75 ms | 19.33 / 21.14 ms | 23.37 / 25.45 ms |
| Driver dispatch (dispatch_enter to exit) | 9.79 / 11.18 ms | 4.07 / 4.34 ms | 7.09 / 8.11 ms |
| AT-SPI walk span | 5.40 / 6.39 ms | not run | 5.60 / 6.35 ms |
| window capture span | 2.33 / 2.38 ms | 2.37 / 2.45 ms | not run |
| MCP response bytes (median) | 30114 | 26428 | 4069 |

**Work deleted** (counted, separate from time):
- `include_accessibility_tree:false` deletes 1 AT-SPI walk per call. That is 142 AT-SPI method calls
  to the app (oracle), plus snapshot publication.
- `include_screenshot:false` deletes 1 X image read per call (1 `ShmGetImage`), plus PNG encoding,
  capture publication and about 26 KB of base64 in the response (30114 to 4069 bytes).

**Wall-clock saved** (paired-row pooled difference of warm medians on this 9-element window): -7.36 ms
[-8.46, -6.52] and -2.98 ms [-4.28, -1.81] per call. Most of each call's client wall time (about 16 ms)
is outside the Driver dispatch: MCP stdio transport, JSON and the Python client. The selectors cannot
remove that part. These are per-observation numbers on a small tree, not whole-task savings. The
#10 accounting should use them only together with how often a task actually takes each observation.

## Supplementary finding (not in the disposition)

`include_screenshot: "false"`, a JSON string, was accepted in 42/42 calls (plus 6 oracle calls). The X
server saw the image read, the screenshot was returned, and the response shape equals the default
`both` row. Nothing signals that the selector was ignored. This is the #16 "silent accept-and-ignore"
failure mode for malformed selector values.

- Mechanism (SOURCE): `get_window_state` reads the selectors with `as_bool()`, so a non-boolean
  becomes `None`, which means the default (true). The registry checks only argument names against the
  closed schema, not their types.
- Candidate follow-up (not done here): a reviewed product fix that refuses non-boolean selector
  values with `invalid_arguments`, with a red-before/green-after test.

Related contract observations:
- `neither` is refused with the generic code `tool_invocation_failed`. Its message is clear, but there
  is no specific machine-readable code.
- The contract has no explicit "omitted" marker; omission is signalled by absence only.

## Deviations

- **D1 (analysis, disclosed):** the frozen harness's `integrity()` returned before its two screenshot
  checks (PNG IHDR == reported dims; dims == window_bounds x frame_scale) whenever a response had no
  `elements`. So those checks were missing for every `screenshot_only` call, and the first analysis
  pass misclassified the row as incomplete and the run as KILL.
  - `analyze.py` now recomputes both checks for every row from the raw per-call fields (the image
    part's `png_dims`, `meta.screenshot_width/height`, `meta.window_bounds`, `meta.frame_scale`),
    with the PREREG formula.
  - Result: 0 violations in all rows.
- **D2 (analysis, disclosed):** `invalidated_snapshot_ids` is a notice about the PREVIOUS call's
  snapshot. It is present after any successful observation and absent after an error, so it varies
  with the preceding row, not with the selector. A per-call strict key-set comparison flagged 1 of 21
  `legacy_omitted` calls in S2, and 1 of 21 `both` calls in S1 against its own modal set.
  - The shape comparison now excludes this one key.
  - The strict per-call counts are kept in the summary as `structured_keys_equal_both_strict_calls`.
- **D3:** the harness does not retain full responses (images are about 26 KB each). Integrity is
  computed at call time by the frozen harness code (hash in PREREG.json), and raw/ keeps the per-call
  derived fields.
- **D4:** build-driver.sh runs an unsandboxed `--version` after the build (host, no display). The
  version was re-recorded inside every session.
- **D5:** the unit-test session's fresh HOME made rustup install the pinned 1.97.1 toolchain into that
  session HOME before testing.
- **Pilots:** 4 pilot sessions are disclosed in PREREG.json and excluded.

## Limits and claim boundary

- Linux X11 on private Xvfb, a private AT-SPI bus, the GTK3 task window (480x320, 9 indexed elements),
  and Driver 229b65b28 + the R2-04 marks + these counting marks (lane binary sha256
  c6caa34fd58b7aab0e546fd79674fc066ee2f8f0b50a36007a6ca3087f4148d5, cua-driver 0.32.0).
- One machine with concurrent lanes, timed under the quiet-lane lock. 1-min loadavg ranged 4.26 to
  9.96.
- Not covered: macOS/Windows parity (BLOCKED on hardware), Wayland/Hyprland (NOT_RUN), other toolkits,
  Chromium/Electron trees, large trees, the overlay root-region capture path (never triggered here),
  and `screenshot_out_file`.
- Timing is per `get_window_state` call, not whole-task.
- No schema change, no new service, and no observation skipping is introduced or recommended. Marks
  and events are measurement hints, never a success or freshness oracle.

**E2 cross-reference (no cross-lane arithmetic):** an arm that sends `include_screenshot:false` on
this Driver and fixture can rely on the producer truth recorded here.
- Capture count 0 in 42/42 calls, and 0 X image reads in 6/6 oracle calls.
- The element set is complete and identical to the `both` row's.

## Provenance

| item | value |
|---|---|
| upstream main tested | 229b65b2849c3a595ddbc85200d7181b18bd2e47 |
| tree identity | `git diff --quiet 229b65b28 c4d0c6625b5c93849aa8bec610782410e9d45f69 -- libs/cua-driver` exits 0 |
| base | 28b915ae9ec2b1330ad3104f281e0bf4bfde2c49 (R2-04 marks) |
| tested source (binary build head) | cd9d6d16929c29517d6aee4ea9c8c64d71c770f3 |
| PREREG commit | 777149eaec54a50dc84666c8fede2f7a6bf7108f |
| live upstream main at analysis | 8d4e7a08618611453794035f7ff6187f99f0c1e9 (10 commits later, 0 `libs/cua-driver` paths changed) |
| publication SHA | recorded by the Publish agent; this lane does not push |
| Driver | lane sha256 c6caa34f...48d5, `cua-driver 0.32.0` (recorded in-session) |
| unit tests | cua-driver-core phase_trace 6/6, platform-linux 599 + 8 passed, 0 failed (in-session) |
| provider | none: 0 attempts, 0 reached |

## Files

- `PREREG.json`: pre-registration, frozen harness hashes.
- `modality_truth.py`, `run_in_session.sh`, `xrecord_capture.py`, `run_batch.sh`: the harness.
- `analyze.py`: computes `own-16-matrix.json` (the machine-readable truth table) and
  `own-16-summary.json` from raw/.
- `verify_artifacts.py`: recomputes both JSON files from raw/ and checks the PREREG hashes, the
  in-session Driver sha256/version, the PREREG-before-trials timing, this README's disposition/row
  classes, and a privacy scan of every packet file.
- `instrumentation.diff`: `git diff 28b915ae9 cd9d6d169`.
- `provenance.json`.
- `raw/{S1,S2,N1,D1}/`: `calls.jsonl` (every call), `session-env.txt` (in-session Driver
  version/sha256), `phase-*.jsonl` (the Driver's full trace), and `oracle/` (X RECORD events,
  gzipped dbus-monitor log) for S1/S2.
