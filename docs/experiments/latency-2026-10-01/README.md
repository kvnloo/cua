# CUA latency research: independent bounded evidence, 2026-10-01

## Result in one paragraph

The exact `#4316` candidate passes the locked source tests and an independent same-input Python/TypeScript guard corpus. In **30 interleaved pairs using the real caller loop, simulated Driver transport and a real HTTP fixture oracle**, guarded completion deletes one mock provider decision (2 → 1), but does **not** improve this cheap-mock latency distribution. A separate real Linux Mousepad experiment confirms useful AT-SPI objects and semantic actions; **6/6 pointer and 6/6 indexed accessibility toggles verified**, but accessibility was slower through this service interface. A fixture-owned event experiment deletes a fixed 100 ms polling sleep while preserving fresh oracle reads. This packet does **not certify native #4316, real Chromium stitching, or a production speedup**.

## Pinned sources and scope

- Tested upstream PR: `trycua/cua#4316`, `a0bca744067d04f05904319d3d919be30c336556`
- Its parent: `345ff6d9db458a9d37b0f420dc4555553f4a4ce5`
- Upstream main fetched separately: `cddd8014fba15324c4c432f55217a4558ccdc43a`
- Canonical context: `kvnloo/cua#73`, `#93`, `#94`, `#59`, `#74`; captured issue bodies included
- Other author's native results linked in those issues are **not** counted as this independent reproduction
- No upstream posts, paid provider requests, production API replay, credential capture, new verifier, new authority store, lifecycle service or competing batch API

## What executed

### P0: guarded completion

- `uv sync --frozen`; **248 Python tests, 1 intentional skip**, pass
- `npm ci --ignore-scripts`; **155 TypeScript tests**, pass; typecheck pass
- **36 identical guard inputs** across actual Python and TS implementations: exact telemetry/candidate-ref parity
- **30 AB/BA-interleaved pairs**: both routes independently verify fixture submission
- Baseline provider calls **2**, guarded **1**; both perform **3 browser-state transport calls** (one bind plus two semantic step observations), **2 actions**, **0 screenshots**, **0 visual parses**
- Accepted proof exposes different prior/fresh refs; foreign-session decline is `session_mismatch`; stale ref decline is `ref_reused`; both fallback runs make two chooser calls
- Ambiguous target declines the guard with `submit_not_unique`, falls back to a second chooser decision and verifies through the fixture. The no-effect action control stays `budget_exhausted`/unverified despite accepted dispatch
- Paired transport timing p50: baseline **7.459 ms**, guarded **7.718 ms**; p95 nearest-rank **10.221 / 15.810 ms**. No speedup claim
- CPU p50: **6.631 / 7.612 ms**. These are local process figures, not native Driver CPU
- First baseline/treatment **18.123 / 21.557 ms** are recorded. They are first-trial measurements, not a qualified cold-browser benchmark
- Actual per-step `semantic_observe_ms`, `visual_observe_ms`, `candidate_build_ms`, `provider_decision_ms`, `action_ms`, `total_step_ms` remain in raw JSONL. They retain upstream millisecond rounding. Whole-task timer includes independent final HTTP verification; do not substitute summed step spans
- `guarded-loop-profile.txt` identifies costs in this **instrumented simulated-transport runner**, not a native browser/Driver profile

The forced path has an empty field initially, requires typing before Submit can verify, and returns a newly numbered ref after mutation. `run_p0_trials.py` invokes the unmodified production example runner; its contract transport is explicitly simulated. The fixture HTTP endpoint owns success. This proves caller/control-flow deletion, **not real Driver freshness enforcement or model quality**.

### P4: native Linux structured control

The shell exposes no desktop variables and prohibits AF_UNIX socket creation, but the separate cloud desktop is live: Xfwm4/X11 window inventory, Mousepad GTK and an explicit `at_spi` tree. That tree exposes buttons, text, checkbox checked state, focus, disabled state and menus.

An indexed `To Uppercase` action changed selected `a` to `A`, confirmed in fresh app text and screenshot. This avoided opening the menu via pointer. A pointer route produced the same result through Edit → Convert → To Uppercase.

