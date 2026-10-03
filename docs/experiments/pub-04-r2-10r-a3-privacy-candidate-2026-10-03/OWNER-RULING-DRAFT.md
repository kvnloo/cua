# PUB-04 owner-ruling draft: the fifth published privacy finding (HELD, not run)

Lane PUB-04 (wave 7) for kvnloo/cua#93 and kvnloo/cua#73. This section extends the PUB-03 owner-ruling
draft (rulings 1-5 there) with the candidate PUB-03 could not build. Nothing in it has been pushed, posted
or deleted. The Publish agent runs the commands below only after the owner rules "replace" on this branch.
If text from this note is posted to the fork, write upstream items as plain text (trycua/cua PR 4316) and
fork items as kvnloo/cua#N.

## Ruling requested

| Published branch @ head | Finding | Held candidate | Recommendation |
|---|---|---|---|
| `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ecf8a679d1425c21120a599775aa0817d` | tmp-dbus: 25 files / 25 occurrences (session-bus socket paths in `raw/logs/*.log`), first `8be812d0c` | `exp/r2-10r-recert-a3-r1c-20261003`, candidate head `a2ded080cac3f8bdd17e3076da1e3b4196b57fa5`; branch tip = candidate head + this evidence packet | Rule it with PUB-03 rulings 2 and 3 (same class). **replace** if those are replaced; **accept** is defensible for the same reason (a random per-session socket name with no user or host in it), and then accept all three. |

## What the candidate is (verified in this packet)

- Rewritten commits (author name, email and date kept): `8be812d0c` -> `a7fc59005`, `ac46b5032` -> `4d496ed1e`,
  `d22eeb2ec` -> `a5ac8368f`; then the note commit `a2ded080c` adds
  `docs/experiments/r2-10r-recert-2026-10-03/PRIVACY-REWRITE.md`. Commits up to `2bd181dff` are shared.
- Normalized diff: the candidate head differs from `d22eeb2ec` in 25 paths (one redaction each) plus the
  added note; 8153 other paths are byte-identical. In each of the 25 paths the published bytes with the
  redaction pattern applied equal the candidate bytes exactly. A pattern-free check gives the same result.
  No commit message and no manifest entry needed a change.
- R2-10R a3 `verify_artifacts.py` from clean clones under `bin/hostless`: 189/189 on the published head,
  on the redaction-only head and on the candidate head, without and with the names file. Published and
  redaction-only output is byte-identical. The candidate head's output differs only in the commit and blob
  counters (+1 each), from the note commit.
- Per-commit scan (every class, word-boundary fix included): 0 private findings in the 17 commits of the
  candidate head and in every commit of the branch tip.
- Every commit after the candidate head touches only
  `docs/experiments/pub-04-r2-10r-a3-privacy-candidate-2026-10-03/`.

## Command list for the Publish agent (HELD: run only on a "replace" ruling)

Set `TIP` to the branch head given in the PUB-04 lane report and in `artifacts/r2/PUB-04/MIRROR.json`.
Run in the main clone (origin = kvnloo/cua). Every step is guarded, so a moved ref stops the sequence.

```sh
R=<main clone>; B=exp/r2-10r-recert-a3-20261003; N=exp/r2-10r-recert-a3-r1c-20261003
OLD=d22eeb2ecf8a679d1425c21120a599775aa0817d; CAND=a2ded080cac3f8bdd17e3076da1e3b4196b57fa5; TIP=<from the lane report>
# guards: published head unchanged, local candidate branch at TIP, TIP = candidate + this packet only, N not yet on origin
test "$(git -C "$R" ls-remote origin "refs/heads/$B" | cut -f1)" = "$OLD"
test "$(git -C "$R" rev-parse "refs/heads/$N")" = "$TIP"
git -C "$R" merge-base --is-ancestor "$CAND" "$TIP"
test -z "$(git -C "$R" diff --name-only "$CAND" "$TIP" | grep -v '^docs/experiments/pub-04-r2-10r-a3-privacy-candidate-2026-10-03/')"
test -z "$(git -C "$R" ls-remote origin "refs/heads/$N")"
# 1. publish the candidate branch (new ref; nothing is overwritten)
git -C "$R" push origin "$TIP:refs/heads/$N"
test "$(git -C "$R" ls-remote origin "refs/heads/$N" | cut -f1)" = "$TIP"
# 2. replace: delete the published branch only if it is still at d22eeb2ec (lease)
git -C "$R" push --force-with-lease="refs/heads/$B:$OLD" origin ":refs/heads/$B"
```

After the replace:

- Record `publication_sha` = `TIP` (candidate head `a2ded080c`) for R2-10R in the loop records.
- Re-point STATE.json `dispositions` for R2-10R (branch and commit) to `exp/r2-10r-recert-a3-r1c-20261003` and
  the candidate head. The R2-10R packet content, numbers and verdicts are unchanged.
- Re-run `docs/experiments/r2-10r-recert-2026-10-03/verify_artifacts.py` and this packet's
  `verify_artifacts.py` from a fresh clone of origin.
- Post one kvnloo/cua#93 comment naming the old -> new branch and head. It must not repeat any redacted value.

On **accept**: run no command. Record in STATE.json `owner_rulings` that the tmp-dbus class is accepted for
this branch. Delete the held local candidate branch only if the owner asks.

## Wave-6 rescan (information for the same ruling)

The 7 heads pushed in wave 6 were re-scanned commit by commit since `main` (read-only, live origin heads
fetched into a clean clone): B-08 `49ae94590`, R2-07e `67b99ddc6`, OWN-78L `d9edde70e`, FIX-03 `e300edbd3`,
OWN-20Q `44116546d`, DOC-3963 `088fe745a`, DOC-10-74 `a3e3cb86e`. Result: 0 private findings in every commit
of every head. So the owner's ruling covers the complete set of published privacy findings: PUB-03
rulings 1-3 and 5, and this one.
