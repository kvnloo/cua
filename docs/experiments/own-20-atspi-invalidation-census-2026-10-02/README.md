# OWN-20: AT-SPI invalidation-signal fidelity census (GTK3, private AT-SPI bus)

Owner: kvnloo/cua#20. Input to R2-09 (kvnloo/cua#93, event-fidelity input). kvnloo/cua#107 is only a consumer of this census and was not touched.
Branch `exp/own-20-atspi-invalidation-census-20261002`. Provider: none (TypeSafe cap 0; 0 attempts, 0 reached).

## Disposition

**#20: KEEP.** The census is complete:
- All 24 pre-registered rows ran, with at least 20 reps each: 526 of 526 forced mutations in 54 blocks, 0 failures, every rep kept.
- Each scope has a terminal classification below.
- Recommendation: **always observe in every scope.** No scope may treat event absence as authority to reuse known state.

Main findings:

- **`child_add` is a NOISY_HINT and fails as an invalidator.** Adding a child control produced no `children-changed:add` event in 40 of 40 reps, in both GTK3 add orders (pack-then-show and show-then-pack). The only events were ancestor `BoundsChanged` layout events, 6 per rep. They woke a listener in 40/40 reps but did not name the change. Event absence therefore cannot authorize reuse of tree structure. Every get_window_state element list *is* tree structure, so a whole-snapshot cache cannot be invalidated by events on this toolkit.
- **Label similarity is not identity.** For a node destroyed and recreated with the same accessible name, the fresh observation was identical at the label level in 20 of 20 reps (role, label and frame unchanged; element tokens are snapshot-scoped anyway). The fixture's own generation counter showed the identity change.
  - The removal was signalled in 20/20 reps, by `StateChanged:defunct=1` on the old node. `ChildrenChanged:remove` arrived only in 2/20: the first recreate of each block, when the construction-time node was still cached by its container.
  - The new node was named by no event in 0/20 reps.
- **Every other scope met the pre-registered SAFE_INVALIDATOR criterion**:
  - scopes: text, focus, selection, checkbox, child_remove, node_recreate (removal side), window, process lifecycle, the pipeline after an app restart, after a registry restart, and for a freshly registered listener;
  - the criterion: a scope-typed event was present in every relevant delta of every own row and every inherited destroy/recreate and restart row.

  This is a **finite zero** (20 to 84 delta reps per scope) on one fixture, binary and session type, not a universal guarantee. It authorizes nothing: no observation-skipping policy is proposed for any scope (product invariant).
- **Focus is not observable** through get_window_state on Linux, which has no focus field. The focus delta is decided by the fixture's state file alone.
- **Controls discriminate.**
  - noop: 0/20 reps with any event.
  - decoy: an unfiltered consumer would have woken on 20/20 reps (88 foreign events); filtering by source bus name took that to 0/20.
  - registry restart with no semantic change: lifecycle signals plus 20 registry events, 0 target events.
  - default-off smoke: the fixture change is inert without its env.

| | |
|---|---|
| forced path | Variant 1: the fixture mutates itself through its env-gated control channel (the Driver is not the producer). Variant 2: the Driver acts (`set_value`; `click` background on the check box and on Exit, AT-SPI route; `click` foreground on a list row; `press_key` Tab foreground). Harness-produced: SIGTERM exit, respawn, registry kill + relaunch. A decoy fixture mutates itself (decoy row). |
| actual producer | per rep in `summaries/own-20-rows.jsonl.gz` (`producer`); Driver variant results: set_value `route=accessibility, effect=confirmed`; check box and Exit clicks `route=accessibility, effect=unverifiable`; list-row click and Tab `route=global_input, effect=unverifiable` |
| oracle | the fresh CUA observation (get_window_state; list_windows for window/process rows) before and after every mutation, plus the fixture's own atomically written state file (cross-check; the only oracle for focus and node identity) |
| candidate invalidator | an independent listener (`atspi_listener.py`, Gio only) on the private AT-SPI bus. It is started, subscribed and registered with the registry before the fixture and before every mutation, and retained per block. A fresh listener per rep is used in `listener_cycle`. |
| negative / fallback controls | noop, decoy (foreign app), registry restart without semantic change, default-off smoke (D1), Chromium gate (G1) |
| tested source | `bc2b47753` (fixture `2d97f0bd3` + harness + PREREG) on upstream main `352507b6c`; AMENDMENT-1 `0aadf3bf2` changes lock mode, timing filter and verifier only |
| Driver | `r2-main-229b65b28`, sha256 `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3`, `cua-driver 0.32.0` read inside all 54 sessions; libs/cua-driver tree of `229b65b28` equals `352507b6c`; no Driver change |
| environment | hostless (v1 for b01-b03, v2 from b04: see Deviations) + one private Xvfb / D-Bus / AT-SPI bus+registry session per block; GTK 3.24.52, at-spi2-core 2.60.6, PyGObject 3.56.3 |
| heads | tested upstream main `352507b6c`; live upstream main at analysis `091c6ee07` (1 commit later, 0 files under libs/cua-driver); no PR under test; publication SHA = the branch head the Publish agent pushes (not published by this lane) |

