# Issue 67

Verdict: NEEDS DESIGN DECISION before an upstream slice.

Downstream test already committed: `test_cancellation_lifetime.py`. It does not choose the #3796 implementation.

Seam: the existing request-id owner. `Lifetime.release` raises if native work has not exited. `finish` raises on a different issuance.

READY WHEN RFC APPROVES that slice. Not before.
