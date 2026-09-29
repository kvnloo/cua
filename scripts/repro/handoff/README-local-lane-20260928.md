# Local execution lane, 2026-09-28/29 (Linux x86_64, CachyOS, rustc 1.97.1)

Upstream main used: b8d619f57ecaac0f9328df8dde880a4cd5921520 (re-checked live via gh api).
PR heads: #4316 e2e86d704, #4317 265373865, #4318 f2ff99daf (all unchanged at end of lane).
All GUI/E2E ran in a private rootless Xvfb+dbus+openbox session (cua-x11-session.sh); the host Hyprland
client list, monitors and workspace were identical before/after (only focus moved between the user's own
kitty/zen windows). Linux evidence only: nothing here speaks for macOS or Windows.

Layout: issue-10-4316-ab (harness, analysis, results/), issue-36-4317-isolation, issue-76, issue-75,
issue-4318/results (step logs). Helper scripts sit beside this file.

Local fix/patch commits (not pushed, no upstream writes):
- 7a4e4a469 fix/4316-verify-setup-decision-routes-test-local  (parent e2e86d704)
- 89f650697 fix/4317-isolation-proof-import-and-refusal-shape-local (parent 265373865)
- c9fb05930 fix/4318-portable-pattern-parity-local (parent f2ff99daf)
- 2e07f6769 perf/jev-use-native-timing-parity-20260928-local (parent b8d619f57)

Reproduce (see each issue dir): ab_harness.py --config ... under cua-x11-session.sh; analyze.py;
run_isolation.sh <examples> <driver> <out> 5 witness|ci; validate-4318.sh / validate-contract-gates.sh;
capture_tools_list.py + analyze_tools_list.py --tokenizer-root <dir with node_modules/gpt-tokenizer>;
compare_base_patched.py --base ... --patched ...
