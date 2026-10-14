# Independent Android ADB timeout review

Verdict: APPROVE for the bounded Python-adapter fix; no blocking finding. Qualification remains LIMITED. No full native or Android acceptance claim.

- Candidate: 16386a256a7a7d5deae7f3c54e73ea77b3dae250
- Base: 8ccf531fb54b6e4f974437a8c2f5af7abc4d45d6
- Candidate checkout: /workspace/scratch/df37e4e44cce/cua-adb-timeout-20261014
- Independent detached base checkout: /workspace/scratch/df37e4e44cce/cua-adb-timeout-review-base-20261014
- Test SHA-256: 50e5aea42511bf4bcfc2d5c93efb037812c3bb492b9680bfc2d3bc8475782dd6
- Candidate adb.py SHA-256: d99ea9a899e85caa1be7c00a5f1c673dabd94802766e4ba328a506839f339166
- Base adb.py SHA-256: 75ca3f189b1dc34c58940d5468155c05e8356677381e1bf1169926a12bd43092
- Guard SHA-256: 8e028dfaa395fcff0085c9df1cc9c1deeb12bd20dfbbf143cc148b9b2e139a47

## Review findings

1. The one production-line change forwards the timeout received by ADBTransport.send to the existing asynchronous and synchronous helpers. Both helpers already forward timeout to subprocess.run. No retry or exception wrapping is introduced.
2. The defaults intentionally differ: public Shell.run has timeout=30 and always sends it for foreground commands, whereas direct shell/execute/run_command sends without a timeout retain the existing lower-level 15-second default. params.get("timeout", 15) also preserves explicit 0 rather than treating it as a missing value.
3. This is a supported route. Sandbox.__init__ constructs Shell(transport); current Android reconnect (sandbox.py around 2624-2647) and create (around 2777-2800) paths select ADBTransport when the corresponding gRPC/QMP transport is absent. The review inspects these selection paths but does not execute lifecycle or connect calls.
4. The tests traverse the real Sandbox, Shell, ADBTransport.send, _adb_cmd_async, event-loop executor and _adb_cmd implementations. The recorded subprocess.run seam is below the defect, verifies command/environment construction, and confirms dispatch on a worker thread. No transport replacement or test-only production switch is used.
5. TimeoutExpired identity, partial output, and single invocation are verified. This establishes propagation without retry, not the subprocess implementation's elapsed-time behavior or guest-process termination.
6. Nonzero exit status, replacement decoding, environment prefix, serial selection and unrelated screen-size timeout are covered. Source inspection shows other ADB operation paths and transports are unchanged. No broad behavioral guarantee for those unexecuted paths is implied.

## Independent results

- Identical final test on isolated base: 10 FAILED / 5 PASSED, exit 1. Every failure is the observed 15-second argument instead of requested/default-public timeout, not a setup/import error.
- Candidate: 15 PASSED, exit 0.
- Adjacent EnvTransport + forward modules, unfiltered: BOTH base and candidate 6 FAILED / 20 PASSED, exit 1. Same six cases fail because native SDK imports are deliberately refused by the guard.
- Same adjacent modules with the explicitly recorded native-dependent exclusions: BOTH base and candidate 20 PASSED / 6 DESELECTED, exit 0.
- Ruff check: PASS. Ruff format --check: 3 files already formatted. git diff --check BASE HEAD: PASS.
- Import-origin audit confirms each run resolves Sandbox, Shell and ADB source from its intended worktree despite the shared editable-install venv; native cua modules are absent.
- before.sha256, after.sha256 and final.sha256 match. Candidate production, test and guard were not edited. Only the exact committed test was copied into the isolated base checkout. No branch push, upstream operation, credentials or destructive action was performed.

## Exact commands

Run from the candidate checkout to create the independent base:

```sh
git worktree add --detach /workspace/scratch/df37e4e44cce/cua-adb-timeout-review-base-20261014 8ccf531fb54b6e4f974437a8c2f5af7abc4d45d6
git show 16386a256a7a7d5deae7f3c54e73ea77b3dae250:libs/python/cua-sandbox/tests/test_adb_transport.py > /workspace/scratch/df37e4e44cce/cua-adb-timeout-review-base-20261014/libs/python/cua-sandbox/tests/test_adb_transport.py
```

For TREE equal to the independent base path, then the candidate path:

```sh
PY=/workspace/scratch/df37e4e44cce/cua-adb-timeout-venv/bin/python
GUARD=/workspace/scratch/df37e4e44cce/cua-adb-timeout-20261014/evidence/cua-adb-shell-timeout-20261014
cd "$TREE"
CUA_TELEMETRY_ENABLED=false PYTHONPATH="$GUARD:$TREE/libs/python/cua-sandbox" "$PY" -m pytest -p cua_adb_guards libs/python/cua-sandbox/tests/test_adb_transport.py -q
CUA_TELEMETRY_ENABLED=false PYTHONPATH="$GUARD:$TREE/libs/python/cua-sandbox" "$PY" -m pytest -p cua_adb_guards libs/python/cua-sandbox/tests/test_env_transport.py libs/python/cua-sandbox/tests/test_env_transport_forward.py -q
CUA_TELEMETRY_ENABLED=false PYTHONPATH="$GUARD:$TREE/libs/python/cua-sandbox" "$PY" -m pytest -p cua_adb_guards libs/python/cua-sandbox/tests/test_env_transport.py libs/python/cua-sandbox/tests/test_env_transport_forward.py -q -k 'not background_shell_and_terminal_use_pty_processes and not files_round_trip and not clipboard_screen_and_environment and not without_spacesd and not the_driver_is_retried_until_ready_timeout'
```

Candidate checks:

```sh
/workspace/scratch/df37e4e44cce/cua-adb-timeout-venv/bin/ruff check libs/python/cua-sandbox/cua_sandbox/transport/adb.py libs/python/cua-sandbox/tests/test_adb_transport.py "$GUARD/cua_adb_guards.py"
/workspace/scratch/df37e4e44cce/cua-adb-timeout-venv/bin/ruff format --check libs/python/cua-sandbox/cua_sandbox/transport/adb.py libs/python/cua-sandbox/tests/test_adb_transport.py "$GUARD/cua_adb_guards.py"
git diff --check 8ccf531 HEAD
```

Raw logs are adjacent to this report: red.txt, green.txt, adjacent-{base,candidate}-{full,scoped}.txt. Import paths and hashes are in import-origins.txt. An initial module-origin diagnostic used a dotted import alias that resolved the package's exported sandbox function; it raised AttributeError in both trees and was corrected with importlib.import_module. This was an introspection-command error, not a test result or source change.

## Limits

The unchanged guard blocks cua imports, subprocess.Popen, os.system and Python socket connect APIs; selected code paths were inspected as well. This is a bounded Python-level safeguard, not a system-wide network/process sandbox. No native SDK, emulator, actual ADB subprocess, guest RPC, network connection, GUI input, lifecycle startup, elapsed-time acceptance or guest termination was exercised. Full package/native SDK/Android/hosted CI acceptance remains unrun. Python 3.12.14, pytest 9.1.1, pytest-asyncio 1.4.0, ruff 0.17.0 shared with the implementer's environment.
