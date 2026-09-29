# #4316 retained-evidence adversarial audit — cycle 001

## Verdict and next decision

**NONQUALIFYING for the intended historical REAL route / provider-work-deletion claim.**
The six retained rows still record successful fixture outcomes. Their original
logs, receipts, journal and final report are unchanged. They lack independent
per-trial provider counters and observation→dispatch/session bindings. A
successful outcome with an unproven intended route is not qualifying evidence.
This is a checker/evidence-chain finding, **not an optimization implementation
bug or a speed measurement**.

Parent decision: independently verify this bundle, then consider integrating
only this evidence tooling. Do not upgrade the historical rows using these new
FIX witnesses. A separately authorized future REAL run must capture passive
provider entries, fresh observation/dispatch refs and sessions, and a keyed
independent fixture oracle. No such REAL run, GUI, live provider, push, upstream
comment, or PR modification occurred here. This lane uses terminal/files only;
no browser/computer-use tools or cached global Driver are invoked. Any future
GUI/input test belongs to the parent in a verified headless **Sway-wm-only**
harness: no native Hyprland and no Xvfb fallback.

## Exact scope and pins

- Base / runner / verifier: `c78f50efed1ee7b289ab8947ec997904ea18fd72`.
- Example tree: `e619bcacf8e587b26cb96e63f89fa35bdaef5455`.
- Rust tree: `71e08f221ebdc86ffee0cd8f37085e1fc434f3e6`.
- Retained Driver SHA-256: `f1d7f2d4ce929a8df80338ac57942bc6535ee5bef4f441f6173688b62da722f7`.
- Node: `v22.23.2`; executable SHA-256:
  `3517c2df0b2f8cd7f422b4b8450ef81c6889f08eb03e281d6de9079b15e6a327`.
- Python: read-only c4316 `.venv`, version and executable hash in
  `source-inventory.json`. Inherited `PYTHONPATH` / `PYTHONHOME` are removed.
- All 56 files under the protected `4316-maintainer-proof-review/` directory and
  all 122 example files in the initial inventory are rehashed by
  `validate_bundle.py`. Driver/Rust/example source is not modified.
- All writes and commits are restricted to this directory on the assigned
  `research/guarded-receipt-audit-20260929` branch.

## Observed results

| Consumer | Trials / tests | Actual result |
|---|---:|---|
| Exact retained verifier on both retained language corpora | 94 | 70 accepted, 24 rejected |
| Of those: valid controls | 10 | 6 untouched rows and 4 valid zero-duration provider controls accepted |
| Of those: adversarial trials | 84 | 60 accepted, 24 rejected |
| New adversarial trials, excluding registered oracle-control replays | 80 | 60 accepted, 20 rejected |
| Narrow downstream auditor, CLI **and** semantic core | 58 | 53 corruptions rejected; 5 valid FIX controls accepted |
| Original verifier tests | 21 | 20 pass, 1 dependency-related skip |
| Original Python consumer tests | 7 | all pass |
| Original TypeScript consumer tests | 20 | all pass |
| New genuine Python consumer captures | 3 | default/accepted/declined have 2/1/2 counted mock-chooser entries; independent HTTP state succeeds |

`existing-controls.json` was written before challenges. It registers 57 test
function/declaration sites (including parameterized templates and positive
controls, **not** a claim of 57 negative tests). Existing verifier negatives and
consumer tests were reused unchanged. Guard-unit tests were inventoried, not
reimplemented or treated as new audit evidence. Four retained-corpus trials
reuse the two registered missing/wrong-oracle controls; each result names its
original control. They are excluded from the count of new adversarial trials.

### Precisely what the retained checker accepts

The per-case truth table is `retained-matrix/summary.json`; complete inputs,
commands, outputs, independent checks and SHA-256s are in each cell directory
and `retained-matrix/results.jsonl`. Python and TypeScript corpus results agree.

- Arbitrary distinct `prior_ref` / `fresh_ref`, a foreign session, or whitespace
  ref/session labels. The checker checks nonempty strings and inequality, not
  actual observations, actual dispatch or the session used by that dispatch.
- `submit_matches: true` or `1.0`, and `provider_decision_ms: false`: Python
  equality accepts these as 1 or 0. The downstream schema requires real integer
  counts and numeric (not boolean) durations.
