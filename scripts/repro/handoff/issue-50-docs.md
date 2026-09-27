# Issue 50

Doc and skill matrix: `scripts/repro/handoff/issue-50-matrix.tsv`.

Audited, and left unedited:

- `libs/cua-driver/rust/Skills/cua-driver/WORKFLOW.md`
- `LINUX.md`, `MACOS.md`, `WINDOWS.md` in the same skill directory
- `libs/cua-driver/examples/jev-use/README.md`
- `libs/cua-driver/docs/action-result-contract.md`
- `libs/cua-driver/docs/perception-extension.md`
- `rfcs/3931-cua-perception-and-jev-use.md`

`run.py` does not call the experiment functions, so the decision table schedules no documentation patch. Every decision cell is BLOCKED.

Patch plan: do not edit those files on this branch.

Lines that must not be weakened, even if a later promotion is earned:

- `WORKFLOW.md` line 44: tree-only observation cannot ground a pixel action.
- `WORKFLOW.md` line 127: canceled, partial, or unknown actions are not replayed.
- `WORKFLOW.md` line 44 again: event absence is not permission to skip.
- RFC 3931 line 403: one capture authorizes at most one action.
- `action-result-contract.md` line 94: `unknown` is not success.

The only line a future lazy-vision promotion would revisit is `WORKFLOW.md` line 38, which says `get_window_state` requests the tree and a grounding screenshot by default. That promotion is not recorded. macOS and Windows skill lines were read here and were not executed.
