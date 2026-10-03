# CUA RFC loop: wave 1 synthesis (2026-10-02 UTC)

Workflow `wf_38e35f25-57f`. Eight lanes ran. Verifiers accepted six, rejected one (B-01, text-only blocking items) and accepted one only as a correct hard-stop report (N-01, no evidence). TypeSafe use this wave was 110 reached / 200 attempts. Loop total is 236 / 600 reached (332 attempts), leaving 364.

## 0. Stop rule: needs a ruling first

END_CONDITION says the loop stops on "any hard-rule breach (host desktop touched, secret exposed, upstream write)". This wave had one confirmed breach of that kind and two others:

| Lane | Rule | Effect | Lane stopped? |
|---|---|---|---|
| N-01 | host isolation | **Confirmed.** A GTK3 import in the worker host shell ran `Gtk.init_check` against the host display server. It probably also registered the atk-bridge on the host session bus. It was short-lived: no window, input or focus change, and no leftover process. | yes (HARD_STOP) |
| OWN-105 | host isolation (`--version` outside the session) | None. `google-chrome` is not on the host PATH, so no process ran. | no (the lane called it a near-miss) |
| B-01 | quiet-lane lock | 3 REAL shakedowns ran with no lock. One of them overlapped R2-07's EXCLUSIVE P4 warm window. No B-01 number depends on them. | no |

**I have not made the stop decision.** The orchestrator or owner has to rule before wave 2 or any Publish: either end the loop under the stop rule, or continue with the breach documented. STATE.json records this as `stop_rules.hard_rule_breach` and `waves[1].publish_gate`. No secret was exposed and nothing was written upstream.

## 1. What changed this wave

