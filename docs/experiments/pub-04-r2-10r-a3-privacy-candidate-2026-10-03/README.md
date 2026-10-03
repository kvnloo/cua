# PUB-04: R2-10R a3 privacy candidate (r1c) and wave-6 rescan (2026-10-03)

Lane PUB-04, wave 7 (fix), for kvnloo/cua#93 (packet hygiene) and kvnloo/cua#73.

**Disposition: KEEP (held candidate built and verified; HELD for the owner ruling).** The fifth published
privacy finding (`exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec`, 25 temp-dir session-bus socket paths) now has
a built, verified, held replacement candidate, as the other four have. The read-only rescan of the 7 wave-6
heads found 0 private findings on every commit. Nothing was pushed or posted. TypeSafe: 0 attempts, 0 reached.

## Provenance (each SHA separate)

| Item | SHA |
|---|---|
| Published branch head (live origin head, unchanged) | `d22eeb2ecf8a679d1425c21120a599775aa0817d` |
| Candidate head (redactions + note; the replacement) | `a2ded080cac3f8bdd17e3076da1e3b4196b57fa5` |
| Redaction-only head (before the note) | `a5ac8368fec372b06fedeb6cc9c6d6ab12e58dc2` |
| Rewritten `8be812d0c` / `ac46b5032` / `d22eeb2ec` | `a7fc59005e767819bd6bd68a4064234d56db2e48` / `4d496ed1e3c9f9a9b94953198e37fd4ddfb82e05` / `a5ac8368fec372b06fedeb6cc9c6d6ab12e58dc2` |
| Last shared commit (unchanged) | `2bd181dffb` |
| Branch tip (candidate head + this packet) | given in the lane report and the artifacts mirror (a file cannot name its own commit) |
| refs/heads/main = origin main | `da46c4bc85bc43f9641d3ce4b6f319e6d7b6c1a9` |
| upstream/main (local ref used as the scan boundary) | `9a2b1d99ec8044ff58b2a2b46802edd2609c057b` |
| Publication SHA | none (held) |

Oracle: the R2-10R packet's own `verify_artifacts.py` (blob `8b0f780e171a`, identical in the published and the
candidate trees). Driver sha256 / version: not applicable, no Driver binary was built or run. Environment and
tool hashes: `provenance.json`.

## Method

1. **Forced path: rewrite.** `tools/pub04_redact.py` rebuilt `8be812d0c`, `ac46b5032` and `d22eeb2ec` with git
   plumbing onto `2bd181dff`, author name, email and date kept, committer Kevin Rajan. The patterns came from an
   untracked file named by `CUA_REDACT_PATTERNS_FILE`, holding the classes tmp-dbus, abs-path (home and mount
   root), host-name and user-name. The tool holds no pattern literal. Only the tmp-dbus class occurred: one
   path per file in 25 session logs, each replaced by the placeholder `<session-bus>`. The tool also searched
   every packet file for the old sha256 and blob id of each redacted log. It found 0 manifest references, so
   no manifest entry changed. The note commit adds `PRIVACY-REWRITE.md` to the R2-10R packet.
2. **Normalized diff** (`tools/normalized_diff.py`). Full trees, path by path, for the 3 rewritten pairs and
   for `d22eeb2ec` vs the candidate head. Check 1 (masked) applies the patterns to the published bytes, which
   must then equal the candidate bytes; completeness requires 0 pattern hits under `docs/experiments/`.
   Check 2 is pattern-free: the published bytes must equal the candidate bytes outside the placeholder spans.
3. **Verifier parity.** R2-10R a3 `verify_artifacts.py` in clean clones of the published head, the
   redaction-only head and the candidate head, under `bin/hostless` and the SHARED quiet-lane lock. Each
   head ran without and with `CUA_PRIVACY_NAMES_FILE`.
4. **Scanner** (`tools/pub04_scan.py`, the PUB-03 per-commit scanner). It covers commit messages and
   identity, path names, blobs, gzip and tar.gz members (member names included), and decoded hex/base64 runs.
   The url-encoded name class gained a word boundary, test first: red, fix, green.
5. **Rescan** (`tools/rescan_heads.py`). The 7 wave-6 heads were fetched from origin into a clean clone and
   checked equal to the listed heads. Then every commit of `<head> --not main` was scanned, each tagged as
   loop or upstream content. No ref was written; nothing was fixed.

## Results

