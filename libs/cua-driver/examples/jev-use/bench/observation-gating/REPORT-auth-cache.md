# REPORT: verify-once-per-connection for history methods (the (a)+(b) hybrid)

Date: 2026-09-25. Branch: `muse/auth-verify-once-per-conn` (kvnloo/cua fork).
Bench: `python/bench_observation_auth_cache.py`. Daemon: `python/mock_daemon.py --auth-cache`.
Raw: `/tmp/authcache_raw.json` (30 iters/arm, paired/interleaved, loopback unix socket).

## Why this exists

The auth-lifetime deep dive (REPORT-auth-lifetime.md) recommended option (a) —
scope the codesign verify to history methods only — as the first move. Upstream
then turned out to have already landed exactly that: #3505 ("authenticate
history requests lazily", merged 2026-09-03) moved the deep verify out of the
accept path in serve.rs; `history_cli_authentication_path` returns None for
non-history methods, so ordinary CLI calls pay zero verify. #3383 itself is
still open with 0 comments.

What #3505 did NOT do: history calls still **re-verify on every request**.
This bench prototypes the remaining hybrid the dq-3383 draft named (a)+(b):
verify once per connection; subsequent history_* calls on that connection skip
re-auth. The trust window this opens — a bundle change mid-connection — is
exactly the auth-lifetime contract question the design draft carries.

## Arms (daemon `--auth-mode request --auth-scope history` for all)

| arm | transport | history auth |
|-----|-----------|--------------|
| D4 | one-shot connections | re-verify per request (= today, post-#3505) |
| F | keep-alive | re-verify per request (= conservative: transport only) |
| E | keep-alive | verify once per connection (= hybrid) |

F vs D4 isolates keep-alive under scoping. E vs F isolates the re-auth cache.
The equivalence gate asserts identical-shape results on every arm, so no arm
wins by skipping work.

## Measured (median ms per iteration; p90 in parentheses)

auth=5ms, history-heavy (4 x history_record):
D4 66.0 (105.7) | F 54.5 (79.7), 1.21x | E 29.5 (58.3), 2.24x | cache win vs F: 1.85x

auth=5ms, mixed (3 steps x 3 obs calls + history_record):
D4 125.0 (243.5) | F 85.5 (182.4), 1.46x | E 66.8 (129.2), 1.87x | cache win vs F: 1.28x

auth=25ms, history-heavy:
D4 142.0 (181.0) | F 130.9 (174.3), 1.08x | E 43.9 (86.1), 3.24x | cache win vs F: 2.99x

auth=25ms, mixed:
D4 169.4 (284.7) | F 148.6 (229.7), 1.14x | E 93.8 (128.4), 1.81x | cache win vs F: 1.58x

## Reading

- Keep-alive alone (F vs D4) is modest: 1.08–1.46x. On loopback the connection
  setup is cheap; the auth tax dominates the per-call budget — the same
  conclusion as the auth-lifetime bench.
- The re-auth cache (E vs F) is the real win: 1.28–2.99x, growing with auth
  cost. At 25ms auth on history-heavy traffic the hybrid is 3.24x vs today.
- On the realistic mixed sequence (observation loop + one history record per
  step) the hybrid lands at 1.81–1.87x vs today.
- p90s track medians in every cell: the win is structural, not a median artifact.

## What this means for the design question

Post-#3505, the (a)-half of dq-3383 is settled by maintainer action. The live
question is only the hybrid: is a per-connection verify cache an acceptable
trust window, or is per-request re-verify load-bearing as a TOCTOU guarantee
on the app bundle? The measurement says the question is worth 1.3–3x on
history traffic — material enough to ask, not so large it decides itself.
If the answer is "re-verify is load-bearing", the fallback is F: keep-alive
with per-request re-verify, a 1.1–1.5x transport win with zero trust change.

## Honesty notes

- The mock's auth is a sleep, not a real codesign verify; it brackets the
  cost (5/25ms) rather than reproducing it. The mechanism (amortization) is
  what is being measured, not the absolute ms.
- `history_record` is a stand-in; the real methods are `history_control` /
  `history_relaunch_state`, which are control-plane-rare, not per-step. The
  history-heavy sequence models bursty control traffic (e.g. scripts polling
  history status); the mixed sequence is the realistic loop shape.
- First full run died on a daemon-start timeout at 25ms/18-of-30 iters (transient
  spawn failure after ~300 daemon launches); the bench now retries daemon
  start 3x and checkpoints full raw times every iteration. Re-ran clean.
