# Publish record: bend-stack run (2026-10-03)

Hard breaches reported: none. All 5 lanes accepted. No write was refused; nothing was held.

## Pushes (new branches, --no-follow-tags, no force, explicit kvnloo URLs, gh credential helper)
| Repo | Branch | Head | Commits since base |
|---|---|---|---|
| kvnloo/bend-native | exp/contract-20261002 | 15ddac2bd545e53e292c0aa22e6c66ef0615d383 | 4 (base e85e65e5) |
| kvnloo/bend-native | exp/b389-20261002 | 0d434457b97e720c59c9075680692eddae771e86 | 3 |
| kvnloo/bend-native | exp/b390-20261002 | e79cfe72e6ab0c51805ab1c06c50ac4aa7c32054 | 2 |
| kvnloo/bend-native | exp/e2e-20261002 | a7a041f8c8b27f4525fc7d2f7fa73cd5a4f81634 | 3 |
| kvnloo/bend-native | exp/aodl-20261002 | 9477f918f579d85c7303b4e7130281310d0e86f4 | 3 |
| kvnloo/hermes-agent | exp/bend-stack-integration-20261002 | ad31bbf079f0ee559ce1b61c5f85178c4c3d9396 | 3 (base 50a6abca) |
| kvnloo/bend | exp/b389-patchonly-20261002 | 6e940a0b27b596606246a4b9f8dd47de48cb93c7 | 1 (base v2.0.34 7d8a3eb0, already in fork main) |
| kvnloo/z0intelligence | none | lanes used existing exp/bend-aodl-gate a0e95785 and dev 6764ae78 unchanged | 0 |

Remote heads confirmed with git ls-remote after push. Note: the Hermes bare repo's `origin` is the upstream
repository, so the push used the explicit kvnloo URL.

## Commit scan (all 19 commits: messages and added lines)
- Identity: author and committer Kevin Rajan noreply on every commit; Co-Authored-By trailer present on every commit.
- Messages: no absolute local paths, host name, secrets, upstream owner/repo#N or upstream issue/PR URLs.
- Added lines: no /mnt, /home/<user>, /workspace, host name or secret patterns (only `$VAR/template/home/...`
  placeholders, generic `/run/user/$(id -u)` and `/tmp/.X11-unix` mask code, and verifier regex literals).
- File content (not autolinking): the plugin's own limitation string with the upstream bendlang/bend issue 1212 URL in
  raw receipts (contract 38, b389 30, b390 262, e2e 52, aodl 28 added lines); Hermes branch has 2 code-comment lines
  naming trycua/cua PR 3873 in owner/repo#N form. Not quoted in any posted text.
- Scan script and outputs: cua-lane-tmp/bend-publish/scan.sh, scan-*.txt.

## Comments (plain-text upstream refs, no local paths)
- kvnloo/hermes-agent#389: https://github.com/kvnloo/hermes-agent/issues/389#issuecomment-5966210842
- kvnloo/hermes-agent#390: https://github.com/kvnloo/hermes-agent/issues/390#issuecomment-5966211013
- kvnloo/hermes-agent#324: https://github.com/kvnloo/hermes-agent/issues/324#issuecomment-5966211144
- kvnloo/hermes-agent#319: https://github.com/kvnloo/hermes-agent/issues/319#issuecomment-5966211249
- kvnloo/bend#2: https://github.com/kvnloo/bend/pull/2#issuecomment-5966211371

## Teardown
- User-local Ollama (pid 2602721, /mnt/zer0models/ollama-stack, 127.0.0.1:11500) stopped with SIGTERM; port closed.
  System Ollama on 11434 untouched.
- Private z0 services: none running (11521/11523 not listening; no bend-service/bend-z0svc processes).
- Live z0 service 11501 and live Hermes home not contacted by the publish step.

## Not done (owner decisions / follow-ups)
- Packet errata (SYNTHESIS.md section 10) not committed; packets published exactly as verified.
- B389 unlocked pilots overlapped other workflows' exclusive windows (b04a2-measured-r20-30, n03a2-a1, r2-10r-a2-nm2);
  recorded in SYNTHESIS.md section 9 for those owners; not posted anywhere.