- Accepted guarded steps marked dry-run, action-error, no tool, or a different
  candidate. It can return `verified` even with no successful submit step in
  the claimed log because the independent fixture was submitted by the
  explicitly adversarial replay child.
- Missing/error first actions, repeated/invalid step numbers, proof duplicated
  onto the first step, and an earlier contradictory outcome followed by the
  required final outcome.
- Invented provider-counter fields, a declined dry-run, and a guarded route in
  the default-off corpus. Default `verify()` certifies outcome, not a requested
  default-route invariant.
- Changed receipt pins/mode/steps and false, foreign-language or duplicated
  journal entries **do not affect its result**. Those sidecars are outside
  `verify()`'s input interface. This is an evidence-chain coverage gap, not a
  claim that it parses and approves those sidecars.

### What it rejects

The new matrix rejects empty session labels; wrong accepted proof status or
field; zero/two Submit matches; extra proof keys; nonzero guarded duration;
wrong/extra declined reason/status fields; and missing/wrong actual HTTP
submission. Existing registered tests also reject the wrong accepted route,
missing proof, equal prior/fresh refs, nonnull guarded confidence/probabilities,
missing/wrong decline proof or route, missing verified outcome, and nonzero
child exit. See `retained-tests.json` and its logs for actual reruns.

`verify_setup.py` at the pinned head: route/proof checks are at lines 142–179,
decline checks at 180–190, and the independent outcome checks at 128–136. It
accepts a caller-supplied command and JSONL; no independent dispatch or provider
trace is consumed.

## Consumer/oracle and auditor boundaries

`challenge_retained.py` calls the **unmodified** `verify_setup.verify()` through
its genuine callable entrypoint. It launches a real subprocess and uses the
unmodified `FixtureServer` HTTP `/submit` and `/state`. There is no mock of
`verify()`, `subprocess.run`, `urlopen`, or its independent oracle. Its producer
is deliberately a replay adversary, not a Driver or a newly claimed REAL run.
Receipt/journal mutants and runner JSONL are retained separately.

`capture_consumers.py` calls the unmodified Python runner's real
`main() → parse_args() → run()` consumer path. It reuses the existing
`FixtureSession` mock MCP transport, wraps the real mock chooser entrypoint
without replacing its result, captures redacted observations/actions at the
transport boundary, and uses the genuine HTTP fixture. The journal wrapper
observes the genuine submission handler; it never initiates submission. The
only decline injection is a duplicate fixture target after typing.

These three captures are **FIX**, not REAL/BENCH. The TypeScript retained tests
use their existing process-isolated runner entrypoint; their mocked oracle is
not promoted to an independently captured REAL oracle. Fresh correlated
Python witnesses never fill missing historical TypeScript or Python fields.

`auditor.py` is a deliberately narrow downstream policy:

1. Require explicit requested mode and exact pins, typed proof and step shape.
2. Require actual observed/dispatch session and ref binding, chronology, field
   proof, uniqueness, success and the known explicit decline/fallback.
3. Correlate counted chooser entries to the trace sequence, not elapsed time.
4. Require independently fetched state and exactly one correctly attributed
   journal entry for the same cell/trial/language.
5. Load witness files only from an externally hash-pinned custody manifest;
   never let the claim choose or reseal witnesses. Reject malformed data,
   duplicate JSON keys and nonfinite JSON numbers.

The CLI emits `QUALIFYING_FIX_ONLY` or `NONQUALIFYING` and exits 0 or 1.
`audit_capture()` is the semantic core for already-trusted witness objects;
production use of this evidence tool should use the custody-checked CLI.
Mutated witnesses are tested both at the core and at the CLI: an integrity
rejection must not conceal a missing semantic check.

Local hash custody is not authentication against an actor who can replace the
externally held anchor and every witness. Descriptive capture strings are not
signatures. This does not certify arbitrary tasks, languages, real Drivers,
or unobserved routes. Missing evidence fails closed.

## Reproduce / independently verify

From the assigned worktree:

