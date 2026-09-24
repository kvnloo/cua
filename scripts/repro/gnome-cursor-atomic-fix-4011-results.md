# PR #4011: atomic cursor admission, executed red/green evidence

## Identity

- Contributor source: `cresslank/cua@54802e70cc7fdcad5f8c5d3a992610d0ca0d777a`, upstream PR https://github.com/trycua/cua/pull/4011.
- Test recipe/workflow commit: `9a528fb432d5d3e9ab38590cdca1bd140428409d` on the user's fork.
- Executed run: https://github.com/kvnloo/cua/actions/runs/35957857904.
- Native test job: https://github.com/kvnloo/cua/actions/runs/35957857904/job/107499897416.
- Proposed two-file patch: [gnome-cursor-atomic-4011.patch](gnome-cursor-atomic-4011.patch). It changes 86 lines in and 36 lines out, with no unrelated formatter changes.
- Patch SHA256: `4575bf1400164e9343df6b308a59911bca1a470fd7e289bd3afc537a3defda66`.

The patch was generated in the isolated CI worktree; production files on the fork and the contributor's upstream PR were not changed. The retained patch and this report are documentation/evidence additions after the tested recipe commit; they do not alter the candidate that was compiled.

## Executed results

The baseline reran the original fixture: **4 controls passed; 1 desired-behavior regression failed**, exit code 101. Its generated test source is byte-identical to the earlier executed reproduction (`4bc51fc4222d6706075a013e6f2b9ae39491eb1eb4cbbc5a83e408dc5a9b2195`).

The candidate passed **11/11 component tests**, including the original five assertions unchanged. Twenty additional runs with four Rust test threads passed **220/220 test executions**. These are repetitions of the same 11 tests, not 220 distinct scenarios or proof of all schedules.

| Boundary | Baseline | Candidate |
| --- | --- | --- |
| 62 pending; semantic movement | Color and movement | Color and movement |
| 63 pending; semantic movement | Color only (regression) | Neither admitted |
| 64 pending; semantic movement | Neither admitted | Neither admitted |
| 63 pending; legacy movement | Movement | Movement |
| 64 pending; hide | Hide accepted | Hide accepted |

Additional candidate coverage checks semantic snap/pulse/begin/end/label arguments and ordering, legacy pulse behavior, two concurrent producers competing for the final pair of slots, unchanged helper-call capacity, closed admission, and reserved/coalesced hide after a rejected pair. Worker execution is controlled with channels/barriers rather than sleep-based scheduling guesses. The fixture reads exactly the admitted number of requests and verifies final shutdown hide.

## Candidate decision

Reserve all helper-call slots for one color-plus-update pair under one queue lock. Either both enter consecutively, or neither enters. The capacity still counts **64 helper calls**, not 64 arbitrarily large batches, plus the existing one reserved hide. FIFO ordering and the existing singleton hide behavior remain intact.

No coalescing, latest-wins policy, per-producer fairness, new worker, helper protocol, capture, real input, or ownership policy is introduced. The test demonstrates admission atomicity only: two separate D-Bus calls may still fail independently after admission. It does not claim an atomic visible display transaction or end-to-end delivery.

## Evidence boundary and reproduction

The experiment compiles actual source excerpts from the two pinned production files with `rustc --test`, then repeats with the exported patch applied. It reuses the prior fixture's fake display sink and small adapters for overlay types, colors and logging. It does not compile the entire platform crate, contact GNOME/D-Bus, or run a desktop suite. Full workspace compatibility, native rendering, latency and real multi-session behavior remain unverified.

Rust: `1.98.1 (48a229cea 2026-09-01)`, x86_64-unknown-linux-gnu. Candidate generated Rust test SHA256: `297984949fe705f363ba3783bc5b477546b9756508e52884e82de5b384df194e`.

In a disposable checkout of the test recipe commit, with Python 3, rustc and rustfmt installed:

```sh
python3 scripts/repro/gnome-cursor-atomic-fix-4011.py
```

The script checks the production files against the source commit, reruns the baseline, applies guarded changes locally, formats the two files, exports `atomic-evidence/candidate.patch`, and runs the candidate tests. Use a disposable checkout: this command intentionally changes its two worktree source files. It never pushes them.

Raw artifact: https://github.com/kvnloo/cua/actions/runs/35957857904/artifacts/10791560760.

Artifact ZIP SHA256: `9488e1e559e2ed0eb6dcfc6ae66eb72ed9e747c4916f7c162286e5c0a69a9de1`. It contains baseline and candidate generated Rust, raw logs for all runs, source hashes, structured results and the patch. GitHub retention is 14 days; the committed recipe and patch are the durable reproduction path.

## Handoff

Offer this bounded change to the existing contributor rather than open a competing implementation. The next integration work is to agree on both-or-neither admission, move the focused regressions into the repository's ordinary test structure, and validate the integrated candidate with the platform suite and required native GNOME checks. The contributor's original ownership, FIFO design and explicitly documented limitations are preserved.