## Question and method

Question (#20): for each GTK3 semantic scope, does an AT-SPI event conservatively signal every relevant semantic change, with no false negatives? If so, event presence could invalidate known state. If not, is the event only a wake hint, or unusable? The fresh observation is the ground truth. Events are candidate invalidators only.

The loop for each mutation (`census.py`; one block = one isolated session, at most 10 measured mutations):
1. Take a fresh `get_window_state` through the Driver, plus `list_windows` for window and process rows, and read the fixture's state file.
2. Wait a 100 ms guard.
3. Force ONE known mutation.
4. Collect listener events until mutation end + 1000 ms. This bounded window was pre-registered. Events caused by either observation's tree walk fall outside it.
5. Take a fresh observation and read the state file again.

**Invalidator levels.** **L2** = a scope-typed event from the target's bus name that names the change type, for example `StateChanged:checked`, `TextChanged`, `SelectionChanged`, or `defunct=1`. For process rows it is the registry's root `ChildrenChanged` naming the target bus name, or `NameOwnerChanged`. **L1** = any AT-SPI event from the target. Sender identity is the bus unique name resolved to a pid, never a label.

**Relevant delta.** A relevant delta is an observation delta of the row's selected fields OR an oracle delta. Both are recorded, together with whether they agree. FN = a delta with no L2 event (FN_L1: no target event at all). FP = no delta but events; false positives are a performance cost only.

**Classification (PREREG, unchanged).** Own and inherited rows are listed in PREREG.json. The inherited rows for in-app scopes are recreate, both exits, process start, the post-restart probe and the post-registry-restart probe.
- SAFE_INVALIDATOR: fn_L2 = 0 in own and inherited rows, with at least 20 delta reps per row.
- NOISY_HINT: otherwise, if fn_L1/n < 0.25.
- UNUSABLE_ALWAYS_OBSERVE: otherwise.

Timeline and evidence order:
1. PREREG.json was committed at `bc2b47753` (05:00:06Z), before the first counted mutation (b01 start 05:00:17Z).
2. Three blocks ran under quiet-timed.
3. AMENDMENT-1 was committed at `0aadf3bf2` (05:53:35Z), before every block it governs (see Deviations).
4. Count-only blocks b19-b54 ran under `flock -s`, then timing blocks b04-b18 under quiet-timed.

## Results

Evidence classes: REAL = the real Driver and a real GTK3 app on a private Xvfb + AT-SPI bus. BENCHMARK = timed in an EXCLUSIVE quiet-lane block. N of M counts every attempted rep.

<!-- GENERATED:BEGIN (render_tables.py summaries/own-20-summary.json) -->
### Classification (pre-registered rule)

| scope | verdict | own delta reps | own FN_L2 | own FN_L1 | inherited FN_L2 (rows) | event absence authorizes reuse | recommendation |
|---|---|---|---|---|---|---|---|
| `text` | SAFE_INVALIDATOR | 40 | 0 | 0 | 0 (exit_v1 0/21, exit_v2 0/21, post_registry_probe 0/20, post_restart_probe 0/42, process_start 0/42, recreate 0/20) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |
| `focus` | SAFE_INVALIDATOR | 40 | 0 | 0 | 0 (exit_v1 0/21, exit_v2 0/21, post_registry_probe 0/20, post_restart_probe 0/42, process_start 0/42, recreate 0/20) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |
| `selection` | SAFE_INVALIDATOR | 40 | 0 | 0 | 0 (exit_v1 0/21, exit_v2 0/21, post_registry_probe 0/20, post_restart_probe 0/42, process_start 0/42, recreate 0/20) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |
| `checkbox` | SAFE_INVALIDATOR | 40 | 0 | 0 | 0 (exit_v1 0/21, exit_v2 0/21, post_registry_probe 0/20, post_restart_probe 0/42, process_start 0/42, recreate 0/20) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |
| `child_add` | NOISY_HINT | 40 | 40 | 0 | 0 (exit_v1 0/21, exit_v2 0/21, post_registry_probe 0/20, post_restart_probe 0/42, process_start 0/42, recreate 0/20) | no | always observe (a relevant false negative exists) |
| `child_remove` | SAFE_INVALIDATOR | 40 | 0 | 0 | 0 (exit_v1 0/21, exit_v2 0/21, post_registry_probe 0/20, post_restart_probe 0/42, process_start 0/42, recreate 0/20) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |
| `node_recreate` | SAFE_INVALIDATOR | 20 | 0 | 0 | 0 (exit_v1 0/21, exit_v2 0/21, post_registry_probe 0/20, post_restart_probe 0/42, process_start 0/42) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |
| `window` | SAFE_INVALIDATOR | 40 | 0 | 0 | 0 (exit_v1 0/21, exit_v2 0/21, post_registry_probe 0/20, post_restart_probe 0/42, process_start 0/42, recreate 0/20) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |
| `process_lifecycle` | SAFE_INVALIDATOR | 84 | 0 | 0 | 0 (none) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |
| `restart_pipeline` | SAFE_INVALIDATOR | 42 | 0 | 0 | 0 (none) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |
| `registry_restart` | SAFE_INVALIDATOR | 20 | 0 | 0 | 0 (none) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |
| `listener_subscription` | SAFE_INVALIDATOR | 20 | 0 | 0 | 0 (none) | no | always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope) |

