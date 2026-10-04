# Guarded-completion consumer evidence: 2026-10-04

This downstream-only snapshot reconciles published receipts with current GitHub
heads. It does not port, replace, or qualify the owned guarded-completion,
outcome-handling, provider-parity, or motion implementations. Kevin Rajan
(`kvnloo`) remains the author of those contributions. No public discussion,
workflow rerun, paid provider call, desktop action, merge, or deployment occurred.

## Current evidence

The timestamp, failed and Jev-use check URLs, review records, source blob identities, and
GitHub comparison endpoint are in [ledger.json](ledger.json). Counts describe
reported checks at capture time, not a guarantee that all required workflows ran.

| Carrier | Current head | Reported checks | Meaning |
| --- | --- | --- | --- |
| [upstream #4316](https://github.com/trycua/cua/pull/4316) | `b2ae7cb934403f2585c7d3ed23a188b44264f293` | 2 success | Attribution and release reminder only; existing changes-requested review remains visible. |
| [downstream #87](https://github.com/kvnloo/cua/pull/87) | `b2ae7cb934403f2585c7d3ed23a188b44264f293` | 202 success, 23 skipped, 13 failure | Jev-use Python and TypeScript checks pass; repository-wide result is not green. |
| [downstream #111](https://github.com/kvnloo/cua/pull/111) | `f74a4d5e1ae804249c0d37f576702890949d76f8` | 14 success, 1 skipped | Draft outcome amendment has hosted evidence on this exact head. |
| [downstream #91](https://github.com/kvnloo/cua/pull/91) | `f5768667ea8d21601c78dfa7ad3ebe34855bdab7` | No checks returned | Historical integration receipt is not current-carrier composition evidence. |

The workflow-run API independently confirms that the successful Jev-use runs
[37159068530](https://github.com/kvnloo/cua/actions/runs/37159068530) and
[37156367659](https://github.com/kvnloo/cua/actions/runs/37156367659) have head SHAs
`b2ae7cb9` and `f74a4d5e` respectively. These are existing hosted results; this
audit executed no CI.

## Reconciliation

- #111's body still says hosted exact-head CI has not executed. Its hosted
  results now exist. Its local aggregate and runtime claims were not rerun here.
- #4316's body still identifies `05225e2a` as its exact head, while the live head
  is `b2ae7cb9`. Do not transfer historical timing claims to a new SHA implicitly.
- #111 describes a stack on `a0bca744`; its base branch now points to the current
  guarded carrier. GitHub compares current carrier to #111 as **diverged**:
  4 commits ahead and 177 behind, with merge base
  `345ff6d9db458a9d37b0f420dc4555553f4a4ce5`. No ancestry was inferred from the
  shallow local checkout.
- The current carrier and #111 have identical `verify_setup.py`, Python guard,
  and TypeScript guard blobs. Their Python runner blobs differ: #111 contains
  the canonical refusal adapter and observation/oracle outcome handling. Thus
  guard-source identity does not establish runner or full-tree identity.
- #87's 13 failing checks include documentation, image validation, Windows
  signing, installer smoke, portable parity, and reference builds. This audit
  records their names/URLs without diagnosing them or dismissing them as
  unrelated. Jev-use passing does not erase those failures.

## Next owner actions

1. The existing #4316 owner can reconcile its PR body with the current SHA and
   address the existing review; this snapshot does not change review ownership.
2. The #111 owner can correct its stale CI sentence and, when ready, decide how
   to reconcile its existing commits with the advanced guarded carrier. Preserve
   those commits and authorship; do not create a competing outcome port.
3. Requalify provider-parity composition on the selected final carrier before
   using #91 as current integration proof. Its current empty check list is not
   evidence of either runtime failure or success.
4. Triage the 13 current downstream failures through their exact job links.
   No workflow cancellation or rerun is requested by this receipt.

## Local validation and limitations

The audit checked carrier SHA identity, #111's 14/1 check count, API-reported
branch divergence, three identical source blobs, and the differing runner blob.
The JSON parses with the standard library; `git diff --check` passes. No runtime
behavior changed, so prior runtime suites were not redundantly rerun. The
workspace has Python, Node, and MCP, but no importable `typesafe` package or
installed Jev-use TypeScript dependencies; no dependency was installed. Native
platform, browser, timing, and live-provider qualification remain outside this
read-only evidence audit.
