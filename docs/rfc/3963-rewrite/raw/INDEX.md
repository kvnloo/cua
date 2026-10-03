# Verifier logs (DOC-3963b, wave 7)

Every run is from a fresh clone under the lane temp directory, under the loop's hostless wrapper, with a private-name file set. Each log's header names the tested commit, the clone kind, the STATE.json sha256 and the command. The logs report private names by entry number only and print no local path or upstream link.

| Log | What it shows | Summary | Exit |
|---|---|---|---|
| `verify-default.log` | clean local clone (git clone --shared of the main clone; git wrote no alternates file because the main clone is shallow, so all its objects are local), default mode | FAIL=0 NEED=0 DIFF=0 FLAG=2 SKIP=2 PASS=15 | 0 |
| `verify-state.log` | same clean local clone, --state mode | FAIL=0 NEED=0 DIFF=3 FLAG=2 SKIP=0 PASS=20 | 0 |
| `verify-heads-only-nofetch.log` | heads-only clone (git clone --no-local --single-branch: only this branch, no other objects), --no-fetch: missing refs must be NEED, not FAIL | FAIL=0 NEED=141 DIFF=0 FLAG=2 SKIP=2 PASS=13 | 0 |
| `verify-heads-only-fetch.log` | same heads-only clone, default fetch behaviour with --state: missing refs fetched read-only from the fork / upstream | FAIL=0 NEED=3 DIFF=3 FLAG=2 SKIP=0 PASS=19 | 0 |
| `neg-stale-number.log` | NEGATIVE CONTROL: planted stale number (section 1 live fill S 45.11 -> 45.21); must FAIL on claims | FAIL=1 NEED=0 DIFF=0 FLAG=2 SKIP=2 PASS=14 | 1 |
| `neg-stale-budget.log` | NEGATIVE CONTROL: planted stale budget line (wave-5 values 562 / 38) in --state mode; must FAIL on claims and regen | FAIL=3 NEED=0 DIFF=3 FLAG=2 SKIP=0 PASS=18 | 1 |
| `neg-private-name-file.log` | NEGATIVE CONTROL: planted untracked file holding a private name (entry 1 of the names file); must FAIL on privacy | FAIL=1 NEED=0 DIFF=0 FLAG=2 SKIP=2 PASS=14 | 1 |
| `neg-upstream-autolink.log` | NEGATIVE CONTROL: planted upstream autolink (owner/repo hash-number) appended to README.md; must FAIL on autolink | FAIL=1 NEED=0 DIFF=0 FLAG=2 SKIP=2 PASS=14 | 1 |

Expected: FAIL=0 in the four verification runs (NEED in a heads-only clone only names refs to fetch; after fetching, two NEED name the held, unpublished PUB-03 candidate and the third is the regeneration waiting on it). Each negative control exits 1 on the check it targets: claims (stale number), claims + regen (stale budget), privacy (private-name file), autolink (upstream autolink).