### Per-row census (all blocks; N of M = reps with the property of reps attempted)

| row | scope | variant | attempted | failures | relevant delta | L2 present | L1 present | FN_L2 | FN_L1 | FP (target) | FP (any AT-SPI) | obs/oracle disagree | L2 types seen | evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `text_v1` | text | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:TextChanged:delete, Object:TextChanged:insert | REAL |
| `text_v2` | text | v2_driver | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:TextChanged:delete, Object:TextChanged:insert | REAL |
| `focus_v1` | focus | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:StateChanged:focused | REAL |
| `focus_v2` | focus | v2_driver | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:StateChanged:focused | REAL |
| `selection_v1` | selection | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:SelectionChanged: | REAL |
| `selection_v2` | selection | v2_driver | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:ActiveDescendantChanged:, Object:SelectionChanged: | REAL |
| `checkbox_v1` | checkbox | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:StateChanged:checked | REAL |
| `checkbox_v2` | checkbox | v2_driver | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:StateChanged:checked | REAL |
| `child_add_pts` | child_add | v1_fixture | 20 | 0 | 20/20 | 0/20 | 20/20 | 20 | 0 | 0/0 | 0/0 | 0 | none | REAL |
| `child_add_stp` | child_add | v1_fixture | 20 | 0 | 20/20 | 0/20 | 20/20 | 20 | 0 | 0/0 | 0/0 | 0 | none | REAL |
| `child_remove_pts` | child_remove | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:StateChanged:defunct | REAL |
| `child_remove_stp` | child_remove | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:StateChanged:defunct | REAL |
| `recreate` | node_recreate | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 20 | Object:ChildrenChanged:remove, Object:StateChanged:defunct | REAL |
| `window_create` | window | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:ChildrenChanged:add, Window:Create: | REAL |
| `window_destroy` | window | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:ChildrenChanged:remove, Window:Destroy: | REAL |
| `exit_v1` | process_lifecycle | v1_harness_sigterm | 21 | 0 | 21/21 | 21/21 | 21/21 | 0 | 0 | 0/0 | 0/0 | 0 | DBus:NameOwnerChanged:, Object:ChildrenChanged:remove | REAL |
| `exit_v2` | process_lifecycle | v2_driver | 21 | 0 | 21/21 | 21/21 | 21/21 | 0 | 0 | 0/0 | 0/0 | 0 | DBus:NameOwnerChanged:, Object:ChildrenChanged:remove | REAL |
| `process_start` | process_lifecycle | harness_spawn | 42 | 0 | 42/42 | 42/42 | 42/42 | 0 | 0 | 0/0 | 0/0 | 0 | DBus:NameOwnerChanged:, Object:ChildrenChanged:add | REAL |
| `post_restart_probe` | restart_pipeline | v1_fixture | 42 | 0 | 42/42 | 42/42 | 42/42 | 0 | 0 | 0/0 | 0/0 | 0 | Object:StateChanged:checked | REAL |
| `registry_restart` | registry_restart | harness_registry | 20 | 0 | 0/20 | 0/0 | 0/0 | 0 | 0 | 0/20 | 20/20 | 0 | none | REAL |
| `post_registry_probe` | registry_restart | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:StateChanged:checked | REAL |
| `noop` | control_noop | v1_fixture | 20 | 0 | 0/20 | 0/0 | 0/0 | 0 | 0 | 0/20 | 0/20 | 0 | none | REAL |
| `decoy` | control_decoy | decoy_fixture | 20 | 0 | 0/20 | 0/0 | 0/0 | 0 | 0 | 0/20 | 20/20 | 0 | none | REAL |
| `listener_cycle` | listener_subscription | v1_fixture | 20 | 0 | 20/20 | 20/20 | 20/20 | 0 | 0 | 0/0 | 0/0 | 0 | Object:StateChanged:checked | REAL |

