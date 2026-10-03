# PKT-01: clean-checkout audit of every published packet, and a packet template, 2026-10-03

Owners: kvnloo/cua#75 (OWN-75R), kvnloo/cua#93 (experiment packets), kvnloo/cua#10 (accounting that cites them).
Lane PKT-01, wave 4, attempt 2. Evidence classes: SOURCE (audit, text fixes), UNIT (template helper
controls), NOT_RUN (no measurement). TypeSafe: 0 attempts, 0 reached.

## Result in one paragraph

- **Coverage: 27 of 27 pushed packets.** The list is the accepted, pushed packets in the loop state
  (`waves[*].publish_commits` and `pushed_branches`): R2-01..R2-10, B-01R, B-02, B-03, N-01R, N-02,
  FIX-01, FIX-02, BUG-01, OWN-09, OWN-09R, OWN-16, OWN-16W, OWN-20, OWN-36, OWN-75R, OWN-78, OWN-105.
  Every recorded head equals the branch head on origin (`git ls-remote origin`, 02:40:08Z).
- **Reproduction from a clean clone: 26 of 27 pass.** Each head was checked out from a fresh
  `git clone --shared` and its own `verify_artifacts.py` ran under `bin/hostless`. OWN-75R (`e02621fdc`)
  fails: `FileNotFoundError` on `raw/unit/head-python-unittest.log`, because the repository rule `*.log`
  kept 48 cited logs out of the published commit. No verifier started a GUI, Driver or browser.
- **Repairs: 4 heads, 4 of 4 pass from a clean clone.** OWN-75R r1b (`112/112 checks passed`) commits
  the 48 logs. R2-10, B-03 and R2-09 r1b apply the open wave-3 publish fixes. R2-10's verifier now also
  recomputes every new number from `raw/` (`132/132 checks passed`). Run against the published head it
  stops with `FileNotFoundError` (`raw/controls/r2-10-verifier-red-before.txt`): that shows the addendum
  files are absent there, not that the new checks discriminate. The discriminating control is a
  mutation: with the README's 27.60 changed to 27.61 and 0.98 to 0.97, exactly the 2 checks that cite
  them fail (127/129 with `--skip-git`; wave-4 fresh verifier, reproduced by PUB-02 in
  `docs/experiments/pub-02-privacy-gate-2026-10-03/raw/controls/r2-10-mutation-control.txt`). No
  measured number or raw trial record changed in any repair.
- **Ignored-but-cited files.** The template helper (whole README and headline JSON) finds a cited,
  git-ignored file at 4 pushed heads. Only OWN-75R's is missing evidence, and it is repaired. The other
  three are deviation text about the ignore rule or a file the README already says is not committed
  (`cited-triage.json`). R2-10 and B-03 also left their chunk and session logs out of the published
  commits. Their READMEs describe those logs in prose, so the helper cannot see them; the repairs commit
  them and cite them by path.
- **Privacy: 0 findings on the 7 new commits** (5 repair commits and the 2 commits of this branch) with
  this audit's scanner. Over the 195 commits of the 27 pushed heads there are 0 absolute local paths,
  0 host names and 0 secret patterns. There are 7 local directory names, all already on origin and none
  of them a path, host or secret. Details are under Privacy. This scanner does not decode hex or base64:
  PUB-02's decoding scan finds R2-10's hex-encoded private-name list in the repair commit `36ccdd766`
  (inherited from `030f6bdbf`, already on origin; `docs/experiments/pub-02-privacy-gate-2026-10-03/`).
- **Earlier-wave publish fixes (N-01R, B-02, FIX-01, OWN-09, OWN-36, OWN-20):** 36 fixes. 27 are open,
  4 partly applied, 2 applied, 1 accepted by ruling and 2 are not packet edits (`publish-fixes-status.json`).
  None of them makes a verifier fail, so none was applied here.
