# FIX-20O: the focus guard stops counting the Driver's own cursor overlay as a popup

Lane FIX-20O, wave 8 of the CUA RFC loop. Owners: kvnloo/cua#20 (the guard rows), kvnloo/cua#73
(invariants), kvnloo/cua#93. Provider: TypeSafe cap 0; **0 attempts, 0 reached**. Upstream items are
written as plain text (trycua/cua PR 4529).

Disposition: @@DISPOSITION@@

## Result in one paragraph

@@RESULT_PARAGRAPH@@

## The fix (F20, `dd7f33b58`)

On upstream main `a9baa8d10`, trycua/cua PR 4529 (`5e13eb777`) keeps the idle X11 agent-cursor
overlay unmapped until it paints. A native click reveals the cursor (`reveal_pointer_action_for`), so
the overlay maps *during* the guarded AT-SPI action. `focus_guard::mapped_popups` counted every
VIEWABLE override-redirect root child, so the guard saw the Driver's own overlay as a newly opened
menu: it set `grab_held_by`, reported "A popup menu is open, so pid N holds a keyboard grab" and,
when the focus had been stolen, returned `focus_outcome=grab_held` without restoring it.

F20 (2 files, +36 lines of product code, +70 lines of tests):

- `overlay.rs`: a process-wide `OWN_X11_WINDOWS` set. `OwnX11Window::register(id)` inserts the id and
  removes it on drop. The overlay thread registers the overlay window right after `create_window`
  (released when the thread returns and its connection closes the window); the startup readback probe
  registers its own short-lived override-redirect window the same way.
- `focus_guard.rs`: `mapped_popups` keeps a root child only when `counts_as_popup(id,
  override_redirect, map_state)` holds, which adds `!crate::overlay::is_own_x11_window(id)`.

Default behaviour is otherwise identical: no env knob, no new service, no state other than the set of
live window ids this process created. The `tools/impl_.rs:983` title rule (`Cua.` on a pid-less window)
was **rejected** on SOURCE grounds: any client can title an override-redirect popup `Cua.*`, and many
toolkits set no `_NET_WM_PID` on popups, so a title rule would hide a real keyboard grab. The POPUP row
measures exactly that with the control binary G0m8T.

## Five mechanism requirements

| Requirement | This packet |
|---|---|
| Forced path | Product route `click` by `element_token` with `delivery_mode: background` through `focus_guard::guarded` (AT-SPI action). R1: the original OWN-20P reply-delay proxy (`xstall_proxy.py`, 2 s X reply hold) plus a focus steal by `stealer.py` keyed on the Driver's `do_action_replied` mark. R1m/DLG: the original OWN-20Q mark-free proxy. PROBE: plain background click, no steal. POPUP: the click opens a real GtkMenu holding the seat grab while a decoy owns the focus. |
| Actual route / producer | Click receipts carry the guard's summary sentence (`focus_outcome=...`, "A popup menu is open"); FRESH-07's probe records `route` and the overlay window (`Cua.AgentCursorOverlay.*`, map state per read). The producer of the false popup is the overlay window mapped by the reveal (PROBE S2 map stamps). |
| Independent target-owned oracle | The GTK3 fixture's own focus log (`focus_in`/`focus_out` per GtkWindow, written by the fixture through `harness/focuslog/sitecustomize.py`), the fixture state file (2 ms sampler) for the action effect, and an independent X observer: the 2 ms focus sampler (input focus + `_NET_ACTIVE_WINDOW`), xtree window-tree reads, X RECORD (OWN-20Q) and a core `XGrabKeyboard` probe (POPUP). A restore counts only when the original analyzer's definition holds **and** the fixture log shows the task window lost and regained the focus. Never the receipt alone. |
| Negative / fallback controls | U0m8F silent-miss positive control (R1), GA8F same-app misclassification positive control (DLG), the unfixed G0m8 / GQ8 / M8 arms, the ablation G0m8A, `replyonly` / `mfonly` / no-steal controls (no false restore), the dialog control, and the real-popup control (F20 must keep reporting a real grab) with the rejected title rule G0m8T as its discriminating negative. |
| Exact provenance | provenance.json: every source SHA separately (upstream main, F20, each chain commit, the revert), patch-ids of every replayed commit vs its original (all equal), binary sha256 + version per build, PREREG commit, live heads at start and end, environment, lock receipts. |

## Provenance

@@PROVENANCE@@

## Method

### SOURCE map (raw/source/source-map-a9baa8d10.txt; line numbers on `a9baa8d10`)

- **Overlay creation / map / unmap** (`platform-linux/src/overlay.rs`): `run_on_thread` spawns the
  `cua-overlay-x11` thread (`:751`, `:792`); `run_overlay_thread` (`:1130`) creates the full-root
  override-redirect window (`:1254`, `:1258`), titles it `Cua.AgentCursorOverlay.<id>` (`:1276`) and
  keeps it unmapped at idle (`:1293-1294`); the startup readback probe creates, maps and destroys its
  own override-redirect strip (`:2457`, `:2487`, `:2502`, `:2525`, `:2571`); `paint_x11_tiles` maps on
  the first visible frame and unmaps on an empty one (`:2647`, `:2776`, `:2778`);
  `blank_x11_overlay_shape` unmaps (`:2608`, `:2616`).
