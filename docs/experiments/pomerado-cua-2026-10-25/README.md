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
  --expected-head "$(git rev-parse HEAD)"
~~~

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

## Upstream promotion gate

After independent evidence and maintainer selection, a caller-side origin/task-scoped plugin or example could expose Pomerado. It is never a built-in Driver dependency or state authority. Pomerado write permission must be independently granted; CUA authorization does not authorize its external calls. Fail closed on unknown effects, site changes or expired scope.

## Arm C (opencli adapter over CDP) and arm-B MCP glue (2026-10-26)

Added on `exp/opencli-arm-20261026`. Caller-side only; no driver change; no model call; no token.
Credit: Pomerado is MIT (Pomerado AI, Inc.); opencli is jackwener/opencli (downstream fork kvnloo/opencli).

- `arm_c/jev/read-status.js` (read) and `arm_c/jev/submit-value.js` (write, `access: 'write'`, needs
  `--confirm-write yes`): copy to `~/.opencli/clis/jev/`. Both refuse any origin except
  `http://127.0.0.1:PORT`. `navigateBefore: false`, because the default would be `https://<domain>`.
- `run_arm_c.py`: one attempt, one receipt, `arm=C`, `route_observed=opencli-adapter-cdp`. It sets
  `OPENCLI_CDP_ENDPOINT` (extension and daemon are bypassed). Chromium is started by the caller with
  `--remote-debugging-port` (attach-only, identical warm state for every arm). Extra receipt field
  `opencli_sha` (REAL: exact SHA or `sha256:`) is required on arm C rows and fixed per cohort.
- `run_arm_b.py` + `mcp_stdio.py`: spawns `pomerado-mcp serve --artifact DIR` (no model request), speaks
  newline-delimited MCP JSON-RPC, calls one tool, polls `get_job` only for a pending job, never calls
  `provide_input`, never replays. A read attempt refuses a tool without `readOnlyHint`. The artifact must be
  minted separately (blocked until the owner approves budget); this script never mints.
- `arm_common.py`: reset via `POST /reset`, require empty `/state` and `/audit` `commit_count == 0`, run, read
  the oracle again, and judge from `/state` and `/audit` rather than the arm's own report. Failures are recorded
  as `route_observed=blocked`, with `fallback_count` 0. Writes need `--allow-write` and a 64-hex read-only proof.
  Default evidence class is `UNIT`; `REAL` requires exact SHA pins.
- `plan_blocks.py --arms ABC` plans pairwise blocks AB, AC, BC (four attempts each, XYYX/YXXY), with
  `arm_pair` on each block. The default `--arms AB` output is byte-identical to before (same manifest hash).
  `verify_plan_coverage.py` still accepts two-arm AB plans only, and rejects a three-arm plan.
- `analyze_receipts.py` accepts arms A, B, C. A block is two arms in XYYX order. Each pair is its own cohort:
  `workflow/variant` for AB (unchanged keys), `workflow/variant[AC]` otherwise, with
  `paired_median_<second>_minus_<first>_ms`. Each non-A arm in a pair needs a measured `mint_ms`.

Tests (UNIT only: fake `opencli` and fake `pomerado-mcp` executables on the real audited fixture):

```bash
python3 -m unittest discover -s docs/experiments/pomerado-cua-2026-10-25 -p 'test_*.py' -v
```

Local smoke (mbp, 2026-10-26, UNIT-labelled, NOT an A/B result): `opencli adapter check jev/read-status` passed; three
`run_arm_c.py` read attempts against the audited fixture with Chrome 155.0.8059.79 (headless, CDP attach) and opencli
916705f were oracle-verified with `audit_after == audit_before == 0`. Wall time was 42.6 s (cold, first call), then
about 10 to 14 s warm, which is dominated by opencli process start and CDP attach. Arm B has no real artifact yet
(mint is blocked on the owner's budget approval), so its glue is covered only by the fake-server tests.
