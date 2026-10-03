# i107 pin and map: live state mirror vs scoped reads vs checked execution (2026-10-02)

kvnloo/cua#107, execution-sequence step 1 ("Pin and map"). This file is SOURCE evidence plus reuse of already-published phase traces. It contains no new timing. The pre-registration for every later lane is `PREREG.json` in this directory.

Path placeholders: `<lanes>` is the lanes root. Upstream items are written as plain text.

## 1. Pins (each identity kept separate)

| Item | Value | How it was read |
|---|---|---|
| Upstream main | `352507b6c03162ab286b21d5ed509125cc3daece` (2026-10-01T20:40:18-07:00, "fix: post-launch CI follow-ups (#4405)") | `git fetch upstream main` + `git rev-parse upstream/main`; `gh api repos/trycua/cua/commits/main` agrees |
| `libs/cua-driver` tree at main | `892fdddb07de3f12deb09c78619e043549ee06cd`, identical to `229b65b28` (the R2 base). 0 files under `libs/cua-driver` changed in the 11 commits since | `git rev-parse <sha>:libs/cua-driver` |
| Caller (A, B, C) | jev-use `libs/cua-driver/examples/jev-use/python/run.py`, tree `635a4f588c6817ccb6cb6f5b7baacddbfc42f786` at main (equal to its tree at `345ff6d9`) | git |
| Guarded-continuation source (D) | trycua/cua PR 4316, head `a0bca744067d04f05904319d3d919be30c336556`, **OPEN, not merged** (`mergedAt` null, not draft, `updatedAt` 2026-10-01T17:03:24Z), base `345ff6d9`, 40 commits behind main. Its only commit touches the jev-use caller and `.github/workflows/ci-jev-use.yml`; no Driver code | `gh pr view 4316 -R trycua/cua` (read-only); `git diff --stat 345ff6d9 a0bca7440` |
| PR 4316 on main | `git merge-tree` of main and `a0bca7440` is conflict-free (tree `23bb7e9c`); the merged jev-use tree is `72bf8156136771da9a767ec12ae7c364e426d910`, byte-identical to the jev-use tree at `a0bca7440` | git |
| i107 tested source | branch `exp/i107-map-20261002`: `352507b6c` + `--no-ff` merge of `a0bca7440` (`2251da142`) + cherry-picks of the R2-01 phase trace (`7d3a28b66` as `fe424500d`) and the B-01 marks/knob (`f5c991e59` as `a5e344291`) + the i107 producer-RPC ledger (`092b065d5`). The first three give a `libs/cua-driver` tree (`5bdb3b61`) identical to B-01's tested source `f5c991e59`, so B-01's traces are valid on this source. All instrumentation is env-gated (`CUA_DRIVER_PHASE_TRACE_FILE`) and default-off; the focus-settle knob `CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS` stays unset in every i107 arm | git |
| Driver binary for every i107 arm | `cua-driver-i107-092b065d5`, sha256 `f3a5c01a2c1b5bce75ccb611d0bacd491a7c3b1a8c3fac65889a1fc9d6977aed`, `cua-driver 0.32.0` (read inside the private session); build receipt in `provenance.json`. Built from `092b065d5` with `build-driver.sh` under `hostless` and the cargo-build lock. Uninstrumented reference (default-off distortion check only): `cua-driver-r2-main-229b65b28`, sha256 `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3`, `libs/cua-driver` tree identical to main | `sha256sum` |
| Provider | mock chooser `choose_mock_for_task` (jev-use `python/jev_adapter.py`). No live TypeSafe request in this track; live-provider cells are BLOCKED pending owner budget | — |
| Browser | Driver-selected Google Chrome 151.0.7922.71, `isolated_new` profile, sandbox on (from R2 SETUP; re-record per lane) | — |
| Fixture | jev-use `fixture_server.py` (`FixtureFormTask`, `/state` oracle) at the tested source, plus an experiment-local churn/control variant each lane commits under its packet (section 7) | — |
| Receipt destination | fork branches `exp/i107-<lane>-20261002`, packets `docs/experiments/i107-<lane>-2026-10-02/`, publication SHA set by the Synthesize publisher | — |

## 2. Where the caller observes (arm A)

`run.py` (main, unchanged by PR 4316 except the flag-gated guard):

