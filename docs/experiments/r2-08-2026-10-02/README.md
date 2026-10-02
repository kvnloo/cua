# R2-08: GUI vs the fixture's HTTP form endpoint, one matched cross-surface equivalence test, 2026-10-02

## Result in one paragraph

The task is jev-use fill→submit on the base fixture. The source is upstream main `c4d0c662` with the unmodified Driver 0.32.0 (`8b037961`), run in a private Xvfb session. The fixture's existing HTTP form endpoint (`POST /submit`) was **equivalent** to the GUI route in **20/20** matched rounds. The three arms were the GUI with default feedback (G_on), the GUI with the agent cursor off (G_off), and a caller POST built from the documented form contract (API). In every round, all three arms agreed on the initial `/state`, the final `/state`, the fixture-journal shape (exactly one `POST /submit`, `application/x-www-form-urlencoded`, field set `[value]`, the exact value, HTTP 200), the single state mutation and the set of side-effecting requests. Every round also enumerated the base form's client-side constraints (required only) and showed the value satisfies them. The API route was faster: paired median T(API) − T(G_off) = **−174.4 ms** (bootstrap 95% CI **−175.7 to −172.9**, 20/20 pairs faster), and T(API) − T(G_on) = **−3170.3 ms**. Median T was 1.56 ms (API), 176.0 ms (G_off) and 3171.8 ms (G_on). All three experiment-owned negatives discriminated **10/10 per route**:
- **N1 (authorization).** The base request shape was refused with 403 `missing_nonce`, while the GUI succeeded with fields `[nonce, value]`.
- **N2 (constraint bypass).** The GUI made 0 submits because the browser fired `invalid`, while the direct POST landed the invalid value.
- **N3 (intermediate effect).** The GUI produced a server-side `validate` before the submit, and the API produced none, although the final `/state` matched.

The spec's contract check (action, method, field name) passed on **all** variants, so a matching contract or request shape detected none of the three differences. Pre-registered disposition: **KEEP**. The claim is narrow: the alternate route is eligible and faster **only with per-task equivalence and authorization evidence**. The Driver stays policy-neutral and the caller chooses. Adoption is an OWNER_DECISION.

## Scope and owners

- Owners: kvnloo/cua#93 (`R2-08`; original `E4`/`E5`), #10 (accounting), #73 (canonical state). Loop end-condition rows advanced: E1 (terminal disposition for R2-08), E2 (alternate-route deletion classified), E4 (negatives).
- Pre-registration: `PREREG.json`, committed first as `da7919209b83883a7a8ab909d4ab4f7bcc49029b` at 02:00:52Z. The first measured trial started at 02:02:02Z. A 10-trial pilot (harness mechanics only) ran before it. The pilot is declared in PREREG and kept in `raw/pilot/`.
- Unchanged:
  - No Driver change.
  - No new service, router, route miner, shadow state or second verifier.
  - No credential capture and no captured-traffic replay.
  - No GitHub writes, no pushes, no live provider (mock chooser; 0 provider attempts, 0 reached).

## Provenance (each SHA separate)

| Item | Value |
|---|---|
| Tested source | upstream main `c4d0c6625b5c93849aa8bec610782410e9d45f69` (jev-use example and fixture at that commit) |
| Driver binary | `<lanes>/bin/cua-driver-r2-main-229b65b28`, sha256 `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3`, `cua-driver 0.32.0`, built from `229b65b2849c3a595ddbc85200d7181b18bd2e47` |
| Binary validity for the tested source | `git diff --quiet 229b65b28 c4d0c6625 -- libs/cua-driver/rust` → rc=0 (`source-head.txt`) |
| PREREG commit | `da7919209b83883a7a8ab909d4ab4f7bcc49029b` |
| Live upstream main at run time | `8d4e7a08618611453794035f7ff6187f99f0c1e9` (read 2026-10-02T02:02Z); `git diff c4d0c6625..8d4e7a086 -- libs/cua-driver` is empty |
| Live PR head | none: R2-08 has no PR |
| Publication SHA | set by the Publish agent; this worker did not push |
| Browser | Driver-selected Google Chrome 151.0.7922.71, `isolated_new` profile, default sandbox |

