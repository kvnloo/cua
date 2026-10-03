# Stack v2 publish record (2026-10-02)

## Refused write (not retried)

- kvnloo/hermes-agent: push of `exp/stack-samples-20261002` @ 5d01f60897373e67 (new branch, --no-follow-tags, via
  h.git with the gh credential helper). It was refused by the Claude Code permission classifier ("External System
  Writes"). Per the rules it was not retried, and no other hermes-fork push was attempted. The remote has no
  `exp/stack-samples`, `exp/stack-addr` or `exp/stack-confirm` branch.

## Held by Publish (not attempted): autolinking upstream reference in commit messages

- kvnloo/cua 61bc07298 (ADDR results packet) and kvnloo/hermes-agent 70cfc7a5 (the ADDR fix) name the upstream
  Driver PR in owner/repo#N form. Upstream is trycua/cua; the PR number is 3873.
- Evidence that this writes upstream: earlier kvnloo pushes whose commits named trycua issues produced "referenced"
  events from kvnloo on the upstream timelines. I saw this read-only on trycua/cua issues 4052 and 3963 (commit
  320451280) and on 3383.
- Affected branches (every one descends from one of the two commits):
  - kvnloo/cua `exp/stack-addr-20261002` @ 2013aa364
  - kvnloo/cua `exp/stack-confirm-20261002` @ 62034ca48
  - kvnloo/hermes-agent `exp/stack-addr-20261002` @ d39e1175
  - kvnloo/hermes-agent `exp/stack-confirm-20261002` @ b51c7a22
- Rewording the messages would change the commit hashes that the ADDR and CONFIRM packets and their verifiers cite:
  PREREG and CONFIRM2_PREREG order, the freeze commit, and the measured-build identities 70cfc7a5, c3d96b04,
  d39e1175 and b51c7a22. That is an orchestrator or owner decision, not a Publish action. The options:
  - (a) Accept the upstream reference event and push as-is.
  - (b) Reword both messages to plain text with author and committer dates preserved (trees identical), add an
    old-to-new hash mapping erratum to both packets, and re-run each verify_artifacts.py on the new heads.
- Otherwise all of these commits scanned clean: no absolute local paths, host name, secrets or binaries; noreply
  author and committer; Co-Authored-By trailer on each.

## Successful writes

- kvnloo/cua `exp/stack-samplesfix-20261002` @ 0e50faebf728681c7c394ef232988bc5bb03b5b9 (new branch).
- Comment: kvnloo/hermes-agent#319, issuecomment-5961784610.
- Comment: kvnloo/z0intelligence#14, issuecomment-5961789232.
- Not commented: kvnloo/cua#36, because v2 has no new multi-session evidence.

## 2026-10-02 owner-approved follow-up (orchestrator)
Owner approved pushing the hermes stack branches and pushing the held commits as-is (accepting the upstream "referenced" event from the trycua/cua#3873 mention in two commit messages). Privacy scan of every non-merge commit since the merge-base: clean. Pushed with --no-follow-tags, new branches, no force:
- kvnloo/hermes-agent: exp/stack-samples-20261002 @5d01f60897, exp/stack-addr-20261002 @d39e1175f3, exp/stack-confirm-20261002 @b51c7a222e
- kvnloo/cua: exp/stack-addr-20261002 @2013aa364b, exp/stack-confirm-20261002 @62034ca48e
The stack track's user-local Ollama (127.0.0.1:11500) was stopped by the orchestrator.
