# i107 lane CSHADOW: shadow-mode mirror qualification and active-C admissibility (2026-10-02)

kvnloo/cua#107, execution-sequence steps "Qualify C in shadow mode" and "Run active C only where admissible". Map and frozen design: `../i107-map-2026-10-02/` (PREREG sha256 `8eeb837f…2c53`). This lane's pre-registration: `PREREG.json` (committed in `9dbd2f966` at 2026-10-02T05:33Z, before any measured trial).

Placeholders: `<lanes>` lanes root, `<tmp>` lane temp root. Upstream items are plain text. Evidence labels per row: SOURCE / UNIT / FIXTURE / REAL / BENCHMARK / LIVE_PROVIDER / BLOCKED / NOT_RUN.

## Results

| # | Item | Evidence | Result |
|---|---|---|---|
| 1 | Active-C admissibility (classify every `get_browser_state` in A traces as (a)-(d)) | SOURCE (run.py loop) + REAL traces reused from B-01 (PENDING; same Driver tree) | **NOT_ADMISSIBLE.** 600 calls in 200 fill traces: 400 (a) ref-minting snapshots whose ref the next mutation resolved, 200 (b) pid+window bindings, **0 outside (a)-(d)**; 0 Driver reads after the last mutation (verification is the fixture oracle, (c)). No active-C trial runs; no amendment. E stays NOT_RUN. `raw/admissibility.json`, `classify_reads.py` |
| 2 | Mirror implementation (bounded, read-only, under `TabRecord`, env-gated, default off) | SOURCE + UNIT | Built test-first: red = 165 compile errors (`raw/unit/unit-red.log`), green = `cua-driver-core` lib **860/860** (821 + 39 mirror tests), `platform-linux` lib **602 passed / 10 ignored** (`raw/unit/unit-green-full.log`), all under hostless. Clippy NOT_RUN (not installed for the pinned toolchain) |
| 3 | Mirror binary | REAL (build) | `cua-driver-i107-cshadow-904b249c1`, sha256 `6b481e0e0d52d624005494f64ebe42a3475f86e14943eb36c36b9fc1d021fd23`, `cua-driver 0.32.0` read inside the private session; 168 s, 0 fresh units (`raw/build/build-receipt.txt`) |
| 4 | CDP event methods vs Chrome's own protocol | SOURCE | Every event the map lists exists in Chrome 151.0.7922.71's protocol (extracted from the installed `resources.pak`, the resource behind `/json/protocol`). Not in the map: DOM `adoptedStyleSheetsModified`, `distributedNodesUpdated`, `adRelatedStateUpdated`, `affectedByStartingStylesFlagUpdated`; CSS `computedStyleUpdated` (node id only: a dirty signal, never a value); Page `frameStartedNavigating`, `frameSubtreeWillBeDetached` and others. `raw/protocol_events.json` |
| 5 | Fixture (W-quiet byte-for-byte, W-churn 500 nodes at 20 Hz, control channel, ack journal, decoy endpoint) | FIXTURE | Self-test without a browser passes (`raw/fixture-selftest.json`) |
| 6 | Default-off, CMP-C-overhead, CMP-C-idle, CMP-C-fidelity, controls, CMP-C-resident | REAL | see "REAL status" below |

## What the mirror is (and is not)

`libs/cua-driver/rust/crates/cua-driver-core/src/browser/i107_mirror.rs`, wired at the fresh `semantic_v2` snapshot only (`engine.rs`, +24 lines) and stored on `TabRecord` (`store.rs`, +6 lines), so `remove_session` / the session-end hook, `invalidate_endpoint_generation` and navigation invalidation (`invalidate_tab_snapshots`) drop it (unit tests for each).

- `CUA_DRIVER_EXP_I107_MIRROR` = `shadow` | `shadow_audit`; anything else (including unset) is off and creates no subscription, session, call or mark (unit test with a recording mock browser: zero CDP traffic). Existing-profile sockets never get a mirror (their allowlist excludes the event domains: BLOCKED cell).
- One persistent event session per tab: subscribe first, then `Target.attachToTarget`, `Page.enable`, `Inspector.enable`, `Page.getFrameTree`, its own `DOM.getDocument {depth:-1, pierce:true}`. Every bootstrap and resync uses a new session (old one detached), so events of older sessions are unrelated by construction and DOM events on the current session always follow its own document reply.
- Covered fields: existence, node name, text node value, attributes, ordered children. **Always unknown:** visibility, geometry, occlusion, focus, typed (property) value, AX role/name/states. `inlineStyleInvalidated` marks `style` uncertain.
- Any inconsistency (missing node or sibling, duplicate insert, child-count mismatch, unmodeled DOM event), navigation, document replacement, session loss, crash, a loader change seen at an audit cut, overflow (10,000 queued) or the node cap (20,000) sets coverage `unknown`, drops the projection and forces a rate-limited resync from a fresh read. Nothing is silently dropped: discards are counted.
- Never mints, revives or validates refs; never touches the action path, mutation revalidation or verification; results go to the phase trace only (`i107.mirror.create|bootstrap|stats|audit|fault|op_applied`). No public tool or field.
- `shadow_audit` brackets the normal fresh read (mirror revision before its `DOM.getDocument`, then an ordered round trip on the mirror session and a full drain) and compares covered fields per backendNodeId; changes inside the window count as `ambiguous_in_flight`, never as agreement.
- `CUA_DRIVER_EXP_I107_MIRROR_FAULT` injects DC18 faults at the intake seam.