Receipts: the Driver sha256, version and Chrome version were printed inside every isolated session (`raw/logs/*.log`). Details are in `provenance.json`.

## Environment

- Host: Linux 7.2.2 x86_64, 10 CPUs.
- Session: `cua-x11-session.sh`, i.e. private rootless Xvfb 1920x1080x24, openbox, picom (xrender) and private dbus. Host Wayland/Hyprland variables were scrubbed, and there was no AT-SPI bus.
- Driver defaults: no permission-mode override, no approval bypass, Chromium sandbox on, no `*-e2e` wrapper.
- Locks:
  - Base: all 60 base trials ran in one session inside an EXCLUSIVE `quiet-lane.lock` window, acquired 02:01:56Z and released 02:04:26Z (`raw/logs/base-run1.lockinfo`).
  - Negatives: each negative chunk of 10 trials, and the 3-trial N2 control, ran in its own session under a SHARED acquisition (`raw/logs/neg-*.lockinfo`, `n2ctl.lockinfo`).
- Load: the 1-minute loadavg before the base trials ranged from 3.85 to 8.18, because other agents were active and the lock only excludes lanes that honour it. Every trial's loadavg is in its raw file.

## Method

**Fixture and oracle.** The jev-use `fixture_server.py` serves a loopback form (`<form method=post action=/submit>`, `<input name=value required>`) and an independent `GET /state` oracle. `variants.py` subclasses the unmodified `FixtureServer`/`FixtureHandler`/`FixtureState`:
- The base variant serves the exact shipped `PAGE` bytes (UNIT-tested), and the unmodified jev-use handler decides and mutates.
- The subclass adds only a target-side journal: request receipts (method, path, content type, field names, value hash, HTTP status, effect) and state mutations, stamped with `time.monotonic_ns()`.
- **Success oracle:** fixture `GET /state` only. Driver results are never the success signal.

**Arms and forced path** (`run_cross_surface.py`):
- **G_on (Driver default feedback; no toggle call):** `get_browser_state semantic_v2` → mock choice (`choose_mock_for_task`) → `browser_type {ref, replace:true}` → `get_browser_state semantic_v2` → mock choice → `browser_click {ref, input_route: dom_event}`. This reuses jev-use `run.py`/`tasks.py`/`jev_adapter.py` functions unchanged.
- **G_off:** the same after `set_agent_cursor_enabled {enabled:false}` immediately after MCP initialize.
- **API:** the caller first runs an eligibility read (`GET /` of the target page, over HTTP) and checks it against the documented contract (`action=/submit`, `method=post`, `field=value`). The documented contract comes from `fixture_server.py` PAGE and from `python/tests/test_fixture_server.py`, which POSTs `urlencode({"value": ...})` to `/submit`. The caller then sends one `POST /submit` (urlencoded `{value}`) built from that contract only. It never uses captured traffic and never retries.
- **Actual route/producer, observed per trial:**
  - G arms: the mock chose `type-verification-value`/`browser_type` (replace=true) and then `submit-form`/`browser_click` with `input_route=dom_event`; both Driver calls returned without error.
  - API: one POST with a status.
  - The fixture journal attributes every submit to its producer: the browser POST carries Origin, Referer and a browser User-Agent; the caller POST carries none of them.

**Per trial:**
- Before T, in every arm:
  - Start a fresh fixture server (port 0), a fresh `cua-driver mcp` and a fresh Chrome.
  - Run `browser_prepare`, wait for the window, bind, and run `browser_navigate`.
  - Wait for the browser's own `GET /` receipt in the journal, so every arm has the same initial page load.
  - Read the initial `/state`.
- Each trial uses a unique value: valid values are `r2-08-` + 12 hex; the N2 invalid value is `r2-08-INVALID-` + 6 hex.
- **T** starts at the send of the first observation (GUI) or of the first eligibility read (API). It ends at the return of the first `/state` read that shows the trial's value.
- After the final action returns, `/state` is polled every 2 ms up to 2000 ms. All arms use the same oracle and the same bounded re-read.

**Order.** 20 rounds, each running the 3 arms in rotation r mod 3: (G_on, G_off, API), (G_off, API, G_on), (API, G_on, G_off), …

