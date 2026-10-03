# PRIVACY-REWRITE: FRESH-07 raw redaction (lane FRESH-07R, wave 8)

The wave-7 publish scan ran over every commit of the unpublished branch
`exp/fresh-07-main-9a2b1d99e-20261003` (head `88ec3d5e6`). It found the local user name 10 times
in commit `0545c331479e`. Each hit was the xhost line `localuser:<name>` inside a gzipped raw member,
`p2/own-20p/raw/fresh07-own20p-{q1..q8,qc1,qc2}/trials.jsonl.gz`.

That branch was never pushed, and it is not modified here. This branch rebuilds the history from
`4c4e90ae5`, which is unchanged. PREREG (`975f31d1e`) and PREREG-P2 (`f8859411b`) therefore keep
their SHAs and commit times.

| Original | Rewritten | Change |
|---|---|---|
| `0545c3314` | `08c777f68` | 10 gz raw files: `localuser:<name>` became `localuser:<redacted-user>`, 1 per file. Re-gzipped with `gzip -n -9`. Same author, author date and file set. |
| `b2ddd9c7b` | `e647854a4` | Cherry-picked unchanged. |
| `88ec3d5e6` | `ca981a25b` | Cherry-picked unchanged. Its tree equals `88ec3d5e6`'s except for the 10 files above. |

Checks:
- **The token is the only change.** Each member keeps its line count. Every changed line equals the
  original line with the token replaced. No other occurrence of the name remained before or after.
  The gz and member sha256 values before and after are listed in `privacy-rewrite.json`.
- **Same analyzer output.** The original OWN-20P and OWN-20Q analyzers (`orig/own-20p/analyze.py`,
  `orig/own-20q/analyze.py`, blob-identical to the accepted packets) were re-run on the redacted raw.
  `own20p-recert-summary.json`, `own20q-summary.json` and both trial-metrics `.jsonl.gz` files came
  out **byte-identical** to the committed files.
- **The verifier repeats these checks.** `verify_artifacts.py` re-runs both analyzers and compares
  bytes. It counts exactly one `localuser:<redacted-user>` in each of the 10 files and checks the
  sha256 values against `privacy-rewrite.json`. Its privacy check now also rejects the local user name
  as a separate word. It reads the name at run time, so the name is never written in any file.
- **raw/build/patch-ids.txt is now committed.** The repository's `build/` ignore rule had dropped it.
  It is force-added as a read-only copy from the FRESH-07 worktree. `patch_ids.sh` recomputes the
  `git patch-id --stable` of the libs/ diff for all 8 replays against their original commits:
  R'' cec1a5b92, R''n bbe2bd6e6, Cn'' 82e6d5227, G0'' c99fcb3cf, GA'' 6f850b558, GQ'' 8abd5789f,
  U0m'' 8d6d4189a, G0m'' 270ca36b2. All 8 are equal (`raw/build/patch-ids-recomputed.tsv`). The 6 rows
  in the original file match the recomputation.

No number in this packet changed because of the rewrite.
