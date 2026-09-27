# Issue 3 macOS trace citation

This file records a trace fetched from GitHub. It is not a walk this Linux host ran.

Source: https://github.com/trycua/cua/pull/4164#issuecomment-5840994846

Author: will-bogusz. Created: 2026-09-25T23:22:06Z.

The comment says the run was macOS 26.1 arm64, Calculator, 205 AX nodes, driver in `mcp --direct` mode, head `fb7841be7` against base `a959b2a23`, with a local log that was not pushed. `verify_state` used `timeout_ms: 0`. Three runs per row matched.

| `verify_state` call | base AX walks | head `fb7841be7` AX walks |
| --- | --- | --- |
| element predicate plus screenshot | 2 | 1 |
| window-only predicate plus screenshot | 1 | 0 |
| element predicate, no screenshot | 1 | 1 |

The comment says the screenshot stayed one `image/png` block, 460×816, with the same encoded size on both heads. It makes no timing claim.

The pull request description at https://github.com/trycua/cua/pull/4164 includes that comment. The pull request is open and is not a draft. Its head is `fb7841be7c9d2ef666a5dd87be6ca78e2de5d254`.

Not in that comment: a Windows UIA walker count, or an AT-SPI walker count from this Linux host. Those runs were not added here.