UNIT finding that bounds every claim: a **dropped attribute event is invisible to the mirror** (coverage stays `current`) and is caught only by a fresh read (`missing_event_is_invisible_to_the_mirror_and_caught_only_by_the_fresh_audit`, `faulted_streams_never_produce_false_current_without_detection_paths`). Structural faults (duplicate/reordered/early/overflow/reconnect) self-detect and go `unknown`; value-only loss does not. That is exactly why rule 4 forbids observation-skipping authority, and why active C has nothing it may delete here.

## REAL status

**BLOCKED: 0 measured REAL trials.** Every REAL cell (default-off check, CMP-C-overhead W-quiet/W-churn, CMP-C-idle W-idle-quiet/W-idle-churn, CMP-C-fidelity W-quiet/W-churn, dependency controls DC01-DC05a, DC07, DC10-DC19, CMP-C-resident) is BLOCKED and reported as BLOCKED in `cshadow-summary.json` (never zero-filled). Reasons:

1. **Isolation approval pending.** The lane spec allows REAL blocks only after the orchestrator provides an approved isolation wrapper. During this lane the canonical `hostless` was replaced (2026-10-02T05:06Z) by a Landlock-based v2 (bwrap v1 kept as `hostless-strict`). Under v2 the Chrome executable shows uid 0, so the map's launch blocker looks resolved. But no approval for REAL browser runs under v2 reached this lane, and v2 scopes abstract unix sockets and signals but not pathname sockets (`/tmp/.X11-unix/X*`, `/run/user/<uid>/*`), which then rely on the environment scrub. The question went to the orchestrator; no answer arrived before this packet.
2. **Quiet lane saturated.** At 05:40Z eight exclusive waiters were queued behind shared-mode holders that kept re-acquiring the quiet-lane lock (1-min loadavg around 18-22). A smoke of this harness started by another agent (label `i107-cshadow-smoke-s0`, run directory under `<tmp>`) exited without acquiring the lock: no ledger receipt and an empty log.

Ready to run once both are cleared: `run_cshadow.py` plans `smoke` (also reads `/json/version` and `/json/protocol` from the Driver-launched endpoint inside the session), `defaultoff` (lane binary with the mirror unset vs the map binary vs mirror on, CDP methods per trial), `overhead`, `idle`, `fidelity`, `controls` (235 trials, A + C_shadow_audit, DC18 x9 faults), `resident`. It refuses unless the hostless and isolation pre-flight checks pass (private X socket owned by the session's Xvfb, session-local runtime dir and D-Bus, no Wayland/Hyprland variables, Landlock `no_new_privs`).

Pre-registered expectation (not a result): the decision table row "C shadow fidelity holds (false-current 0) and C_active NOT_ADMISSIBLE" gives **park the persistent mirror**. The NOT_ADMISSIBLE half is established here. The fidelity, overhead and budget halves are untested. Disposition now: **BLOCKED for shadow qualification; active C NOT_ADMISSIBLE (no deletable read on this fixture), so no active-C trial or E**.

## Commands

- Unit: `hostless <tmp>/i107-cshadow/unit-full.sh <wt>` (cargo test `-p cua-driver-core --lib`, `-p platform-linux --lib`).
- Build: `hostless flock <tmp>/locks/cargo-build.lock <lanes>/build-driver.sh <wt> i107-cshadow-904b249c1 cua-release-i107`.
- Classification: `hostless python3 classify_reads.py <B-01 trials-measured.tar.gz> raw/admissibility.json`.
- REAL block: `hostless quiet-timed <label> <lanes>/cua-x11-session.sh <jev-use>/.venv/bin/python run_cshadow.py --driver <bin> --out <dir> --plan <plan> --block <label> [...]`.
- Analysis: `hostless python3 analyze_cshadow.py .`; verification: `hostless python3 verify_artifacts.py [--b01-archive <path>]`.

## Hard-rule log

- hard_rule_breach: none. Nothing reached the host desktop or session. No browser was launched, no secret was handled, nothing was written upstream, no number was measured.
- near_miss: several `python3` invocations ran in the plain host shell instead of under hostless. One parsed a JSON file and printed counts; the others were heredoc text replacements on repository files, used as an editor. None imported a GUI, session or network library, so none could have had an effect. Every build, test, fixture, classifier, protocol extraction, analysis and verification run happened under hostless.
- No push, no GitHub write, no stash, 0 TypeSafe requests, no process killed. A foreign smoke in this worktree was left untouched.