For the controlled Match case checkbox, six alternating AB/BA pairs all changed the app's independently read checked state. Native `at_spi` whole-task median is **1307 ms**, pointer **1024.5 ms**; nearest-rank p95 is **1778 / 1218 ms** respectively (only n=6 each; tail estimate is weak). Both routes read fresh app state before and after. The pointer coordinates came from a setup screenshot and current window bounds were rechecked; this is **not** a screenshot/vision-per-step baseline. The accessibility route deletes an **explicit pointer-click API call**, but raw backend pointer events were not instrumented. Its API-level route attribution is weaker than a Driver trace. Remote CPU/memory, bytes/tokens and exact Driver version are unavailable.

Negative result: Linux `setValue` explicitly refuses, preserving the field. `typeText` failed with `editable Paste did not insert text`; an ordinary single-character key fallback worked. AX includes hidden menus/toolbars: an AX node census cannot automatically claim all nodes are currently visible.

### P5: fixture event wake

The current runner's completion loop (`python/run.py` around lines 654–661) reads its oracle then sleeps 100 ms up to 20 times. `run_event_wait.py` forces completion after 15 ms and compares that wait shape with a fixture-owned event, followed by the **same actual HTTP oracle read**.

- 20 interleaved normal pairs: polling p50/p95 **102.628 / 103.750 ms**, event **16.580 / 17.355 ms**
- Both perform **2 fresh reads**; polling has **1 fixed sleep**, event **0**
- CPU p50 **2.182 / 2.230 ms**: no CPU saving established
- Spurious wake does not verify; missing event causes a deadline read, not an assumption of freshness; timeout and refuted outcomes pass
- Subscribe before dispatch to avoid lost-wake races. Event absence never authorizes mutation

This is an executed **Python fixture event mechanism**, not an AT-SPI/CDP event implementation or measured production latency gain. The forced 15 ms delay and 100 ms polling interval explain this local benefit.

### P6: limited correctness probe

Five existing-guard prepare/commit projections pass: cold, correct prediction, wrong prediction, target invalidation and stale session. They execute **zero mutations**, and always run the actual existing guard against fresh sources. Wrong prediction, target disappearance and session change refuse. These tests do **not** demonstrate overlapping preparation with native action or critical-path savings.

## Source census and prototype

`capability-census.json` separates **observed**, **source-inferred**, and **unavailable** fields; it contains no invented live Chromium coverage percentage.

The existing driver already has much of the requested stitching:
- `browser/semantic.rs`: `SemanticNode` carries AX identity, backend ID, role/name/value/state, frame, visibility and actions
- `browser/store.rs`: `RefEntry` binds backend identity and declared actions; `SnapshotRecord` and `BrowserStore.resolve_ref` own session/generation/snapshot validity
- `browser/tools.rs`: `dom_event` resolves the current backend node into an ephemeral runtime handle and invokes `Runtime.callFunctionOn`; this is an explicit opt-in route and reports application effect unverified
- `browser/cdp_ws.rs`: a pooled event-capable demultiplexer already exists

Backend IDs and frame identity are intentionally private. Do not build a new public handle authority or a global world model.

`stitched_object_probe.rs.inc` is the smallest **uncompiled, test-only attachment prototype** using the existing store fixture/resolver. It makes all attached handle access contingent on current authority and checks cross-layer backend-ID equality. `apply_stitched_probe.py` places it in the existing test module in a disposable exact-head checkout. It is not live DOM/AX identity proof, has no mutation path, and is not ready to promote.

A source hypothesis worth measuring next: `dom_event` awaits `visualize_browser_action`, which on Linux can await cosmetic cursor arrival before delivering the DOM call. This proves an awaited path exists; it does **not prove** it caused the other owner's ~1.5 s action spans. Rank the controlled enabled/disabled feedback experiment before redesigning routing.

## Exact environment and execution boundaries

`machine-manifest.json` contains requested shell command output, return codes and errors (ephemeral container hostname redacted in this public copy; result manifest hashes point to this redacted copy). `machine-manifest-augmented.json` adds the separately observed desktop capabilities. Do not equate shell resources with an independently measured desktop-server manifest.

