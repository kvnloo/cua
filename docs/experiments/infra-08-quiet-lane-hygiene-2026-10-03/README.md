# INFRA-08: quiet-lane hygiene (quiet-timed v2, quiet-shared, quiet-holders)

Lane INFRA-08, wave 8 of the CUA RFC loop. Owner: kvnloo/cua#73 (loop infrastructure; STATE.infra_followups W7).
Type: fix to loop tooling outside the product. Evidence class for every test row: **UNIT**. TypeSafe: 0 attempts / 0 reached (lane cap 0).

**Disposition: KEEP.** The three scripts are installed in the loop `bin/`. In the final runs (8, 9 and 10), every v2 row passed: 17 of 17 per run. In the same runs, the v1 rows showed the red-before results set in PREREG: 12 of 12 rows matched their expected result per run.

**Defect in the first install, found and fixed in this lane.** The first installed quiet-timed v2 (install_1) could leave its alarm `sleep 900` behind when the lock was granted at once. The leftover sleep held the caller's stdout and stderr, so a caller reading them waited up to 900 s. A 300-run stress showed 47 hangs out of 300. The defect was live from 21:11:58Z to 21:37:29Z, when install_2 replaced it. The red-before / green-after evidence is under T7 below.

## Problem (wave-7 evidence)

- `bin/quiet-timed` (v1) opened fd 9 on `quiet-lane.lock` without close-on-exec. Every process the timed command started inherited the lock, and a daemon started inside a phase kept it after quiet-timed exited.
- If quiet-timed was killed while it waited, its `flock -x` child stayed queued.
- There was no starvation signal.
- `flock(2)` has no writer priority, so overlapping SHARED holders can starve EXCLUSIVE waiters indefinitely. In wave 7, another track's SHARED wrapper leaked the same fd and held SHARED from about 14:59Z to 18:48Z. This blocked B-09 and R2-07f and delayed R2-07g and FRESH-07.

## Fix (three scripts; templates in `scripts/`, rendered by `render.sh`)

| script | change |
|---|---|
| `quiet-timed` v2 | **What stays the same:** the CLI, the exit code, and the receipt line (`label, pid, acquired, released, rc, cmd_sha256`), which is byte-compatible with v1. **Lock fd:** the command runs as `"$@" 9>&-`, so only quiet-timed holds the lock. **Waiting:** the shell owns two children, the `flock -x 9` waiter and one `sleep` timer for the alarm, and waits for whichever ends first with `wait -n -p`. TERM, INT and HUP only set a flag, so every exit path knows both pids. Cleanup sends SIGKILL to its own two children. On a signal while waiting, quiet-timed exits 143, 130 or 129 and writes no receipt. After the lock is granted, the traps are removed, so signal behaviour during the command matches v1. **Alarm:** each time the timer fires (every `QUIET_STARVE_ALARM_S`, default 900 s; 0 disables), quiet-timed writes `locks/starvation/<label>-<utc>.txt` with an atomic write. The alarm signals nothing. |
| `quiet-holders` | New, read-only. Prints a TSV with `state mode pid ppid elapsed_s exe` for every FLOCK entry on the lock inode in `/proc/locks`, matched by inode and by the mount's major:minor. ppid, elapsed time and exe (the `comm` name) come from `ps`. It never prints command lines or environment. |
| `quiet-shared <label> <max_s> <cmd>` | New SHARED helper for the loop. It waits while `quiet-holders` shows a queued EXCLUSIVE (`waiting WRITE`) entry. It then takes SHARED with a polled `flock -n -s`, so it never queues in the kernel ahead of or among writers. It runs the command with fd 9 closed under `timeout -k 30 <max_s>` and appends a receipt with the same six keys plus a trailing `"mode":"shared"`. |