- **Template:** `docs/experiments/_template/` has a packet-local `.gitignore`, a README skeleton with the
  provenance fields, and `verify_helper.py`. The UNIT controls pass 5 of 5: a planted ignored or
  untracked cited file is caught (positive), and a packet that uses the template `.gitignore` passes
  (negative) (`raw/controls/template-unit.txt`).

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Audit branch base | upstream main `41c34cb0d704d816e612dd3f9d0c816cdfacf178` (main at planning) | SOURCE |
| Audited heads | the 27 rows below, each also equal to origin at 02:40:08Z (`raw/origin-heads-start.txt`) | SOURCE |
| Repair heads | the 4 rows below (local branches, not pushed; Publish pushes them) | SOURCE |
| Verifier versions | sha256 of each `verify_artifacts.py` in `audit.json` (`pushed[*].verifier.sha256`, `repairs[*].verifier.sha256`) and its git blob | SOURCE |
| Environment | every verifier, audit and helper run under `bin/hostless` (env strip, private runtime dir, Landlock scope); Python 3.14.7, git 2.55.0, Linux 7.2.2; no private X11/sway session needed or started | SOURCE |
| Audit runs | repairs 03:16:54Z, pushed 03:24:11Z (`raw/audit-repairs.json`, `raw/audit-pushed.json`) | SOURCE |
| Origin heads at end | `raw/origin-heads-end.txt`, read 03:26:16Z: every audited head unchanged | SOURCE |
| Publication SHA | set by Publish; this lane pushes nothing | - |
| Driver binary | none run (no measurement) | NOT_RUN |
| Provider | none: 0 attempts, 0 reached | NOT_RUN |

## Method

1. **Heads.** `git ls-remote origin` once at the start, filtered to the audited branches
   (`raw/origin-heads-start.txt`), and once at the end (`raw/origin-heads-end.txt`).
2. **Clean checkout.** `audit_packets.py run` makes one `git clone --shared --no-checkout` of the main
   clone per head and checks the head out on a branch with the published name. No lane worktree file is
   used. The clone is deleted afterwards.
3. **Verifier.** The packet's `verify_artifacts.py` runs from its packet directory with the flags the
   packet documents: `--git <clone>` (FIX-02), `--git-range <merge-base>..HEAD` (OWN-09, OWN-09R),
   `--ledger <quiet-lane-ledger>` (OWN-20) and `--host <host>` (OWN-16W). TMPDIR is private to each run.
   Output is scrubbed of machine strings read at run time and kept under `raw/verifier-output/`.
4. **Cited files.** `../_template/verify_helper.py` (`check_cited`, whole README plus headline JSON)
   lists every cited packet path that git does not track, and whether git ignores it.
5. **Privacy.** Every commit from the merge-base with upstream main to the head is scanned: every added
   or modified blob (members of `.gz` and `.tar.gz` too), path names, commit messages and identities.
   Patterns: absolute home and mount paths, the local roots, `/tmp` paths, the host name, local
   directory names, and secret shapes. Only counts are recorded, never matched values. Public locations
   are recorded but are not findings: the GitHub Actions runner home, `/run/user/<n>`, and
   `/tmp/.X11-unix` / `/tmp/.ICE-unix`.
6. **Repairs.** Repairs are made only where a verifier fails (OWN-75R), plus the three wave-3
   publish-fix branches. Each repair is the smallest change: force-added logs with sha256 manifests,
   errata and wording. Each log first goes through the packet's own scrubber. Measured numbers and raw
   trial records are never edited.
7. **Assemble.** `audit_packets.py assemble` writes `audit.json`, which holds the summary, the gates,
   the publish-fix status and every per-head record. `verify_artifacts.py` re-checks it against the
   heads (`--rerun` re-runs the repaired verifiers from fresh clones).

## Pushed heads (SOURCE; verifier columns from a clean clone under hostless)

