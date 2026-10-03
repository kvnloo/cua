# Privacy rewrite of this branch (PUB-04 held candidate, 2026-10-03)

This branch, `exp/r2-10r-recert-a3-r1c-20261003`, is a rewrite of the published `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ecf8a679d1425c21120a599775aa0817d` (R2-10R attempt 2, packet `docs/experiments/r2-10r-recert-2026-10-03/`). It is held for the owner ruling (kvnloo/cua#93, kvnloo/cua#73) and is not to be pushed before it.

## What was redacted

- Class `tmp-dbus`: the session-bus socket path (a per-session socket file under the system temp directory) in the `[session]` line that each session log prints. 25 files under `raw/logs/`, 25 occurrences, one per file. Each path is replaced by the placeholder token `<session-bus>`. The rest of each line (display number, process ids, bus guid) is unchanged.
- No other class occurred: no absolute local path, host name or user name was found in any commit of the published branch (PUB-03 census; PUB-04 per-commit scan), so none was redacted.
- Commit messages: 0 redactions. Manifests: no file in the packet records a hash or blob id of these logs (`raw/package-report.json` counts trials only), so 0 manifest entries changed.

## Why

The loop's privacy rule is checked on every commit of a branch. A temp-dir socket path is a local machine path; PUB-03 (wave 6) reported it in this branch as the fifth published privacy finding. The redaction is mechanical (pattern supplied from an untracked file at rewrite time, never committed) and changes no trial, number, gate or verdict: none of the packet's analyses read `raw/logs/`.

## Commit map (author name, email and date kept)

| Published | Candidate | Change |
|---|---|---|
| `8be812d0c7cd1b1558f21b68e65ea271643f49fd` | `a7fc59005e767819bd6bd68a4064234d56db2e48` | 25 redactions in 25 files |
| `ac46b50323a6bf0dcb3be80c9d731e589be049d1` | `4d496ed1e3c9f9a9b94953198e37fd4ddfb82e05` | re-parented (inherits the redaction) |
| `d22eeb2ecf8a679d1425c21120a599775aa0817d` | `a5ac8368fec372b06fedeb6cc9c6d6ab12e58dc2` | re-parented (inherits the redaction) |

Commits before `8be812d0c` are unchanged (shared with the published branch).

## Per file (old -> new git blob id)

| File (`raw/logs/`) | Redactions | Old blob | New blob |
|---|---|---|---|
| `failed-sessions-p0-b-c1-R-r1-session-failed.log` | 1 | `08fcafb8e86c` | `31c58f2f2bb0` |
| `failed-sessions-p0-b-c1-R-session-failed.log` | 1 | `a42903088dbf` | `b3196d11d03f` |
| `interrupted-S2.log` | 1 | `cb6fed0d1b27` | `9d7449b45c03` |
| `m-N1.log` | 1 | `894a4b82c117` | `ec9015152feb` |
| `m-S1.log` | 1 | `41005d52ebd4` | `3ea871c7ea02` |
| `m-S2r.log` | 1 | `c8b890041c7e` | `b71cc68aa868` |
| `m-d1.log` | 1 | `99ff3c909f1f` | `123057ac1db2` |
| `m-nd1.log` | 1 | `d26f6e792271` | `eb7b7098a520` |
| `m-nm1.log` | 1 | `d2e1a72d59e2` | `81ddf990af1a` |
| `m-nm2.log` | 1 | `a30ab7a33e5b` | `ef084319136a` |
| `p0-b-c1-R.log` | 1 | `f1cb7b5299c6` | `b9f798313946` |
| `p0-b-c1-U.log` | 1 | `f04227245ca5` | `ffd1b5f692a5` |
| `p0-c-nw2-R.log` | 1 | `153cc6f26415` | `e5d6fdecea0d` |
| `p0-c-nw2-U.log` | 1 | `06d38c48433a` | `e00175ad37ea` |
| `p0-d-native-C.log` | 1 | `5fa1dc7b0840` | `09e9066f5e2b` |
| `p0-d-native-R.log` | 1 | `f3aa12f42d2c` | `4ef852ae7df0` |
| `p0-d-smoke-C.log` | 1 | `81a0da669a71` | `6df4b9a76363` |
| `p0-d-smoke-R.log` | 1 | `fd24e243e4ca` | `ee4e3eb8f382` |
| `p0-d-tools-C.log` | 1 | `1eef9478b23e` | `cf0363e47880` |
| `p0-d-tools-R.log` | 1 | `bfe51a1421a9` | `85f524e81460` |
| `p0-e-g5.log` | 1 | `91c2dd66833b` | `9a530838eb1a` |
| `p0-e-train.log` | 1 | `9201ee707574` | `e03ab7a9c198` |
| `runs-d1k1.log` | 1 | `cbafc96399d7` | `19e04f2c0d30` |
| `runs-nshake1.log` | 1 | `d817442f976e` | `30ca6edb72a0` |
| `runs-shake1.log` | 1 | `90985dbf60e5` | `58fa227da898` |

Evidence (normalized diff, per-commit scan, verifier parity) is in `docs/experiments/pub-04-r2-10r-a3-privacy-candidate-2026-10-03/` on this branch. No redacted value or encoding of it appears in this note.
