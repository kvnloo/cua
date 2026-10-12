# cua-bench scroll direction — 2026-10-12

Downstream work owner: dot/ayo, [canonical #132](https://github.com/kvnloo/cua/issues/132), claimed before coding. Pinned base `f982ea064bb1f6e29f6f2004e5021407f7006320` matched upstream main at initial qualification. Tested code commit: `c1bdaf4d743dfca113095b595c53afc5e7cf04a3`. Final evidence-publication commit is distinct and adds only this packet after the code commit.

## Problem and smallest repair

Bench sent a negative Sandbox scroll_y for up, despite [Mouse.scroll](https://github.com/trycua/cua/blob/f982ea064bb1f6e29f6f2004e5021407f7006320/libs/python/cua-sandbox/cua_sandbox/interfaces/mouse.py#L25) documenting positive as up. The genuine EnvTransport negates vertical notches into native deltaY; [computer.proto](https://github.com/trycua/cua/blob/f982ea064bb1f6e29f6f2004e5021407f7006320/libs/cua/proto/cua/env/v1/computer.proto#L203) defines positive native delta_y as content down. The old bench conversion therefore reversed the native direction before any OS setting was involved.

Only three production sign lines change: RemoteDesktopSession negates down instead of up; SandboxInterface's scroll_down uses negative Sandbox notches and scroll_up positive. Original min-one/floor/absolute-amount conversion, center coordinates, horizontal zero, and native line units are preserved. Two old mock assertions were corrected to match the documented Sandbox convention, alongside the stronger owning regressions. SDK Mouse, EnvTransport, native proto/backend and QMP semantics remain unchanged.

The directly related compatibility aliases were included only after their own RED reproduction. #2344 owns separate click-position/element-delivery changes; its changed hunks were inspected and are untouched. #1337 concerns a different loop. Canonical factory #14/#77 and project #74, known recent branches and bounded symptom/owner searches were refreshed; no competing scroll-direction owner found. This is not upstream publication or a complete project-wide review sweep.

## Exact evidence

| Execution | Result |
| --- | --- |
| Initial fixture attempt | 11 setup ERRORS: nonexistent from_sandbox method; not behavioral RED |
| Corrected regression overlay on untouched base | 10 FAIL / 1 direct-SDK control PASS; 11 other tests deselected |
| Fixed owning test_remote_session.py | 22 PASS |
| Adjacent test_actions.py + test_ale_compat.py | 43 PASS |
| Existing Sandbox EnvTransport scroll control | 1 PASS; 23 deselected |
| Independent xhigh rerun: owning / SDK control | 22 PASS / 1 PASS |

The eleven new cases compose actual candidate-source RemoteDesktopSession.attach, Sandbox, Mouse, SandboxInterface and EnvTransport through its existing env_factory seam. **Only the native client is a recording fake** for these cases: pointer_json captures the genuine outgoing JSON; displays supplies synthetic dimensions. This differs from the eleven pre-existing owning tests, some of which retain their original fake_sdk sys.modules package fixtures. Do not describe the entire 22-test file as real SDK execution.

Up/down run through execute_action and public session.scroll at amounts50 and350. Wire assertions require deltaY=-1/-3 for up and +1/+3 for down, position640/360, deltaX0 and SCROLL_UNIT_LINE. The amount50 case preserves the existing minimum-one notch;350 preserves floor conversion to3. Both legacy aliases are exercised through genuine Sandbox screen.size and Mouse. Direct positive Sandbox scroll3 at17/29 produces native-3 and remains a passing control before and after the fix. The corrected baseline failure output shows the opposite deltas at the real Python transport boundary.

## Scope and provenance

This is actual package execution with a mocked native-client boundary. No native RPC/proto parser, real spacesd/Driver binary, OS input, screenshot, VM, provider or desktop effect was exercised. The parent source critic additionally confirmed spacesd's positive-dy to Driver-down mapping and QMP's positive Sandbox scroll_y to wheel-up mapping. Local/Fleet inheritance and QMP reach are **source analysis**, not executed platform qualification. Real desktop E2E and hosted CI remain unqualified.

Exact commands, exit results and sanitized logs are included. Source hashes compare parent and tested code; SDK/transport/proto hashes are unchanged. The existing approved Python3.12.14 dependency environment was reused with bench and Sandbox source roots in PYTHONPATH. Ruff was absent; its declared lightweight official PyPI binary wheel0.17.0 was inspected then installed hash-pinned, without compilation. Ruff on all three changed files and git diff --check pass. No OS/native build or unrelated test suite was run.

`attribution.json` records official GitHub blame pinned to the base: Dillon DuPont / ddupont, GitHub ddupont808, authored the relevant original bench and Sandbox code. Original direction line lineage is906a1b81621fa7c035a463d37725011b0f5bdb89; SDK adapter/compatibility lineage9166817485ae53f3966935c13878a8196d79a399; Mouse initial lineage7d1fa31fb6ed1d5565fad6eef756044be76061e4. Original source history remains the parent, with no competing external patch adapted. Candidate author is OpenAI Codex; the address resolves to GitHub codex on a verified existing published commit. No human DCO/CLA/signoff or approval is fabricated.

Independent xhigh critic reran exact code, scrutinized the signs and direct SDK control, verified actual imported module paths, and checked unchanged SDK/transport blobs. See critic-receipt.txt. The receipt also preserves the initial fixture failure separately. Machine roots and volatile addresses are sanitized; no environments, caches, credentials or generated private state are included. Packet manifest excludes itself. No upstream write, default/force push, destructive cleanup, canceled upload or denied-path retry is included; other owners and holds remain untouched.

Final main-drift check: upstream main is `40f82b4b61d3d2fc00c38e7be457140c6b981d87`. `git diff --exit-code f982ea064bb1f6e29f6f2004e5021407f7006320 40f82b4b61d3d2fc00c38e7be457140c6b981d87 -- libs/cua-bench libs/python/cua-sandbox libs/cua/proto` passed: relevant trees are identical. Tests certify the explicitly pinned candidate above; main drift was checked by source comparison.