`QUIET_LANE_LOCKDIR` overrides the lock directory, for tests only. Installed copies default to the loop lock directory, which is unchanged from v1. The committed templates hold the placeholder `@QUIET_LANE_DEFAULT_LOCKDIR@` in place of a local path. Each script starts with a USAGE note. `v1-vs-v2.diff` is the diff of the templated v1 against the final v2. The templated v1 renders back to the installed v1 byte for byte (sha256 `65c8741b…579b`). `scripts/history/quiet-timed.v2pre` is the install_1 template, kept as red evidence.

**Why SIGKILL for its own children.** A child that receives a signal after `fork` but before `exec` still runs the parent shell's signal handlers. A TERM can therefore be swallowed, after which the child execs anyway and survives. Two versions showed this. The alarm-subshell design (v2pre) orphaned its sleep in 47 of 300 uncontended runs. A `wait -n` rewrite that still used TERM (run6) left a sleep behind in 1 of 20 runs, and quiet-timed then waited on it. With SIGKILL: 0 of 300.

## Tests: forced path, oracle, controls

The harness is `tests/test_quiet_lane.py`, run under `bin/hostless`. It refuses to run outside it. Each test renders the templates into its own scratch lock directory, so the live lock file is never used. The oracle is the kernel lock table (`/proc/locks`), the test's own `flock(LOCK_EX|LOCK_NB)` try-lock, and `/proc` process state. The scripts' own output is not used as the oracle. A row whose precondition fails is recorded as INVALID and never counts as a match.

| test | forced path | v1 (red-before) | v2 (green-after) |
|---|---|---|---|
| T0 | v2 rendered with a sentinel default and run with the override: the sentinel is never created. Without the override, the rendered default is used. | N/A | GREEN |
| T1 | The command starts a `setsid sleep 600` daemon and exits. With the daemon confirmed alive, the test tries an exclusive try-lock. | **RED**: the daemon holds the lock | GREEN |
| T1s | Same as T1, through quiet-shared | N/A | GREEN |
| T2 | Same command (args with a space and a quote): key list and order, `cmd_sha256`, and the line with pid and timestamps masked | GREEN (baseline schema) | GREEN: v1 and v2 lines identical after masking; quiet-shared = the same 6 keys plus `mode` |
| T3 | The test holds EXCLUSIVE, quiet-timed queues, and the test sends TERM (v2 also INT and HUP). Survivors are taken from the descendant set captured before the signal. | **RED**: the `flock` waiter survives and stays queued | GREEN: no survivors, no queued entry, the command never ran, no receipt |
| T4 | The test holds SHARED, quiet-timed queues EXCLUSIVE, then quiet-shared starts | **RED** (no quiet-shared) | GREEN: no acquire within 3 s while the writer is queued. Order is X then S; shared `acquired` ≥ exclusive `released` |
| T4c | Control: a plain `flock -s` wrapper in the same setup | GREEN: it overtakes the writer (S, X) | GREEN: it overtakes (S, X). The control discriminates. |
| T4n / T4t | No writer queued: quiet-shared acquires in under 3 s. `max_s=1` on `sleep 30`: rc 124 in under 5 s, receipt rc 124, lock free afterwards | N/A | GREEN |
| T5 | The test holds EXCLUSIVE with `QUIET_STARVE_ALARM_S=2`. The command carries a marker argument and the environment carries a marker value. | **RED** (no alarm) | GREEN: at least 2 snapshots (first and repeat), header keys exactly `label waiter_pid waited_s utc`, columns exactly `state mode pid ppid elapsed_s exe`, a holding row for the test pid and a waiting WRITE row. Both markers are absent, and no file appears after the lock is granted. |
| T6 | rc 0, 1, 7 and 255 | GREEN | GREEN (quiet-timed and quiet-shared; receipt rc = exit code) |
| T7 / T7s *(added after PREREG)* | 20 uncontended calls with stdout and stderr on pipes: each call must return within 5 s, and no process may remain with the scratch directory as its cwd | GREEN | GREEN. **v2pre (install_1): RED** (run7). Stress of 300 calls: v2 0 hung / 0 leftover; v2pre 47 hung / 47 leftover sleeps |

### Results: N of M (every run kept, `raw/runN/<impl>.{jsonl,log}`, `raw/stress/`)