**Equivalence signature** (pre-registered; compared per round across all three arms):
- the initial `/state` and the final `/state` (value normalised);
- the `POST /submit` receipts (method, path, content type, field set, value equality, status, effect, reason);
- the state mutations;
- the side-effecting (non-GET, non-harness) requests;
- the `/validate` count.

GET reads and transport headers are excluded by pre-registration and reported below.

**Negatives** (experiment-owned variants in `variants.py`, documented and UNIT-tested in `test_variants.py`). The GUI route is G_off and the API route is the base request shape, sent unchanged. Each variant ran 2 chunks of 10 alternating trials, giving n = 10 per route per variant.
- **N1 authorization.** Every render embeds a fresh server nonce in a hidden field. A `POST /submit` without the current nonce is refused with 403, and the refusal is journaled with `effect=refused`.
- **N2 constraint bypass.** The field has a client-side `pattern="r2-08-[0-9a-f]{12}"`, while the server keeps the base handler. The value is invalid. A probe script beacons the browser's `invalid` event; this is instrumentation, not a task effect.
- **N3 intermediate effect.** A page script POSTs the field value to `/validate` on every `input` event, and the server journals each one as a task effect. `/state` keeps the base shape.
- **N2 valid-value GUI control** (secondary, n = 3): the same N2 page with a valid value. It shows the N2 block is the constraint, not a broken page.

**Statistics.** D_r = T(API)_r − T(G_off)_r over rounds; median D with a percentile bootstrap 95% CI (10000 resamples, seed 20261002). Every trial is kept.

## Results

| Row | Result | Evidence class |
|---|---|---|
| Base: rounds equivalent (signature(API) = signature(G_off) = signature(G_on), all oracle-confirmed, constraints check) | **20/20** (differs 0, not established 0) | REAL (owned fixture) |
| Base: oracle-confirmed G_on / G_off / API | 20/20 / 20/20 / 20/20 | REAL |
| Base: forced path as assigned G_on / G_off / API | 20/20 / 20/20 / 20/20 | REAL |
| Base: journal shape, every trial | exactly 1 `POST /submit`, urlencoded, fields `[value]`, exact value, 200 accepted; 1 mutation; side effects `[POST /submit]` only; 0 `/validate` | REAL |
| Base: form constraints enumerated from the page (API eligibility read) | `{type text, required true, pattern null, maxlength null, minlength null}`, no extra fields, value satisfies → irrelevant for valid values, 20/20 | REAL |
| Base: differences outside the signature (descriptive) | API makes 1 extra GET read (the eligibility read); browser POST carries Origin + Referer + browser UA, caller POST none; no cookies either way | REAL |
| T median (p95), G_on / G_off / API | 3171.8 (3179.7) / 176.0 (180.2) / 1.56 (1.74) ms | BENCHMARK |
| Paired T(API) − T(G_off), median [95% CI] | **−174.4 ms [−175.7, −172.9]**, 20/20 pairs API faster | BENCHMARK |
| Paired T(API) − T(G_on), median [95% CI] | −3170.3 ms [−3171.6, −3169.1], 20/20 | BENCHMARK |
| N1: GUI predicted (confirmed, 1 accepted submit, fields `[nonce, value]`) | **10/10** | REAL |
| N1: API predicted (not confirmed, `/state` null, 1 submit fields `[value]`, 403, `effect=refused`, `missing_nonce`, 0 mutations) | **10/10** | REAL |
| N2: GUI predicted (type + click accepted, 0 submits, `/state` null, 0 mutations) | **10/10**; browser `invalid` beacon in 10/10 | REAL |
| N2: API predicted (invalid value lands, 1 accepted submit) | **10/10** | REAL |
| N2 valid-value GUI control (secondary) | 3/3 confirmed with 1 accepted submit | REAL |
| N3: GUI predicted (confirmed, 1 accepted submit, ≥1 `validate` with the value before the submit) | **10/10** | REAL |
| N3: API predicted (confirmed, same final `/state` shape, 1 accepted submit, 0 `validate`) | **10/10** (`validate` total 0) | REAL |
| Spec contract check (action, method, field name) on the variant pages | eligible on N1 10/10, N2 10/10, N3 10/10. It saw an extra `nonce:hidden` field (N1), a pattern the value fails (N2) and 1 script (N3), but none of these is part of the check | REAL |
| Correctness invariants, all 123 measured trials | 0 duplicate mutations, 0 duplicate submit requests, 0 POST retries, 0 GUI action retries, 50/50 API trials with exactly one POST, 0 errors, 10/10 refusals `effect=refused`, 123/123 initial `/state` null with page loaded before T | REAL |
| Unverified successes | 0: success is only the fixture `/state` read | SOURCE (by construction) |
| Programmatic request from the documented contract only | `api_task` builds the body from `DOCUMENTED_CONTRACT` | SOURCE |
| Fixture variants behave as documented; base serves the shipped page | 8/8 tests; jev-use `test_fixture_server.py` 3/3 | UNIT |
| Live provider | not used (mock chooser), 0 attempts / 0 reached | NOT_RUN |