1. `browser_prepare {allow_launch, profile isolated_new}` → `wait_for_window` (`list_windows` every 0.25 s, up to 40 times; `run.py:326`) → bind `get_browser_state {pid, window_id}` → `browser_navigate`.
2. Per step (`run.py:404`): an oracle read (`task.read_oracle()` = fixture `GET /state`), then **one full `get_browser_state {target_id, tab_id, snapshot_format:"semantic_v2"}`** (`run.py:412-419`), then `task_candidates_for_step` (visual parse skipped when a page-structure candidate exists, `--visual-observation auto`), the chooser (`choose_mock_for_task`, `run.py:444`), `validate_choice`, and the action (`browser_type` with `replace:true` on step 1, `browser_click input_route:"dom_event"` on step 2).
3. After a completion candidate, up to 20 oracle reads with `asyncio.sleep(0.1)` between them (`run.py:571`).

Each action uses the ref minted by that step's fresh snapshot. The caller never reuses a ref across snapshots. Per fill→submit task: 2 decision snapshots (+1 bind read), 2 decisions, 2 mutations.

PR 4316's guard (`guarded_completion.py`): after a provider-chosen `type-verification-value`, `plan_guarded_completion` binds the session, the completion candidate id and the logical target (role `button`, name `Submit`) plus the prior ref (only so it can refuse reuse). On the next step it re-proves, **from that step's fresh semantic snapshot**, `verification_field == contains_required_token`, exactly one matching Submit ref, a fresh ref different from the prior one, and exactly one executable candidate bound to that fresh ref; otherwise it declines with a stable reason and the chooser runs. It retains role+name+uniqueness only: not the Submit's form/ancestor scope, visibility or enabled state (relevant to the dependency controls in section 8).

## 3. Driver seams on the observation path

All in `libs/cua-driver/rust/crates/cua-driver-core/src/` (line numbers at pinned main `352507b6c`).

