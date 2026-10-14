# Independent portable-packet clearance

Reviewed 2026-10-14, after the producer's packaging corrections.

**CLEARED for the stated LIMITED evidence-only classification.** No remaining review blocker was found. Maintainer requirements and identity/admission policy remain undecided; this clearance does not authorize publication or establish a live nightly result.

- Confirmed Git 2.47.3 is distinguished from the ordinary-shell 2.52.0 version.
- Confirmed documentation discloses the `-I` bytecode-cache caveat and lack of filesystem confinement; no unexecuted `-B` change is represented as tested.
- Confirmed equivalent historical commit-content and provenance-based name-matching wording.
- Confirmed independent artifacts are included; copied raw logs and verification JSON match originals byte-for-byte. The original review body was changed only by the declared path substitutions, followed by a separately identified producer response. Original review and raw rerun logs remain intact.
- Executed the exact corrected `reproduce.sh` against the existing source into a new reviewer output directory. Wrapper exit: 0. Characterization: 7 PASS / exit 0. Separate proposed parity: 1 expected assertion FAIL / exit 1. Both phase observations, receipts, and status files match the earlier independent run byte-for-byte; no unexpected guard denial occurred.
- Repeated the identical wrapper command with the same output path. It refused with exit 2 before execution. Complete output-directory entry sets, file hashes, sizes, and modification timestamps remained unchanged.
- Rechecked all 17 source copies and hashes, scripts, manifest, metadata, and independently copied evidence. The source checkout remains tracked-clean at tested SHA `22c99c02ff119344e746e19bf8ecc782dbd1f679`.

Tested wrapper SHA-256:
`b436bf744d4b405a7cd8602d4be81476d3b21c2290a184a490eb1241bb4dc51f`

Reviewed README SHA-256:
`e15ec509d5861138c838285a74dc193467be9855eb9be5099de9a4ded60b904d`

Evidence is adjacent: `first-invocation.log`, `second-invocation.log`, respective exit files, `before-reinvoke.json`, `after-reinvoke.json`, `portable-verification.json`, and both `reproduction/` phase directories.

No external service action, network execution, dependency installation, missing-source fetch, or production source edit was performed. Existing source/metadata ownership and all prior scope limitations remain unchanged.