```sh
cd /mnt/zer0models/github/cua-lanes/speed-audit
A=research/work-deletion/audit-cycle-001
P=/mnt/zer0models/github/cua-lanes/c4316/libs/cua-driver/examples/jev-use/.venv/bin/python

# Read-only verification of all canonical artifacts and protected source bytes.
python -B "$A/validate_bundle.py"

# Current RED boundary: unmodified retained checker accepted this corruption.
# Exit 1 / one failed assertion is the expected RED result.
AUDIT_CHECKER=retained python -B "$A/test_auditor.py" \
  AuditorTests.test_success_with_unobserved_fresh_ref_is_nonqualifying

# GREEN: downstream auditor tests, including real CLI invocation.
python -B "$A/test_auditor.py"

# Audit one saved FIX capture with the independently recorded custody anchor.
python -B "$A/auditor.py" --claim "$A/fix-captures/accepted/claim.json" \
  --custody "$A/fix-captures/custody.json" \
  --custody-sha256 6052ffffe79bd3e1cea2c3bdbcbe3b66189e2350942b9dff5818201737cbbfbb

# Fresh executions; these refuse existing output directories.
# Only the audit-local ignored tmp/ tree is written by these reproduction runs.
env -u PYTHONPATH -u PYTHONHOME PYTHONDONTWRITEBYTECODE=1 "$P" -B \
  "$A/challenge_retained.py" --out "$PWD/$A/tmp/repro-retained"
env -u PYTHONPATH -u PYTHONHOME PYTHONDONTWRITEBYTECODE=1 "$P" -B \
  "$A/capture_consumers.py" --out "$PWD/$A/tmp/repro-captures"
python -B "$A/run_auditor_matrix.py" --out "$PWD/$A/tmp/repro-downstream" \
  --captures "$PWD/$A/tmp/repro-captures" --retained "$PWD/$A/tmp/repro-retained"
```

`run_retained_tests.py` reruns the registered suites and rewrites its local test
logs/receipt; do not do that before checking an existing seal. It checks that
all read-only donor TypeScript source bytes and its lockfile match this exact
head. An audit-local dependency symlink is removed in `finally`. Source and
shared dependencies are not modified. A sole TS argument-validation skip in
the verifier suite reflects absent dependencies in the assigned example
checkout; all 20 retained TS consumer tests were separately executed using
the byte-matching donor dependencies and Node22.

`prepare.py` refuses to replace the initial inventory. `validate_bundle.py
--seal` is for deliberately issuing a new local artifact seal, not for hiding
changed evidence. Validate before resealing; the protected evidence comparison
is always against the original `source-inventory.json`.

## Artifact map and issues

- `audit-report.json`: machine verdict, counts, exact pins, limitations and decision.
- `artifact-hashes.json`, `validation.json`: every canonical artifact SHA-256,
  source preservation and privacy checks. The manifest excludes itself and
  audit-local `tmp/`/bytecode, not any canonical cell.
- `existing-controls.json`, `source-inventory.json`: initial registration and pins.
- `retained-matrix/{language}/{mode}/{mutation}/`: complete retained-verifier trials.
- `fix-captures/{mode}/`: actual consumer JSONL, independent transport/oracle
  witnesses, claim, capture receipt; `custody.json` binds them.
- `downstream-matrix/{mode}/{mutation}/`: complete intentionally mutated inputs,
  original witness hashes, CLI command/exit/result and semantic-core result.
- `downstream-matrix/historical-verdicts.json`: six untouched historical rows
  explicitly remain nonqualifying; retrospective labels are not original trial IDs.
- `final-test-receipts.json`, `red-final.log`, `green-final.log`: final executable
  RED/GREEN checks with command exits and current source hashes.
- Earlier `red-*.log` / `green-*.log` are incremental development evidence, not
  independent historical qualification. Superseded local captures remain only
  in ignored `tmp/pre-final/` and are not part of the committed bundle.

Initial harness bootstrap failed because inherited `PYTHONPATH` pointed the
Python 3.12 venv at Python 3.14 extensions and nested TS tests could not resolve
`tsx` from the audit cwd. Those failures are retained as `.bootstrap-failed`
logs. Removing inherited Python paths and using a temporary audit-local
read-only dependency link fixed the environment without installs or changes to
other worktrees. No field values/tokens are included in this bundle; captures
use ephemeral values in memory/transient process environment and persist only
comparison booleans, refs, sessions, counters and attribution keys.