| Packet | Branch | Head | Verifier | Flags | Cited and git-ignored | Commits scanned | Severe privacy findings |
|---|---|---|---|---|---|---|---|
| R2-01 | `exp/r2-01-feedback-ab-20261001` | `2ca82efaedf0` | PASS (rc 0) | - | 0 | 4 | 0 |
| R2-02 | `exp/r2-02-cdp-wake-20261001` | `8e751a75dd45` | PASS (rc 0) | - | 0 | 8 | 0 |
| R2-03 | `exp/r2-03-guarded-live-20261001` | `6bab214abb70` | PASS (rc 0) | - | 0 | 4 | 0 |
| R2-04 | `exp/r2-04-atspi-profile-20261001` | `9bfd43739057` | PASS (rc 0) | - | 1 | 4 | 0 |
| R2-05 | `exp/r2-05-ack-loss-real-20261001` | `236e37e01792` | PASS (rc 0) | - | 0 | 8 | 0 |
| R2-06 | `exp/r2-06-trusted-input-20261001` | `f00b9396365a` | PASS (rc 0) | - | 3 | 3 | 0 |
| R2-07 | `exp/r2-07-compiled-routine-20261002` | `2d71548b4611` | PASS (rc 0) | - | 0 | 5 | 0 |
| R2-08 | `exp/r2-08-cross-surface-20261002` | `afba150d5542` | PASS (rc 0) | - | 0 | 3 | 0 |
| R2-09 | `exp/r2-09-native-event-wake-20261002` | `3539e34ae16d` | PASS (rc 0) | - | 0 | 9 | 0 |
| R2-10 | `exp/r2-10-composition-20261002` | `030f6bdbf811` | PASS (rc 0) | - | 0 | 11 | 0 |
| B-01R | `exp/b-01r-browser-critpath-textfix-20261002` | `0cd63f786290` | PASS (rc 0) | - | 0 | 9 | 0 |
| B-02 | `exp/b-02-browser-driver-sites-20261002` | `b282ff3894fa` | PASS (rc 0) | - | 0 | 12 | 0 |
| B-03 | `exp/b-03-toggle-cold-snapshot-20261002` | `b34eef71ee40` | PASS (rc 0) | - | 0 | 15 | 0 |
| N-01R | `exp/n-01r-native-wait-ab-20261002` | `3bb4a7fc70d1` | PASS (rc 0) | - | 0 | 6 | 0 |
| N-02 | `exp/n-02-native-transport-20261002` | `9846ac8033a8` | PASS (rc 0) | - | 0 | 10 | 0 |
| FIX-01 | `exp/fix-01-detached-node-refusal-20261002` | `4a301d32a96d` | PASS (rc 0) | - | 0 | 10 | 0 |
| FIX-02 | `exp/fix-02-token-ownership-retry-scope-20261002` | `cea02cb74cc1` | PASS (rc 0) | --git <clone> | 0 | 10 | 0 |
| BUG-01 | `exp/bug-01-delivery-cdp-sessions-20261002` | `097b4f0974d5` | PASS (rc 0) | - | 0 | 10 | 0 |
| OWN-09 | `exp/own-09-cancel-barrier-rows-20261002` | `bf07c8fe374b` | PASS (rc 0) | --git-range 352507b6c031..HEAD | 2 | 8 | 0 |
| OWN-09R | `exp/own-09r-84-revision-20261002` | `0c2896a53e18` | PASS (rc 0) | --git-range 989cc76cec26..HEAD | 0 | 11 | 0 |
| OWN-16 | `exp/own-16-modality-truth-20261002` | `7a4f3252af9c` | PASS (rc 0) | - | 0 | 5 | 0 |
| OWN-16W | `exp/own-16w-sway-modality-20261002` | `1b981915777f` | PASS (rc 0) | --host <host> | 0 | 6 | 0 |
| OWN-20 | `exp/own-20-atspi-invalidation-census-20261002` | `6da15bf3516d` | PASS (rc 0) | --ledger <quiet-lane-ledger> | 0 | 4 | 0 |
| OWN-36 | `exp/own-36-session-isolation-native-20261002` | `ff77554f46db` | PASS (rc 0) | - | 0 | 2 | 0 |
| OWN-75R | `exp/own-75r-timing-parity-4336-20261002` | `e02621fdc1fe` | FAIL (rc 1) | - | 2 | 5 | 0 |
| OWN-78 | `exp/own-78-provider-receipts-4394-20261002` | `5107f3ccaef3` | PASS (rc 0) | - | 0 | 4 | 0 |
| OWN-105 | `exp/own-105-runner-reconcile-20261002` | `b97daa4ba086` | PASS (rc 0) | - | 0 | 9 | 0 |

## Repair heads (SOURCE; not pushed)

