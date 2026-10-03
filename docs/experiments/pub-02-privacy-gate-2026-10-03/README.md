# PUB-02: publish-gate privacy fix, clean R2-10 candidate, decoding template scanner, branch audit, 2026-10-03

Lane PUB-02, wave 5 (kvnloo/cua#73, kvnloo/cua#93, kvnloo/cua#10). This is a publish-gate fix (SOURCE +
UNIT). There is no measurement and no PREREG (no measured trial), and 0 TypeSafe requests were attempted
or reached. No private value appears in this packet: every finding is a class, a count, a pattern tag
(`name#i(role)`) and a commit SHA.

## Result in one paragraph

R2-10's `verify_artifacts.py` carried a hex-encoded list of private names. The R2-10, R2-10R and PKT-01
scanners did not decode hex, so all three missed it. This lane makes three branches, all unpushed.

- **A.** `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec` rebuilds the 6 unpublished R2-10R commits onto
  `45dff8f32` with no encoded list in any commit. Its clean-clone verifier passes **189/189** both
  without and with `CUA_PRIVACY_NAMES_FILE` (the 188 original checks + 1 new privacy check). The same
  verifier run over the original history fails 2 privacy checks (187/189).
- **B.** `exp/r2-10-composition-r1c-20261003` @ `eaca68df9` is the clean R2-10 history candidate for the
  owner. Its clean-clone verifier passes **133/133** both ways (132 + 1). Run over the original r1b
  history it gets 131/133.
- **C.** `docs/packet-template-privacy-20261003` upgrades the template scanner. It now decodes hex and
  base64 runs, matches the exact encodings of each name, scans gzip members in memory, and fails on a
  committed encoded name list. The upgraded scanner catches the planted dummy name 3/3, the
  absolute-path plant 1/1 and the encoded-list plant 1/1, and it passes the clean template. The old
  template catches 0 of these plants. The upgraded scanner also passes 11/11 unit tests.