| run | quiet-timed template | v1 | v2 | v2pre | counts |
|---|---|---|---|---|---|
| run1 | `8a03808b` (commit `2cdfbd80d`) | 11/11 *(T3 row invalid)* | not run | | no: test bug |
| run2 | `8a03808b` | 11/11 | 15/15 | | no: superseded |
| run3 | `710c38aa` | 11/11 | 15/15 | | no: superseded (alarm subshell; T7 did not exist) |
| run4, run5 | `745e66b0` (= v2pre, install_1) | 11/11 | 15/15 | | no: superseded (orphan defect) |
| run6 | `620a77cc` (`wait -n`, TERM cleanup) | 12/12 | **16/17** (T7 RED) | 16/17 (T7s expectation mis-set) | no |
| run7 | `2502ef3f` (final) | 12/12 | 17/17 | 17/17 (T7 RED as expected) | v2pre red evidence |
| run8, run9, run10 | `2502ef3f` (final) | 12/12 each | 17/17 each | | **yes** |

The tests took about 20-40 s per implementation per run. There is no timing claim. This lane deletes no work and saves no wall-clock time from any task. Its effect is on lock availability for the timing lanes, and that effect is not measured here.

## Install record (sha256 only)

The installs followed the green runs. `quiet-timed` was backed up once, to `quiet-timed.v1` with `cp -p`. Each script was rendered with the default lock directory, written to a dot-temp file in `bin/`, set to mode 755 and moved onto its name with `mv -f`. That is an atomic rename to a new inode, so running instances keep their old inode. No process outside this lane's own tests was signalled or stopped, and no other track's wrapper was edited.

| file | before install_1 | install_1 (21:11:58Z) | install_2 (21:37:29Z, current) |
|---|---|---|---|
| quiet-timed | `65c8741b9f93486dd91a68bd6a7071086d8702ab50c4aab73be0f75113dd579b` (v1) | `b55f84a40d937af863d9bdbd32e361fcf66d9f2b94e7bfe3a302fdfcc55cd170` (v2pre, defect) | `e3e9b1da0491ad429ab62fec34aeb355bf3bf8d999e552755d1b1ca83e43c603` |
| quiet-timed.v1 | absent | `65c8741b9f93486dd91a68bd6a7071086d8702ab50c4aab73be0f75113dd579b` | unchanged |
| quiet-shared | absent | `2fd7ae829abf655129329a75020d000b39364be050925b52770d4d4090ea9e38` | unchanged |
| quiet-holders | absent | `28a5493091bac4fa4974fde2be110f91cf6dc3a446163ca4c0faab0bb00a206a` | unchanged |

**install_1 exposure.** While install_1 was live, the ledger shows three EXCLUSIVE receipts: this lane's smoke and two receipts from another track (labels `bendperf-audit-repro` and `bendperf-audit-untried`). A sleep orphaned by those runs, if any, holds no lock fd and exits by itself within 900 s. This lane did not signal it.

**Live smoke 1 (install_1): RAN.** It ran as `hostless timeout 600 quiet-timed infra08-smoke true`. It started at 21:12:05.553Z with 5 SHARED holders on the lock and waited 271 s. EXCLUSIVE was granted at 21:16:36.583Z and released at 21:16:36.586Z, with rc 0. The receipt has the v1 key set. Evidence: `raw/install/`.

**Live smoke 2 (install_2): SKIPPED (not granted within 10 min).** It ran as `hostless timeout 600 quiet-timed infra08-smoke2 true`, with the output captured through a pipe. It started at 21:37:44.226Z with 6 SHARED holders on the lock. Other tracks then held the lock SHARED without a gap for the full 600 s; at the end, one python3 holder was at 708 s and one flock holder at 939 s. `timeout` sent TERM at 21:47:44Z. quiet-timed exited (rc 124 from `timeout`), returned the captured pipe at once with 0 bytes, and wrote no receipt. The holder list afterwards shows no waiting entry, so its waiter was reaped on the live lock. This is the starvation the Limits section describes, observed again live. Evidence: `raw/install2/smoke.log`.