| Packet | Branch | Head | Verifier | Flags | Cited and git-ignored | Commits scanned | Severe privacy findings |
|---|---|---|---|---|---|---|---|
| OWN-75R | `exp/own-75r-timing-parity-4336-r1b-20261003` | `efe36d1a1efd` | PASS (rc 0) | - | 0 | 7 | 0 |
| R2-10 | `exp/r2-10-composition-r1b-20261003` | `36ccdd766fca` | PASS (rc 0) | - | 0 | 12 | 0 |
| B-03 | `exp/b-03-toggle-cold-snapshot-r1b-20261003` | `911e2079694e` | PASS (rc 0) | - | 0 | 16 | 0 |
| R2-09 | `exp/r2-09-native-event-wake-r1b-20261003` | `ffb4919a7b5b` | PASS (rc 0) | - | 0 | 10 | 0 |

What each repair changes (all SOURCE, no new run):

| Packet | Base (pushed head) | Change | Verifier from a clean clone |
|---|---|---|---|
| OWN-75R | `e02621fdc` | `823ff9784` (attempt 1, reviewed here): packet `.gitignore` (`!*.log`, `!build/`), the 48 cited logs force-added from the wave-3 lane worktree after the packet's own Sanitizer and D14 rule, sha256 manifests, errata. Review: all 48 committed hashes equal `raw/force-added-logs.sha256`; unit and mutation logs byte-identical to the lane worktree, which is byte-identical to the artifact mirror; the 16 session logs differ only by the two placeholder rules the errata names; privacy clean. `efe36d1a1`: errata names the r1b branch and records this review. No file was missing anywhere | `112/112 checks passed` (was `FileNotFoundError`) |
| R2-10 | `030f6bdbf` | the 7 wave-3 publish fixes: 28 scrubbed chunk logs force-added (scrubber 0 changes; dbus socket path rewritten in 27) with manifests; S on T_land next to S on T_oracle (native checkbox X 1.00 [0.95, 1.06] vs 1.18; text X 27.60 [26.62, 27.65]); `provenance-addendum.json` (browser Driver name + sha256 per manifest; `live_heads_at_publication` for Publish); Deviation 2 discloses `nw2gate`; fill COMP_K amortized ratio of means 0.98 [0.92, 1.01] next to median 1.01; evidence classes on decomposition and work-deleted rows. Attempt-1's uncommitted work was reviewed and reused; the addendum was restructured to carry name + sha256 per manifest and the logs were re-derived (byte-identical to attempt 1's) | `132/132 checks passed`; 17 new checks recompute each new number from `raw/` |
| B-03 | `b34eef71e` | the 6 wave-3 publish fixes: six session/runner logs committed (packager rules re-applied: 0 changes); freshness row 437 files (300 was the compare-API cap); R2-10 shake1 took the quiet lock 17 ms after `b03-measured-a` released it (loop ledger 17:35:21.360Z / 17:35:21.377Z); per-process part at D0 also absorbed by waiting; failed negative control cause undetermined; disposition reason 3 removed as a reason; D80 is ~81-82 ms after navigate returns; K5V untested fraction 1.007 explained; PREREG `failing_gate` vs analyzer (Deviation 9); kvnloo/cua#N references | 17 checks, `"failures": []` |
| R2-09 | `3539e34ae` | the 5 wave-3 publish fixes: control (b) foreign events inside the real wait median 9.5 (6-11), recomputed from `raw/` with the packet's `analyze.trial_metrics` (the summary's 15 counts reply -20 ms to +50 ms); in-page decoy events inside the wait 8/10; settle-watch focus-change qualifier; controls REAL+FIXTURE; KILL-over-KEEP precedence stated (both rules fired; not ordered in PREREG); Chromium foreground SOURCE + REAL pilot n=1 | `PASS: 0 failed checks` |

## Ignored-but-cited files and other cited paths not in git

| Packet (head) | Path the helper reports | Kind | Reading |
|---|---|---|---|
| OWN-75R (`e02621fdc`) | `raw/real/session-block-*.log`, `session-block-m11.log` | ignored | missing evidence; **repaired** on r1b (with the 32 unit and mutation logs the README cites only by directory) |
| R2-04 | `*.log` | ignored | deviation text about the rule; the renamed `raw/unit/*.txt` are tracked |
| R2-06 | `raw/main/probe-stdout.log`, `*.log`, `main.log` | ignored | Deviation 6 already says the log was dropped from the Files list and is not committed; no check reads it |
| OWN-09 | `raw/logs/*.log`, `*.log` | ignored | deviation text: the logs are committed as `raw/logs/*.txt` |
| R2-09 (both heads) | `r209-trial-metrics.jsonl` | untracked | the analyzer output name in the Method command; committed gzipped (`r209-trial-metrics.jsonl.gz`) |
| FIX-01 | `raw/learn/artifact.json` | untracked | R2-07's file, cited by blob |
| R2-10, B-03 (pushed) | chunk logs (`raw/logs/`), `raw/*/…session.log` | not seen by the helper (prose or placeholder citation) | flagged by the wave-3 verifiers; **committed** on r1b and cited by path |

