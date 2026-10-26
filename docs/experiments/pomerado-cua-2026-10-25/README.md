# Pomerado × CUA: optional website procedure reuse (downstream pilot)

**Status: PREREGISTERED / NOT_RUN.** No CUA or Pomerado integration has run from this packet. Do not report a speedup from this plan or synthetic validator tests.

- Tracking: https://github.com/kvnloo/cua/issues/161
- Reuse https://github.com/kvnloo/cua/issues/93 (R2-07), https://github.com/kvnloo/cua/issues/107 (state/read/checked execution), https://github.com/kvnloo/cua/issues/10 (whole-task accounting), https://github.com/kvnloo/cua/issues/73 (disposition), https://github.com/kvnloo/cua/issues/74 (sole promotion queue), and https://github.com/trycua/cua/issues/3963 (decided upstream RFC).
- External tool: https://github.com/Pomerado/pomerado — Pomerado AI, Inc., MIT licensed. Preserve original contributor credit.

## Hypothesis and ownership

Pomerado **mints a deterministic site/task-specific MCP integration**, not a cache of page contents or a way to reactivate stale browser refs. Its local open-source minter uses Playwright plus OpenAI model calls; its published integration runs without model calls. A new mint needs Node 24.21+ and an OpenAI API key; this pilot does **not** authorize paid mint calls, Pomerado Cloud, real accounts or third-party credentials.

CUA Driver retains its own observation/action authority. A Pomerado MCP tool executes **outside** CUA Driver; it cannot borrow Driver permissions, stale refs or safety guarantees. An opt-in *caller* may expose a separately authorized Pomerado tool for an exact site, task and read/write authority. The default route remains unmodified CUA. No Driver patch, global install, browser-profile attach or persistent login.

Success requires reducing **verified end-to-end task** cost, net of build, verification, errors and fallbacks, without wrong-target or unauthorized effects.

## Existing resettable fixture — no duplicate server

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

Pre-register label/selector churn, two plausible Submit buttons, changed form ancestor, stale document, wrong task inputs, unexpected redirect/origin, MCP unavailable, login expiry, unknown write outcome and concurrent resets. Expect refusal or a fresh bounded fallback. Write experiments use only the synthetic resettable form **after** read-only parity and separate permission validation. Never repeat a possibly committed write before independent /state reconciliation.

## Evidence

PREREG.json freezes cohorts and gates. Each observed task attempt needs **one** redacted JSONL receipt (cua.pomerado.trial.v1) described there. An independent /state oracle evidence reference is required; an MCP success response is not proof of website success. Record route actually executed and include all failures and fallbacks.

Once **real** receipts exist:

~~~sh
python3 docs/experiments/pomerado-cua-2026-10-25/analyze_receipts.py /path/to/redacted-real-receipts.jsonl
python3 -m unittest discover -s docs/experiments/pomerado-cua-2026-10-25 -p 'test_*.py' -v
~~~

The checker rejects malformed/mismatched four-trial blocks and missing proof; it publishes NOT_READY rather than timing claims unless coverage/safety criteria are met. Publish complete sanitized receipts and exact source/build/artifact pins. Report attempted + verified counts, route evidence, p50/p95 end-to-end time *including failures*, cold mint cost and warm amortization. Never call a mock-only result a live-provider benchmark.

## Upstream promotion gate

After independent evidence and maintainer selection, a caller-side origin/task-scoped plugin or example could expose Pomerado. It is never a built-in Driver dependency or state authority. Pomerado write permission must be independently granted; CUA authorization does not authorize its external calls. Fail closed on unknown effects, site changes or expired scope.
