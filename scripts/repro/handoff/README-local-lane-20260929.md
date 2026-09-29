# Local lane 2026-09-29 (RFC trycua/cua#3963 critical path)

Nothing here was pushed or posted. Pins verified at start (unchanged): main 22456aa59, #4316 d391a663a,
#4317 52d379c85, #4318 b55326f65, #3961 e899fb93e.

Evidence types: SRC source inspection, UNIT unit test, FIX controlled fixture, REAL Driver/MCP/Chromium (or GTK3),
BENCH measured benchmark, LIVE external provider call.

Lane dirs (each has results/ and the analysis script that produced it):
- issue-10-4316-exact/        A/B (mock clean + traced, live), unit step tables. Harness: ../issue-10-4316-ab/
- issue-36-4317-exact/        10x two-session isolation incl. session_ended + same-label restart. Harness: ../issue-36-4317-isolation/
- issue-36-guarded-cross-session/  guarded plan across sessions on the composed #4316+#4317 worktree (10 reps)
- issue-4318-contract/        exact-head gate steps, fmt failure log, fmt-fix gate logs, flake counts
- rfc-3963-next-cost/         phase ranking, action-latency probes, cursor-glide and window-bound A/Bs
- rfc-3963-guarded-generalization/  toggle -> confirm on a real Driver path (local owned fixture)
- issue-75-native-timing/     real GTK3 base-vs-patch comparison
- issue-9-cancellation-slice-a/    ledgers for scenarios A/B/C and the owned-blocking prototype
- issue-77-openjev/           #3961 loopback matrix
- issue-8-passive-observation-vectors/  proposal vectors + reference evaluator (data only)
- lane-infra/                 X11 session wrapper (private Xvfb+dbus+openbox+picom, optional AT-SPI), builders

Reproduce (paths under /mnt/zer0models/github/cua-lanes = $L; worktrees c4316 c4317 c4318 cmain c3961 cint cexp p75b ccancel):
  $L/cua-x11-session.sh /usr/bin/python3 $H/issue-10-4316-ab/ab_harness.py --config <cfg> --out <ABS dir> --only-mode clean|traced
  python3 $H/issue-10-4316-ab/analyze.py <run dir> --json .. --md ..
  $H/issue-36-4317-isolation/run_isolation.sh <examples> <driver> <out> 10 witness
  $H/issue-36-guarded-cross-session/run_reps.sh <cint examples> <driver> <out> 10
  $L/validate-4318.sh <wt> <out> <target>; $L/validate-contract-gates.sh <wt> <out> <target>
  python3 $H/rfc-3963-next-cost/next_cost.py <run-mock> --traced <run-mock-traced> --out-json .. --out-md ..
  CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 $L/cua-x11-session.sh ... verify_native.py --harness gtk3 --typescript --output-dir ..
  python3 $H/issue-75-native-timing/compare_real_native.py <base out> <patch out>
  cargo test --locked -p cua-driver-sdk --lib slice_a -- --include-ignored --test-threads=1   (in ccancel)
  python3 $H/issue-77-openjev/openjev_matrix.py --examples-dir <c3961 examples> --out-dir ..
Live key: forwarded by NAME only (CUA_SESSION_FORWARD_SECRETS); no value is stored in any artifact.
