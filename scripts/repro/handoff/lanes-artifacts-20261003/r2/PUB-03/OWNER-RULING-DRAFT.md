# PUB-03 draft owner-ruling note for the Publish agent (2026-10-03, not run)

Lane PUB-03 (wave 6) for kvnloo/cua#20, kvnloo/cua#93 and kvnloo/cua#73. This note is a draft. Nothing in it
has been pushed, posted or deleted. Publish runs the command list for a branch only after the owner rules
on that branch. If text from this note is posted to the fork, write upstream items as plain text
(trycua/cua PR 4316) and fork items as kvnloo/cua#N.

## Rulings requested

| # | Published branch @ head | Finding (class: count, first commit) | Held candidate @ head | Recommendation |
|---|---|---|---|---|
| 1 | `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc064cecfd9ba4702466a1d0f24b1799b6` | user-name-in-raw: 10 files / 10 occurrences (raw xhost output in `trials.jsonl.gz` members), first `ce7544cc0` | `exp/own-20g-guard-final-diff-r1c-20261003` @ `cb18ebfbdfa41b733b8c68c1971760ab39f392f4` | **replace** (delete + re-push). It is the account name of this machine. |
| 2 | `exp/n-03-native-closure-axfg-a3-20261003` @ `6b70ec9024cc3921f7637bba2ffabcc93e29fc77` | tmp-dbus: 21 files / 21 occurrences (session logs), first `d8768373d` | `exp/n-03-native-closure-axfg-r1c-20261003` @ `a2f7a93efa6689f201b7d4e4e8f53a37749bca2c` | **replace** recommended. **accept** is defensible: the path is a random per-session socket name, with no user or host in it. |
| 3 | `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2` | tmp-dbus: 7 files / 7 occurrences (chunk session logs), first `9d7d8d7a5` | `exp/n-04-native-composition-rprime-r1c-20261003` @ `32299f857c80683e1ebbe9e5602316f1a77a9635` | Same as #2. Rule #2 and #3 together. |
| 4 (new) | `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ecf8a679d1425c21120a599775aa0817d` | tmp-dbus: 25 files / 25 occurrences (raw/logs/*.log), first `8be812d0c` | none yet. Proposed: `exp/r2-10r-recert-r1c-20261003` (rewrite `8be812d0c`, `ac46b5032`, `d22eeb2ec`; the same procedure) | Owner rules the class. If #2/#3 are replaced, build this candidate next wave and replace it too. If they are accepted, accept this one as well. |
| 5 (known, PUB-02) | `exp/r2-10-composition-20261002` @ `030f6bdbf811e124e11daa2de0569bffb993b66d` | encoded-name 3, encoded-list 1, in `030f6bdbf` | `exp/r2-10-composition-r1c-20261003` @ `eaca68df9d7f4757028ba787f2e2fa82c92bafe7` (held since wave 5; this scan finds 0 private findings in its 12 commits, tmp-dbus included) | **replace** (an encoded name list is a private value). Still pending from wave 5. |

The census of the other 45 loop branches (plus 2 adjacent non-loop branches) found 0 private-class findings
in every commit (`census/CENSUS.md`).

## What each candidate is (verified)

- **Diff from the published head.** It touches only the redacted lines, the raw manifest entries (N-03 and
  N-04 only) and one added `PRIVACY-REWRITE.md`. The line-level check passes:
  - OWN-20G: 10 gz members, 10 lines, 10 replacements;
  - N-03: 21 lines, 21 replacements, 42 manifest value lines (21 entries);
  - N-04: 7 lines, 7 replacements, 14 manifest value lines (7 entries).
- **Clean-export verifier.** Each run uses a clean clone whose working tree is the `git archive` export of
  the head, under `bin/hostless`, without and with `CUA_PRIVACY_NAMES_FILE`. Each candidate gets the same
  PASS count as its published head:
  - OWN-20G: 277/277 and 277/277;
  - N-03: 8/8 PASS lines (VERIFY OK) both ways;
  - N-04: 10/10 PASS lines (VERIFY OK) both ways.

  The only output differences are +1 commit or +1 tracked file, from the note commit.
- **Manifest red control.** The candidate tree with the published `raw/MANIFEST.json` fails exactly the
  manifest check: N-03 7/8 and N-04 9/10. So the manifest update is what keeps that check green.
- **Per-commit scan of every candidate commit.** OWN-20G (8 commits), N-03 (17) and N-04 (13) have 0
  private-class findings. The scan covers the user name, the host name, local roots, tmp-dbus, secrets, and
  hex, base64 and url-encoded forms. The only generic hits are the 2 public runner paths from trycua/cua
  PR 4316 in `.github/workflows/ci-jev-use.yml`.
- **What is rewritten.** Only the lane's own commits that carry the value, and their descendants. Author
  dates are kept, and the committer is Kevin Rajan. The reused lane commits keep their SHAs:
  - OWN-20G: `a30cbbc3b`, `d17a8c0b4`, `5c9a97e2c`;
  - N-03: `d929b49f2`, `b057b45d7` (PREREG commit unchanged);
  - N-04: `aa1c2a346` (PREREG commit unchanged).

## SHA maps (published -> candidate)

- OWN-20G: `ce7544cc0` -> `fa47a0450`, + note `cb18ebfbd`.
- N-03: `d8768373d` -> `2ec3ee3a2`, `960bc20aa` -> `640f45393`, `63d419034` -> `4b57fadf6`,
  `6b70ec902` -> `20dd88672`, + note `a2f7a93ef`.
- N-04: `9d7d8d7a5` -> `b1fb2a56a`, + note `32299f857`.

## Side effects of a replace (for the owner)

- **OWN-20P's verifier** (`exp/own-20p-guard-port-a11y-20261003`) runs its harness-equality check against
  `ce7544cc0` only when that commit exists (`git cat-file -t ce7544cc0`). In a fresh clone of origin after
  the delete, that object is absent and the check falls back to the recorded blob ids. The harness blobs
  are identical on the candidate, so nothing becomes false, but the git-object sub-check is skipped.
- **N-04 cites N-03 `63d419034`** by text and harness blob ids (`PREREG.json`, `harness/n04_harness.py`,
  `verify_artifacts.py`). The blob ids are unchanged on the N-03 candidate, so the N-04 check still passes.
  The commit SHA text now maps to `4b57fadf6`.
- **N-03's README and provenance** cite `960bc20aa` and `63d419034`. They now read through
  `PRIVACY-REWRITE.md`.
- **Loop records** cite the published heads and must be updated after the push:
  - STATE.json dispositions (OWN-20G, N-03, N-04);
  - drafts/w4 and drafts/w5 (`ce7544cc0`, `6b70ec902`, `9d7d8d7a5`);
  - PUB-02's audit files.

  E5 deliverables must cite the candidate heads once pushed.
- **GitHub retention.** GitHub can keep serving an unreferenced commit by SHA for some time after a branch
  delete. Fully purging cached objects needs a GitHub support request; the owner decides whether to make one.
- **Open PRs.** No fork PR (28 read, all states) has any of these branches as its head (gh read, 2026-10-03).

## Command list for Publish (run per branch only after the owner rules "replace")

Run from the main clone. Each block stops if a check fails. Each delete is a lease-guarded delete of the
exact published head.

```sh
R=/mnt/zer0models/github/cua
git -C "$R" fetch origin

# 1. OWN-20G
test "$(git -C "$R" rev-parse origin/exp/own-20g-guard-final-diff-a2-20261003)" = ce7544cc064cecfd9ba4702466a1d0f24b1799b6
test "$(git -C "$R" rev-parse exp/own-20g-guard-final-diff-r1c-20261003)" = cb18ebfbdfa41b733b8c68c1971760ab39f392f4
git -C "$R" push origin exp/own-20g-guard-final-diff-r1c-20261003:refs/heads/exp/own-20g-guard-final-diff-r1c-20261003
test "$(git -C "$R" ls-remote origin refs/heads/exp/own-20g-guard-final-diff-r1c-20261003 | cut -f1)" = cb18ebfbdfa41b733b8c68c1971760ab39f392f4
git -C "$R" push --force-with-lease=refs/heads/exp/own-20g-guard-final-diff-a2-20261003:ce7544cc064cecfd9ba4702466a1d0f24b1799b6 origin :refs/heads/exp/own-20g-guard-final-diff-a2-20261003

# 2. N-03
test "$(git -C "$R" rev-parse origin/exp/n-03-native-closure-axfg-a3-20261003)" = 6b70ec9024cc3921f7637bba2ffabcc93e29fc77
test "$(git -C "$R" rev-parse exp/n-03-native-closure-axfg-r1c-20261003)" = a2f7a93efa6689f201b7d4e4e8f53a37749bca2c
git -C "$R" push origin exp/n-03-native-closure-axfg-r1c-20261003:refs/heads/exp/n-03-native-closure-axfg-r1c-20261003
test "$(git -C "$R" ls-remote origin refs/heads/exp/n-03-native-closure-axfg-r1c-20261003 | cut -f1)" = a2f7a93efa6689f201b7d4e4e8f53a37749bca2c
git -C "$R" push --force-with-lease=refs/heads/exp/n-03-native-closure-axfg-a3-20261003:6b70ec9024cc3921f7637bba2ffabcc93e29fc77 origin :refs/heads/exp/n-03-native-closure-axfg-a3-20261003

# 3. N-04
test "$(git -C "$R" rev-parse origin/exp/n-04-native-composition-rprime-20261003)" = 9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2
test "$(git -C "$R" rev-parse exp/n-04-native-composition-rprime-r1c-20261003)" = 32299f857c80683e1ebbe9e5602316f1a77a9635
git -C "$R" push origin exp/n-04-native-composition-rprime-r1c-20261003:refs/heads/exp/n-04-native-composition-rprime-r1c-20261003
test "$(git -C "$R" ls-remote origin refs/heads/exp/n-04-native-composition-rprime-r1c-20261003 | cut -f1)" = 32299f857c80683e1ebbe9e5602316f1a77a9635
git -C "$R" push --force-with-lease=refs/heads/exp/n-04-native-composition-rprime-20261003:9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2 origin :refs/heads/exp/n-04-native-composition-rprime-20261003

# 5. R2-10 (PUB-02 candidate; only on its own "replace" ruling)
test "$(git -C "$R" rev-parse origin/exp/r2-10-composition-20261002)" = 030f6bdbf811e124e11daa2de0569bffb993b66d
test "$(git -C "$R" rev-parse exp/r2-10-composition-r1c-20261003)" = eaca68df9d7f4757028ba787f2e2fa82c92bafe7
git -C "$R" push origin exp/r2-10-composition-r1c-20261003:refs/heads/exp/r2-10-composition-r1c-20261003
test "$(git -C "$R" ls-remote origin refs/heads/exp/r2-10-composition-r1c-20261003 | cut -f1)" = eaca68df9d7f4757028ba787f2e2fa82c92bafe7
git -C "$R" push --force-with-lease=refs/heads/exp/r2-10-composition-20261002:030f6bdbf811e124e11daa2de0569bffb993b66d origin :refs/heads/exp/r2-10-composition-20261002

# 4. R2-10R a3: no command this wave (candidate not built). On "accept", nothing to run.
```

After each replace:

- Record `publication_sha` = the candidate head in the loop records.
- Re-point STATE.json `dispositions.<lane>.branch` and `.commit` to the candidate.
- Re-run the candidate's verifier from a fresh clone of origin.
- Post one kvnloo/cua#20 / kvnloo/cua#93 comment naming the old -> new branch and head. The comment must
  not repeat any redacted value.

On **accept**: run no command. Record in STATE.json `owner_rulings` that the class is accepted for that branch,
and drop the held candidate branch locally only if the owner asks.
