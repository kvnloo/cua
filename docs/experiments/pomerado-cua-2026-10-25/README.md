# Pomerado × CUA: optional website procedure reuse (downstream pilot)

**Status: PREREGISTERED / NOT_RUN.** No CUA or Pomerado integration has run from this packet. Do not report a speedup from this plan or synthetic validator tests.

- Tracking: https://github.com/kvnloo/cua/issues/161
- Reuse https://github.com/kvnloo/cua/issues/93 (R2-07), https://github.com/kvnloo/cua/issues/107 (state/read/checked execution), https://github.com/kvnloo/cua/issues/10 (whole-task accounting), https://github.com/kvnloo/cua/issues/73 (disposition), https://github.com/kvnloo/cua/issues/74 (sole promotion queue), and https://github.com/trycua/cua/issues/3963 (decided upstream RFC).
- External tool: https://github.com/Pomerado/pomerado — Pomerado AI, Inc., MIT licensed. Preserve original contributor credit.

## Hypothesis and ownership

Pomerado **mints a deterministic site/task-specific MCP integration**, not a cache of page contents or a way to reactivate stale browser refs. Its local open-source minter uses Playwright plus OpenAI model calls; its published integration runs without model calls. A new mint needs Node 24.21+ and an OpenAI API key; this pilot does **not** authorize paid mint calls, Pomerado Cloud, real accounts or third-party credentials.

CUA Driver retains its own observation/action authority. A Pomerado MCP tool executes **outside** CUA Driver; it cannot borrow Driver permissions, stale refs or safety guarantees. An opt-in *caller* may expose a separately authorized Pomerado tool for an exact site, task and read/write authority. The default route remains unmodified CUA. No Driver patch, global install, browser-profile attach or persistent login.

Success requires reducing **verified end-to-end task** cost, net of build, verification, errors and fallbacks, without wrong-target or unauthorized effects.

## Original resettable fixture + downstream-only audited wrapper

Reuse the repository-owned fixture:

- libs/cua-driver/examples/jev-use/fixture_server.py: loopback GET /, independent GET /state, POST /reset, optional --visual-fixture.
- libs/cua-driver/examples/jev-use/python/run.py: existing CUA caller, with --provider mock --fixture-url ... --token ... --log ....
- libs/cua-driver/examples/jev-use/verify_setup.py: supported baseline preflight. It starts its own fixture; for matched comparisons run both tools against the **same separately managed** fixture origin and independently reset it between individual trials.

