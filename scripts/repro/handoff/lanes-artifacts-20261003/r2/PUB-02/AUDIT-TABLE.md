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