Audit (D) of 133 origin tips and every unpublished commit of the 26 wave-4/5 loop branches that existed
at lane start: 2 of 133 origin tips carry a private-class finding: `exp/own-20g-guard-final-diff-a2-20261003` (user-name-in-raw 10); `exp/r2-10-composition-20261002` (encoded-name 3, encoded-list 1). 3 of 26 unpublished branches do: `exp/r2-10r-recert-a2-20261003` (encoded-name 12, encoded-list 4); `exp/r2-10-composition-r1b-20261003` (encoded-name 3, encoded-list 1); `exp/r2-10r-recert-0f1955d2f-20261003` (encoded-name 3, encoded-list 1). The three PUB-02 branches carry 0 private-class findings in every commit.

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Forced path | each check runs on git objects at a named SHA, in a clean `git clone --shared`, under `bin/hostless` | SOURCE |
| Actual route / producer | A/B: each packet's own `verify_artifacts.py` (rewritten privacy section); C/D: `verify_helper.PrivacyScanner` (`verify_helper.py`, a copy of the template helper) | SOURCE |
| Independent target-owned oracle | git itself: `git diff --stat` of each head against its original, `git cat-file` blobs, `git log -S` pickaxe over 8f3a646b4's history | SOURCE |
| Negative / fallback controls | red-before: the rewritten verifiers on the original histories (A 187/189, B 131/133); the old template (cca59642d) on the plants (0/3); a clean template copy (passes); R2-10 mutation control (exactly 2 FAIL) | UNIT |
| Tested source SHA | A head `d22eeb2ecf8a679d1425c21120a599775aa0817d`; B head `eaca68df9d7f4757028ba787f2e2fa82c92bafe7`; C template `49301c1a2ee17a470036c8d960de10bfe6735aa4`, PKT-01 text fixes `58d17492af2184687487052f6d6d967f6d055a02` | SOURCE |
| Driver binary | none (no Driver code changed, built or run) | SOURCE |
| Environment | one Linux host; `bin/hostless` v2 for every code-executing command; Python 3.14.7; `CUA_PRIVACY_NAMES_FILE` = untracked file of the host name and the local user name | SOURCE |
| PREREG commit | none: no measured trial | SOURCE |
| Live heads at test time | origin heads read by `git fetch origin` at 2026-10-03T07:17Z (`raw/audit/origin-heads-at-start.txt`, 133 exp/* + docs/*); local `upstream/main` = `cb685fad7` (not fetched by this lane) | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`) | SOURCE |
| Live heads at publication | set by Publish (`provenance.json: live_heads_at_publication`) | SOURCE |
| Provider | TypeSafe: 0 attempts, 0 reached | SOURCE |

## Method

- **A (R2-10R).** Each original commit `caf3d68a7..c183b95e3` is rebuilt with git plumbing (`read-tree`,
  `update-index`, `commit-tree`). It keeps its original tree, except that `verify_artifacts.py` is
  replaced by a scripted transform of that commit's own version. The transform:
  - drops the encoded list and reads names from `CUA_PRIVACY_NAMES_FILE` plus the host name, as whole
    tokens (the B-05 pattern);
  - decodes and scans hex and base64 runs;
  - adds 1 check that fails on a committed list of encoded name-like strings;
  - scans gzip members, not their compressed bytes.

  The rebuilt commits keep their author dates; the rewrite is noted in each message. One final commit
  annotates raw/provenance/builds.log (rc=143 = the RECERT-FIX lane's pkill at ~02:44:58Z) and adds
  README Deviation 12 with the SHA map. The list was matched by shape and never decoded, printed or
  written.
- **B (R2-10).** The same rebuild of `2cedaa9a4`, `030f6bdbf` and `36ccdd766` onto `8f3a646b4`.
  `2cedaa9a4` (PREREG) carries no list and is reused unchanged.
- **C (template).** `verify_helper.check_privacy` and `PrivacyScanner` are added to
  `docs/experiments/_template/verify_helper.py`, together with 6 UNIT tests. `control_plants.py` copies the template at a
  given SHA into throwaway repositories, plants one item each, and runs `verify_helper.py --privacy`.
  The plants use a non-private dummy name built at run time; nothing planted is committed.
  `mutation_control.py` reproduces the R2-10 verifier mutation control on B's head.
- **D (audit).** `audit_privacy.py` runs the upgraded scanner, with counts only, over:
  - the files each origin `exp/*` and `docs/*` tip changes against its merge-base with upstream main
    (or against the upstream main tree when the shallow clone holds no merge-base);
  - every commit not on origin of the 26 loop branches named `*-20261003` in the lane-start snapshot
    (parallel tracks excluded);
  - every commit of the three PUB-02 branches.

  The first offending commit is traced for the private classes. `abs-path` counts paths under this
  machine's local roots (home, the checkout mount, TMPDIR). `abs-path-generic` counts any other
  `/home/<x>/`, `/mnt/<x>/` or `/Users/<x>/` path, which includes public upstream and CI paths.
  `secret-like` counts key or token patterns, all of which are in upstream code or tests here. Neither
  of these two classes is traced.

## Results (N of M, evidence class per row)

| Row | N of M | Result | Evidence class |
|---|---|---|---|
| A: rebuilt commits differ from the originals only in `verify_artifacts.py`, author date kept | 6/6 | `raw/rewrite/r2-10r-a3/sha-map.txt` | SOURCE |
| A: head vs `c183b95e3` | 3 files | `verify_artifacts.py`, `README.md` (Deviation 12, Files note), raw/provenance/builds.log (1 line), `raw/rewrite/r2-10r-a3/diff-stat-vs-c183b95e3.txt` | SOURCE |
| A: clean-clone verifier, without / with `CUA_PRIVACY_NAMES_FILE` | 189/189, 189/189 | 188 original checks + 1 encoded-list check; privacy scan of 16 commits `0f1955d2f..d22eeb2ec` | UNIT |
| A: red-before (rewritten verifier over the original history) | 187/189 | name and encoded-list checks FAIL at caf3d68a7, 0bfd24053, 567d76e2b, c183b95e3 | UNIT |
| B: rebuilt commits | 3/3 | `2cedaa9a4` reused; `030f6bdbf` -> `9c3ed9f7d`, `36ccdd766` -> `eaca68df9` differ only in `verify_artifacts.py` | SOURCE |
| B: head vs `36ccdd766` | 1 file | `verify_artifacts.py` only (`raw/rewrite/r2-10-r1c/diff-stat-vs-36ccdd766.txt`) | SOURCE |
| B: clean-clone verifier, without / with `CUA_PRIVACY_NAMES_FILE` | 133/133, 133/133 | 132 original + 1; privacy scan of 12 commits `989cc76ce..eaca68df9` | UNIT |
| B: red-before (original r1b history) | 131/133 | FAIL at 030f6bdbf and 36ccdd766 | UNIT |
| B: 8f3a646b4 and its ancestors carry no list | 0 of 264 local commits | `git log -S` for the decode expression, the list assignment and every hex/base64 encoding of each private name: 0 (`raw/rewrite/r2-10-r1c/ancestor-check-8f3a646b4.txt`) | SOURCE |
| C: dummy name hex / base64 / gzip member | 3/3 caught | `raw/controls/plants-green-49301c1a2.txt` | UNIT |
| C: absolute-path plant; encoded-list plant | 1/1; 1/1 | same file | UNIT |
| C: clean template copy | passes | same file | UNIT |
| C: red-before, template `cca59642d` (no privacy scan) | 0/3, 0/1, 0/1 | `raw/controls/plants-red-before-cca59642d.txt` | UNIT |
| C: template unit tests, with / without names file | 11/11, 11/11 | `raw/controls/template-unit.txt` | UNIT |
| C: R2-10 mutation control (PKT-01 text fix) | 2 of 2 mutated numbers caught | 129/129 unmutated; 127/129 mutated (`raw/controls/r2-10-mutation-control.txt`) | UNIT |
| D: PUB-02 branches, every commit | 0 private findings in 16, 12, 4 commits | tables below | SOURCE |

## Audit tables (D; counts only, no values)

Classes: encoded-name (a private name hex/base64-encoded, or found after decoding a run); encoded-list (>= 2
quoted encoded literals decoding to name-like tokens in one file); plain-name; user-name-in-raw (the local
user name inside a raw/ file or gzip member); abs-path (this machine's local roots); abs-path-generic and
secret-like (counted for completeness; here all public upstream/CI content, not traced).

### Origin exp/* and docs/* tips

| Branch | Scope | Scanned | encoded-name | encoded-list | plain-name | user-name-in-raw | abs-path | abs-path-generic | secret-like | First offending commit (private classes) | Evidence class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `exp/own-20g-guard-final-diff-a2-20261003` | tip ce7544cc0 (merge-base) | 178 files | 0 | 0 | 0 | 10 | 0 | 0 | 0 | user-name-in-raw ce7544cc0 | SOURCE |
| `exp/r2-10-composition-20261002` | tip 030f6bdbf (merge-base) | 145 files | 3 | 1 | 0 | 0 | 0 | 1 | 0 | encoded-name 030f6bdbf, encoded-list 030f6bdbf | SOURCE |
| 131 other origin exp/* and docs/* tips | tips | 172339 files | 0 | 0 | 0 | 0 | 0 | 9781 | 379 | - | SOURCE |

### Unpublished wave-4/5 loop branches (every commit not on origin, as at lane start)

| Branch | Scope | Scanned | encoded-name | encoded-list | plain-name | user-name-in-raw | abs-path | abs-path-generic | secret-like | First offending commit (private classes) | Evidence class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `exp/r2-10r-recert-a2-20261003` | c183b95e3 --not upstream/main --remotes=origin | 14 commits | 12 | 4 | 0 | 0 | 0 | 1 | 0 | encoded-name caf3d68a7, encoded-list caf3d68a7 | SOURCE |
| `exp/b-05-browser-mcp-transport-a2-20261003` | a91a86a4a --not upstream/main --remotes=origin | 7 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/b-05-browser-mcp-transport-a3-20261003` | a91a86a4a --not upstream/main --remotes=origin | 7 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/n-03-native-closure-axfg-a2-20261003` | 63d419034 --not upstream/main --remotes=origin | 6 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/r2-10-composition-r1b-20261003` | 36ccdd766 --not upstream/main --remotes=origin | 1 commits | 3 | 1 | 0 | 0 | 0 | 0 | 0 | encoded-name 36ccdd766, encoded-list 36ccdd766 | SOURCE |
| `exp/r2-10r-recert-0f1955d2f-20261003` | 3028d8078 --not upstream/main --remotes=origin | 10 commits | 3 | 1 | 0 | 0 | 0 | 1 | 0 | encoded-name caf3d68a7, encoded-list caf3d68a7 | SOURCE |
| `exp/fix-recert-0f1955d2f-20261003` | 087162d54 --not upstream/main --remotes=origin | 2 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/fix-recert-a2-20261003` | 087162d54 --not upstream/main --remotes=origin | 2 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/own-75r-timing-parity-4336-r1-20261003` | 823ff9784 --not upstream/main --remotes=origin | 0 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/b-05-browser-mcp-transport-20261003` | b376f1ff3 --not upstream/main --remotes=origin | 3 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/own-09r2-0f1955d2f-20261003` | ba611b51a --not upstream/main --remotes=origin | 6 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/own-09r2-a2-20261003` | ba611b51a --not upstream/main --remotes=origin | 6 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/own-16w2-0f1955d2f-20261003` | 7e31eae59 --not upstream/main --remotes=origin | 3 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/own-16w2-a2-20261003` | 7e31eae59 --not upstream/main --remotes=origin | 3 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/fix-02r-0f1955d2f-20261003` | df4f1edf5 --not upstream/main --remotes=origin | 7 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/fix-02r-a2-20261003` | df4f1edf5 --not upstream/main --remotes=origin | 7 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/n-03-native-closure-axfg-20261003` | 85a73c2c7 --not upstream/main --remotes=origin | 1 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/r2-10r-control-20261003` | 8a2362770 --not upstream/main --remotes=origin | 0 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/b-07-transport-residual-rprime-20261003` | 45dff8f32 --not upstream/main --remotes=origin | 8 commits | 0 | 0 | 0 | 0 | 0 | 1 | 0 | - | SOURCE |
| `exp/own-20g-guard-final-diff-20261003` | bdf33d9fe --not upstream/main --remotes=origin | 0 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `docs/packet-template-audit-20261003` | 0f1955d2f --not upstream/main --remotes=origin | 0 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/r2-10-composition-r1-20261003` | 030f6bdbf --not upstream/main --remotes=origin | 0 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/r2-09-native-event-wake-r1-20261003` | 3539e34ae --not upstream/main --remotes=origin | 0 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/b-03-toggle-cold-snapshot-r1-20261003` | b34eef71e --not upstream/main --remotes=origin | 0 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/b-04-observation-reconcile-20261003` | 8f3a646b4 --not upstream/main --remotes=origin | 0 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |
| `exp/r2-07c-toggle-modal-compiled-20261003` | 8f3a646b4 --not upstream/main --remotes=origin | 0 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |

### PUB-02 output branches (every commit of the range)

| Branch | Scope | Scanned | encoded-name | encoded-list | plain-name | user-name-in-raw | abs-path | abs-path-generic | secret-like | First offending commit (private classes) | Evidence class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `exp/r2-10r-recert-a3-20261003` | 0f1955d2f..d22eeb2ec | 16 commits | 0 | 0 | 0 | 0 | 0 | 2 | 0 | - | SOURCE |
| `exp/r2-10-composition-r1c-20261003` | 989cc76ce..eaca68df9 | 12 commits | 0 | 0 | 0 | 0 | 0 | 2 | 0 | - | SOURCE |
| `docs/packet-template-privacy-20261003` | 41c34cb0d..58d17492a | 4 commits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | SOURCE |

The `abs-path-generic` hits in A and B are the public GitHub Actions runner path in
`.github/workflows/ci-jev-use.yml`. They come from trycua/cua PR 4316 (`a0bca7440`, and via the merges
`6f438492b` and `b10cd09f2`), and the R2-10/R2-10R verifiers allowlist them.

### For the owner's decision

- OWN-20G (`exp/own-20g-guard-final-diff-a2-20261003`, published, tip `ce7544cc0`): user-name-in-raw **10** (first commit `ce7544cc0`). This confirms the published raw xhost-output finding.
- `exp/r2-10-composition-20261002` (encoded-name 3, encoded-list 1): tip `030f6bdbf`, first commits encoded-name 030f6bdbf, encoded-list 030f6bdbf.
- Unpublished: `exp/r2-10r-recert-a2-20261003` (encoded-name 12, encoded-list 4), first encoded-name caf3d68a7, encoded-list caf3d68a7; `exp/r2-10-composition-r1b-20261003` (encoded-name 3, encoded-list 1), first encoded-name 36ccdd766, encoded-list 36ccdd766; `exp/r2-10r-recert-0f1955d2f-20261003` (encoded-name 3, encoded-list 1), first encoded-name caf3d68a7, encoded-list caf3d68a7. These branches are not to be pushed as they are. A replaces R2-10R a2 (and its attempt-1 branch `exp/r2-10r-recert-0f1955d2f-20261003`), and B replaces R2-10 r1b.

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock saved | Evidence class |
|---|---|---|---|
| none (publish-gate fix) | none | not measured | NOT_RUN |

## Deviations and near misses

1. **Gzip compressed bytes.** The first B rebuild, with the transform as first written, failed the
   with-names run 132/134. The local user name occurred once, by chance, in the compressed bytes of the
   3.98 MB raw/browser/scripted-trials.tar.gz and in 0 of its members. The transform now scans gzip
   and tar.gz members only. Both branches were rebuilt from scratch, and only the final heads are
   reported. The earlier objects are unreferenced, and no `refs/original` exists.
2. **Rerun of the tip audit.** The first tip audit stopped on an old docs branch that has no local
   merge-base with upstream main (the clone is shallow). Such tips are now scanned against the upstream
   main tree, and their rows say so in Scope. The rerun traces first commits only for private classes.
3. **builds.log annotation.** The wave-4 publish notes said "do not edit raw" for the rc=143 note.
   This lane's spec asked for an annotation in raw/provenance/builds.log. The original line is kept,
   and one annotation line follows it.
4. **SHAs in other files.** R2-10R's other files (provenance.json, PREREG-AMENDMENT-*.json, README
   rows) still cite the original SHAs. README Deviation 12 maps them to the rebuilt ones. B's README
   and provenance cite `030f6bdbf`; on the candidate branch that commit is `9c3ed9f7d`
   (`raw/rewrite/r2-10-r1c/sha-map.txt`).
5. **Near misses:** none.

## Limits and claim boundary

- Covers the git objects named above on this clone. The local clone is shallow, so "8f3a646b4 and its
  ancestors" means the 264 commits reachable locally.
- The hex and base64 run thresholds (>= 8 and >= 12 chars) miss encodings of names shorter than 4 or 9
  bytes. The exact-encoding search and the encoded-list check cover those for the names in the names
  file.
- Names outside the names file (host and user here) are caught only through the encoded-list shape or
  the path patterns.
- No branch was pushed and nothing was written to GitHub. Pushing B, or any force-push of the
  published `exp/r2-10-composition-20261002`, waits for the owner.

## Disposition

KEEP (fix). A is ready for Publish to push as R2-10R. B is the clean candidate for the owner's ruling on
`exp/r2-10-composition-20261002`; do not push it before that ruling. C hardens every future packet's
privacy scan and applies PKT-01's three text fixes.

## Files

| File | Contents |
|---|---|
| `README.md` | this file |
| `provenance.json` | branches, heads, bases, environment, provider |
| `pub02-summary.json` | audit totals, control and verifier results, recomputed by `verify_artifacts.py` |
| `verify_artifacts.py` | recomputes the summary and README tables from `raw/`, checks controls, rewrite evidence (git objects when present), cited files and privacy |
| `verify_helper.py` | copy of the upgraded template helper (`check_cited`, `check_privacy`, `PrivacyScanner`) |
| `.gitignore` | template packet-local ignore overrides |
| `audit_privacy.py` | the D audit (counts only) |
| `control_plants.py` | the C plant controls |
| `mutation_control.py` | the R2-10 mutation control |
| `raw/audit/origin-heads-at-start.txt`, `raw/audit/unpublished-at-start.txt`, `raw/audit/ranges.txt` | audit inputs |
| `raw/audit/audit-tips.json`, `raw/audit/audit-commits.json`, `raw/audit/audit-ranges.json` | audit outputs (class, where, tag, SHA; no values) |
| `raw/controls/plants-green-49301c1a2.txt`, `raw/controls/plants-red-before-cca59642d.txt` | plant controls |
| `raw/controls/template-unit.txt`, `raw/controls/r2-10-mutation-control.txt` | unit and mutation controls |
| `raw/rewrite/r2-10r-a3/sha-map.txt`, `raw/rewrite/r2-10r-a3/diff-stat-vs-c183b95e3.txt` | A rewrite map and tree diff |
| `raw/rewrite/r2-10r-a3/r2-10r-a3-clone.txt`, `raw/rewrite/r2-10r-a3/r2-10r-a3-no-names-file.txt`, `raw/rewrite/r2-10r-a3/r2-10r-a3-with-names-file.txt`, `raw/rewrite/r2-10r-a3/r2-10r-red-before-original-c183b95e3.txt` | A verifier runs |
| `raw/rewrite/r2-10-r1c/sha-map.txt`, `raw/rewrite/r2-10-r1c/diff-stat-vs-36ccdd766.txt`, `raw/rewrite/r2-10-r1c/ancestor-check-8f3a646b4.txt` | B rewrite map, tree diff, ancestor check |
| `raw/rewrite/r2-10-r1c/r2-10-r1c-clone.txt`, `raw/rewrite/r2-10-r1c/r2-10-r1c-no-names-file.txt`, `raw/rewrite/r2-10-r1c/r2-10-r1c-with-names-file.txt`, `raw/rewrite/r2-10-r1c/r2-10-red-before-original-36ccdd766.txt` | B verifier runs |

Verify from a clean clone: `CUA_PRIVACY_NAMES_FILE=<untracked names file> <lanes>/bin/hostless python3 verify_artifacts.py`.
Mirrors are in the lanes artifacts directory: `artifacts/r2/PUB-02/`, and for A also
`artifacts/r2/R2-10R/attempt-3-privacy/`.
