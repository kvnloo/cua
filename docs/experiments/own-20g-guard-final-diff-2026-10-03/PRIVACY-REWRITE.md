# Privacy rewrite of this packet (PUB-03, 2026-10-03)

This branch, `exp/own-20g-guard-final-diff-r1c-20261003`, is a held candidate. It is not published. It differs from the published `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc064cecfd9ba4702466a1d0f24b1799b6` only by a redaction, the raw manifest entries that hash the redacted files (where the packet has a manifest), and this note. The Publish agent replaces the published branch only after the owner rules (kvnloo/cua#20, kvnloo/cua#93, kvnloo/cua#73).

## What changed and why

- **Value:** the local Unix user name inside the raw `xhost` output line (`{"event": "xhost", ..., "out": "localuser:<user> being added to access control list"}`) of each affected `trials.jsonl.gz` member.
- **Replacement:** every occurrence becomes `<user>`. Nothing else in any file changes.
- **Why:** the published packet carried the account name of the machine that ran the trials. It is not evidence: no check, summary or analysis reads that field (`analyze.py` recomputes `own20g-summary.json` byte-identically from the redacted raw files).
- The redacted value, and any encoding of it, appears nowhere in this note, in any commit message, or in any file of this branch.

## Commits

The rewrite is scripted and reproducible: each lane commit is rebuilt with git plumbing (`read-tree`, `update-index --cacheinfo`, `write-tree`, `commit-tree`) onto its rebuilt parent. Author name, e-mail and author date are kept. The committer is Kevin Rajan, with the rewrite time as committer date. Each rewritten message keeps its text and gains one PUB-03 rewrite paragraph before the Co-Authored-By trailer. A lane commit that holds none of the value and whose parent is unchanged is reused as is.

| Published commit | Candidate commit | Author date (kept) | Change |
|---|---|---|---|
| `a30cbbc3b230e8bad7d86ae1e89866d4f9cdd1af` | `a30cbbc3b230e8bad7d86ae1e89866d4f9cdd1af` (reused, identical) | - | none |
| `d17a8c0b40fdb9f3938a0318fcea936538c96eef` | `d17a8c0b40fdb9f3938a0318fcea936538c96eef` (reused, identical) | - | none |
| `5c9a97e2c369bf10ae47ba51307aefa724c4106d` | `5c9a97e2c369bf10ae47ba51307aefa724c4106d` (reused, identical) | - | none |
| `ce7544cc064cecfd9ba4702466a1d0f24b1799b6` | `fa47a0450d7a87fa4c4f137ec6c0cdabec426692` | 2026-10-03T00:31:31-05:00 | 10 files, 10 replacements |

This note is added by one further commit on top of the rewritten head.

## Files (per file: replacements, old blob -> new blob)

Blob ids are git object ids. They are the same in every rewritten commit listed above.

| File (packet-relative) | Replacements | Old blob | New blob |
|---|---|---|---|
| `raw/own20g-r1qa-r1/trials.jsonl.gz` | 1 | `547961fd5611cf88a816e563c83263706f2d3fa9` | `1adbfdded8fd439dea1d39d76755fb0cef6364ca` |
| `raw/own20g-r1qb/trials.jsonl.gz` | 1 | `deaf4358ddc90ff216d1bf4591778af521351e78` | `93049ccd76de22ceb8df16eec9e61273372cd72d` |
| `raw/own20g-r1qc/trials.jsonl.gz` | 1 | `640fb827c55d291d128b7170589450636073b3f8` | `ceda08e35c729e81d41d633aab32634cf4d124f6` |
| `raw/own20g-r1qd/trials.jsonl.gz` | 1 | `401377bf0fe6b613459479a8c8a9e6dae56d804e` | `55e8311c27c774b6157b224d959c8b50e087e6be` |
| `raw/own20g-r1qe/trials.jsonl.gz` | 1 | `4750a0b4a6ca6532a5e6f0f83ba634b51548e89a` | `def82795316f3728cefe4754ad59c0b99b2502f5` |
| `raw/pilots/own20g-pilot0-p04-r1/trials.jsonl.gz` | 1 | `ce945f7fe58aceb53b8a51a5dbfdd55531fbec59` | `dd4c0c2e2aaf30353be2103f305a63a58b5a2337` |
| `raw/pilots/own20g-pilot0-p04-r2/trials.jsonl.gz` | 1 | `17dc6e8af6b50a05964c58ed7ba856cfba21d0ae` | `5ebc94ac116c7793628644ea43eed5a4cbcc6cd4` |
| `raw/pilots/own20g-pilot0-p04-r3/trials.jsonl.gz` | 1 | `bd956563b92e59306bc6ab5444a556f72aab6b4a` | `f5f7e81da31b2c429d463811a37d87815dfa3463` |
| `raw/pilots/own20g-pilot0-p04-r4/trials.jsonl.gz` | 1 | `a542cdea56370aef10818128e37c4f67cc495ab2` | `70d973eadaf55ec91ab82e474f179cc58fc843d2` |
| `raw/pilots/own20g-pilot0-p05/trials.jsonl.gz` | 1 | `0b04d07e8a3608a5946c4bd8dcbe4775295a9f13` | `17749793be558531c65ad5c7ae72c25aa2b89dcf` |
| **total** | **10** in 10 files | | |

The packet has no raw manifest; no hash list or verifier expectation covers these files, so no other file changes. `verify_artifacts.py` is unchanged.

The gzip members are re-written with the packet's own writer settings (`package.py`: `GzipFile`, `compresslevel=9`, `mtime=0`, member name kept). The rewrite first re-compressed every affected original member with those settings and got the published bytes back exactly, so the only difference in each new blob is the redaction.

## SHAs cited elsewhere

Text in this packet, in other packets and in loop records still cites the published SHAs. Read them through the table above. Tested sources, Driver binaries, measured data and verdicts are unchanged.

