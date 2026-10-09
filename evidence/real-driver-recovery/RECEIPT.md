# Real Driver recovery acceptance: BLOCKED, 2026-10-09

## Executed result

`python3 evidence/real-driver-recovery/preflight.py` exited **2**.
`bash evidence/real-driver-recovery/run-native-control.sh --preflight` also exited
**2**. The checked-in `preflight.json` is actual stdout. Unix stream socket
creation returns `EPERM`; an actual `dbus-run-session -- true` exits **127**
with `Failed to open socket: Operation not permitted`. The D-Bus probe uses
its own writable temporary runtime directory, so this is not merely a missing
home directory. AF_INET socket creation works. No display, session bus, Cargo,
or PyGObject/GTK3 is available. Installing packages cannot remove the socket
restriction. No security workaround, desktop impersonation, or real input was
attempted. No Rust build slot was consumed.

**No real Driver was built or run in this lane. No RED/GREEN product result.**
No isolated/mock test suite was rerun or substituted as acceptance. Bash syntax
validation of the run script passed; this is script syntax evidence only.

## Exact sources and scope

- #4734: `32ca35a6c03a646d712390b39a9a67fab1831b98`, branch
  `kvnloo/cua:grok/cua/4374-no-progress-save-note`, base
  `4c2403fc557492cbd1e8018a0f2104cdcd6fd838`.
- #4902: `bb3885fcd7b61e63f698db1d073ac50c8acf44a0`, branch
  `kvnloo/cua:fix/jev-use-action-refusal-20261008`; latest GitHub PR base
  `5a364bbe60e1f8a901ceacd889606b6367dc96ab`. The historical PR body cites
  `c1c2b5f`; the API base is recorded separately rather than treated as the
  tested head's parent.
- Both PR heads were read from GitHub and confirmed with `git ls-remote`.
- Driver Rust trees differ: #4734 `e1f5feb81db599891112215087a37a618668aa7a`,
  #4902 `3f336db24c7f57508fba6d5875d3bdd35152e465`. They must not share a
  binary under an exact-head certification claim.
- Evidence branch: `dot/cua-real-driver-recovery-20261009`, based on #4734.
- [Fork-only claim](https://github.com/kvnloo/cua/pull/103#issuecomment-6090254185)
  was posted and reread before file creation. It had no competing claim.
- Only this evidence directory changes; no product, schema, generated binding,
  owner branch, main branch, or upstream PR changes.

## Runnable prerequisite lane

On an authorized disposable **Linux X11 desktop with AT-SPI and a session bus**,
install the official dependency set documented by `.github/workflows/ci-jev-use.yml`
and the GTK3 requirements in `libs/cua-driver/tests/fixtures/build/linux.sh`.
Use the repository-pinned Rust toolchain. Do not alter the current restricted
sandbox's security policy. Run against a clean checkout of each exact source:

```sh
CUA_DISPOSABLE_DESKTOP=1 \
SOURCE_ROOT=/absolute/exact-head-checkout \
EXPECTED_SHA=32ca35a6c03a646d712390b39a9a67fab1831b98 \
EVIDENCE_DIR=/absolute/new-evidence-directory \
bash /absolute/evidence-branch/evidence/real-driver-recovery/run-native-control.sh
```

Repeat independently with the #4902 SHA. This source-builds its own Driver,
records source/tree/binary identity, stages the canonical GTK3 fixture, installs
locked Python/TypeScript dependencies, and runs the existing `verify_native.py`
with both languages. That verifier independently reads the app's state for
counter, note, and choice tasks. The chooser is deterministic; Driver and the
app must be real. This is **not live-provider acceptance**. The script stops
before build on failed preflight. Even if all native controls pass, it exits
**2**, leaving `ACCEPTANCE_BLOCKED.txt`: generic happy-path verification does
not certify the requested fault matrix. The prepared-desktop run is **NOT_RUN**.

## Required fault matrix: all NOT_RUN

The existing `verify_native.py` only admits verified happy-path results; it
has no supported forced-recovery selector. Do not change its expected result
to count an unrelated failure as desired abstention. A real fault fixture is
still required before this task can claim acceptance. Preserve the existing
owner tests; use test-only orchestration, never shipped Driver switches.

| Row | Real boundary and independent oracle needed | Required result |
| --- | --- | --- |
| Repeated no-progress | Real native observations of an unchanged GTK3 app; controlled chooser can select reobserve, but must not replace Driver responses | Both runners emit `abstained`, `reason=no_progress`, bounded streak; zero mutation calls for reobserve |
| Same-candidate delivery | Real native mutation repeatedly leaves task-owned progress unchanged; real fixture journal proves no completion | Bounded same-candidate abstention; dispatch receipt alone never becomes progress |
| Recovery / changed candidate | Obtain real stale/refused action results; alternate recovery and delivered same candidate with unchanged journal; separate changed-candidate/proven-progress controls | Recovery streak cannot reset merely on dispatch; genuine candidate switch/app progress resets as specified |
| `effect=refused`, no MCP error | Capture an actual source-built Driver MCP response with that envelope | Both wrappers raise structured error; independent app unchanged; exactly one attempted mutation |
| `effect=refused`, MCP error set | Capture a real Driver route producing that envelope separately | Same safety outcome and code/escalation semantics; exactly one attempted mutation |
| Ambiguous acknowledgement / delayed effect | Owned resettable fixture and transport-boundary fault after actual dispatch; journal shows applied or later-applied mutation | Unknown until reconciled; no blind redispatch; include delayed-effect negative-read case |

Record raw sanitized MCP envelopes, exact tool/attempt counts, app journal,
source and binary identity for each row and each language. If a source version
cannot produce one envelope form through a real public route, mark that row
**unsupported/NOT_RUN**. Toggling `isError` in a fake response is unit evidence,
not the missing native row. No tests currently supplied in this evidence
packet implement these forced fault scenarios; the table is the concrete
remaining acceptance contract, not a statement they were executed.

## Existing ownership and composition risks

- #4734 reviewer: @injaneity. [Fork #117](https://github.com/kvnloo/cua/pull/117)
  owns observation composition after merged #4913; preserve `full_output: true`
  and the narrowly scoped old-version fallback when composing current main.
- #4902 reviewer: @ddupont808. Existing fork metadata `93acf502` and canonical
  escalation `d742080f` successors already own error-code/escalation semantics;
  [fork #119](https://github.com/kvnloo/cua/pull/119) composes guarded completion.
  Do not reimplement them or certify their composition from an older test run.
- Credit remains with @Andrew9603 for #4374, @IRONICBo for progress-evidence
  boundaries, @f-trycua for #4913, and @kvnloo for the refusal-envelope work.

## Smallest unblock and limits

Use an already-authorized disposable desktop environment that permits Unix
sockets and D-Bus, then build each exact source and run the native controls.
The forced-fault orchestration above remains a separate implementation and
execution gate there. This host failure is not a product regression. No
Python/TypeScript native parity, recovery, no-blind-retry, Windows/macOS,
OmniParser, live-provider, canonical full-matrix, or release qualification is
claimed. No rebuildable artifacts were created; there is nothing large to clean.
