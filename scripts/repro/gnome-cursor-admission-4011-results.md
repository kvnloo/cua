# PR #4011 cursor admission: executed evidence

Source under test: `trycua/cua@54802e70cc7fdcad5f8c5d3a992610d0ca0d777a`.
Test runner commit: `94244b649832183e7daab3db62b2017fa2a8fefb`.
Run: https://github.com/kvnloo/cua/actions/runs/35956908564
Job: https://github.com/kvnloo/cua/actions/runs/35956908564/job/107497056798

## Result

Compiled and executed five Rust component tests: **4 control tests passed; 1 desired-behavior regression failed**. Native test exit status: 101. The enclosing evidence workflow succeeds because it requires this exact expected failure plus the passing controls; that is not product acceptance.

| Pending requests before submission | Submitted update | Observed at the test helper sink |
| --- | --- | --- |
| 62 of 64 | Semantic movement | SetCursorColor, then MoveCursor |
| 63 of 64 | Semantic movement | SetCursorColor only; MoveCursor dropped |
| 64 of 64 | Semantic movement | Neither part accepted |
| 63 of 64 | Non-semantic movement | MoveCursor accepted |
| 64 of 64 | Disable cursor | Reserved HideCursor accepted |

The failing assertion requires both parts of a logical semantic movement, or neither. The actual result was:

```text
logical update was split: expected both parts or neither, got [VisualRequest { method: "SetCursorColor", args: ["test-color:producer-B"] }]
test result: FAILED. 4 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out
```

## Scope and limitations

The runner verifies both source files against the pinned commit, extracts the production dispatcher/queue/public helper methods and the production overlay forwarding function without changing their bytes, and compiles them using `rustc --test`. It uses the PR's existing thread-local dispatcher injection seam. Logging, display I/O and unrelated overlay type/color helpers have test adapters. A channel holds the consumer during admission, so the 63-slot condition does not depend on sleep timing. The fixture drains the exact admitted count, rather than inferring a drop from a timeout.

This establishes the queue-admission split under the chosen both-or-neither UX requirement. It does not establish live GNOME rendering, end-to-end latency, sustained producer fairness/starvation, or atomic execution across separate D-Bus calls. No full workspace or desktop matrix was run. No production fix is included and no upstream comment/PR was created by this test run.

Rust compiler: `rustc 1.98.1 (48a229cea 2026-09-01)`, x86_64-unknown-linux-gnu.

Evidence artifact includes the generated Rust test, raw build/test logs, source hashes and structured result:
https://github.com/kvnloo/cua/actions/runs/35956908564/artifacts/10790826151

Artifact ZIP SHA256: `8b8b720b916d46aac52c726fda94cce0210b2cf0d44aa03b6c1a94293e540632`.

Production shell_helper.rs SHA256: `d961b3b38600593613eab07ddd5604520f752ab72ad430e6b3a1e44b404effef`.
Production overlay.rs SHA256: `daf3398d6e79e44bfaae0674a3cef3d2fa6c172f29f9e39204f5fa7a602e1fb8`.

The narrow next change to evaluate is all-or-nothing queue admission for one logical overlay update. Coalescing, fairness and a new compositor protocol are separate design decisions, not implied by this reproduction.