Start the existing fixture in an isolated Linux/X11/Chromium environment (not a user's authenticated browser):

~~~sh
cd libs/cua-driver/examples/jev-use
uv sync --frozen --python 3.12
uv run --frozen --python 3.12 python fixture_server.py
# In another terminal, baseline smoke:
uv run --frozen python python/run.py --provider mock \
  --fixture-url http://127.0.0.1:8765/ --log /tmp/cua-pomerado-baseline.jsonl
~~~

**Feasibility gate first:** verify the current Pomerado local minter accepts this loopback origin and can publish a **read-only** integration without accounts or privileged network changes. Its sign-in URL rules differ from ordinary navigation rules; do not assume localhost sign-in works. If unsupported, record BLOCKED and do not weaken safety checks. Confirm the local MCP host runs in the same isolation harness. After separate budget approval, Pomerado documents: npx -y -p pomerado pomerado-mcp mint --root /absolute/path/to/integrations. Never put OPENAI_API_KEY in chat, receipts or commits.

## Arms and ordering

- **A: actual CUA baseline.** Unmodified jev-use caller and its approved Driver actions. Check whether current run_steps / run_script can preserve task semantics and compare the eligible current batch/script route too; do not use an obsolete expensive per-step caller as the sole basis for advantage.
- **B: Pomerado warm procedure.** Local pinned, separately authorized, minted site/task tool routed by caller. Observe its structured response and the same external fixture oracle. Record all B retries, refusals, and fallback-to-A attempts as B *attempts*.
- **Diagnostic:** existing checked continuation / compiled-route results in #93/#107. No second cache, verifier or DSL.

Only run A/B after read-only parity. Use ABBA/BAAB blocks with independent resets per trial: 15 blocks of each order per workflow/variant (30 blocks / 120 attempts). Pin seed and interleave instead of running all A then all B. Freeze feedback settings, policy, model/provider, browser mode, action authority, task outcome and oracle. Record one cold mint and repeated warm use; calculate amortization at 1, 5, 20 and 100 uses. Different runtime browser versions/profiles are a confound to report, not a basis to claim caching alone caused a difference.

### Negative/changed-site cohorts

Pre-register label/selector churn, two plausible Submit buttons, changed form ancestor, stale document, wrong task inputs, unexpected redirect/origin, MCP unavailable, login expiry, unknown write outcome and concurrent resets. Expect refusal or a fresh bounded fallback. Write experiments use only the synthetic resettable form **after** read-only parity and separate permission validation. Never blindly repeat a possibly committed write. The original /state endpoint shows only the last value, not mutation count. Use the opt-in downstream /audit wrapper for synthetic write accounting, and **fail closed after an ambiguous timeout**: a momentarily empty /state and /audit does not rule out a delayed commit in flight. Require an independently bounded quiescence/reconciliation protocol before any further write; the tests explicitly demonstrate a write that lands after a caller timeout.


## Offline randomized trial manifest (no executor)

`plan_blocks.py` freezes a seed-derived, interleaved schedule without sending any
network traffic or creating real result receipts. For the frozen fixture and ten
negative variants it produces **330 planned blocks, 1,320 planned attempts**:
15 ABBA and 15 BAAB blocks per variant, 4 attempts per block. This is **only a
plan**, not 1,320 executions or evidence of a performance improvement.

~~~sh
python3 docs/experiments/pomerado-cua-2026-10-25/plan_blocks.py \
  --head-sha "$(git rev-parse HEAD)" \
  --output /tmp/pomerado-plan.json
python3 -m unittest discover -s docs/experiments/pomerado-cua-2026-10-25 -p 'test_*.py' -v
~~~

Each manifest pins the exact candidate HEAD, preregistration digest, seed and
manifest digest, with arm *assignment* explicitly separate from a traced
executed route. Every attempt still requires independent reset, /state
verification, and /audit accounting where available. The synthetic-write
*planning* mode requires a read-only proof SHA256 and remains non-executing; it
does not establish consent, a spend budget, or a verified read-only result.

## Evidence

PREREG.json freezes cohorts and gates. Each observed task attempt needs **one** redacted JSONL receipt (cua.pomerado.trial.v1) described there. An independent /state oracle evidence reference is required; an MCP success response is not proof of website success. Record route actually executed and include all failures and fallbacks.

Once **real** receipts exist:

~~~sh
python3 docs/experiments/pomerado-cua-2026-10-25/analyze_receipts.py /path/to/redacted-real-receipts.jsonl
python3 -m unittest discover -s docs/experiments/pomerado-cua-2026-10-25 -p 'test_*.py' -v
~~~

Before accepting a complete cohort, validate **every planned attempt** against the
immutable plan, separately from the per-receipt analyzer:

~~~sh
python3 docs/experiments/pomerado-cua-2026-10-25/verify_plan_coverage.py \
  --plan /tmp/pomerado-plan.json \
  --receipts /path/to/redacted-real-receipts.jsonl \
  --prereg docs/experiments/pomerado-cua-2026-10-25/PREREG.json \
  --expected-head "$(git rev-parse HEAD)" \
  --expected-manifest-sha256 "$INDEPENDENT_PREEXEC_MANIFEST_SHA256"
~~~

Capture `INDEPENDENT_PREEXEC_MANIFEST_SHA256` from the **canonical `manifest_sha256` field** in a separate, immutable, reviewed pre-execution handoff, before any trial receipts. Never derive it from the plan being validated: a self-digest can be recomputed after balanced ABBA/BAAB assignments change. Missing/mismatched external pins now fail closed; neither digest authenticates execution or independent oracles.

The exact 40-character HEAD must match the **pre-execution** plan's candidate
SHA, not whichever source HEAD is current after later edits. Coverage fails
closed if even an entire four-attempt block is omitted, if a planned attempt
is replayed, if the A/B order or route assignment was changed, or if the
preregistration and manifest digests disagree. Observed fallbacks are counted
as attribution confounds, never silently discarded. **A passing result only
proves plan/receipt consistency**, not actual CUA or Pomerado execution,
authority, independent oracles, or timing. Complete coverage and the
independent /state + /audit evidence gates are all required before any real
descriptive comparison. This tool never launches a runner, model or site.

The checker rejects malformed/mismatched four-trial blocks and missing proof; it publishes NOT_READY rather than timing claims unless coverage/safety criteria are met. Publish complete sanitized receipts and exact source/build/artifact pins. Report attempted + verified counts, route evidence, p50/p95 end-to-end time *including failures*, cold mint cost and warm amortization. Never call a mock-only result a live-provider benchmark.

## Boat VM lane (2026-10-26) — FIXTURE_BROWSER_ONLY, not an A/B result

This is **operator-supplied environment evidence**, not a confirmed execution
of a CUA/Pomerado comparison or of this branch's Driver. Environment: Boat
disposable Ubuntu 24.04, 4 vCPUs, real Chromium 151.

| Observation | Evidence class / conclusion |
| --- | --- |
| Experiment Python unittest suite: **56/56** passed | UNIT_ONLY; validates packet and fixture logic, not Driver/Pomerado tool dispatch |
| `smoke_browser.py --repeat 5`: **40/40** passed in Chromium 151 | **FIXTURE_BROWSER_ONLY**; `read_only`, `submit`, `duplicate_target` refused ambiguous, `renamed_target` refused changed, `visual_only`, `origin_escape` refused origin, `wrong_input`, `uncertain_commit` reconciled without repeat (five repetitions each). This script explicitly uses Playwright, **not** CUA or Pomerado |
| Boat's preinstalled `cua-driver --version`: **0.23.2** (latest component version reported at investigation: **0.38.0**) | NOT branch-built. Its `browser_prepare` refused with `browser_route_unavailable` until **both `/opt` and `/opt/google`** were changed to `root:root`; no successful branch Driver route is established |
| Pomerado **0.4.0-canary.399** MCP exposed `get_job`, `provide_input`, `cancel_job`, `mint` with no API key | MCP discovery only. No mint, integration execution, cost, or Pomerado website procedure proof |

**Every A/B trial cell remains `NOT_RUN`.** No 30-block/variant cohort, no
Driver-versus-Pomerado outcome, no warm-reuse savings, and no mint budget was
tested. Do not import these smoke counts as trial receipts.

### Branch-built Driver + Chrome safety preflight on a fresh Boat VM

`boat_setup.sh` is a separate opt-in CUA **mock fixture setup probe**, not the
Pomerado arm. Run it only inside a **full clean checkout** of Draft PR #162's
`exp/pomerado-site-procedure-20261025` branch, with Cargo, uv, Python 3.12,
a working local Linux desktop/Chromium session, and the reviewed exact PR
head SHA. The existing CI `boat-fixture-only` bundle copies only fixture
files; it is **not** a full branch checkout and cannot run this source build.

~~~sh
# Supply the SHA copied from the *current PR head*, not a locally assumed ref.
PR_HEAD='replace-with-current-reviewed-40-character-PR-head-SHA'
bash docs/experiments/pomerado-cua-2026-10-25/boat_setup.sh \
  --expected-head "$PR_HEAD"

# ONLY after inspecting any exact sudo chown/chmod recommendations, opt in:
bash docs/experiments/pomerado-cua-2026-10-25/boat_setup.sh \
  --expected-head "$PR_HEAD" --fix-ownership
~~~

The default **refuses before build/launch** if Chrome is missing, symlinked,
not root-owned (`uid=0`, `gid=0`), or group/other-writable at `/`, `/opt`,
`/opt/google`, `/opt/google/chrome` or the browser executable. It prints
exact one-path remediations, for example `sudo chown root:root /opt`
and `sudo chown root:root /opt/google`, **without** changing ownership. The
flag performs only explicit, nonrecursive owner/mode repairs of existing
non-symlink paths, then rechecks; missing/unsafe path types still refuse.

The script rejects wrong branch/head or modified tracked sources, records
the preinstalled Driver version without selecting it, **builds** CUA Driver
with `cargo build --locked --release -p cua-driver --bin cua-driver` from
the exact checkout, embedding the reviewed Git HEAD, and checks the
selected `cua-driver --version` against the Rust workspace version. It also
reads `cua-driver doctor --json` and **refuses** if the *running executable's*
`build.version`, `build.git_sha` or `build.exe_sha256` disagrees with the
expected version, reviewed HEAD or independently hashed file. The only
allowed active Driver is the source-built
`libs/cua-driver/rust/target/release/cua-driver`, passed to the Jev MCP
runner as `CUA_DRIVER_BIN`. Version equality **alone** does not prove source
identity. The temporary private receipt retains HEAD, version, binary SHA-256
and the separate Doctor environment-probe exit code; unrelated Doctor probe
errors never become proof of browser readiness.

Only after those gates, the script starts `fixture_server.py --port 0`,
verifies a loopback `/state` clean oracle, shuts that process down, then runs
`verify_setup.py --output-dir` on a **fresh, previously nonexistent** evidence
directory (the verifier owns its own fixture). Results stay in an isolated
`/tmp/cua-boat-jev.*` directory for inspection; a failure is never promoted
to a passed setup claim. This tests the mock CUA Driver path **only** when
actually executed, not Pomerado or A/B.

Unprivileged, bats-free fake-root tests (no real `/opt`, sudo, model, network
or browser) and syntax checks:

~~~sh
python3 -m unittest discover \
  -s docs/experiments/pomerado-cua-2026-10-25 -p 'test_boat_setup.py' -v
bash -n docs/experiments/pomerado-cua-2026-10-25/boat_setup.sh
shellcheck docs/experiments/pomerado-cua-2026-10-25/boat_setup.sh
# Then rerun the full existing packet (these are UNIT, never A/B):
python3 -m unittest discover \
  -s docs/experiments/pomerado-cua-2026-10-25 -p 'test_*.py' -v
~~~

## Audited synthetic fixture reset barrier (2026-10-26; no CUA/Pomerado)

A late `POST /submit` from trial N could previously land after a successful
`POST /reset` and appear as trial N+1's first committed write. Even a matching
`/state` value plus `/audit.commit_count == 1` would then misattribute the
effect. The downstream-only `audit_fixture.py` now returns **HTTP 409** rather
than resetting while any *observed in-flight* submit is dispatching or awaiting
its acknowledgement; after the request settles, reconciliation and an explicit
reset can proceed. This does **not** authorize an automatic retry of the
original write.

Two new real-HTTP fixture regression controls cover the dispatch-delay and
lost-ack windows. Both failed against the previous exact audit fixture and
passed with this guard, alongside the original nine HTTP fixture controls
(11/11 locally, three runs). This is **FIXTURE_HTTP_ONLY**, not browser, Driver,
Pomerado, Avrea or Boat evidence. The guard cannot detect requests still queued
*outside the HTTP handler* or prove which external executor submitted a write.
Operators must quiesce both executors, reconcile uncertainty, then independently
verify `/state`, `/audit` and route receipts before starting a new ABBA/BAAB
trial. No actual A/B experiment is unblocked by these tests alone.


## Monotonic write oracle amendment (2026-10-26; fixture HTTP + UNIT only)

An additional reset **between two completed submissions** previously erased
the first write from the per-reset `/audit` journal. A trial with two actual
effects then appeared to have only one commit. The downstream-only fixture
now exposes `reset_epoch` (increments on each accepted reset) and
`total_commit_count` (monotonic for the fixture process) alongside
`commit_count` and the redacted per-reset journal.

Receipts must capture both monotonic counters **before and after each
attempt**. The analyzer refuses a changed epoch, decreasing or noninteger
counts, or a lifetime write delta different from the per-reset write delta.
These gates apply to all outcome classes and must never be inferred from the
tool response or self-reported route. Resets rejected with 409 do not advance
the epoch. External host/process restart, connections not yet handled, and
fabricated receipts remain distinct risks; quiescence, source/binary pins,
independent route traces, and exact pre-execution manifest SHA256 are still
required. Previously generated offline plans must be regenerated after this
preregistration amendment and their digest independently retained.

In a local loopback reproduction against the former exact audit fixture
(blob `218dcccac0f2f410038a24b7eae2f82b78074468`), two identical
submits separated by a reset yielded `/audit.commit_count == 1`.
The amended fixture exposed `total_commit_count == 2` and a changed epoch.
New tests and analyzer controls are **fixture HTTP / UNIT only**, not
proof of Driver, Pomerado, Avrea, Boat, or real A/B execution.

## Fixture-process incarnation gate (2026-10-26; FIXTURE_HTTP_ONLY + UNIT_ONLY)

An audited-fixture **restart on the same TCP port** resets both `reset_epoch`
and `total_commit_count`. Two committed writes before the restart can therefore
disappear from a post-restart `/audit` check with the *same* integer counters.
Neither `/state` nor per-reset counts can detect that loss.

The downstream-only `/audit` response now includes a **new 128-bit random
`instance_id` for each fixture process**, stable across ordinary resets. Trial
receipts must record `fixture_instance_before` and `fixture_instance_after`
from **independent** pre/post `/audit` reads. The receipt analyzer requires
matching 32-character lowercase hex values per trial and the same fixture
instance across trials in each ABBA/BAAB cohort. A restart invalidates that
comparison; it does **not** authorize retrying a possibly committed write.

The red reproduction used the original fixture and analyzer exact Git blobs:
two real synthetic HTTP commits before stopping the fixture, then a fresh
fixture bound to the same port, reset to the same epoch and zero counters.
Before the patch, there was no process identity to compare and fabricated
receipts with mismatched identities were accepted. After the patch, 35
focused tests passed twice locally on GitHub-identical original source plus
the proposed exact patch: 14 fixture-HTTP and 21 UNIT cases per run. Full
repository CI/Boat/Avrea and real CUA-vs-Pomerado comparison remain NOT_RUN.
The nonce is a *restart detector*, not authentication of route or oracle
provenance, and cannot detect lost writes outside a single fixture process.
All offline trial plans must be regenerated and independently re-pinned
after the preregistration change.

## Upstream promotion gate

After independent evidence and maintainer selection, a caller-side origin/task-scoped plugin or example could expose Pomerado. It is never a built-in Driver dependency or state authority. Pomerado write permission must be independently granted; CUA authorization does not authorize its external calls. Fail closed on unknown effects, site changes or expired scope.

### Consecutive trial handoff (2026-10-26, UNIT-only)

For positions 1–4 in each ABBA/BAAB block, individually verify exactly one independent reset between attempts: the next pretrial `/audit.reset_epoch` must be the prior posttrial epoch + 1, on the same fixture `instance_id`. The next pretrial `total_commit_count` must equal the prior posttrial count. A missed/double reset or intertrial write invalidates the block even if each individual pre/post pair looks clean. Preserve receipts for all refusals, timeouts, and fallbacks. This gate checks **internal consistency, not authentication** of route execution or independent oracle evidence. Cross-block scheduling still requires an externally retained frozen manifest and independently checked observations; no actual A/B comparison has run.
