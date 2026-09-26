# Issue 63 — final promotion packet

Final disposition: **PROMOTE / completed**.

Canonical upstream PR: trycua/cua#4164.
Exact head: `fb7841be7c9d2ef666a5dd87be6ca78e2de5d254`.

Independent native macOS evidence from @will-bogusz:
- macOS 26.1 arm64, Calculator, 205 AX nodes.
- 3 identical runs per row.
- element predicate + screenshot: base 2 AX walks (205,205) → PR 1 walk (205).
- window-only predicate + screenshot: base 1 walk (205) → PR 0.
- element predicate without screenshot: 1 → 1 control.
- final screenshot remained one 460×816 PNG with identical encoded size.

Focused PR regression: `observation_args_request_only_needed_modalities`, pinning screenshot-only vs element-bearing observation arguments and preserving `_observation_only`.

Limitations:
- producer-count proof, not a latency claim;
- native trace is macOS only;
- cross-platform runtime selector parity remains downstream issue #16;
- upstream fork workflows are blocked by GitHub `action_required`, not failing tests.

The old "trace missing / verdict withheld" text is obsolete. Live issue #63 is closed completed.
