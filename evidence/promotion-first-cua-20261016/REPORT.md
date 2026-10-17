# Lane 3 CUA — exact-head evidence; no remote writes

## Goal and authority

User items 3, 6, 19, 24, 25, 28 and 29. Existing carriers only; parent is sole remote writer. Read current factory policy/registry and full CUA #74 collection (26/26 comments). Linear is retired. No ownership takeover, merge, force push, workflow approval/recheck, legal attestation, phone pairing, native-device mutation or denied-write retry was performed. No child worker was spawned. All product worktrees remain unchanged, except the explicitly labelled #5362 baseline test-file overlay. Independent review of this new evidence packet is still required; prior authors' reviews are not relabelled as ours.

Canonical queue: https://github.com/kvnloo/cua/issues/74

## Results and exact next gates

| Item | Exact tested/live head | Newly executed evidence | Remaining gate / disposition |
|---|---|---|---|
| #4316 guarded completion | `9ab4878e4933897b33c34ef00e776400a947ee30` | Complete Python suite: 248 run, OK with 1 documented cua-s1 skip. Focused guard8 and verify_setup21 overlap the full suite. Node22.23.2 TypeScript155 pass; typecheck pass. | Existing accepted-proof/decline-reason changes remain on the carrier. f-trycua CHANGES_REQUESTED persists. Exact-head jev-use workflow37810129551 is action_required with zero jobs. No fresh full Driver/Chromium guarded acceptance or speedup claim. No additional re-review ping. |
| #3961 OpenJev | `6ece26927ab4c532af8fb459c2de6434a8339aa0` | Complete Python suite: 248 run, OK with 1 documented cua-s1 skip. Focused19 includes existing real CLI subprocess/owned loopback HTTP coverage and overlaps full suite. Node22.23.2 TypeScript116 pass; typecheck pass. | f-trycua backend-only scope preserved; CHANGES_REQUESTED remains. jev-use38913473901 action_required, zero jobs. External OpenJev service/Driver/native desktop not tested. |
| #122 represented by origin #5362 | `0cc1cf92099c21f6078c5c31d8785216bbce6430` | Full SDK TypeScript build/typecheck pass. Real Node22.23.2 fetch/loopback tests56 pass. Full original base `85d001220940b7fb171634ba5de9262082fbbdd3` built with candidate test-file overlay:53 pass/3 expected fail (pre-aborted request and caller abort/timeout during partial body). | **Newly reconciled blocker:** CLA and contributor-attribution FAIL, not merely held. CLA bot reports codex unsigned; attribution job117023417390 says original `f031cbbe` author codex differs from landing author and lacks an explicit source PR. No fabricated source PR, identity mapping, rewrite or signature. Human/maintainer attribution/admission resolution required. SDK38915972398 action_required, zero jobs. Do not create another cancellation PR. |
| #149 represented by origin #5374 | `254848a874ef9be2c730b1bf3c04935b92d35979` | Ruff lint/format pass. Exact repository release-title validator and `validate_release_versions.py --product sandbox` pass. Built real sdist and wheel with small build-only tooling; wheel's adb.py equals exact source bytes. | Original15 cannot collect: current package imports missing fleet_sdk (supported Python3.11 attempt); Python3.14 attempt also lacks jsonschema and is outside package range. No new15/20 or Android acceptance. Existing ADB server read-only inventory returned zero devices. Native SDK/full hermetic package suite and hosted approval remain missing. No fake adb/guest-termination claim. |
| #5256 | `355c6736f9e73a58071c75cbb3ddc7ad7c9725c6`; main `24f6fc04d892468defc1f6efff1db5df91e1c369` | Real isolated headless Chromium153 preserves `opacity: 0 !IMPORTANT` / mixed-case priority, computes ancestor opacity0 and child opacity1 with positive bounds. Exact compiled Rust predicate extraction from old base returns hidden=true; head/current return false. Lowercase, no-priority and visible-opacity controls retained. | **LIMITED:** browser facts + real exact-source predicate execution, NOT full Driver semantic_v2/MCP/native platform acceptance. #5256 merged as `a212cd026e260c6e397efd105726e20a2f914144`. Potential follow-up belongs to injaneity; no production edit or takeover. Full pipeline reproduction and owner coordination still required. |
| #5184 | `85509ff6dbe81c1245b4aa2ba662301a3f711817` | Live reconciliation: closed/unmerged, maintainer explicitly redirects to #5372. #5372 merged at `8a66f0d8d9553e3f5fdc52e265755aff0f06c5d3`, head `fd94532858ee3e42196ddac5d3ce62b341810e89`. | Original fynixart credit retained. Linux host cannot certify macOS AX-focus. No new implementation target or false acceptance. |
| #5286 | `a5a73c29d1ac6a5211ff222441aa35b1b5fb6576` | Exact CI failure log recovered: Linux native driver compiled, then docs generator reports drift in window-state.mdx and cua-driver-mcp-linux.json. Local exact-head native build attempted under nonblocking shared build lock with -j2, stopped before compilation: offline rquickjs unavailable. Prepared local Sway1.12 verified by --version, not launched. | Actual pure-Sway discovery remains NOT RUN. No masking /run/user host paths, no host compositor access, no unpinned Driver substitution. ceckert owns implementation; coordinate generator repair and prepared native dependency/toolchain before further tests. |