- Debian 13.6 x86-64, kernel 6.18.44; `nproc=9`; RAM 9.7 GiB; overlay 32 GiB / 23 GiB available at capture
- Python 3.12.14 and Node 24.19.0; shell Chromium 151.0.7922.173
- `lscpu` cannot read CPU sysfs; `lspci` and `rustc` absent; no `/dev/dri`
- Shell Chromium fails AF_UNIX `socket()` with EPERM, including one approved escalated execution. AF_INET loopback HTTP succeeds
- Browser service rejects shell loopback (`ERR_BLOCKED_BY_CLIENT`); a standalone offline data URL was also refused by its protocol policy. No alternate endpoint/transport workaround attempted afterward
- Documented cloud browser API offers read-only DOM/locator actions, not raw CDP handle access or arbitrary event subscriptions
- Native service offers AT-SPI actions but no raw subscriptions/CPU profiler/build identity

## All requested deliverables

| # | Deliverable | Status |
|---|---|---|
|1|Exact machine manifest|Captured shell commands and separate desktop observations; service-internal details explicitly unavailable|
|2|Independent #4316 results|Source/contract reproduction complete; real Driver reproduction blocked|
|3|E0 structured census|Machine-readable source/observed/unavailable split; live Chromium census blocked|
|4|Stitched Chromium prototype|Minimal existing-store test attachment supplied; uncompiled, real Chromium proof blocked|
|5|Pointer/DOM/accessibility A/B|Real native pointer/AT-SPI 6+6; browser A/B/C blocked|
|6|Structured native Linux|Mousepad semantic transformation and checkbox A/B executed|
|7|Event wait|Fixture event + same HTTP oracle executed; OS/CDP event integration blocked|
|8|Prepare/commit|Five guard correctness projections; native overlap/performance unexecuted|
|9|CPU/profile|Local instrumented caller profile plus CPU/RSS; remote desktop profile unavailable|
|10|Deleted stages|One chooser call, one explicit native pointer call, one fixture fixed sleep; no generalized observation/vision/token savings claimed|
|11|Failures/regressions|Native typeText failure; unsupported setValue; hidden AX nodes; semantic route slower; browser/IPC restrictions; no source regression found after locked dependencies|
|12|Reproducible artifacts|Scripts, raw trials/logs, pinned sources, manifests and self-check included|
|13|Downstream publication|Evidence-only branch/draft; exact published SHA supplied outside this report; no upstream promotion|
|14|Next25|Ranked JSON with explicit planning priors and cost assumptions|

P7 orthogonal browser/native execution and independently owned server/file state is incomplete; the P0 transport fixture owns its HTTP oracle, while native checkbox uses fresh app state over the same observation interface. P8 GUI→trace→equivalent route→negative replay and P9 fully compiled routines remain **unexecuted**, not certified by the small guard or event tests.

## Reproduction

From this evidence directory, create the pinned source directory (not included in the bundle):

```sh
EVIDENCE_ROOT="$PWD"
git clone --depth 1 https://github.com/trycua/cua.git cua
git -C cua fetch --depth 2 origin refs/pull/4316/head
git -C cua checkout --detach a0bca744067d04f05904319d3d919be30c336556
cd cua/libs/cua-driver/examples/jev-use
uv sync --frozen
npm ci --ignore-scripts --no-audit --no-fund
.venv/bin/python -m unittest discover -s python/tests
npm test
npm run typecheck
cd "$EVIDENCE_ROOT"
cua/libs/cua-driver/examples/jev-use/.venv/bin/python run_p0_trials.py
cua/libs/cua-driver/examples/jev-use/.venv/bin/python run_parity.py
cua/libs/cua-driver/examples/jev-use/.venv/bin/python run_event_wait.py
cua/libs/cua-driver/examples/jev-use/.venv/bin/python run_prepare_contract.py
python verify_artifacts.py
```

Use the recorded SHA, not a moving PR head. Re-run the manifest first on another machine and keep old results separate. Source tests can execute without native Driver; this is not a substitute for the blocked real-browser gates. Native replay requires the documented cloud desktop interface and freshly discovered application/window IDs, never historical coordinates as authority. See `native-probe-recipe.js`.
