# AR harness fixtures and controls (evaluator side), 2026-10-02

These are the reference task, the controls, the spot-check fixtures and the external checks for the kernel autoresearch pilot (kvnloo/cua#93; invariants from kvnloo/cua#73). Evaluator agents build and hold them (owner default D9). Proposers never see or edit them, and every file here is frozen for G0 (see `MANIFEST.sha256`).

No model or provider runs anywhere here. The caller is a fixed script.

## What one trial is

`ar_trial.run_trial(harness, fixture, kind, seed, index)` runs exactly one trial inside a private session (`cua-x11-session.sh` with the private AT-SPI bus) and returns one JSON record. The AA/AB harness times this call.

1. **Fixture app.** A fresh `ar_gtk3_app.py` process per trial.
   - It gets a 128-bit nonce on an inherited pipe (`--nonce-fd`).
   - It reports readiness (pid, X window id, seeded layout, initial state, `CLOCK_MONOTONIC`) on a second pipe (`--ready-fd`).
   - The harness starts it before the Driver, so app startup is not in T.
2. **Driver.** Spawned per trial over MCP stdio inside a bwrap sandbox (`ar_sandbox.py`, owner default D8):
   - the whole filesystem is read-only;
   - only a fresh per-trial HOME/TMPDIR, the session runtime dir and `/dev` are writable;
   - the evaluator's private root (state journals, nonces, ledgers) is an empty read-only tmpfs, so the Driver can neither read the oracle nor forge it;
   - no pid, net or time namespace is unshared, so the harness, the app and the Driver all stamp the same `CLOCK_MONOTONIC`.
3. **Frozen caller.** The R2-04 scripted path (no model):
   - `list_windows`, then `get_window_state` (tree + screenshot);
   - jev-use `eligible_controls`, looking up the label;
   - `click(element_token, delivery_mode="background")`; the text task does `set_value` and then the Save click;
   - poll the app's journal until it confirms the effect (0.5 ms poll, 3 s deadline).

   The caller never retries, never redispatches and never reads trace marks.
4. **T** = `t_done_ns - t_spawn_ns`. Both are harness `CLOCK_MONOTONIC` stamps:
   - `t_spawn_ns` is taken immediately before the Driver (bwrap) exec;
   - `t_done_ns` is taken when the journal first shows the expected effect with this trial's nonce and pid.

   The verdict also requires the journal's own `t_applied_ns <= t_done_ns` and `t_handler_ns >= t_spawn_ns`. `T_ms` is set only for `verified` outcomes.
5. **After done (outside T):**
   - one fresh verification observation (cross-layer check only);
   - an external snapshot while the Driver is alive;
   - Driver shutdown, then a 1 s linger to catch late duplicates and let the focus timeline play out;
   - a final external snapshot and the final journal read.

## Reference task and provenance (`gtk3_checkbox:reference`)

Toggle the checkbox named `target_label` once.

**Provenance.** The app writes `state/journal.jsonl` **only from its toggle handler**: one line per handler invocation, appended with a single `write` on an `O_APPEND` descriptor. In the `delayed` variant the line comes from the GLib timeout that the handler itself schedules. Each line carries:
- the nonce and the app pid;
- the handler's own invocation count;
- `t_handler_ns` and `t_applied_ns` (host `CLOCK_MONOTONIC`).

The oracle (`ar_oracle.evaluate_gtk`) reads that file outside the sandbox. It is `verified` only when all of these hold:
- exactly one own record;
- no foreign record (wrong nonce, wrong pid or wrong schema);
- the expected direction (`checked == not initial`);
- the stamp order `spawn <= handler <= applied <= done`.

**Randomized per trial, same meaning** (`ar_layout.layout_for(task, seed, variant)`, which is pure):
- the target label and 3 distractor checkbox labels, drawn from one pool;
- 2 distractor buttons;
- the target's position among the 6 controls;
- GTK widget names (ids);
- spacing and border;
- window size and position;
- the initial checked state;
- the window title.

The same seed gives the same layout, so the two arms of an AB/BA pair can share a seed while no coordinate, index, label or token can be replayed across seeds.

## Controls

| Kind | What happens | Pass |
|---|---|---|
| `negative_stale_token` | Observe, observe again (replacing the snapshot), then click the old token | Driver refuses (error code contains `stale`); journal empty; 0 `DoAction` on the bus |
| `negative_no_action` | Observe only | Journal empty; 0 `DoAction` |
| `canary_absent` | No control carries the target label (a fresh distractor keeps the tree size) | Caller outcome `refused`/`unknown`; journal empty |
| `canary_disabled` | Target eligible at observation. The harness then tells the app (control socket) to make it insensitive, and the caller clicks the still-fresh token | Driver dispatch reached; outcome `refused`/`unknown`; journal empty |
| `delayed_effect` | The handler applies the effect 200-500 ms later (seeded) | Verified once; `done >= applied`; observed delay >= 200 ms; 1 caller dispatch; 1 `DoAction`; no Driver claim of the effect before it landed |
| `focus_steal` | A separate "User notes" process holds the desktop focus. 30-200 ms after the toggle (seeded), the app maps a "Notice" toplevel and takes the focus with a fresh server timestamp | Verified once; the external focus journal (`xprop -root -spy _NET_ACTIVE_WINDOW`) shows the steal; the focus ends with the user's window |

Every kind is also checked for **unverified success**: an action result that claims `verified` or `applied` when the target never changed, or claims it before the target changed, fails the trial (`unverified_success_claims`).

## Spot-check fixtures (before any keep)

- **`gtk3_text:text_save`** (`ar_gtk3_app.py --task text`). The note field and its Save button have seeded labels. The caller runs `set_value(field, unique value)` and then clicks Save. The oracle is the journal record written by the Save handler: `note_saved == value`, exactly once, with nonce, pid and stamps.
- **`browser:fill_submit`** (jev-use browser fixture).
  - The page is jev-use `fixture_server.PAGE` plus a capture-phase listener journal and a seeded top padding.
  - The caller: `browser_prepare` (isolated_new), navigate, `semantic_v2` refs, `browser_type` the token, trusted `browser_click` (foreground), then poll `/state`.
  - The oracle (`evaluate_browser`) requires all of these:
    - `/state.submitted == token`;
    - exactly one POST `/submit` with the token, stamped by the server on `CLOCK_MONOTONIC` and no later than done;
    - an in-order trusted `pointerdown → mousedown → pointerup → mouseup → click` on the Submit button, followed by `submit`;
    - no untrusted click.
  - **Blocked on the Driver under `hostless`** (see Deviations).
- **`browser_selfcheck:{xdotool_trusted,js_untrusted}`** validates the browser oracle without the Driver.
  - The harness launches Chrome itself: sandbox on, throwaway profile, inside the private session.
  - `xdotool_trusted` fills and submits through XTest. The oracle must verify it.
  - `js_untrusted` has the page fill the field and call `button.click()` from script (isTrusted false). The POST lands, and the oracle must reject it.

## External checks (never Driver output or trace marks)

`ar_external.py` takes three inventories of the private session's process tree (found from the `xvfb-run` ancestor): before the Driver is spawned, just before it shuts down, and after it has exited plus the linger. Each inventory has:

- processes (by `comm`);
- listening sockets held by those processes (unix sockets with `__SO_ACCEPTCON`, TCP LISTEN, bound UDP);
- the files under the only paths the sandbox can write (trial HOME, session runtime dir, `/dev/shm`).

Harness-owned pids and all their descendants are ignored: the fixture apps (including GTK's glycin/bwrap image loaders), the bus monitor and the focus spy. Names are normalised (digit runs, long hex runs, mktemp suffixes in paths). Each trial's diff is flattened into a `signature`.

G2's "no new process/socket/file" is `extra_vs_reference(candidate_signature, champion_reference)`, where the reference is the union over the champion validation runs (`champion_reference.json`).

Other external evidence:
- the duplicate-mutation counter is the journal's own record count;
- a `dbus-monitor` on the private AT-SPI bus counts `Action.DoAction` calls per trial (`--no-bus-monitor` turns it off for timed blocks);
- the focus journal is an `xprop -spy` with `CLOCK_MONOTONIC` stamps.

## Files

| File | Role |
|---|---|
| `ar_gtk3_app.py` | GTK3 fixture app: checkbox, text and user-window tasks; normal, delayed, focus_steal, disabled and absent variants |
| `ar_layout.py` | Seeded layout (pure) |
| `ar_oracle.py` | Journal/state oracles and control verdicts (pure) |
| `ar_external.py` | Process/socket/file inventory, diff and signature |
| `ar_sandbox.py` | bwrap argv and env for the Driver under test (pure) |
| `ar_trial.py` | One trial: app, sandboxed Driver, frozen caller, oracle, external checks; browser fixture server; Driver-free browser self-check |
| `validate_fixtures.py` | N-fold interleaved validation of every cell on one Driver (correctness only) |
| `run_in_session.sh` | Runs a script from this directory with the worktree's jev-use venv, and refuses outside a private X11 session |
| `tests/test_fixtures_pure.py` | Unit tests for the pure modules |
| `champion_reference.json` | Champion external-signature reference and per-cell champion facts (route, codes, DoAction counts) |
| `validation-summary.json` | Sanitised 10x validation summary on the champion |
| `MANIFEST.sha256` | sha256 of every file above (G0 tamper check) |

## How to run

```sh
# from the worktree root, never in a host shell: hostless + private session
<lanes>/bin/hostless env CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1" \
  <lanes>/cua-x11-session.sh docs/experiments/ar-harness-2026-10-02/fixtures/run_in_session.sh <worktree> \
  validate_fixtures.py --wt <worktree> --driver <driver-bin> --run-root <tmp>/ar-fixtures/<run> --n 10
# unit tests (no display needed)
<lanes>/bin/hostless libs/cua-driver/examples/jev-use/.venv/bin/python -m unittest discover \
  -s docs/experiments/ar-harness-2026-10-02/fixtures/tests
```

## Deviations and decisions (read before using these fixtures)

1. **Browser spot check: blocked on the Driver under `hostless`.**
   - `hostless` is a bwrap user namespace. Inside it, root-owned files show as uid 65534; `stat /opt/google/chrome/chrome` gives `65534 nobody` inside and `0 root` on the host.
   - The champion's isolated launch accepts only a root-owned, non-writable Chromium (`platform-linux/src/browser_platform.rs`, `trusted_root_owned_installation`). It therefore refuses every `browser_prepare` with `browser_route_unavailable`.
   - The only other route, `strategy.kind=existing_profile`, needs an explicit profile grant. That relaxes a safety setting, so it was not used.
   - The fixture, caller and oracle are complete, and the oracle is validated Driver-free (`browser_selfcheck`). Running the spot check on any Driver needs an owner decision: an isolation that keeps host uid 0 visible as root, or accepting the self-check plus the GTK text spot check before a keep.
2. **No bwrap for the browser Driver, even once unblocked.** The same root-ownership check fails inside any unprivileged bwrap. HOME/TMPDIR still move to the trial home, and the browser oracle is the in-process server journal, not a file.
3. **`delayed` variant.** The journal line is written by the GLib timeout that the toggle handler schedules, not inside the handler itself. The handler stamp and the applied stamp are both kept.
4. **`focus_steal` timing** is inside the champion's guarantee: the Notice maps and takes focus 30-200 ms after the toggle, inside `SETTLE_WATCH` after the post-`DoAction` sleep.
   - A first design mapped the Notice early without focus and stole focus 250-650 ms later. That fails on the champion: mapping changes `stacking_top`, the guard restores that change, and it returns before the later steal.
   - That late-steal case is outside what the champion handles. It is not a control here.
5. **`canary_disabled`.** The champion leaves insensitive controls out of `get_window_state` entirely, so a control that starts disabled is just another `absent`. The canary therefore disables the target after the observation. The Driver gets a fresh token for a now-impossible action: it sends one `DoAction`, which has no effect, and reports `effect: unverifiable`.
6. **Driver environment.** It is jev-use `driver_environment()`, with HOME and TMPDIR moved to a fresh per-trial home. R2-04 used one session HOME per session. As a result, every trial is a first run for the Driver's installation, telemetry and version-check files; they are visible in the champion reference. Telemetry stays at its default in every arm.
7. **Bus monitor.** It is on in validation, to count `DoAction` per trial. For timed blocks pass `--no-bus-monitor` (R2-04 measured at most 1.8% perturbation on action calls), or keep it identical across arms.
8. **Validation ran without the quiet-lane lock** (correctness only; no timing claim), at nice 10. Host loadavg came from other agents and is recorded per trial.

## Limits

- One machine and one private Xvfb/openbox session type. GTK 3.24 through system PyGObject.
- The champion Driver forks `pacman` during startup (installation detection), and it does a network version check and sends default telemetry. These are in the champion reference set. A candidate that stops doing them shows *fewer* signature entries, which G2 allows.
- The process/socket inventory covers the private session's process tree. A daemon that double-forks out of the session tree would escape it. The sandbox makes the Driver's filesystem effects visible only under the trial home, the session runtime dir and `/dev/shm`.
- N-01 (native causal A/B on the same waits) had no packet at the time of writing (`<lanes>/artifacts/r2/n-01` was empty, and its worktree was still at the R2-04 instrumentation commit). Nothing here duplicates it.

## Validation on the champion (correctness only, 2026-10-02)

- **Driver.** `229b65b2849c3a595ddbc85200d7181b18bd2e47`, the unmodified `cua-driver 0.32.0` binary from the R2 setup (sha256 `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3`).
- **Sessions.** Two private sessions under `hostless`, 10 trials per cell, interleaved round-robin, a fresh seed per trial. The fixture sha256 set recorded by each run matches `MANIFEST.sha256`.
- **No timing claim.** `T_ms` is only checked for presence and stamp order.

| Cell | Passed | Champion facts |
|---|---|---|
| `gtk3_checkbox:reference` | 10/10 | `route: accessibility`, 1 `DoAction`, 1 journal record, fresh observation agrees 10/10 |
| `gtk3_checkbox:negative_stale_token` | 10/10 | refused `stale_element_token`, 0 `DoAction`, journal empty |
| `gtk3_checkbox:negative_no_action` | 10/10 | 0 `DoAction`, journal empty |
| `gtk3_checkbox:canary_absent` | 10/10 | caller `unknown` (target not found), journal empty |
| `gtk3_checkbox:canary_disabled` | 10/10 | 1 `DoAction` on the now-insensitive target, `effect: unverifiable`, caller `unknown`, journal empty |
| `gtk3_checkbox:delayed_effect` | 10/10 | delay 273-500 ms; the tool returned before the effect in 9/10; done always after the effect; 1 `DoAction`, 1 record |
| `gtk3_checkbox:focus_steal` | 10/10 | steal observed 10/10; focus back with the user's window 10/10; 1 record |
| `gtk3_text:text_save` | 10/10 | `set_value` then Save, `route: accessibility`, 2 `DoAction` (activate commit + Save), 1 record, fresh value agrees 10/10 |
| `browser_selfcheck:xdotool_trusted` | 10/10 | trusted pointerdown..click on Submit, then submit, 1 POST: verified |
| `browser_selfcheck:js_untrusted` | 10/10 | `isTrusted:false` click, 1 POST: correctly **not** verified |
| `browser:fill_submit` | 0/10, **BLOCKED** | `browser_prepare` refused `browser_route_unavailable` in 10/10 under `hostless` (Deviation 1) |

`validation-summary.json` has the per-cell counts and failure reasons. `champion_reference.json` has the G2 reference signatures.