All five refreshed open carrier heads matched the initial pins at final readback. GraphQL mergeStateStatus returned UNKNOWN on final reads; earlier REST snapshots reported blocked/unknown. Do not label any current carrier mergeable from these observations. Hosted CLA/attribution success for #4316/#3961/#5374 is separate from action-required product jobs.

## Landed, deduplicated, and recovered claims

- #4930 closed/unmerged; #5163 merged `341d1e17237815340991376828992115a64ee15c`. Retire stale fork #126 promotion action, preserving hippoley/original implementation credit.
- #4020 acknowledgement already exists at https://github.com/trycua/cua/pull/4020#issuecomment-6129253423. No duplicate comment.
- #154 is not evidence-free: remote `dot/cua/4898-timeout-revalidation-evidence-20261014` = `66ed52c41f02b0738726312058897c3f6f377377`. Recovered README and independent review: historical real-file controls4 pass; intentional recency mutant2 pass/2 fail. Origin owner TanishGudise; reviewer ddupont808. Not rerun here. Empty issue comments do not establish an absent executor or missing work.
- #155 likewise has remote `evidence/cua-5174-control-retention-20261014` = `58a7bea246858045632661cbf99f2fa4a3e1043c`. Recovered original independent review/results/source provenance. Historical6 rollback+2 success controls pass; two isolated mutations establish missing selected-suite coverage, not a production defect. Origin #5174 merged `ca6a0e21050966e8ed6a3404b7ba2843b1cf6878`. Preserve injaneity salvage, GDemay/Guillaume Demay implementation/tests, and anxkhn report. Not rerun or taken over.
- Actual current executing worker IDs for #154/#155 were not established from GitHub artifacts. Treat them as published evidence with stale claimed issue envelopes, not proof of two running workers. Parent must reconcile its live executor registry before reassignment. Both owner refs untouched.

## Commands and artifacts

`gates.jsonl` records each actual command, cwd, exit and raw-log path; `gate-summary.json` derives counts from logs. `collection-audit.json` reconciles18 item snapshots and each declared comment/file count. Original raw API payloads and three failed CI job logs remain here. `final-heads.json`, `final-worktree-identities.json` and product-jobs JSON retain exact state.

Principal commands, from the matching exact-head component:

```sh
python -m unittest discover -s python/tests -v
npm test
npm run typecheck
npm run build
node --test test/spaces-unit.test.mjs test/presence-netcode.test.mjs
ruff check --no-fix --no-cache cua_sandbox/transport/adb.py tests/test_adb_transport.py
ruff format --check --no-cache cua_sandbox/transport/adb.py tests/test_adb_transport.py
python .github/scripts/release_attribution.py validate-title --title 'fix(sandbox): honor shell timeout on Android ADB transport' --require-release
python .github/scripts/validate_release_versions.py --product sandbox
uv run --no-project --python 3.12 --with build --with hatchling python -m build --no-isolation --outdir RECEIPT/dist
python chrome_opacity_probe.py
```

The installed matching jev-use venvs and node_modules were reused with matching manifests/locks; Python import/session environment was scrubbed. Node26 preliminary successes are retained but final TS qualification uses installed Node22.23.2. The package build installed eight small build-tool dependencies into uv's isolated tool environment; no native CUA SDK, Android SDK, Rust crate download or large toolchain install occurred.

The first #5362 replay and full Python passes lacked sparse-checkout sibling fixtures. Those failed attempts are retained as setup failures, not regressions. Restoring only exact-head fixtures yielded the reported green results. No test expectation or production file was changed. #5362 baseline retains only the intentional regression-test overlay.

Package artifacts:
- `dist/cua_sandbox-0.9.0.tar.gz`, SHA256 `052c80bc223f1424a1dfbfacb1581009125089511b94fff272cc98e097650ef0`.
- `dist/cua_sandbox-0.9.0-py3-none-any.whl`, SHA256 `06c30fcc89b52bf56ed138dc9eb886f893ab7dcae795cb3aa5bb6920161a5cce`.
- `chrome-opacity-result.json`, original fixture/DOM, three exact-source Rust excerpts/build logs: limited reproduction, not Driver acceptance.

## Parent actions / clearance

1. Preserve #5362's original author and resolve the real codex CLA/source-attribution situation with the human/maintainer. Do not blindly add an unrelated Salvaged-from link, invent a coauthor, rewrite history or sign for another identity. No local source repair can clear this legal/provenance gate.
2. Parent may use the unsent existing-thread payloads after its own authorization, duplicate/head refresh and independent evidence review. No new PR is warranted for #122/#149, #4930/#126, #5184 or #155.
3. Remaining native gates require dependency-equipped exact builds plus safe prepared devices/platforms. An installed Sway binary is not a certified isolation lifecycle; current harness carries an explicit independent-review hold. No exception was inferred from its presence.
4. All previously denied/canceled/pending writes remain unchanged. This lane attempted no remote write and establishes no new clearance for those operations. No narrow product fix bundle was justified within owner-authorized scope; only a local evidence bundle is prepared, with independent review pending.