- **The census and its diff** (`platform-linux/src/input/focus_guard.rs`): `mapped_popups` (`:191`,
  filter `:204`); `capture` stores the before-set (`:494`, `:506`); `restore_if_changed_opts` takes the
  after-set and the difference (`:622-623`), sets `grab_held_by` from the new windows' pid or the
  target pid (`:627-630`) and returns without restoring when it is set (`:685`); the outcome
  `grab_held` (`:381`) and the sentence "A popup menu is open" (`:484`).
- **Reveal ordering** (`platform-linux/src/tools/impl_.rs`): `overlay_glide_to_for` (`:5290`) re-enables
  the cursor (`:5295`) and, with no known start position, sends a ClickPulse without awaiting the paint
  (`:5305-5308`); `reveal_pointer_action_for` (`:5318`) glides (`:5331`) then pulses (`:5332-5336`); the
  element click reveals (`:6380`) before the guarded AT-SPI action (`:6454`). So the map lands after
  the guard's snapshot. The title rule this fix rejects is at `:983`.
- **Same class, not changed here:** `input/mod.rs:1820` (`mapped_popups`, xlib) feeds `new_popups`
  (`:2233`, `:2530`) of the MPX pointer route's effect check, and `input/foreground.rs:205` lists popups
  for the foreground window set. They are not exercised by these rows (AT-SPI route) and stay a
  follow-up.

### UNIT red / green (UNIT)

@@UNIT@@

### Builds

Target dir family `cua-release-fresh07`, each build `flock cargo-build.lock build-driver.sh` under
hostless inside a quiet-lane SHARED hold (lock order quiet SHARED, then cargo). Versions were read
inside the private session. Every replayed commit's patch-id equals its original
(raw/build/patch-ids.tsv). The revert of `5e13eb777` for the ablation is clean (no conflict;
`overlay.rs` after the revert is byte-identical to `5e13eb777^`).

### Rows

PREREG.json (`1fc04763e`, 21:56:13Z) was committed before the first REAL trial (22:56Z? see
verify_artifacts check 5). All rows ran under hostless + hostless-strict in `cua-x11-session.sh` with a
private AT-SPI bus, one fresh Driver and one fresh fixture per trial, AB/BA order inside each block as
in the original plans. harness/passes.json maps each original role to a binary per pass:

| Pass | Plan / blocks | U slot | G slot | Rows |
|---|---|---|---|---|
| P1 | own-20p q1-q8, qc1, qc2 | G0m8 | G0m8F | R1, R1 control |
| P2 | own-20p q1-q8 | U0m8F | G0m8A | R1 positive control, ablation |
| P3 | own-20p n1-n8 | M8 | G08F | NORMAL |
| Q1 | own-20q q1-q4, qt1-qt4, qc1, qct1 | M8 | G08F | R1m and its control |
| Q2 | own-20q d1-d4, dd1, dd2, n1, n2, nt1, nt2 | GA8F | GQ8F | DLG, dialog control, normal path |
| Q3 | own-20q d1-d4 | GQ8 | GQ8F | DLG on the unfixed port |
| X | probe x1-x4 (5 reps x 2 binaries each) | M8 | M8F | PROBE, overlay integrity |
| C | popup p1-p4, t1 | G0m8T / M8 | G0m8F / M8F | POPUP, tools/list integrity |

The analyzer re-keys every trial by the `driver_sha256` it recorded, never by the role name, and
imports the original analyzers' per-trial metric functions unchanged.

## Results

@@RESULTS@@

## E4

@@E4@@

## Work deleted vs wall-clock saved

This lane deletes no work and claims no saving: it is a correctness fix. The guard's restore path
costs what it cost on the old line (`0f1955d2f`), where the overlay never changed map state mid-action.
Wall times are descriptive only (non-timing SHARED rows).

## Lock evidence

@@LOCKS@@

## Deviations

@@DEVIATIONS@@

## Near misses and hard rules

@@NEARMISS@@

## Limits and claim boundary

Linux X11 only (private Xvfb + openbox + picom) with the canonical GTK3 fixture and the original
OWN-20P / OWN-20Q forced paths. The Wayland / Hyprland guard rows stay **BLOCKED** (real seat). The
pointer-route census in `input/mod.rs` is the same class and is not covered. A fork fix candidate
only: nothing is posted upstream; upstream items appear as plain text. Binaries are the exact sha256s
in provenance.json; the publication SHA is set by Publish.

## Reproduce

```
python3 verify_artifacts.py      # every check, including analyze.py --check
python3 analyze.py               # rewrites fix20o-summary.json and fix20o-trial-metrics.jsonl.gz
```