### Component timings (base, median ms, n = 20 each)

| Component | G_on | G_off | API |
|---|---|---|---|
| observation 1 (`get_browser_state` semantic_v2) | 20.8 | 20.3 | — |
| decision 1 (candidates + mock + validate) | 0.07 | 0.06 | — |
| `browser_type` | 1603.3 | 126.8 | — |
| observation 2 | 6.0 | 5.7 | — |
| decision 2 | 0.05 | 0.05 | — |
| `browser_click` (dom_event) | 1540.4 | 22.0 | — |
| eligibility read (`GET /`) | — | — | 0.47 |
| contract check (parse) | — | — | 0.15 |
| `POST /submit` | — | — | 0.46 |
| verify (final action return → first confirming `/state`) | 1.15 | 0.92 | 0.43 |
| unattributed | 0.05 | 0.06 | 0.04 |
| **T** | **3171.8** | **176.0** | **1.56** |

- In G_off, `browser_type` is 72% of T and the two observations together are 15%.
- In G_on, the two visualized actions are 99% of T. This matches R2-01 (awaited cursor glide).

### Work deleted (separate from wall-clock saved)

Per trial, inside T. Every value is identical across all 20 trials of an arm.

| Work inside T | G_on | G_off | API | Deleted by API vs G_off / G_on |
|---|---|---|---|---|
| Driver calls | 4 | 4 | 0 | 4 / 4 |
| observations (semantic_v2 snapshots) | 2 | 2 | 0 | 2 / 2 |
| decisions (mock choices) | 2 | 2 | 0 | 2 / 2 |
| actions (`browser_type`, `browser_click`) | 2 | 2 | 0 | 2 / 2 |
| visualized actions (cursor glide) | 2 | 0 | 0 | 0 / 2 |
| caller HTTP requests | 1 (oracle) | 1 (oracle) | 3 (eligibility GET, POST, oracle) | −2 (API adds 2 caller requests) |

Wall-clock saved is the paired figure in Results: 174.4 ms vs G_off, 3170.3 ms vs G_on. Work outside T is not deleted in this design: browser_prepare, window, bind and navigate stay identical in every arm, because the spec requires the same initial page load. Skipping the browser entirely on the API route is **not measured**.

## E2 classification (input to #10 / #73)

For the reference task fill→submit on the base fixture, the alternate HTTP route deletes every GUI component of T: observation, decision, type, click and feedback. It is classified as an **eligible deletion only under proven per-task equivalence and authorization evidence**, and as **OWNER_DECISION**, not a default:
- Adopting it changes caller policy and route choice.
- The Driver is unchanged and policy-neutral.
- N1 to N3 show that the eligibility does not transfer to a superficially identical form.

This packet does not authorise a Driver contract, router, route miner or general programmatic-surface mandate. The RFC delta from this packet is **none** beyond the per-task eligibility rule.

## E4: what the negatives prove

- **A matching network shape is not authorization (N1).** The API's base request matched the shape proven equivalent on the base fixture and passed the contract check, yet the target refused it 10/10 with `effect=refused` and no state change.
- **A permitted direct request can bypass task constraints (N2).** The GUI was blocked 10/10, and the browser fired `invalid`; the direct POST landed an invalid value 10/10. A matching endpoint does not mean the same constraints apply.
- **A matching final state is not equivalence (N3).** The final `/state` had the same shape in 20/20 trials, but the GUI produced the server-side `validate` effect in 10/10 trials and the API in 0/10.
- **Every negative discriminated.** The base API arm passed 20/20, and each variant showed the predicted divergence in 10/10 trials per route.

