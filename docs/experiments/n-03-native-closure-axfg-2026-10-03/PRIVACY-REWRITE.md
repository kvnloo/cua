# Privacy rewrite of this packet (PUB-03, 2026-10-03)

This branch, `exp/n-03-native-closure-axfg-r1c-20261003`, is a held candidate. It is not published. It differs from the published `exp/n-03-native-closure-axfg-a3-20261003` @ `6b70ec9024cc3921f7637bba2ffabcc93e29fc77` only by a redaction, the raw manifest entries that hash the redacted files (where the packet has a manifest), and this note. The Publish agent replaces the published branch only after the owner rules (kvnloo/cua#20, kvnloo/cua#93, kvnloo/cua#73).

## What changed and why

- **Value:** the private-session D-Bus socket path (a random `dbus-` socket under the system temp directory) on the `[session] ... dbus=unix:path=...` line of each affected session log.
- **Replacement:** every occurrence becomes `<session-bus>`. Nothing else in any file changes.
- **Why:** the path names a per-session socket of the private X11 session on the machine that ran the trials. It is not evidence: no check, summary or analysis reads it. The rest of the line (display, process ids, the bus GUID) is unchanged.
- The redacted value, and any encoding of it, appears nowhere in this note, in any commit message, or in any file of this branch.

## Commits

The rewrite is scripted and reproducible: each lane commit is rebuilt with git plumbing (`read-tree`, `update-index --cacheinfo`, `write-tree`, `commit-tree`) onto its rebuilt parent. Author name, e-mail and author date are kept. The committer is Kevin Rajan, with the rewrite time as committer date. Each rewritten message keeps its text and gains one PUB-03 rewrite paragraph before the Co-Authored-By trailer. A lane commit that holds none of the value and whose parent is unchanged is reused as is.

| Published commit | Candidate commit | Author date (kept) | Change |
|---|---|---|---|
| `d929b49f25c83f237141641fab3eb03a3c231739` | `d929b49f25c83f237141641fab3eb03a3c231739` (reused, identical) | - | none |
| `b057b45d7c3745e857914cf5962d80f5eb52b635` | `b057b45d7c3745e857914cf5962d80f5eb52b635` (reused, identical) | - | none |
| `d8768373d0cf82f924485710aec37d93bc2ccedf` | `2ec3ee3a25479c52ca7bb23ea3114a623c67fbcb` | 2026-10-03T00:49:34-05:00 | 21 files, 21 replacements, raw/MANIFEST.json entries |
| `960bc20aab79a2ad42375114d6f0b28f34622fe8` | `640f45393ef95e1f196f9e235d82f3e38526b8c7` | 2026-10-03T00:49:54-05:00 | 21 files, 21 replacements, raw/MANIFEST.json entries |
| `63d419034fdbc837572052029e2205b2367cee07` | `4b57fadf62bb082b28048822587329a99afc0120` | 2026-10-03T01:03:55-05:00 | 21 files, 21 replacements, raw/MANIFEST.json entries |
| `6b70ec9024cc3921f7637bba2ffabcc93e29fc77` | `20dd88672a6d8abd0340edf5f5dc9229690dd904` | 2026-10-03T02:22:32-05:00 | 21 files, 21 replacements, raw/MANIFEST.json entries |

This note is added by one further commit on top of the rewritten head.
The value first entered at `d8768373d`; the later rewritten commits only inherit the redacted blobs (their own changes are untouched).

## Files (per file: replacements, old blob -> new blob)

Blob ids are git object ids. They are the same in every rewritten commit listed above.

| File (packet-relative) | Replacements | Old blob | New blob |
|---|---|---|---|
| `raw/pilots/n03a2p-ap1/session-log.txt` | 1 | `846b024849546ee19be07c890f1c6ef59c9f4e22` | `3216cdae76130e16ce0e2d7a6eaf83820fa32411` |
| `raw/pilots/n03a2p-ap2/session-log.txt` | 1 | `4db602f6a0dcee9f88c22febdb72d566b2b1f018` | `010791f5ae97b7fd3c95e5b38672108d02b0dd2c` |
| `raw/pilots/n03a2p-bp1/session-log.txt` | 1 | `3ed7390e7845d0bee8c455154a4167c70358f9e6` | `8cf4a1ca9decdfdb22e1a7bbb9d9c95539c21676` |
| `raw/pilots/n03a2p-bp2/session-log.txt` | 1 | `93ef195c44e40e3a7ab91811e4d6a2a176a6d028` | `686dd49c6952ae3fb1553a2381c60c06da85ef49` |
| `raw/pilots/n03a2p-bp3/session-log.txt` | 1 | `392ebda6f2ee859867a4832c8ee18c517660a281` | `c253922fb4fb2727fbe1fab36a1f98c7789e19e8` |
| `raw/pilots/n03a2p-bp4/session-log.txt` | 1 | `d02f139049f69405503a60b8ebac1d99faf0fffb` | `ad68a1cbdd3260adfa58b7709790c95ced689f99` |
| `raw/pilots/n03a2p-bp5/session-log.txt` | 1 | `53d74f77a7fe38d72aa4441e6f18826bccdb4f2d` | `bee2cf949dc251ade90a5dee802a201db0279907` |
| `raw/runs/n03a2-a1/session-log.txt` | 1 | `3e888d6e0fb832298d5872e1e0f280d7a1d703e0` | `534b5706c941687a3f9d9ce36fc16d0fe75484e1` |
| `raw/runs/n03a2-a2/session-log.txt` | 1 | `a5160484354d36dd0f05d872ba766d415eed4f9c` | `19bed599c6d9e98435a69eeae5aed949a7f59d3a` |
| `raw/runs/n03a2-b1/session-log.txt` | 1 | `f314bc7795817cac59ee378ea9717a4b946c4f80` | `e0df0cc45ea0a52c9f652def4b56614606f0bdb2` |
| `raw/runs/n03a2-bd1/session-log.txt` | 1 | `09c272ce16d7cb9b8821488b801e36f416349a59` | `fef90ba81c9a0c96db4e52c783ef6b486d5c1028` |
| `raw/runs/n03a2-bd2/session-log.txt` | 1 | `e8c463efb99ec9360634931722b8ee070a0da751` | `ea8e60a1e2fc03b5a1ed558b9486eb7d5bf4df23` |
| `raw/runs/n03a2-bs1/session-log.txt` | 1 | `0df2e3d3e31a87d977c0a7bd07bd4a4e6d6727a3` | `77fa719c608b87d4816bb56400382973de8eea10` |
| `raw/runs/n03a2-bu1/session-log.txt` | 1 | `31efb98dc5020fd0ac7706ca3e8e60faaf6f70d0` | `580102dc180fce8eabbf7ea956dd45bb5bc28fca` |
| `raw/runs/n03a2-cd1/session-log.txt` | 1 | `0b7bae884a23e32dd8e66bcc9cb88d4df3ec0449` | `84f004a4ee4dfa2c6b27ae1181b90b52b7cb14ac` |
| `raw/runs/n03a2-cd2/session-log.txt` | 1 | `1cd40f04f76b167862a016f5bd271846521b996c` | `3d22ce62a61f0f408cab0f3f5d476810652ec34b` |
| `raw/runs/n03a2-csn3/session-log.txt` | 1 | `f70c83f319746cce0274f0baa23c30d1eeb97229` | `edfd0dca42ac430609a2624a269d2094a5afa975` |
| `raw/runs/n03a2-csr/session-log.txt` | 1 | `8654608a2f34b6d121b677aa8f01dce495a02e41` | `9f0a6d6c1279ce25aacf57d372382717c6bbdcf1` |
| `raw/runs/n03a2-cv1/session-log.txt` | 1 | `100c3c60fd64d6b740cb4ce0074da4f9e2f46216` | `08729472f323865707e93ca1616f856d61474d2e` |
| `raw/runs/n03a2-k1/session-log.txt` | 1 | `9533f2a7c6e867caf8ae3da829a79dfddd9b49a4` | `8ed4684f1618167b1332e564d695c2b10a7bf504` |
| `raw/runs/n03a2-k2-r1/session-log.txt` | 1 | `b8b287073f49db5fe6bbf3e83891a9d53cc3e9cf` | `f63a813893c6d12daa53b40a82bfb319816c20dd` |
| **total** | **21** in 21 files | | |

`raw/MANIFEST.json`: the `bytes` and `sha256` of the 21 redacted files are updated in place (layout kept; no other entry changes): `5649a0e26a3829797a55bcbf4da6dc1da39461f5` -> `b06b3a83aba54f5b4d427460d55c6937aba3e570`. `verify_artifacts.py` checks every raw file against this manifest, so the update is what keeps that check passing; no verifier code changed.

## SHAs cited elsewhere

Text in this packet, in other packets and in loop records still cites the published SHAs. Read them through the table above. Tested sources, Driver binaries, measured data and verdicts are unchanged.