## Deviations

1. **Shakedown before PREREG.** One smoke render and run of v2 ran in a scratch lock directory. It was not a trial and is not counted.
2. **run1 test bug.** The T3 scratch directory name contained spaces. v1 assigns `LOCKDIR=` without quotes, so the v1 script broke (rc 127) and its T3 row was RED for the wrong reason: no waiter was ever queued. Fixes: space-free scratch names, plus the INVALID precondition state. The local path in the run1 log is redacted to `<lane-tmp>`.
3. **v2 redesign after PREREG and after install_1.** The verifier re-run (`verify_artifacts.py --rerun`, with output piped) hung because orphaned `sleep 900` processes from the alarm subshell held the pipe. The cause, the fix (`wait -n` with SIGKILL cleanup and no alarm subshell) and the new regression test T7/T7s are described above. T7 was added after PREREG. Its expectations are recorded in the test file (`EXPECT`), including v2pre RED. Earlier script tweaks (atomic snapshot write, a repeat snapshot in T5) are also post-PREREG. PREREG pins the tests and pass rule, not the code.
4. **Second install.** install_2 replaced install_1's quiet-timed by atomic rename. Only quiet-timed changed; quiet-shared and quiet-holders are byte-identical.
5. **Leftovers from this lane's own test runs.** 21 orphaned `sleep 900` processes (runs 4-5, the first verifier re-run and a reproduction script) and 1 from v2pre run7 were identified by their cwd in this lane's directories and killed by exact pid. All were started by this lane's own tests.
6. **Near misses (no effect possible).** Four host-shell commands ran outside `hostless`, none touching the desktop: `bash -n` (syntax check only), `python3 -` with empty stdin, and `python3 -c 1` twice.

## Limits

- **No writer priority over non-cooperating SHARED holders.** quiet-shared yields only for the loop's own SHARED users. Other tracks' wrappers (not edited) can still overlap SHARED holds and starve EXCLUSIVE waiters. The alarm makes this visible but cannot stop it. quiet-shared checks for queued writers and then try-locks; in the gap between the two (one poll), a writer that queues can be overtaken once.
- **Holder pids from flock(1).** For a lock taken by `flock <fd>` from a shell (as v1, v2 and most wrappers do), `/proc/locks` records the pid of the `flock` process, which has already exited. quiet-holders shows these as `- - (not-running)`. The process that actually holds the fd, such as a leaked daemon, cannot be named from `/proc/locks`. Under `hostless`, Landlock also denies reading other domains' `/proc/<pid>/fd`.
- **SIGKILL of quiet-timed while waiting** cannot be trapped. The `flock` waiter stays queued until the lock is granted and then exits at once. The timer exits after at most one period and holds no lock fd and no caller stdio.
- **Inode match.** If `findmnt` is unavailable, quiet-holders matches by inode only.
- `wait -n -p` needs bash 5.1 or later. This host has 5.3.

## Claim boundary

This lane changes loop tooling only. It does not change Driver behaviour, adds no product service and touches no `libs/` source. It cannot force other tracks to yield, so remaining starvation from cooperating-but-long SHARED holders is reported, not solved. None of the results is a timing measurement.

## Files

`PREREG.json`, `scripts/` (templates; `scripts/v1/quiet-timed` = installed v1; `scripts/history/quiet-timed.v2pre` = install_1), `render.sh`, `tests/test_quiet_lane.py`, `raw/run1..run10/`, `raw/stress/`, `raw/install/`, `raw/install2/` (smoke logs and holder snapshots, pids and comm names only), `v1-vs-v2.diff`, `summary.json`, `provenance.json`, `verify_artifacts.py`.

Verify with `hostless python3 verify_artifacts.py`, which runs the static checks. Add `--rerun --tmp <scratch>` to re-run both implementations, and `--installed-bin <bin> --live-lockdir <lockdir> --tmp <scratch>` to check the install record.