### Timings (timing blocks only, AMENDMENT-1; ms, median / nearest-rank p95)

| row | first L2 event after mutation start | first L1 event | last target event in window | first L2 after Driver tool return | fixture op | Driver call | evidence |
|---|---|---|---|---|---|---|---|
| `text_v1` | 0.226 / 0.361 (n=10) | 0.226 / 0.361 (n=10) | 0.802 / 0.913 (n=10) | n/a | 0.460 / 0.485 (n=10) | n/a | REAL+BENCHMARK |
| `text_v2` | 9.051 / 19.406 (n=10) | 9.051 / 19.406 (n=10) | 9.667 / 20.154 (n=10) | -8.041 / -7.453 (n=10) | n/a | 17.483 / 27.730 (n=10) | REAL+BENCHMARK |
| `focus_v1` | 0.512 / 1.007 (n=10) | 0.512 / 1.007 (n=10) | 203.180 / 224.968 (n=10) | n/a | 0.514 / 1.100 (n=10) | n/a | REAL+BENCHMARK |
| `focus_v2` | 18.763 / 28.819 (n=10) | 18.763 / 28.819 (n=10) | 42.904 / 222.189 (n=10) | -841.028 / -836.790 (n=10) | n/a | 860.719 / 886.170 (n=10) | REAL+BENCHMARK |
| `selection_v1` | 0.298 / 0.341 (n=10) | 0.298 / 0.341 (n=10) | 159.809 / 168.010 (n=10) | n/a | 0.592 / 0.703 (n=10) | n/a | REAL+BENCHMARK |
| `selection_v2` | 1109.959 / 1162.395 (n=10) | 1090.793 / 1142.028 (n=10) | 1288.769 / 1340.302 (n=10) | -824.042 / -822.383 (n=10) | n/a | 1935.976 / 1990.158 (n=10) | REAL+BENCHMARK |
| `checkbox_v1` | 0.758 / 1.045 (n=10) | 0.758 / 1.045 (n=10) | 1.408 / 102.287 (n=10) | n/a | 0.593 / 0.788 (n=10) | n/a | REAL+BENCHMARK |
| `checkbox_v2` | 16.907 / 22.859 (n=10) | 16.907 / 22.859 (n=10) | 18.495 / 112.185 (n=10) | -301.471 / -298.218 (n=10) | n/a | 319.871 / 327.022 (n=10) | REAL+BENCHMARK |
| `child_add_pts` | n/a | 1.212 / 3.045 (n=5) | 1.720 / 4.657 (n=5) | n/a | 0.666 / 2.269 (n=5) | n/a | REAL+BENCHMARK |
| `child_add_stp` | n/a | 1.310 / 2.813 (n=5) | 1.967 / 3.597 (n=5) | n/a | 0.685 / 1.723 (n=5) | n/a | REAL+BENCHMARK |
| `child_remove_pts` | 0.454 / 0.721 (n=5) | 0.281 / 0.533 (n=5) | 1.401 / 1.906 (n=5) | n/a | 0.636 / 1.045 (n=5) | n/a | REAL+BENCHMARK |
| `child_remove_stp` | 0.452 / 2.424 (n=5) | 0.322 / 0.837 (n=5) | 1.866 / 4.344 (n=5) | n/a | 0.883 / 1.990 (n=5) | n/a | REAL+BENCHMARK |
| `recreate` | 0.481 / 0.881 (n=10) | 0.297 / 0.535 (n=10) | 1.736 / 2.763 (n=10) | n/a | 0.966 / 1.873 (n=10) | n/a | REAL+BENCHMARK |
| `window_create` | 1.286 / 1.558 (n=5) | 0.989 / 1.197 (n=5) | 4.107 / 4.843 (n=5) | n/a | 1.230 / 1.626 (n=5) | n/a | REAL+BENCHMARK |
| `window_destroy` | 0.586 / 0.622 (n=5) | 0.291 / 0.332 (n=5) | 2.479 / 3.752 (n=5) | n/a | 0.843 / 1.029 (n=5) | n/a | REAL+BENCHMARK |
| `exit_v1` | 4.489 / 8.806 (n=3) | 4.489 / 8.806 (n=3) | n/a | n/a | n/a | n/a | REAL+BENCHMARK |
| `exit_v2` | 36.652 / 39.861 (n=3) | 36.652 / 39.861 (n=3) | n/a | -33.030 / -24.801 (n=3) | n/a | 69.682 / 71.843 (n=3) | REAL+BENCHMARK |
| `process_start` | 146.197 / 192.061 (n=6) | 146.197 / 192.061 (n=6) | 208.923 / 267.074 (n=6) | n/a | n/a | n/a | REAL+BENCHMARK |
| `post_restart_probe` | 1.008 / 1.419 (n=6) | 1.008 / 1.419 (n=6) | 78.875 / 125.632 (n=6) | n/a | 0.827 / 1.159 (n=6) | n/a | REAL+BENCHMARK |
| `registry_restart` | n/a | n/a | n/a | n/a | n/a | n/a | REAL+BENCHMARK |
| `post_registry_probe` | 1.147 / 1.736 (n=5) | 1.147 / 1.736 (n=5) | 2.399 / 86.069 (n=5) | n/a | 0.950 / 1.366 (n=5) | n/a | REAL+BENCHMARK |
| `noop` | n/a | n/a | n/a | n/a | 0.008 / 0.035 (n=10) | n/a | REAL+BENCHMARK |
| `decoy` | n/a | n/a | n/a | n/a | 0.692 / 1.058 (n=10) | n/a | REAL+BENCHMARK |
| `listener_cycle` | 2.817 / 4.114 (n=10) | 2.817 / 4.114 (n=10) | 3.572 / 152.906 (n=10) | n/a | 0.961 / 1.321 (n=10) | n/a | REAL+BENCHMARK |