| Seam | Location | What it does |
|---|---|---|
| Tool entry | `browser/tools.rs:261` `GetBrowserStateTool`; schema `snapshot_format`, `scope_ref`, `query`, `continuation`, `include_screenshot` | Snapshot mode requires an explicit session, `target_id` and `tab_id`. `scope_ref`/`query`/`continuation` are accepted only with `semantic_v2` (`tools.rs:396`) |
| Snapshot | `browser/engine.rs:2501` `snapshot_tab_semantic` | (a) `scope_ref` → `BrowserStore::resolve_ref` (current snapshot + generation, else `browser_ref_stale`); (b) `attach` = `Target.attachToTarget {flatten}` **on every call, never detached** (BUG-01 part B: sessions accumulate); (c) `semantic_document` = `DOM.getDocument {depth:-1, pierce:true}`, with bounded-depth fallback + `DOM.describeNode` hydration on size/timeout errors (`engine.rs:2339`); (d) `local_frame_tree` = `Page.getFrameTree`; (e) `collect_semantic_session` (`engine.rs:2258`) = `DOMSnapshot.captureSnapshot {computedStyles, includePaintOrder, includeDOMRects}` ∥ `Page.getLayoutMetrics`, then `Accessibility.getFullAXTree` per local frame; (f) OOPIF: `Target.setAutoAttach` + `attachedToTarget` events + per-child repeat of (c)-(e) + `Target.detachFromTarget`; (g) `SemanticDocument::page(offset, 300, query, scope)`; (h) mint snapshot id, then `stored_tab.snapshots.clear()` and insert the new `SnapshotRecord` (`engine.rs:2775`), so every earlier ref of the tab becomes stale |
| Projection | `browser/semantic.rs:196` `page`, `:999` `scoped_indices`, `:575` `apply_page_occlusion` | Filtering by `query`/`scope_ref`, the 300-node budget, ranking and omission counts all run **after** acquisition, over the whole composed document. Occlusion compares every positioned (`fixed`/`absolute`) layout node with higher paint order against each in-viewport target: a global dependency on the whole page's layout |
| `SemanticNode` | `browser/semantic.rs:113` | ax id/parent/children, `backend_node_id`, role, name, value, kept AX states, frame, visibility class, action kinds, document order. `to_ref_entry` makes the stored `RefEntry` (semantic, declared actions) |
| `BrowserStore` | `browser/store.rs:261` | Session → target → tab → snapshot namespace. `resolve_ref` (`:343`) requires the snapshot id to still exist and its generation to equal the target's. `invalidate_tab_snapshots` (`:421`), `remove_session` (`:431`, wired to the session-end hook in `engine.rs:657`), `invalidate_endpoint_generation` (`:437`). Continuations (`:384`) page through the **stored** document; they re-prove only main-frame identity via `Page.getFrameTree` and do not re-acquire |
| `SnapshotStore<S>` | `snapshot_store.rs:120` | Native element-token snapshots (AT-SPI/AX/UIA), pid-scoped lanes with an LRU cap. **Not used on the browser path.** Relevant only to later native work (#20); the browser mirror must not route through it |
| CDP machinery | `browser/cdp_ws.rs` | `CdpConnection::call` (`:353`) id-matched replies, 20 s timeout, existing-profile method allowlist (`:41`). `subscribe` (`:307`) fans every unsolicited event to **unbounded** mpsc subscribers in arrival order; events emitted before a command's reply are queued on a subscriber created before the call. One persistent event session per target already exists for dialogs (`register_dialog_session`, `:316`; `tools.rs:2223` registers before `Page.enable`). `CdpPool` shares one socket per endpoint |
| Ref resolution and stale refusal | `tools.rs` `browser_click` / `browser_type`; `engine.rs:1741` `lock_mutation`, `:1415` `revalidate_for_mutation`, `:1844` `frame_session_for_mutation` | Per mutation: lock by real CDP target → full binding re-proof (binding quality exact, generation, lifecycle owner, process fingerprint, native window ownership, **owned-endpoint re-discovery**, CDP target in the bound window with geometry or singleton proof, fresh attach, origin manifest when delegated) → `resolve_ref` (stale ⇒ `browser_ref_stale` before any dispatch; B-01: 28/28) → semantic action declared → frame identity re-proved against the live frame tree (navigated ⇒ invalidate + stale) → `dom_event`: `DOM.resolveNode` (failure ⇒ stale) → `scrollIntoViewIfNeeded`/`getBoxModel` (feedback only) → `Runtime.callFunctionOn this.click()`. **No `isConnected` check**: a detached node that still resolves is clicked and accepted (R2-07 N4a, 3/3; affects every arm) |
| Verification | caller + fixture | `dom_event` returns `effect:"unverifiable"`. Verification is the fixture `/state` oracle: the runner's 100 ms poll, and in experiment harnesses an independent 2 ms re-read thread (B-01). The effect can land after tool return (R2-06): every verification must be a bounded re-read |
| Session lifetime | `engine.rs:657` session-end hook → `BrowserStore::remove_session`; `prepare.rs` `cleanup_prepared_session` | The whole namespace (targets, tabs, snapshots, refs) dies with the session |

## 4. Arm B feasibility: producer-side scoped read

**Verdict: B (producer-side scoped fresh read) is BLOCKED through the existing contract. Fallback named: B-proj, a `semantic_v2` `query` read, which is payload projection only and is recorded separately with no read-cost claim.**

Evidence (SOURCE, to be confirmed REAL by lane AB through the producer-RPC ledger):

1. The contract does *express* scope (`scope_ref`, `query`, `continuation`), but the implementation acquires the whole document first. For any `scope_ref`/`query` call, `snapshot_tab_semantic` still issues `DOM.getDocument {depth:-1}`, `Page.getFrameTree`, `DOMSnapshot.captureSnapshot` (all computed styles, paint order and rects), `Page.getLayoutMetrics`, `Accessibility.getFullAXTree` per frame and the OOPIF walk. Only then does `SemanticDocument::page` filter. That is fetch-then-filter: payload projection, not deleted acquisition.
2. `continuation` reads the stored document of the current snapshot. It is not a fresh read, so it cannot stand in for B.
3. A producer-side implementation behind the existing parameters would not be semantically equal, so it would weaken the contract:
   - occlusion (`page_occluded`) depends on every positioned element in the page (`apply_page_occlusion`), so a subtree read cannot prove "not covered";
   - `query` uses a document-wide exact-match test before falling back to term scoring (`scoped_indices`), so its result set is a global property;
   - `DOMSnapshot.captureSnapshot` has no subtree form, and `Accessibility.queryAXTree`/`getPartialAXTree` differ in matching and coverage, and `Accessibility.*`-scoped methods beyond `getFullAXTree` are not in the existing-profile allowlist.
4. `dom_refs_v1` acquires less (no AX tree, no layout) but returns no role/accessible value and mints legacy permissive refs. The task's field-state fact (`value == token`) cannot be computed from it. Using it would substitute a weaker contract, so it is excluded.

Consequences:
- A↔B read-cost comparison: **BLOCKED**. Any change to make B real is an internal Driver optimization that must first prove result equality (including occlusion and query semantics), or a public-contract change through #73/#74. Neither is authorized here.
- B-proj is run as a diagnostic: identical acquisition (the ledger must show equal CDP methods, bytes and acquired node counts), smaller model-visible projection. It measures projection/encoding/transport/validation cost only.
- D's "B's fresh scoped reads" becomes D(A-reads): the guarded continuation on A's full fresh reads.
- C's question "does maintenance beat scoped acquisition" cannot be asked; C is compared with A on the same binary.

## 5. CDP event sources a shadow mirror could subscribe to, and their coverage gaps

From the CDP protocol (tip-of-tree knowledge; lane CSHADOW must confirm each method against the protocol JSON served by the Driver-launched Chrome 151 endpoint, `/json/protocol`, read inside the private session, and record any difference).

| Source | Events | Establishes | Documented / structural gaps |
|---|---|---|---|
| DOM (enabled implicitly by `DOM.getDocument` on the subscribing session) | `documentUpdated`, `setChildNodes`, `childNodeInserted`, `childNodeRemoved`, `childNodeCountUpdated`, `attributeModified`, `attributeRemoved`, `characterDataModified`, `shadowRootPushed/Popped`, `pseudoElementAdded/Removed`; experimental `inlineStyleInvalidated`, `topLayerElementsUpdated`, `scrollableFlagUpdated` | DOM structure, attributes, text of nodes **already known to that session** | Only for nodes the session has requested; unknown subtrees yield only `childNodeCountUpdated`. Per-session `nodeId`s (bootstrap needs its own full `getDocument` = one extra full acquisition). `documentUpdated` invalidates everything. **No property events**: typed `input.value`, `checked`, `selectedIndex`, `disabled` set as a property without attribute reflection. `inlineStyleInvalidated` carries ids only, no values. No computed-style, layout, geometry, visibility, focus or paint-order events. Per frame session for OOPIFs |
| Accessibility (`Accessibility.enable`) | `loadComplete`, experimental `nodesUpdated` | AX role/name/value/state for nodes the client fetched | Experimental; coverage of property changes not guaranteed. Enabling keeps renderer accessibility on for every mutation (renderer CPU under churn). `Accessibility.enable` is **not** in the existing-profile allowlist, so the source is unavailable on approved personal profiles |
| Page (`Page.enable`; optional `setLifecycleEventsEnabled`) | `frameNavigated`, `navigatedWithinDocument`, `frameAttached/Detached`, `frameStartedLoading/StoppedLoading`, `lifecycleEvent`, `domContentEventFired`, `loadEventFired`, `documentOpened` (experimental), `frameResized`, `javascriptDialogOpening/Closed` | Document generation, frame lifecycle, dialogs | Navigation events lag the effect (R2-02: `frameNavigated` arrives after the oracle already shows the change). Nothing for intra-document mutation. `setLifecycleEventsEnabled` is not in the existing-profile allowlist |
| Target (`setDiscoverTargets`, `setAutoAttach`) | `targetCreated/Destroyed/InfoChanged/Crashed`, `attachedToTarget`, `detachedFromTarget` | Tab and OOPIF set, renderer crash | `setDiscoverTargets` is not in the existing-profile allowlist. A crash invalidates every node id |
| Inspector | `detached`, `targetCrashed`, `targetReloadedAfterCrash` | Session loss, renderer restart | Session-scoped |
| Runtime (`Runtime.enable`) | `executionContextCreated/Destroyed/Cleared` | Document/context generation proxy | `Runtime.enable` is not in the existing-profile allowlist; page-injected observers (`addBinding` + MutationObserver) would inject code into the page and are not proposed |
| CSS (`CSS.enable`) | `styleSheetAdded/Changed/Removed`, `mediaQueryResultChanged`, `fontsUpdated` | Coarse "styles may have changed" | No per-node computed-style results; class/style effects on visibility need a fresh layout read |
| LayerTree / Animation | `layerTreeDidChange`, `animationStarted` etc. | Compositor/animation activity | Heavy, compositor-level, no element visibility semantics |

Structural facts that bound any mirror on this source:
- **Visibility, geometry, overlay/occlusion, focus and typed-value changes have no establishing event.** A mirror must mark those fields `unknown` (or invalidate on any possibly-related event) and require a fresh read before any decision that depends on them. The fill task depends on exactly one such field (the typed `value`) and on Submit visibility/occlusion.
- The demux `subscribe` channel is unbounded and every subscriber gets a clone of every event; the mirror must drain promptly, enforce its own queue/node caps and declare overflow as loss of coverage.
- Session accumulation (BUG-01 part B): each tool call attaches one more CDP session; post-navigation event bursts scale with the count. A mirror must use one persistent, registered event session per tab (the dialog-session pattern) and count event volume per session.
- The existing-profile allowlist excludes `Accessibility.enable`, `Runtime.enable`, `Target.setDiscoverTargets` and `Page.setLifecycleEventsEnabled`. Extending it is a permission change: mirror cells on approved existing profiles are BLOCKED. This experiment uses the Driver-owned `isolated_new` profile only.
- Refs cannot be minted from mirror state (`RefEntry` only comes from a snapshot) and a new snapshot clears the tab's previous refs. Any action therefore needs a fresh `semantic_v2` snapshot regardless of the mirror (section 6).

## 6. Active-C admissibility on the admitted fixture

Every Driver read on the fill→submit path is one of: (a) a ref-minting snapshot immediately before a mutation, (b) a binding/revalidation read inside the mutation tool, (c) a post-effect verification read (fixture oracle, not the Driver), or (d) a #105 reconciliation read. None may be skipped on mirror evidence (#107 rules 3-5). The pre-registered expectation is therefore **active C = NOT_ADMISSIBLE on this fixture** (no Driver read can safely disappear), and E = NOT_RUN. Lane CSHADOW must still test this claim against the actual trace (every `get_browser_state` call classified a-d) and report it. If it finds a read outside a-d, it registers an amendment before any active-C trial.

## 7. Workload conditions and fixture extension (lanes commit the variant)

- **W-quiet**: the jev-use `FixtureServer` page byte-for-byte (one input, one Submit, two paragraphs).
- **W-churn**: the same form plus an unrelated region (default 500 nodes, seeded RNG) mutated at 20 Hz (each tick: text changes, attribute flips, insert/remove pairs on 10 random region nodes; no node in the region contains "submit" or "verification"; the form subtree is untouched).
- **W-idle**: a 20 s interval with the Driver session open, the page loaded, no tool calls, under W-quiet and under W-churn background.
- **W-static** (secondary): the W-churn page with churn stopped (size effect without churn).
- Control channel for dependency tests: the page holds an EventSource to the fixture server; the harness posts an operation, the page applies it and posts an ack; the server journals the ack on CLOCK_MONOTONIC. The oracle `/state` adds which form/button submitted. The mutation channel never goes through the Driver.

## 8. Dependency-test controls (all arms where applicable; independent oracle grades)

See `PREREG.json` `dependency_controls` for the per-control expected outcomes. The list is the issue's, plus two concrete look-alike variants: R1 benign re-render inside the same form, and R2 a relocated look-alike Submit in a different form (PR 4316's guard retains role+name+uniqueness only, so R2 is expected to expose a missing scope fact in D and in A alike).