| # | Row | Result | N of M | Class |
|---|---|---|---|---|
| G1 | Candidate scan, every commit of the candidate head (`--not upstream/main`) | 0 private findings | 17/17 commits clean | SOURCE |
| G1 | Same scanner on the published head | 25 tmp-dbus, all in `8be812d0c` | 1/16 commits with findings | SOURCE |
| G2 | R2-10R verifier, published / redaction-only / candidate, no names | 189/189 each | 3/3 heads | SOURCE |
| G2 | Same, with names file | 189/189 each | 3/3 heads | SOURCE |
| G2 | Output diff published vs redaction-only | byte-identical | 2/2 modes | SOURCE |
| G2 | Output diff published vs candidate | only `privacy: 16 commits, 257 blobs` -> `17 commits, 258 blobs` (note commit) | 2/2 modes | SOURCE |
| G3 | Normalized diff, masked + pattern-free | pass | 4/4 pairs | SOURCE |
| G3 | Head pair `d22eeb2ec` -> candidate | 8153 identical paths, 25 redacted paths (25 redactions), 1 added (the note), 0 removed | 25/25 masked-equal | SOURCE |
| G4 | Scanner unit tests before the fix | 11 failures, all url-encoded name class (owner token, synthetic prefix handle) | 5/10 tests OK | UNIT |
| G4 | Scanner unit tests after the fix | OK | 10/10 tests | UNIT |
| G4 | Normalized-diff tampered controls, masked | fail as expected | 5/5 | FIXTURE |
| G4 | Same, pattern-free | fail 4; the "unredacted file left" control passes (known limit; the scanner and the masked completeness gate catch it) | 4/5 | FIXTURE |
| G4 | Scanner real-data control (one redacted log restored, child of the candidate head) | tmp-dbus x1 | 1/1 | FIXTURE |
| G5 | Rescan of the 7 wave-6 heads, per commit since `main` | 0 private findings | 7/7 heads, 176/176 commits | SOURCE |
| - | Live provider | not used | 0 attempts / 0 reached | NOT_RUN |

Rescan per head (commits since `main`, of which loop commits; private findings): B-08 `49ae94590` 27 (22) 0;
R2-07e `67b99ddc6` 17 (17) 0; OWN-78L `d9edde70e` 11 (11) 0; FIX-03 `e300edbd3` 18 (13) 0; OWN-20Q `44116546d`
28 (11) 0; DOC-3963 `088fe745a` 37 (1) 0; DOC-10-74 `a3e3cb86e` 38 (2) 0. Total: 0 private findings. Non-private
findings: the public CI runner path in `.github/workflows/ci-jev-use.yml` (trycua/cua PR 4316 content:
`a0bca7440`, its merges `b10cd09f2` and `6f438492b`) and upstream-main content (generic home paths in macOS/Swift
sources and test fixtures, 3 secret-like test literals). The unfixed PUB-03 scanner gives the same counts on
all 7 heads, so the fix removed no real finding there.

Component timings: none claimed. This is a hygiene lane and nothing was timed. Work deleted vs wall-clock
saved: not applicable; no Driver or task path changed.

## Controls

- Negative, normalized diff: five tampered candidates were built in a scratch clone (unreferenced commits, never
  in the main clone): an extra byte in a redacted line, one log left unredacted, a removed path, an unlisted
  added path, and a one-word README change. Masked mode fails all five. Pattern-free mode fails four of them.
- Positive, scanner: planted dummy name in plain, upper-case, hex, HEX, base64, percent-encoded (full and
  partial), decoded hex and base64 runs, raw file, gz member, tar member name and content, path name, hex- and
  base64-encoded path names, and commit message. Also a temp-dir bus path in plain, url-encoded, base64 and gz
  member form; local-root paths; a secret-like literal. Every plant hits its class.
- Negative, scanner: the fork owner token in all 12 encodings, inside tar/gz members and path names, and in a
  commit message. Also a synthetic prefix-handle pair. The real case is exercised on this machine: the local
  user name is a prefix of the fork owner token. All give 0 private findings after the fix. Before the fix,
  the percent-encoded owner token counted as the user name.

## Deviations

1. The main clone is shallow, so `git clone --shared` falls back to a full object copy (no alternates). This is
   the same as PUB-03. Each clone is a fresh checkout of its target with 0 status lines before and after.
2. The PUB-03 scanner was imported with two changes before the fix: the repository comes from `CUA_SCAN_REPO`,
   because a committed local path would fail privacy, and the commit identity is scanned with the message.
   Both are recorded in the red commit.