The helper cannot see a file that is cited only by its directory (OWN-75R's `raw/unit`) or in prose.
The verifier run is the check for those.

## Privacy (every commit of every audited head)

- Severe findings (absolute home or mount path, local root, host name, secret pattern): 0 at the 27
  pushed heads (195 commits) and 0 at the 4 repair heads.
- New commits, 7: the repair commits `823ff9784`, `efe36d1a1`, `36ccdd766`, `911e20796`, `ffb4919a7`
  (this audit) and this branch's `058774ffb`, `cca59642d` (wave-4 fresh verifier): 0 findings of any
  counted kind, including `/tmp` paths and local directory names. Identities: Kevin Rajan with
  7121943+kvnloo@users.noreply.github.com. The scan does not decode hex or base64; `36ccdd766` carries
  R2-10's hex-encoded private-name list (found by PUB-02).
- Already on origin, not paths, host or secrets, not changed here. Local directory names occur 7 times,
  each a commit and file pair:
  - the privacy regexes of the R2-02 verifier (3 commits), the N-01R verifier (`8ff42418d`,
    `9421e1ccd`; also inherited by N-02 and R2-09; accepted in wave 2) and the B-03 verifier (accepted
    in wave 3);
  - the default lock path in R2-08 `run_negatives.sh`, a relative path.
- Also already on origin: 33 finding records of example paths under the system temp directory, from
  the upstream jev-use README (`jev-native-*` directories) and verifier regex literals.
- Not findings (records): the GitHub Actions runner home in upstream CI (9), `/run/user/0` in upstream
  Wayland code (2), `/tmp/.X11-unix` (16).

## Earlier-wave publish fixes (`publish-fixes-status.json`)

| Packet | Fixes | Open | Partly | Applied at pushed head | Other | Verifier fails because of one |
|---|---|---|---|---|---|---|
| N-01R | 5 | 4 (wording, R2-09 framing, 900 ms knob note, rounding) | 0 | 0 | 1 accepted by ruling (history blobs) | no |
| B-02 | 7 | 7 | 0 | 0 | 0 | no |
| FIX-01 | 6 | 6 | 0 | 0 | 0 | no |
| OWN-09 | 4 | 0 | 1 (R4 relabelled; C-ABI NOT_RUN sentence missing) | 1 (M R1 by-rule caveat) | 2 not packet edits | no |
| OWN-36 | 6 | 4 | 1 (PREREG time) | 1 (I3 shared window) | 0 | no |
| OWN-20 | 8 | 6 | 2 (headline, hostless v1/v2) | 0 | 0 | no |

None of these makes a verifier fail, so under this lane's rule none was applied. They stay open for
the documents that cite these packets (the kvnloo/cua#10 table and the trycua/cua issue 3963 rewrite).

## Template (`docs/experiments/_template/`)

| File | Contents | Evidence class |
|---|---|---|
| `.gitignore` | packet-local `!*.log`, `!build/` (plus `__pycache__/`, `*.pyc`) | SOURCE |
| `README.md` | skeleton: forced path, route/producer, oracle, controls, tested SHA + rust tree, Driver sha256 + version, environment, live heads vs tested vs publication SHA, claim boundary, evidence class per row, work deleted vs wall-clock saved, Files table | SOURCE |
| `verify_helper.py` | `check_cited(packet, scope)`: fails on a file cited in the README Files section (whole README if there is none, or with `--readme all`) or in `*summary*.json` / `headline*.json` that git ignores or does not track | SOURCE |
| `test_verify_helper.py` | UNIT controls, 5/5 pass: positive (a cited `raw/run.log` and `raw/build/report.txt` reported `ignored`, a never-added `raw/extra.json` reported `untracked`, a headline-JSON citation reported); negative (the same packet with the template `.gitignore` and every file committed: no finding); scope; the template itself passes | UNIT |

Applied to real heads, the helper reports OWN-75R's session logs as ignored at `e02621fdc` and finds
nothing at the r1b head.
PUB-02 (2026-10-03) later added `check_privacy` to `verify_helper.py` and 6 UNIT tests to
`test_verify_helper.py` (11/11 pass); see `docs/experiments/pub-02-privacy-gate-2026-10-03/`.

## Gates (recomputed by `verify_artifacts.py`; the privacy gate is qualified by PUB-02)

| Gate | Result | Evidence class |
|---|---|---|
| every repaired head's verifier passes from a clean clone | 4/4 | SOURCE |
| the audit covers 100% of pushed packets | 27/27, heads equal to origin | SOURCE |
| 0 privacy findings on any new commit | 0 on 7 new commits with this audit's scanner; not met under PUB-02's hex/base64-decoding scan (`36ccdd766`: encoded name list) | SOURCE |
| the template helper catches a planted ignored-but-cited file and passes a clean packet | positive and negative controls pass | UNIT |

## Work deleted vs wall-clock saved

None claimed. This packet measures nothing. Timing evidence: NOT_RUN.

## Deviations and near misses

1. The OWN-75R repair starts from attempt 1's commit `823ff9784`, as the plan says, because the review
   found nothing wrong with it. One commit on top only updates the errata.
2. R2-10's addendum from attempt 1 mapped each manifest to a binary label only. It now carries the
   binary name and sha256 per manifest, and the verifier checks both against `provenance.json`.
3. Attempt 1 left its uncommitted work in place. It was read only, never modified, and its branches and
   temp directory are untouched.
4. Near miss (no effect possible): one small shell script that only ran `git show` piped to `grep`
   (to read README text at the pushed heads for the publish-fix status) ran in the plain shell instead of
   under `bin/hostless`. It started no Python, GUI, Driver or browser. Every Python, verifier, helper and
   audit run went through `bin/hostless`. Otherwise the plain shell ran only git, file reads and edits,
   and read-only inspection (`grep`, `cmp`, `ls`). Nothing was pushed or posted.

## Limits and claim boundary

Reproducibility and wording only; no new evidence. A pass here means that the packet's own verifier
passes from a clean checkout of that exact head, under `bin/hostless`, on this machine. The verifiers
recompute from committed `raw/`. They do not re-run trials, and this audit does not re-judge any
disposition. Publish-fix status is a SOURCE reading of README text at the pushed heads. Publication
SHAs and live heads at publication are recorded by Publish. A fresh verifier re-runs every repaired
verifier with `verify_artifacts.py --rerun`.

## Disposition

KEEP (deliverable). All four gates hold with this audit's scanner. OWN-75R and the B-03 and R2-09
publish fixes are ready for Publish on their r1b branches. R2-10 r1b is held: its verifier carries
R2-10's hex-encoded private-name list, which this scanner did not decode (PUB-02 prepares a clean
history candidate). Every other pushed packet reproduces as published.

## Files

| File | Contents |
|---|---|
| `README.md` | this file |
| `packets.json` | the 27 audited heads, the R2-10 control companion, and the 4 repair heads |
| `audit_packets.py` | the audit (`run --set pushed|repairs`, `assemble`) |
| `audit.json` | summary, gates, publish-fix status, every per-head record |
| `publish-fixes-status.json` | earlier-wave publish fixes and their status at the pushed heads |
| `cited-triage.json` | why each reported cited path is not missing evidence |
| `verify_artifacts.py` | re-checks `audit.json` against the heads; `--rerun` re-runs the repaired verifiers |
| `raw/audit-pushed.json`, `raw/audit-repairs.json` | the two audit runs |
| `raw/verifier-output/pushed/*.txt`, `raw/verifier-output/repairs/*.txt` | scrubbed verifier output per head |
| `raw/origin-heads-start.txt`, `raw/origin-heads-end.txt` | `git ls-remote origin`, filtered to the audited branches, the R2-10 control branch, main and HEAD |
| `raw/controls/template-unit.txt` | template helper UNIT controls |
| `raw/controls/r2-10-verifier-red-before.txt` | R2-10 r1b verifier run against the published head (red) |

Raw outputs are mirrored at `artifacts/r2/PKT-01/attempt-2/` in the lanes directory.