## 9. Baseline A span decomposition (#10 spans)

Reused from B-01 (kvnloo/cua, branch `exp/b-01-browser-critpath-20261002`, packet `docs/experiments/b-01-browser-critpath-2026-10-02/`, reviewed commit `6689610d5`). **B-01 is PENDING (rejected for two text-only items; the verifier reproduced every number).** Its tested `libs/cua-driver` tree equals this map's tested source, so the traces are valid here. Mock chooser, fill→submit, mean ms per task, BENCHMARK from REAL traces, n = 20:

| #10 span | B-01 components | K0n (default feedback, no guard = current caller at defaults) | K2 (feedback OFF, guard on; decision cost ≈ 0) | K3 (OFF + settle 0) |
|---|---|---|---|---|
| Observation acquisition | `observation_cdp` (2 snapshots; first ≈ 15 ms cold, second ≈ 5-6 ms) | ≈ 19.7 of 21.2 | 18.9 of 20.4 | ≈ 19.4 of 20.9 |
| Projection / encoding / transport | observation processing + driver post-dispatch + stdio transport + client output-schema validation | ≈ 1.5 + 2.7 + 2.4 + 13.0 | 1.5 + 2.5 + 2.6 + 13.1 | ≈ 1.5 + 2.6 + 2.6 + 13.1 |
| Provider inference | decision (mock) | 0.01 | 0.005 | 0.005 |
| Resolution / validation | resolution + revalidate (endpoint re-proof ≈ 19.8 of it) + MCP admission (driver pre-dispatch) + input prep | 2.2 + 22.1 + 8.7 + 2.6 | 2.2 + 22.0 + 9.6 + 1.4 | 2.3 + 21.8 + 9.2 + 1.1 |
| Dispatch | dispatch + dispatch_post | 2.9 + 1.0 | 2.3 + 1.0 | 2.3 + 0.6 |
| Wait | visualization (glide) + focus settle + completion sleeps/polls + target-effect lag | **2998.0** + 101.1 + 5.0 + 0.3 | 1.5 + **101.1** + 0.0 + 0.3 | 1.6 + 0.05 + 5.0 + 0.3 |
| Fresh verification | verification reads (oracle) | 1.6 | 1.3 | 1.2 |
| Cleanup | session close, browser teardown | not measured (NOT_RUN in B-01) | NOT_RUN | NOT_RUN |
| Runner overhead / unattributed | — | 0.2 / 0.0 | 0.2 / 0.0 | 0.2 / 0.0 |
| **T_runner mean (median)** | | **3185.0 (3180.7)** | **181.5 (181.7)** | **84.9 (78.7)** |