3. The rewrite was run twice. The first run listed inherited redactions in descendant commits' notes. Its
   commit objects are unreferenced and stay in the object store until gc. Only the second run's commits are on
   the branch.
4. The masked normalized diff first scanned binary blobs repository-wide as raw bytes. A 3-letter name occurs
   by chance in compressed bytes, which gave 43 false hits in upstream images and in tar/gz blobs. The
   completeness gate now reads blobs with the scanner's text rules (members decompressed, binary = printable
   runs) and covers `docs/experiments/`. Upstream binary assets are out of scope.
5. This packet's commits sit on the candidate branch after the candidate head. The candidate (head `a2ded080c`)
   differs from `d22eeb2ec` only in redactions and the note. The packet commits touch only this directory, and
   `verify_artifacts.py` checks that live.
6. The first version of the scanner test spelled the fork owner token as two string literals. The first of them
   is a whole token equal to the local user name. This packet's live per-commit scan caught it (plain-name, one
   finding in the first red commit) before anything was pushed. The unpublished branch was reset to the PREREG
   commit, and the red and fix commits were rebuilt with the token written as one literal. The red run was
   repeated and gave the same 11 failures, and the green run was repeated. The scanner blob after the fix is
   unchanged (`e8899ae85131`), so every scan above stands. The two dropped commits are unreferenced, local only,
   and stay in the object store until gc.

## Limits and claim boundary

- Claim: the candidate differs from the published head only by 25 tmp-dbus redactions and the note. It carries
  no private class in any commit of its history. The R2-10R verifier result is unchanged. No R2-10R number,
  gate or verdict changed.
- Not claimed: any finding about branches outside the PUB-03 census and the 7 wave-6 heads; the PUB-03
  candidates (not re-verified here); upstream binary assets.
- The pattern-free normalized diff cannot detect a value left unredacted, by design. Completeness rests on
  the scanner and the masked gate, which needs the untracked pattern file.
- The name classes depend on the verifying machine's user and host name plus the names file. Without the
  names file the host and user names are still checked.

## Files

- Gates and plan: `PREREG.json`. Summary: `pub04-summary.json`. Provenance: `provenance.json`.
- Owner-ruling section and held command list: `OWNER-RULING-DRAFT.md`.
- Verifier: `verify_artifacts.py` (run under `bin/hostless` from a clean clone; set `CUA_PRIVACY_NAMES_FILE`
  for the full name check, `CUA_REDACT_PATTERNS_FILE` to re-run the masked diff).
- Tools: `tools/pub04_redact.py`, `tools/normalized_diff.py`, `tools/pub04_scan.py`, `tools/verify_helper.py`,
  `tools/test_pub04_scan.py`, `tools/rescan_heads.py`.
- Rewrite map (per commit and per file: counts, old/new blob ids and sha256, manifest references):
  `raw/rewrite/rewrite-map.json`.
- Normalized diff: `raw/diff/normalized-diff-masked.json`, `raw/diff/normalized-diff-masked.txt`,
  `raw/diff/normalized-diff-patternfree.json`, `raw/diff/normalized-diff-patternfree.txt`.
- Verifier parity: `raw/verify/o-d22eeb2ec.nonames.txt`, `raw/verify/o-d22eeb2ec.names.txt`,
  `raw/verify/r-a5ac8368f.nonames.txt`, `raw/verify/r-a5ac8368f.names.txt`, `raw/verify/c-a2ded080c.nonames.txt`,
  `raw/verify/c-a2ded080c.names.txt`, and `raw/verify/*.setup.txt`.
- Scans: `raw/scan/scan-candidate-a2ded080c.json`, `raw/scan/scan-published-d22eeb2ec.json`.
- Scanner tests: `raw/unit/scanner-tests-red-before-fix.txt`, `raw/unit/scanner-tests-green-after-fix.txt`.
- Controls: `raw/controls/ctl-summary.txt`, `raw/controls/ctl-commits.txt`, `raw/controls/ctl-*-masked.json`,
  `raw/controls/ctl-*-patternfree.json`, `raw/controls/scan-control-restore.json`, `raw/controls/ctl-commits-scanner.txt`.
- Rescan: `raw/rescan/rescan-heads.txt`, `raw/rescan/rescan-live-refs.txt`, `raw/rescan/rescan-wave6-heads.json`,
  `raw/rescan/rescan-wave6-heads.txt`, `raw/rescan/rescan-wave6-heads-pub03scanner.txt`, `raw/rescan/pub03scanner-*.json`.
- Lock receipts: `raw/locks/shared-lock-receipts.jsonl`.
