# Independent review: CUA #4898 timeout revalidation evidence

Date: 2026-10-14 UTC

## Verdict

The packet supports the narrow claim that the existing recency guard preserves a refreshed environment between timeout selection and release. The exact target-file bytes pass the four deterministic cases, and removing only that guard makes the refreshed and equality cases fail. This is file-level evidence, not whole-package acceptance or approval to promote the PR.

Implementation owner TanishGudise, assigned human reviewer ddupont808, and `risk:human` remain unchanged. No implementation takeover, origin writes, or #4899/#4929 work was performed.

## Independently reproduced

I ran the final head and mutant commands from `commands.txt`, with their isolated interpreter, sanitized environment, 20-second outer timeout, and unchanged guards:

- `logs/reviewer-head.json`: exit 0; 4 PASS.
- `logs/reviewer-mutant.json`: exit 2, as expected; `refreshed` and `exact_timeout_boundary` FAIL, while `expired` and `still_expired_after_touch` PASS.
- Both runs: no guard denials, zero pending closes in every case, exactly one recorded import-time daemon suppression, and only MainThread remaining.
- The failing mutant cases close the environment once, remove its original state from the registry, and return its slot to availability. Their failure is behavioral, not an import or infrastructure failure.

## Byte and mutation verification

- Target head recorded in provenance: `4fa9c8e8ba2e11cc9a0a98f1ad057886117988b3`.
- Target file Git blob verified by the executed harness: `524413d0cc3fbe662805010c320ba4f2537aa7a2`.
- Target SHA256: `60266d6a5ebd9aa05926c2f2fecc0ef9e96cb36264102b44dff6922647d4f68d`.
- Mutant SHA256: `a13545b871514398695a797f3182ba679a1b65a4bf33fb21d71121c4e3f40828`.
- Reviewed harness SHA256: `60f9954864a08940d51c69980fc4f33b67d2e608aa6e3ebe864f775d984413b7`.

I independently checked that the mutant is exactly one substitution removing `or expired_at - state.last_accessed <= state.timeout`, retaining `state is None`, with all other target bytes unchanged. I also verified all nine dependency files byte-for-byte against the existing checkout and their manifest SHA256, Git-blob hashes, and lengths. These are complete unchanged source files, not fake modules or extracted functions. Their checkout-reported commit is `2600a2abb095a70e01a56bfe8f8308a03b4cdc67`, separate from the target head. I did not independently fetch or revalidate the remote commit-to-file mapping.

## Evidence validity

The barrier is reached after the real checker selects the expired candidate and drops the real non-reentrant lock. Refresh uses the real `_get_env` and records the controlled clock read while that lock is held. The original `_release_env`, `_close_env_soon`, and asynchronous close path then execute; only the environment's terminal `close()` implementation is inert. State identity, registry membership, active/available status, close counts, and pending futures are checked.

Callback drainage is ordered correctly: the checker finishes only after release has registered its close future, and observation waits for the pending-close set to drain. The expired controls verify that the harness does not merely prevent every release.

## Limits and safety qualifications

- The module is loaded through a file loader, bypassing the unrelated workers package initializer. The genuine dependency import closure is incomplete and comes from a different checkout; this is not a complete candidate-package installation.
- The normal import-time timeout daemon is suppressed; one controlled checker sweep runs instead. Production daemon startup, periodic scheduling, and shutdown lifecycle are not validated.
- Equality and still-expired controls deliberately move the test clock backwards after selection to construct boundary states. They validate the comparison, not realistic elapsed-clock behavior.
- No live environment, driver, container, provider, credentials, source acquisition, or installation is exercised. Backend closure is not validated by the inert terminal close implementation.
- Python audit/import/thread guards are defense in depth, not an operating-system security boundary. The earlier fail-closed directory-listing stop and its documented narrow correction remain preserved in the packet; neither independent final run encountered a denial.
- The 500 MiB cap is for disk/source/evidence; process memory is separately bounded at 1 GiB. The packet was 205,422 bytes before this review file.
- These deterministic runs do not establish stress-test coverage, all possible interleavings, endpoint integration, or merge readiness.