## Controls

- Negative controls: N1, N2 and N3 as above. All three are discriminating.
- Fallback/positive controls:
  - The N2 valid-value GUI control (3/3), on the N2 page itself.
  - The N1 GUI arm (10/10 confirmed). This shows the nonce page works through the GUI, so the API refusal comes from the missing authorization, not from a broken variant.
- Uncertain outcome: no transport error happened. By construction a transport error on the POST or click is never retried; the oracle decides.

## Deviations

1. A pilot of 10 trials ran before PREREG to check the harness mechanics. It is declared in PREREG, kept in `raw/pilot/` and not used for any number above.
2. `analyze.py` was edited after the runs (declared in `provenance.json` `post_registration_changes`). Three invariant fields that were hard-coded constants (`api_post_retries`, and the SOURCE labels) are now computed from raw or labelled with their evidence, and two counts were added (`gui_action_retries`, `api_trials_with_exactly_one_post`). No gate, prediction, signature or statistic changed, and the disposition and every gated number are identical before and after.
3. `run_negatives.sh` (the host-side loop that ran the six negative chunks plus n2ctl) and `verify_artifacts.py` were added after registration. The loop invokes the registered harness with the registered plan.
4. The base lock receipt has no explicit `mode=` line. The base used `flock` without `-s` (exclusive), as recorded in `provenance.json`; the negative receipts carry `mode=shared`.
5. After the runs, the absolute lock path in `run_negatives.sh` was replaced by an optional fifth argument whose default resolves to the same lock file from the lanes root, so the committed script carries no local path. The behaviour is unchanged.
6. The base ran under the exclusive quiet-lane lock, but loadavg was 3.85 to 8.18 because other agents were active. The paired AB/BA rotation and the very large effect (all 20 pairs within −190.6 to −171.2 ms) make this immaterial to the gate. Absolute milliseconds are environment-specific.

## Limits and claim boundary

- **Scope:** one resettable owned fixture, loopback HTTP, X11 Xvfb, Chrome 151.0.7922.71, Driver 0.32.0 `8b037961`, mock chooser, one task (fill→submit).
- **Not claimed:** real sites, credentials, sessions/cookies, CSRF/Origin-checking servers, other tasks, other surfaces (CLI, AT-SPI), and macOS/Windows.
- **Header difference:** the signature excludes headers. The browser sends Origin and Referer and the caller does not, so a server that checks them would make the routes non-equivalent. This is a further reason why equivalence needs per-task evidence.
- **Nonce:** the API eligibility read of the N1 page itself minted a new nonce, so the page GET changes server state there. An API route re-derived from the N1 page (reading and sending the nonce) is a different route and needs its own authorization evidence. It is not tested.
- **Not measured:** API wall-clock without the browser setup.
- **Adoption** into the composed configuration (R2-10) is an OWNER_DECISION through #73/#74.

## Disposition

**KEEP** (pre-registered rule: G1 20/20 equivalent, G2 N1–N3 10/10 each, G3 CI [−175.7, −172.9] ms excludes 0).

Claim: *the existing HTTP form endpoint is an eligible and faster route for this task only with per-task equivalence and authorization evidence; the Driver stays policy-neutral; the caller chooses.*

## Files

- `PREREG.json`: the pre-registration.
- `variants.py`: fixture variants, documented contract and eligibility parser.
- `test_variants.py`: UNIT tests.
- `run_cross_surface.py`: trial harness.
- `run_in_session.sh`: isolation guard and identity receipts.
- `run_negatives.sh`: negative chunk loop.
- `analyze.py`: recomputes `r2-08-summary.json`.
- `verify_artifacts.py`: recomputation, counts, receipts, PREREG ordering, privacy scan.
- `provenance.json`, `source-head.txt`.
- `raw/{pilot,base,neg,n2ctl}/*/trials/*.jsonl`: one file per trial, with events, the summary and the journal.
- `raw/logs/`: sanitized session logs, lock receipts and UNIT logs.

The unsanitized mirror is at `<lanes>/artifacts/r2/R2-08/`.