### Listener subscription and cleanup cost (timing blocks only; ms, median / p95)

| listener | subscription (address + connect + subscribe + RegisterEvent x4) | spawn to ready (process start included) | cleanup (DeregisterEvent x4 + unsubscribe + close) | SIGTERM to exit | evidence |
|---|---|---|---|---|---|
| retained, one per block | 3.879 / 9.980 (n=18) | 112.076 / 181.458 (n=18) | 1.234 / 7.555 (n=18) | 47.247 / 113.678 (n=18) | REAL+BENCHMARK |
| fresh, one per listener_cycle rep | 6.779 / 12.382 (n=10) | 161.681 / 238.979 (n=10) | 2.042 / 3.038 (n=10) | 63.553 / 113.696 (n=10) | REAL+BENCHMARK |
<!-- GENERATED:END -->

Notes on the tables:
- "first L2 after Driver tool return" is negative when the event arrives before the tool call returns. For example, the foreground click and keypress return after the cursor feedback, about 0.8 s after the effect.
- "last target event in window" shows how long a scope keeps emitting. Focus and selection changes trigger roughly 200 ms trains of `BoundsChanged` animation frames (median spurious target events per rep: selection 60-66, focus_v1 16), all inside the 1000 ms window.
- Process exit is signalled on the bus and by the registry within 4.5 ms of SIGTERM (median, n=3) and 36.7 ms after the Driver's Exit click starts. A new process becomes visible 146 ms (median, n=6) after spawn.
- `listener_cycle`: a listener that became ready immediately before the mutation saw it in 20/20 reps. The retained listener saw it in 20/20 too. The Driver's own `object:` registration was present throughout, so this does not isolate the registry-propagation race for a sole listener.
- `registry_restart`: after the registry was killed and relaunched, the retained listener received the next mutation's event in 20/20 reps, even though its registration was held by the killed registry. This is an observation, not an explained mechanism.

