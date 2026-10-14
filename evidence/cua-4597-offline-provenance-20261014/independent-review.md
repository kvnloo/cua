Public copy: local absolute paths replaced with relative packet paths only. Original review SHA-256: ea2efa732f883c5abe7e2d13de0f29c383527762a505ae55956ca857f04d53a3

# Independent bounded offline attribution review

## Verdict

The packet reliably reproduces a narrow behavioral divergence at source commit `22c99c02ff119344e746e19bf8ecc782dbd1f679`. It is suitable as characterization and as a separately labelled proposed consistency test. It does not establish a maintainer-approved parity requirement, an approved admission/identity policy change, or a presently held nightly.

- Characterization rerun: **7 passed**, exit **0**, in 0.11 seconds.
- Separate proposed-parity rerun: **1 failed**, exit **1**, in 0.05 seconds, precisely at the proposed expectation that preflight returns no unresolved identities.
- The observations, run receipts, and exit status files in both phases are byte-identical to the original packet. Stdout differs in timing and traceback-relative paths only; preserve the independent logs as their own artifacts.

## What was actually exercised

The actual `nightly_attribution_preflight` reads checked-in attribution config and calls the actual `commits_in_range` over `1553a3f360ea12155be3bc77e27c427ca62f967a..c8edda06be53e13a759c69de125ce37189023954`. The historical parent relationship was independently verified. Paths, exclusions, and companion exclusions come from the pinned source's registry.

The fixture then reads the same range again and supplies that real historical commit record to the actual `_change_contributors` with the unchanged `data` objects from three recorded API responses. These are equal historical commit contents, not a shared Python object instance between preflight and contributor resolution.

Observed result:

- Preflight reports Dillon DuPont's historical coauthor trailer unresolved.
- Contributor resolution accepts `ddupont808` as an internal coauthor through the existing merging-maintainer provenance rule.
- `wszkxlllll` is retained as both external PR author and external issue reporter.
- PR #4500's real `Fixes #4477` link is preserved. The recorded issue #4477 object is read, rather than stripping the link or inventing a reporter.
- Recorded client calls are exactly PR #4500 commits and issue #4477. No HTTP client is used in these calls.

The seven characterization cases consist of the real paired characterization, the existing checked-in-config resolver positive case, four existing fail-closed provenance cases, and the existing unresolved-coauthor helper case. The negative cases reject an external merger, mismatching author name, a name linked to another account, and an unlinked author. This is useful focused coverage, not a complete test-owner or workflow run.

## Source and input provenance

All **17** manifest files independently matched their SHA-256 hashes, declared byte sizes, computed Git blob hashes, and blob entries in the pinned HEAD tree. The source is detached and tracked-clean after the runs. No production source edit was made.

Recorded metadata identifies these capture times:

- PR #4500: `2026-10-14T12:47:52.633Z`
- PR #4500 commits: `2026-10-14T12:47:55.311Z`
- Issue #4477: `2026-10-14T12:54:07.460Z`

The recorded PR identifies the tested squash commit, five source commits, and `ddupont808` as merger. Three recorded commits link GitHub author `ddupont808` to case-normalized name `Dillon Dupont`, satisfying the existing resolver seam. Full input hashes and relevant metadata are in `independent-verification.json`. The independent reviewer did not re-fetch GitHub; hashes establish consistency with the supplied snapshots, not independent live-service authentication or freshness.

SHA-256:

- `run.py`: `137297e571626af2710272a8a6b1a30108fea955ab969d98ad32192a3fbdcbe1`
- `test_pair.py`: `6e15285c7de7ff8a33c8d720427b10180ced5f30b2afb27a9990d0e605469d85`
- `source-manifest.json`: `53efa28b78931921cfc8cc1cfa15046a0c2ca244eda11e7bc43e3bfd3a7780cd`
- `metadata/4477.json`: `4053e07b905f53bb5f23338a2e37f730f3a7aba64b7e50136d8b8ea6c85d5b3a`
- `metadata/4500.json`: `3e3a0f9df2594d9004a9b16910d267aa8fa84e2eae7acc38dd68d2c09b44f425`
- `metadata/4500-commits.json`: `b2f412ace7b30857ba66f1b7b05a1e9c8d921655dcc6475fdb55da5b06f6c020`
- `independent-verification.json`: `b7488bc566f695328bf62910fcea11a348349ca13388157de84387020f3cdfef`