Reading: with feedback at its default, 94.1% of T is the cursor glide (R2-01 KEEP_H1, B-01 H_V). With feedback held OFF (the setting every i107 arm holds fixed), observation acquisition is ≈ 19-20 ms per task (11% of K2's T): the **ceiling** of what B or C could delete on W-quiet, before the mirror's own costs. Of the remainder, the 100 ms focus settle (owner decision, B-01 H_T), the endpoint re-proof (≈ 10 ms per mutation, UNTESTED, security-relevant) and MCP admission/validation dominate; none of those is observation work.

R2-01 (`2ca82efae`) and R2-02 (`8e751a75d`) traces are on the same Driver tree (+ their own marks). R2-01 contributes the visualization span only; R2-02's event-wake arm (KILL) shows that a CDP commit event arrives after the oracle already shows the effect and that per-call CDP sessions add a session-age drift term.

Lane AB must re-measure A on the i107 binary with feedback OFF and no guard (B-01 has no exact A-OFF-unguarded arm), add the cleanup span and the producer-RPC ledger, and keep the >90% named-span gate.

## 10. Infrastructure blocker found while smoking the binary (REAL)

The binary builds, passes `cua-driver-core` lib tests (821/821, UNIT) and prints its version inside the private session, all under `hostless`. A REAL browser run does not start: inside `hostless` (bubblewrap, unprivileged user namespace) host root-owned files appear as uid 65534, so the Driver's isolated-launch trust check refuses `browser_prepare` with `browser_route_unavailable` ("no root-owned, non-writable system Chromium executable is available for isolated launch"). Every REAL browser cell in this experiment, and in any other track that runs browsers under `hostless`, is BLOCKED until the orchestrator or owner chooses a host-isolation wrapper that does not remap file ownership. Bypassing the Driver's trust check or running outside `hostless` is not an option. Separately, `hostless` does not unshare the network namespace, so the host's abstract X11 sockets (`@/tmp/.X11-unix/X0` and others) remain reachable from inside it if a process sets `DISPLAY`; the wrapper relies on the variable scrub for that path.

## 11. Relevant existing owners

#93 (R2-01 feedback KEEP_H1; R2-02 event wake KILL; R2-03 guarded completion KEEP live; R2-07 compiled routine KILL pending a Driver `isConnected` refusal; R2-10 composition), #10 (accounting envelope), #73/#74 (canonical disposition, promotion), #17/#36 (session, target, document generation and stale-ref refusal), #105/#9/#33 (uncertain effects, cancellation, no blind replay; OWN-105 runner fixes are not in the main caller), #38 (receipt truthfulness), #20/#94/#101 (native and Hyprland; not in scope). Upstream: trycua/cua PR 4316 (guard, OPEN), trycua/cua PR 4394 (provider receipts, OPEN, not used), trycua/cua 4052 (CDP session accumulation).
