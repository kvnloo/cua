# Independent review: CUA #5174 control retention

Reviewed on 2026-10-14 UTC against head `a0fbe31a3bf544b1ba231439aedb1b592f0b6c58` and production base `5e607bc5d7bc60ae0b80c8fcd9659847f575cc33`.

## Verdict

**Accept as narrowly scoped evidence of useful omitted unit controls. This is not a production defect finding, upstream approval, package-release certification, or merge-readiness assessment.** I found no blocker to the README's qualified control-retention conclusion. The final reruns independently reproduce the reported matrix. Production behavior under these selected mocked-transport tests passes; the deliberate mutants are the only failing implementations in this review.

The useful new result is that the six retained `test_tunnel.py` cases do not detect two selected regressions which the original controls do detect. This supports retaining those controls or preserving their contract coverage in an appropriate owner test. It does not prove that the entire repository lacks equivalent coverage.

## Independent verification performed

- Recomputed Git blob identities for all 167 staged exact-head production/test files: 80 production and 87 test files. All match the recorded, non-truncated GitHub trees. The copied `AGENTS.md` and package `pyproject.toml` also match their recorded official blobs.
- Recomputed all 80 base production-file Git blobs against base tree `d457f01772cfd59e8ed41b666d77bb36eeb80d68`: no mismatches. Although assembled by replacing the tunnel file, this is the complete exact-base production package, not an unverified hybrid. The copied test directory remains the head test tree; it is not asserted to be the base test tree.
- Verified unchanged original test bytes (`bef5062c65e4158164bf91319447b6eb5a54fcfe`), retained test bytes (`5fd9e10016cee88c1314b111d6d392be66e8986a`), head tunnel bytes (`d6da76629dc2a83a9708117c6879fff43a1dad82`), and base tunnel bytes (`e3f66b8b5d69744b72c9db0e3408c74e6f7b556b`) against the saved source responses. Original and salvage production tunnel bytes are identical.
- Compared the three variant directories against head: their only file difference is the intended `cua_sandbox/interfaces/tunnel.py` substitution or mutation.
- Independently checked all 538 dependency-module files loaded by the retained-suite run against their logged SHA-256 values and installed distribution RECORD hashes: zero missing records or mismatches. This establishes installed-file consistency, not wheel authenticity or clean-install compatibility.
- Read the package initializer, tunnel implementation, retained and original tests, wrapper, initial failure logs, relevant package test references, source/ownership snapshots, and README.
- Reran the full selected matrix after the runner's path-only `CUA_EVIDENCE_SITE` change, using the precise sanitized environment in `commands.txt`, Python 3.12.14, `-I -B -S`, and a 30-second outer timeout. No guards, tests, implementation, or dependencies were changed by the reviewer.

## Independent final reruns

| Variant | Suite | Result |
| --- | --- | --- |
| head | import preflight | exit 0 |
| head | retained | 6 passed |
| head | original controls only | 2 passed, 6 deselected |
| base | original controls only | 2 passed, 6 deselected |
| no_context_cleanup | retained | 6 passed |
| no_context_cleanup | original controls only | context cleanup fails; other control passes |
| single_result_dict | retained | 6 passed |
| single_result_dict | original controls only | single-result identity assertion fails; other control passes |

Final runner SHA-256: `6c5b2a2b85fc9cf1c4303881539329129c5804ce42eae9cf8ee03a7de7bad0d3`.

Raw final outputs are `logs/reviewer-final-*.log`; the machine-readable summary is `logs/reviewer-final-summary.json`. Additional independent identity checks are `logs/reviewer-source-integrity.log`, `logs/reviewer-base-integrity.log`, and `logs/reviewer-dependency-integrity.log`. Earlier `reviewer-*.log` execution outputs are a preliminary matrix using the pre-portability runner and a reduced sanitized environment; they agree, but the `reviewer-final-*` matrix is the authoritative independent replay.

Every final execution recorded exactly the known denied urllib3 IPv6 capability probe, only `MainThread` at exit, and `native_imported=false`. Each test run imported 60 source-package modules and 538 installed dependency modules; preflight imported 425 dependency modules. Expected mutant-control process exit is 1, not a production failure.

## Interpretation and limits

1. **Mutation usefulness is specific.** Removing context-exit close calls is detected by the omitted context control. Returning a dict for one target is detected by the omitted plain-await control's identity assertion. The latter mutant does not independently establish sensitivity to its later open-until-closed or repeated-close assertions. Passing controls on base is appropriate for preserving an existing contract, not evidence of a baseline defect.
2. **Other test owners exist.** Exact-head `tests/test_env_transport_mock.py::test_port_forward_over_the_real_driver_tunnel` and `tests/live/test_unified_api_live.py` also dereference the single tunnel handle at stronger/native boundaries. Those tests were inspected, not executed. No repository-wide uniqueness claim or full-suite mutation score is justified.
3. **Imports are real but constrained.** The source-package initializer and real installed dependencies execute; package stubs are not substituted. However, site/`.pth` startup, plugin autoload, repository conftest, and pytest logging/cache plugins are deliberately disabled. This is guarded source-package import and mocked unit-test evidence, not the documented native/full-package command, a wheel build, frozen-lock installation, platform matrix, or backend integration result.
4. **Guard refusals must remain visible.** urllib3 catches the denied IPv6 socket-creation attempt and sees IPv6 as unavailable. There is no zero-denial claim. The seven earlier attempts stopped at pytest logging's prohibited `/dev/null` open before test execution. Disabling that plugin avoids the operation without relaxing the guard. The Python guards are defense in depth rather than a comprehensive OS security boundary.
5. **Keep provenance stages distinct.** `qualification/local-source-availability.json` is a pre-staging availability check with two mismatches; it is not the final integrity manifest. Final staged byte verification succeeds. Installed distribution metadata includes packages not necessarily exercised, and RECORD matching does not authenticate their download origin.
6. **Ownership and current gates are external snapshots.** The supplied commit records retain Guillaume Demay / GDemay as implementation author and injaneity as salvage owner, with anxkhn credited for the original report/approach. `qualification/checks-all.json` has 36 unique exact-head checks: 34 success, one skipped, one failing CLA check. These saved upstream results are separate from this review's local reruns. No fresh network query was made by this reviewer.

No real-loopback rollback evidence was reproduced or counted; that already belongs to the original PR. No installation, network/native/VM/cloud action, git fetch, upstream write, implementation edit, or default-branch action was performed. The reviewed README states the important boundaries and credits appropriately. A maximally precise short headline would say “the selected head unit behaviors pass,” rather than imply all current production behavior was tested.