- **R2-07 compiled routine: KILL** (spec-binding). Measured on warm replay, the compiled fill→submit routine deleted both provider decisions. Median T was 186.1 ms, against 454.5 ms guarded and 672.0 ms ordinary. The paired C−B difference was −273.0 ms [−285.0, −241.2], with 20/20 verified. It is still a KILL. In N4a (a re-render between bind and dispatch), the Driver's `dom_event` `browser_click` accepted a click on a detached node 3/3. Nothing landed and the routine stopped as unknown. The source has no `isConnected` check anywhere, and unmodified run.py gets the same acceptance (N4a_ord). REVISE exists only as a proposed amendment that is not in force. R2-10 must not include compiled replay until (a) the planner adopts the amendment and (b) a reviewed Driver `isConnected` refusal lands and N4a is re-run.
- **R2-08 cross-surface: KEEP.** The existing POST /submit route was equivalent to the GUI route in 20/20 rounds. T(API) − T(G_off) was −174.4 ms [−175.7, −172.9]. N1 (nonce authorization), N2 (client pattern bypass) and N3 (intermediate validate effect) each discriminated 10/10 per route. Choosing this route is an OWNER_DECISION per task, never a default.
- **OWN-105 (#105 runner): KEEP.** G1–G3 and the pre-write rule are fixed in both runners. On real MCP stdio: 0 duplicates in 148 fixed trials, and all 148 ended with a receipt. The unfixed base reproduced every gap 20/20, including 5 real duplicates.
- **OWN-78 (trycua/cua PR 4394 receipts): REVISE.** The backend field is configuration-derived adapter identity, and it matched the HTTP responder 30/30 live and 20/20 mock. There was no replay after partial progress (20/20, connection-refused fixture only). On the PR runner, live TypeSafe abstains at step 1 in 30/30 trials; the pre-PR runner verified 5/5. The abstain is attributed to the PR's request construction as a whole; the cause inside it is not isolated. The S1 row is BLOCKED.
- **OWN-16 (#16 Linux selector): KEEP** for boolean selectors on X11/GTK3. An omitted producer never ran in 42/42 calls, and an independent oracle agreed 21/21 per session. Per-call saving: −7.36 ms for screenshot_only, −2.98 ms for accessibility_only. The string `"false"` is silently ignored, which needs a follow-up product fix. macOS and Windows are BLOCKED. Wayland is NOT_RUN and needs a BLOCKED record.
- **BUG-01:**
  - Part A is a CONFIRMED_BUG with a fix candidate, `2533db6d5` + `49a3adf0f`. Foreground trusted clicks were labelled background 20/20; with the fix they are foreground 20/20, and no other receipt field changed.
  - Part B is ACCUMULATION_ONLY. Each browser call leaves one CDP session attached, so 300 calls leave 304 live. The post-navigation event burst scales with that count (1/101/201).
- **B-01: REJECTED, stays PENDING.**
  - The numbers were reproduced independently. Two text fixes block acceptance: (1) the MCP admission cost is ~2.2 ms per tools/call and 4.4 ms per action step, not "4.4 ms per call"; (2) the provenance row asserts a build lock that was never receipted.
  - Separately, the lock breach above.
- **N-01: HARD_STOP**, with no data. Its STEP 0 source findings were verified and change the re-plan:
  - C_off is race-only, because every reveal re-enables the cursor.
  - `dwell_after_click_ms` has no reader on Linux.
  - `glide_duration_ms` governs both spans, so the composed arm should be C_fast+S0.

## 2. Per-reference-task decomposition (best known)

Rules: never add rows across sources, binaries or providers. B-01 rows come from a packet that is not accepted; a verifier reproduced them, but they are not accepted evidence.

### Browser fill→submit

| Configuration (source / binary / provider) | Median T | Main components |
|---|---|---|
| Default feedback (B-01 `f5c991e59` / `2e0248ad`, scripted chooser) | 3180.7 ms | glide 94.1%, focus settle 101.1 ms (3.2%) |
| Best composed, no provider (B-01 K3) | 78.7 ms (mean 84.9); K5 70.4 ms on T_oracle | revalidate 21.8 (25.7%; endpoint re-proof 19.8), observation 20.9 (24.6%), client validation 13.1 (15.4%), Driver pre-dispatch 9.2 (10.8%; tool-list validation 8.7), stdio + post-dispatch 5.2 (6.2%), sleeps/polls 5.0 (5.9%) |
| Live provider, feedback off (R2-07 `031ee5f58` / `8b037961`, TypeSafe) | A 672.0 / B 454.5 / C 186.1 ms | provider share A 63.8% (428.9 ms), B 46.5% (211.4 ms), C 0 (KILL); ~49 ms per-process provider setup inside A/B |
| GUI vs API (R2-08 `c4d0c6625` / `8b037961`) | G_on 3171.8 / G_off 176.0 / API 1.56 ms | G_off: browser_type 126.8 (72%, includes the 100 ms settle), snapshots 20.3 + 5.7, click 22.0 |

E2 verdicts:
- feedback glide: OWNER_DECISION (the fast glide recovers 98.6–98.7% of OFF's saving; B-01 pending)
- 100 ms focus settle: OWNER_DECISION (insert_text replace site only; B-01 pending)
- second provider decision: DELETED by guarded completion (R2-03)
- remaining provider decision: IRREDUCIBLE at this source (R2-07 KILL; can be reopened)
- client schema validation: DELETED
- completion poll: IRREDUCIBLE (not material)
- API route: OWNER_DECISION
- endpoint re-proof, tool-list validation and cold first snapshot: **UNTESTED**

**Untested share: 51.2%** of composed T (no provider, T_runner).

### Browser toggle→confirm and modal→act (B-01, pending)

| Task | Default T | Glide share | Best composed (K5) | Components (mean) | Untested share |
|---|---|---|---|---|---|
| toggle→confirm | 2487.3 ms | 97.3% | 52.2 ms (mean 53.1) | revalidate 22.2 (41.8%), observation 11.9 (22.4%), pre-dispatch 9.1 (17.1%), stdio 4.4 (8.2%) | **70.2%** |
| modal→act | 2471.7 ms | 97.3% | 53.2 ms (mean 54.5) | revalidate 22.6 (41.5%), observation 12.3 (22.6%), pre-dispatch 9.4 (17.2%), stdio 4.6 (8.4%) | **69.3%** |

Guarded completion bound nothing on toggle/modal at this source (0/160). A compiled routine for toggle would also need a checked_state precondition plus the `isConnected` fix.

### Native GTK3 checkbox and text entry (R2-04, localized only)

| Task | Median T | Main components |
|---|---|---|
| checkbox | 585.2 ms | cursor reveal 254.6–1416.4 ms, post-DoAction sleep ~51.3 ms, focus-guard settle ~241 ms |
| text entry | 3046.2 ms | the same Driver waits across 2 actions (keyboard-cursor positioning goes through the same reveal path) |

AT-SPI RPC is under 1% of T. Every large component is UNTESTED, because N-01 hard-stopped. **Untested share: roughly 90% or more.** OWN-16's observation selector is KEEP, but it saves only 3–7 ms per get_window_state call. About 16 ms per call is MCP transport plus the Python client.

## 3. Dispositions

| ID | Disposition | Class | Publication commit |
|---|---|---|---|
| R2-07 | KILL (amendment → REVISE is proposed, not in force) | LIVE_PROVIDER+REAL+BENCHMARK (P5/P6 are REAL+FIXTURE) | `2d71548b4` |
| R2-08 | KEEP | REAL (owned fixture)+BENCHMARK+UNIT | `afba150d5` |
| OWN-105 | KEEP | REAL+UNIT | `b97daa4ba` |
| OWN-78 | REVISE (S1 BLOCKED) | LIVE_PROVIDER+REAL+FIXTURE+UNIT | `5107f3cca` |
| OWN-16 | KEEP (Linux X11, boolean selectors) | REAL+UNIT | `7a4f3252a` |
| BUG-01 | A CONFIRMED_BUG (fix `2533db6d5`+`49a3adf0f`); B ACCUMULATION_ONLY | REAL+UNIT | `097b4f097` |
| B-01 | PENDING (rejected round 2) | — | not publishable (`6689610d5` reviewed) |
| N-01 | PENDING (HARD_STOP, no data) | — | nothing to publish |

Earlier waves: R2-01 KEEP_H1, R2-02 KILL, R2-03 KEEP, R2-04 REVISE, R2-05 KEEP, R2-06 KEEP. R2-09 and R2-10 are PENDING.

BLOCKED (external): #6 (Windows), #8 (macOS + upstream trycua/cua 3904 decision), #13 (macOS), #19 (Windows UIA), #31 (macOS/Windows rows), #72 (macOS), #94 with #92/#100/#101 (real Hyprland seat), the #78 S1 row (adapter not local; TypeSafe only), the #9 held-input row (macOS oracle), the #16 macOS/Windows rows (hardware).

## 4. What remains, E1–E6

- **E1:** R2-01…R2-08 are now terminal. Open items:
  - R2-09 is gated on N-01. R2-10 has a PREREG draft from B-01 but needs B-01 accepted.
  - B-01 and N-01 are PENDING.
  - Linux owner rows still PENDING: #9 core barrier rows (wave 2), #20 (needs N-01), #36, #75.
  - #16 Wayland needs a BLOCKED record.
- **E2:** far from met. The untested share is 51–70% on the browser classes (B-01, pending) and roughly 90% or more native. Next causal A/Bs:
  - browser: endpoint re-proof (security review), tools_list caching at admission, warm first snapshot
  - native: the re-planned N-01
- **E3:** not run. The R2-10 browser draft needs 330 reached of the 364 left, so it fits only if no other live lane runs first. It must gate on the spec's T (T_oracle), or on both T_oracle and T_runner. It excludes compiled replay. Native arms wait for N-01.
- **E4: not met for the page-re-render case.** The Driver accepts clicks on detached nodes. This shows up in R2-07 N4a and also on the unmodified run.py path, so it is a Driver gap that affects every browser caller. Two runner issues also showed up in R2-07: run.py treats `effect=refused` with `isError=false` as success, and it re-dispatches Submit after an unverifiable click (N4a_ord). Every other accepted packet reports 0 duplicates, 0 unverified successes and discriminating refusals.
- **E5:** nothing staged yet: no #10 final table, no #3963 rewrite, no #74 queue. The wave-1 drafts are in `drafts/w1/`.
- **E6:** freshness is OK. Upstream main is `352507b6c`, 11 commits past `229b65b28`, with 0 files under `libs/cua-driver`. trycua/cua PR 4316 is at `a0bca7440`, kvnloo/cua#105 at `98a45e6c5` and trycua/cua PR 4394 at `039257811`; all three equal the tested heads. No judges have run.

## 5. Shared-infrastructure findings for the loop owner

1. `cua-x11-session.sh`: `xvfb-run -a` handed R2-07 block b1 display :99 while another lane's Xvfb held it. That is a display-allocation race.
2. `cua-x11-session.sh`: the dbus-run-session socket defaults to /tmp. Point it at `$RUN`.
3. `build-driver.sh`: the trailing `--version` runs outside the session.
4. No lock receipts for builds, unit runs or some REAL blocks (B-01, OWN-78, OWN-105).
5. Start worker shells with the display, Wayland, Hyprland and runtime variables unset, so accidental host contact fails closed. This would have prevented N-01 and the OWN-105 near-miss.
6. Harnesses should take the EXCLUSIVE lock before opening the Driver MCP session (OWN-16 session expiry).

## 6. Ranked follow-ups

1. Rule on the stop rule (N-01).
2. Shared-infrastructure fixes (§5).
3. B-01 text fix pass, then a fresh verifier.
4. N-01 re-plan with the revised arms.
5. B-01 untested components, causal A/B.
6. Driver `isConnected` refusal (reviewed product fix), then an R2-07 N4a re-run and an amendment ruling.
7. R2-10 on one source.
8. OWN-78: isolate the cause of the abstain and re-run live.
9. OWN-16: non-boolean selector refusal; Wayland BLOCKED record.
10. Stage the BUG-01 fixes for kvnloo/cua#38 (upstream trycua/cua 4009) and trycua/cua 4052.
11. #9, #36, #75.
12. Re-check or disclose R2-07's P4 timing overlap.
13. Publish-time text fixes listed in STATE.json.
