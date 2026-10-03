# Privacy rewrite of this packet (PUB-03, 2026-10-03)

This branch, `exp/n-04-native-composition-rprime-r1c-20261003`, is a held candidate. It is not published. It differs from the published `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2` only by a redaction, the raw manifest entries that hash the redacted files (where the packet has a manifest), and this note. The Publish agent replaces the published branch only after the owner rules (kvnloo/cua#20, kvnloo/cua#93, kvnloo/cua#73).

## What changed and why

- **Value:** the private-session D-Bus socket path (a random `dbus-` socket under the system temp directory) on the `[session] ... dbus=unix:path=...` line of each affected session log.
- **Replacement:** every occurrence becomes `<session-bus>`. Nothing else in any file changes.
- **Why:** the path names a per-session socket of the private X11 session on the machine that ran the trials. It is not evidence: no check, summary or analysis reads it. The rest of the line (display, process ids, the bus GUID) is unchanged.
- The redacted value, and any encoding of it, appears nowhere in this note, in any commit message, or in any file of this branch.

## Commits

The rewrite is scripted and reproducible: each lane commit is rebuilt with git plumbing (`read-tree`, `update-index --cacheinfo`, `write-tree`, `commit-tree`) onto its rebuilt parent. Author name, e-mail and author date are kept. The committer is Kevin Rajan, with the rewrite time as committer date. Each rewritten message keeps its text and gains one PUB-03 rewrite paragraph before the Co-Authored-By trailer. A lane commit that holds none of the value and whose parent is unchanged is reused as is.

| Published commit | Candidate commit | Author date (kept) | Change |
|---|---|---|---|
| `aa1c2a34676b5c979b9db9365e8acd293db5f2a6` | `aa1c2a34676b5c979b9db9365e8acd293db5f2a6` (reused, identical) | - | none |
| `9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2` | `b1fb2a56a4fdab0b13fef591e32af9e8f0ec070e` | 2026-10-03T04:15:25-05:00 | 7 files, 7 replacements, raw/MANIFEST.json entries |

This note is added by one further commit on top of the rewritten head.

## Files (per file: replacements, old blob -> new blob)

Blob ids are git object ids. They are the same in every rewritten commit listed above.

| File (packet-relative) | Replacements | Old blob | New blob |
|---|---|---|---|
| `raw/chunks/n04-c01-session-log.txt` | 1 | `3b3e89582ce6cceb9af93122dd304857d515cfe6` | `d7e984a33216791e9ae4fb11753c4a1ae05d66b9` |
| `raw/chunks/n04-c02-session-log.txt` | 1 | `5124dba586586936cf57d1217aae5b117efab292` | `0983390a20c561b5abe79b65c2f287399bdf58bc` |
| `raw/chunks/n04-c03-session-log.txt` | 1 | `5a41d783370fbcc14420bb426593d68e27a57aa3` | `3f460acb2639308cdfdf1fa02696902f6dcea19a` |
| `raw/chunks/n04c-c01-session-log.txt` | 1 | `ad9ebf29a55205297929ea3041619379b0daa3d0` | `fa8f331ef6f89616d789aec62d50d0e5e48fb698` |
| `raw/chunks/n04c-c02-session-log.txt` | 1 | `b2f2dc5da3184128189e6d296c2f9643021d8ef5` | `c55cfd4a3c3366dbe3c38d0d46e1fd14adeaa09c` |
| `raw/pilots/chunks/n04p-c01-session-log.txt` | 1 | `cd8e0d4aacff8733d0c2148e1927ed5b1d766af6` | `67d19678f826ea5013fd7cebc9d3d34cf2a67611` |
| `raw/pilots/chunks/n04p-c02-session-log.txt` | 1 | `8fb9d9a5f6fa957cd34bc01187ec5cef9fcbf0cf` | `ce6ac76ff89fed00021cdbf788b215ec122320b9` |
| **total** | **7** in 7 files | | |

`raw/MANIFEST.json`: the `bytes` and `sha256` of the 7 redacted files are updated in place (layout kept; no other entry changes): `b2a8d5863eb18667955733b4cf7552e4854ef87a` -> `d7ccf4edc3c0a1f9a82e207babdd390fe4e98796`. `verify_artifacts.py` checks every raw file against this manifest, so the update is what keeps that check passing; no verifier code changed.

## SHAs cited elsewhere

Text in this packet, in other packets and in loop records still cites the published SHAs. Read them through the table above. Tested sources, Driver binaries, measured data and verdicts are unchanged.