## Guard assessment and limits

Both requested phase commands used fresh HOME directories and the specified minimal environment, Python `-I`, plugin autoload disabled, global/system Git configuration suppressed, lazy fetching disabled, and optional Git locks disabled. Each receipt lists the seven permitted local Git calls and two expected guard self-test denials. There were **zero unexpected guard denials**.

The guard is a Python audit hook and monkeypatched process allowlist. It is not an OS network namespace, filesystem confinement, or a proof against deliberately hostile native code. No network execution was performed by this review.

Minor reproducibility/hardening caveat: Python `-I` ignores `PYTHONDONTWRITEBYTECODE`. Independently checked `sys.dont_write_bytecode` is therefore `False` with the requested command. Import caches may be written even though tracked source remains unchanged. If a strict no-bytecode-write guarantee is intended, add `-B` in a future authorized runner revision; no runner was edited here.

Exactly **19 registry-required files** remain absent, listed in `missing-registry-files.json`. No attempt was made to materialize them. Therefore this is not a full registry validation, `plan_nightly` execution, release manifest build, current release-range check, GitHub Actions reproduction, or native/desktop workflow proof. Source inspection shows preflight output is one input to the planner's held-attribution decision, but this replay does not establish the actual present planner inputs or outcome.

No policy change or fix is proposed here. Existing resolver, planner, and adjacent issue ownership are preserved. No public write, claim, origin operation, dependency install, stopped endpoint retry, or alternate route was attempted.

## Independent artifacts

Directory: `logs/independent-*`

- `characterize/stdout.log`, `run-receipt.json`, `observation.json`, `exit-status.txt`
- `proposed-parity/stdout.log`, `run-receipt.json`, `observation.json`, `exit-status.txt`
- `independent-verification.json`
- `missing-registry-files.json`

Runtime: Python 3.12.14, pytest 9.1.1, Git 2.47.3.

## Portable publication draft review

Reviewed `README.md` and `reproduce.sh` in `.` at 13:00 UTC. Verified the portable `run.py` and `test_pair.py` are byte-identical to the executed originals. `bash -n reproduce.sh` passed; the wrapper itself was not executed. The LIMITED / evidence task complete / requirement decision outstanding classification is appropriate.

Corrections recommended before packaging:

1. README reports Git 2.52.0. The requested minimal PATH used Git **2.47.3** in this independent run. Report the actual execution-path version or distinguish it from a shell-default Git version.
2. The wrapper says it creates fresh homes, but `mkdir -p` reuses an existing output/home and overwrites logs. Require a new output directory or create genuinely fresh homes.
3. As already noted, `-I` ignores `PYTHONDONTWRITEBYTECODE`. Add `-B` if no import-cache writes are intended, and distinguish the amended command from these original rerun receipts.
4. Prefer “same historical squash commit content” to avoid implying the exact same Python object instance. The two actual Git scans yield equivalent record values.
5. Prefer “no standalone name/email guess” to the broader claim that no identity was inferred from name/email: the checked-in resolver explicitly uses a normalized author-name match in conjunction with merged-by, internal-handle, and GitHub-linked-commit provenance.

README references independent artifacts that were not yet present when inspected; include them before delivery. Historical ownership, live/main-refresh context, and claim receipt were supplied by the parent and not independently re-fetched during this offline review.

## Packaging response

Producer corrected the PATH-selected Git version, rejected pre-existing output directories, and clarified equivalent commit contents and provenance-based name matching. The bytecode caveat is disclosed; no strict no-cache or filesystem-confinement claim is made. Independent artifacts are included. These editorial/wrapper changes do not modify run.py, test_pair.py, source or recorded inputs.