Work deleted vs wall-clock saved: **none of either is claimed.** This census measures signal fidelity only. No observation was skipped and no component was deleted. Its contribution to R2-09 and E2 is the negative result: observation cannot be replaced by event absence in any scope with a false negative (`child_add`, and hence whole-tree snapshots). For the SAFE scopes, any reuse policy would be a new, separately reviewed product decision. That is outside this lane and outside the current invariants.

E4 for this packet:
- 0 reuse decisions were made anywhere: the harness always re-observes.
- No authority came from passive state or event absence.
- 0 stale-token dispatches. Every Driver action used a token from the observation taken immediately before it.
- 0 duplicate mutations: one forced mutation per rep, acknowledged by the fixture or by the Driver's result.
- No blind replays.

## Controls

- **noop:** 0/20 reps with any target or any AT-SPI event; observation and state unchanged in 20/20.
- **decoy:** a second, lane-started fixture process toggled or edited itself; the target was unchanged in 20/20 reps. Unfiltered FP 20/20 (88 foreign events); source-filtered FP 0/20.
- **registry_restart (no semantic change):** observation and state unchanged in 20/20. Each rep produced 5 lifecycle signals (NameOwnerChanged ×4, Available) and one registry `ChildrenChanged:add` re-embedding the app (unfiltered FP 20/20), and 0 target events.
- **D1 default-off smoke** (`raw/controls/D1-default-off`): the base fixture at `352507b6c` and the modified fixture were launched without `CUA_GTK3_CONTROL_FIFO`, in task mode and in the default harness mode. Element digest (relative frames), element count, window size, tree_markdown and state-file keys were identical in both modes.
- **G1 Chromium gate** (`raw/controls/G1-chrome-gate`, `-2`): see Deviations and Limits. Chromium/Electron rows are NOT_RUN.
- **Observation vs oracle:** they disagree only on `recreate` (20/20), by design: the label-level observation is unchanged while the identity changed. Focus is oracle-only (no observation field).

## Deviations

1. **AMENDMENT-1 (lock mode), committed before any block it governs.** Exclusive quiet-lane acquisition was starved by other lanes: block b03 waited about 35 min, and 3 blocks took about 50 min. The changes:
   - Round 0 (b01-b18, one block of every type) stayed under quiet-timed and is the only source of reported timings.
   - b19-b54 became count-only blocks under `flock -s`, with receipts in `raw/lock-ledger.jsonl`.
   - Order: b19-b54 first, then b04-b18.
   - Rows, reps, loop, windows, definitions and the classification rule are unchanged.
   - My own waiting b04 (never acquired: no receipt, no session) was stopped with the batch runner, before the amendment. Only this lane's own processes were stopped.
