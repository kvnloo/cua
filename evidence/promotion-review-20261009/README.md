# Cua promotion review — 2026-10-09

## Recommendation
Use upstream #4888 as the single Vertex carrier, with the narrow fork #118
compatibility repairs reviewed and integrated by its owner. Keep #4871/#115 as
comparative evidence; do not merge both competing implementations.

This is an evidence-only snapshot, not merge readiness or permission to run CI.
Ownership was reread on fork #115 and #118 before publication. No source, owner
branch, upstream comment, new PR, approval, privileged workflow, or merge changed.

## Exact-head Actions observation
Fresh read: 2026-10-09T23:40:29.169Z to 2026-10-09T23:40:36.149Z.
See observations.json for every returned run ID, workflow name, state, head,
base, merge SHA, and timestamps.

| Upstream PR | Head | Returned runs |
|---|---|---|
| #4734 | 32ca35a6 | 6 action_required |
| #4902 | bb3885fc | 4 action_required |
| #4871 | f520a122 | 25 action_required |
| #4888 | 6dba09b0 | 32 success |

The first three have approval gates, not executed test failures. Sampled jev-use
and Linux-unit job lists were empty. No review submissions were returned for
any of the four. Empty legacy commit-status lists do not imply missing Actions.
Counts are observed runs, not distinct required checks or proof that every
possible workflow exists. Skipped/missing coverage is not promoted to PASS.

[Existing #4888 live smoke](https://github.com/trycua/cua/actions/runs/37947944801)
really ran Linux GTK3 and Windows WinForms. The
[Linux log](https://github.com/trycua/cua/actions/runs/37947944801/job/113879001525)
checks out PR merge SHA 5c473887a4ba369fc1b791f186f007df740ad64e,
combining head 6dba09b0394f93b0d6a7ad0cc31c62c764538af1 with base
b6c3814e416f4bd0ea041d47f1891b36c0837a4a. It records 12 PASS rows,
including application readback, stale-token refusal, and unknown-option refusal.
Returned smoke job steps contain no skips. Its generic smoke scope does not
certify jev-use forced recovery, no-progress, ambiguous acknowledgement, or
no-blind-retry, and cannot certify later fork fixes.

## Compatibility evidence and remaining changes
The separate #118 publication lane's reviewed local receipt at 56279767d
identifies executable candidate fcfa929ee923b44e5fab971df5bcdb9a66927518.
It records 66 contract and 93 overlay passes, native Python 5/5 and TypeScript
5/5, generated binding/manifest drift checks, 63 direct-stdio tool schemas,
and numeric direct/batch argument admission. Broader core: 938 pass / 13
environment failures. These counts are the existing lane receipt, not tests
rerun by this review; the publishing owner supplies its verified remote head.

Crucially, typed explicit-null collapse already existed in Option<bool> before
#4888. The null patch repairs older lost reset intent. Generated-SDK legacy
boolean rejection and numeric batch rejection have separate native RED/GREEN
evidence. Numeric admission probes intentionally stop at a no-token refusal;
they do not prove delivery into an application.

The successor still intentionally rejects observe:"true"/"false". Published
Vertex schemas may still cause locally validating clients to reject old
numeric/bool/null forms. Therefore this is not blanket backward compatibility.
The #4871-based lane records 934 core passes with the same 15 exact-baseline
failures, including two genuine observe regressions and 13 environment failures;
those must not be mislabeled as all environmental.

## Native recovery gate
The 23:38:32Z preflight still reports AF_UNIX EPERM and D-Bus exit 127.
No desktop/session bus is available. The forced-fault matrix remains NOT_RUN;
no security bypass was attempted. Reuse the existing
[recovery acceptance receipt](https://github.com/kvnloo/cua/blob/6476a3044ef4209ae5f0a80ca5509750554f6a29/evidence/real-driver-recovery/RECEIPT.md).
Cargo absent from the unmodified preflight PATH is not a claim that other lanes
lack their explicit private toolchain. The socket restriction is decisive.

## Maintainer handoff — draft, not posted
Please retain #4888 as the Vertex carrier and review the narrow compatibility
fixes from fork #118, then run fresh CI on the integrated candidate. Preserve
#4913's full_output and narrowly scoped old-driver fallback when rebasing
#4734; integrate #4902 metadata 93acf502 before canonical escalation d742080f.
Existing green #4888 CI cannot certify those compositions. Canonical daemon
and the real wrapper fault matrix still require a disposable desktop permitting
Unix sockets and D-Bus. Explicitly decide/document the observe-string break.

Credit remains with injaneity for #4888 and its testkit design, RitikaxG for the
live-inventory diagnosis, kvnloo for the original Vertex work and downstream
repairs, Andrew9603/IRONICBo for the no-progress evidence boundary, and
f-trycua for #4913. No submitted contribution is reimplemented or reattributed.