2. **hostless v1 to v2 mid-run.** The loop infrastructure replaced `bin/hostless` at 05:06:31Z: v1 used a bwrap user namespace; v2 uses an env scrub, a private runtime dir and Landlock. b01-b03 (and the uncounted pilots) ran under v1; b04-b54 and the controls ran under v2. Every block ran hostless (`raw/batch.jsonl`). The text_v1, text_v2 and focus_v1 timings come from v1 blocks; no row compares v1 data against v2 data. The b01 (v1) and b36 (v2) text_v1 counts agree (10/10 L2 each).
3. **Chromium gate: the pre-registered NOT_RUN reason became obsolete.** PREREG expected that hostless v1 would stop the Driver launching Chrome, and in the pilot it did: root ownership was masked to uid 65534 and the launch was refused with `browser_route_unavailable`. Under v2 the Driver launched Chrome 151 (`/opt/google/chrome/chrome`, isolated profile, default safety, no extra flags). The gate is now decided by AT-SPI exposure:
   - G1 attempt 1 (`data:` URL) was refused by `browser_navigate` (http/https/about only).
   - G1 attempt 2 used an `http://127.0.0.1` page. Chrome took a name on the private AT-SPI bus and emitted frame-level events (Activate, `accessible-name`, `StateChanged:active`). `get_window_state` exposed only the browser frame (1 element, "own20 probe - Google Chrome") in 10/10 polls over 10 s; the page's checkbox and text field were never exposed.

   Web content is not exposed through AT-SPI without a renderer-accessibility flag, and adding a flag would change the Driver-chosen launch. So the Chromium/Electron rows are **NOT_RUN** (frame-level AT-SPI only). Attempt 2 ran a working-tree revision of `chrome_atspi_probe.py` (http page; Chrome names resolved while alive) that the packet commit contains.
4. **Load.** Count-only blocks shared the machine with other lanes' builds and tests: 1-min loadavg per mutation 3.95-31.55, median 17.26, recorded on every rep. No relevant false negative coincided with load: the only FN row (`child_add`) is structural, with 0 typed events at any load.

## Limits and claim boundary

- **Claim boundary:**
  - the GTK3 fixture (task window + test-only control channel);
  - X11 Xvfb with a private AT-SPI bus and registry;
  - tested source `bc2b47753` on upstream main `352507b6c`;
  - Driver binary sha256 `8b037961…` (cua-driver 0.32.0).

  Excluded: other toolkits (GTK4, Qt, WebKitGTK), Chromium/Electron web content (NOT_RUN), Wayland, a real desktop seat, and any observation-skipping policy.
- SAFE verdicts are finite zeros over 20-84 delta reps per scope, with type-level L2 matching from the target bus name. Event paths were not tied to the observed element, because the observation exposes no AT-SPI path. A different app, toolkit version or widget mix may behave differently.
- `child_add` woke a listener in 40/40 reps only because adding a button reflowed its ancestors. A child added without a layout change, for example into a fixed-size or scrolled container, may produce no event at all. That case was not measured.
- Driver variants exist only for the value scopes and Exit. Structural mutations are fixture-produced (control channel) by design.
- Process exit timings have n=3 per variant in the timing blocks (counts n=21).
- No mechanism is claimed for why apps keep emitting after a registry restart.

## Files

- `PREREG.json`, `AMENDMENT-1.json`, `schedule.json`, `schedule.py`: pre-registration, amendment, block schedule
- `census.py`, `atspi_listener.py`, `run_in_session.sh`, `run_batch.sh`, `run_controls.sh`, `default_off_smoke.py`, `chrome_atspi_probe.py`: harness and controls
- `analyze.py`, `render_tables.py`, `verify_artifacts.py`: analysis, table rendering, verifier
- `raw/blocks/<block>/`: `mutations.jsonl.gz` (every rep's before/after observation and state, mutation timing and producer), `events.jsonl.gz` (the retained listener's every bus signal with CLOCK_MONOTONIC arrival, sender, path), `fresh-NN.jsonl.gz` (listener_cycle), `session-env.txt` (Driver version + sha256 inside the session, DISPLAY, loadavg)
- `raw/batch.jsonl` (per block rc, timestamps, loadavg, hostless, lock mode), `raw/lock-ledger.jsonl` (18 quiet-timed receipts copied from the live ledger + 36 shared block receipts + 3 control receipts), `raw/controls/`
- `summaries/own-20-summary.json`, `summaries/own-20-rows.jsonl.gz` (per-rep records: SHA-independent ids, mutation id, variant, before/after selected fields and digests, event types and source identities with arrival times, delta, FN/FP flags)
- `provenance.json`

Reproduce: `python3 verify_artifacts.py [--ledger <quiet-lane-ledger.jsonl>]` recomputes everything from `raw/` and exits 0 only if every check passes.
