# #4597 offline attribution characterization

**LIMITED / requirement decision outstanding.** This evidence-only packet reproduces an asymmetry between existing Python functions. It does not approve identity-policy changes, clear the nightly hold, propose a production patch, or prove a live release.

Tracking: https://github.com/kvnloo/cua/issues/151
Origin: https://github.com/trycua/cua/issues/4597

## Result
At tested source `22c99c02ff119344e746e19bf8ecc782dbd1f679`, both functions consume the same historical #4500 squash commit content (separately collected CommitRecord instances):
- Actual `nightly_attribution_preflight` returns the Dillon DuPont trailer unresolved.
- Actual `_change_contributors` accepts ddupont808 as internal coauthor, preserving wszkxlllll as external author and reporter. It uses unchanged recorded #4500 PR/commit responses and the actual linked #4477 reporter response.
- Characterization plus existing regressions: **7 passed**, exit 0. This includes the four original fail-closed controls: external merger, mismatched name, wrong linked account, and unlinked account.
- A separately named **proposed consistency expectation** produces **1 expected assertion failure**, exit 1. It is explicitly not an approved maintainer requirement.

Raw receipts/observations and stdout are under `logs/`. Each phase verified SHA-256 for 17 source/policy files and recorded every permitted git command. No unexpected guard denial occurred.

## Exact inputs and provenance
`source-manifest.json` gives Git blob SHA, SHA-256 and length for every frozen source copy under `source/`.
- `release_channels.py`: blob `38507dc86ec75af0339d729c305db0dded31d161`
- `release_attribution.py`: blob `dc7a1d5a51b08566ec23059472eb98cf09dfb675`
- Real git range: `1553a3f360ea12155be3bc77e27c427ca62f967a..c8edda06be53e13a759c69de125ce37189023954`. The original commit object is preserved in `metadata/git-commit-c8edda06.txt`.
- `metadata/4500.json`, `4500-commits.json`, and `4477.json` preserve exact fetched public API data inside retrieval-time/source-URL envelopes. The PR reports 5 commits; the commit-list response contains all 5. Three have GitHub author.login=ddupont808 and git author.name=Dillon Dupont. There is no standalone name/email guess or fabricated identity: the existing resolver combines normalized author name with merger, internal-handle and GitHub-linked-commit provenance.
- The PR's actual Fixes #4477 link remains intact. No body stripping or synthetic reporter response.
- Canned-client request allowlist: #4500 PR/commits and #4477 issue only. The executed positive call used commits and issue, since merged_by was already present on the PR object.
- Python 3.12.14 / Linux x86_64; pytest 9.1.1; jsonschema 4.26.0; PATH-selected Git 2.47.3 (the ordinary shell default was 2.52.0). Dependencies reused an existing environment, not a freshly verified install.

Source links:
- [preflight](https://github.com/trycua/cua/blob/22c99c02ff119344e746e19bf8ecc782dbd1f679/.github/scripts/release_channels.py#L429-L452)
- [raw scan](https://github.com/trycua/cua/blob/22c99c02ff119344e746e19bf8ecc782dbd1f679/.github/scripts/release_attribution.py#L498-L519)
- [accepted manifest fallback](https://github.com/trycua/cua/blob/22c99c02ff119344e746e19bf8ecc782dbd1f679/.github/scripts/release_attribution.py#L893-L980)

## Reproduce
Provide an already available, clean source checkout at the tested SHA with the stated historical commit range and the manifest-listed files. This packet's source copies are for audit; they do not contain a complete git object database. No missing component file or remote API fetch is part of execution.

Run `bash reproduce.sh /path/to/source /path/to/venv/bin/python /path/to/new-output`. The script creates fresh homes and writes both stdout logs, exit statuses, JSON observations and execution receipts. Expected codes are 0 and 1 respectively. All paths are caller-supplied or relative to the packet.

`run.py` selects the original positive, four original negative, and raw-scanner negative tests without changing them. `test_pair.py` adds only the descriptive paired characterization and separately labelled proposed assertion. No repository code is patched.

## Guard and coverage limits
The runner uses a minimal credential-free environment, disabled pytest third-party plugin autoload, disabled Git global/system configuration and lazy fetch, a Python socket/direct-process audit guard, and an exact local-git subprocess allowlist. Guard self-tests are recorded. **This is not OS-level network/PID isolation.** It does not provide a general hostile-code sandbox or filesystem-write confinement. The executed Python -I command ignores PYTHONDONTWRITEBYTECODE, so Python bytecode caches may be written; tracked source bytes remained unchanged.

Only real local Python functions and an original bounded git range run; GitHub is recorded data. No live HTTP request, native cua extension, guest, device, build, signing or release mutation is involved. No full `plan_nightly` integration, CLI/workflow execution, full manifest assembly, API-availability test, whole suite, native platform acceptance, or latest scheduled-run status is proved.

The qualification checkout lacks 19 component files required by the full registry-backed planner tests; none was fetched or fabricated. A prior named-workflow-run endpoint and separate encoded-tree read were rejected as unsupported; they remained stopped. Their absence does not become evidence that a current live run is held.

## Requirement and ownership boundaries
[PR #3411](https://github.com/trycua/cua/pull/3411) introduced fail-closed early holds. [PR #4566](https://github.com/trycua/cua/pull/4566) introduced the narrow internal-merger provenance rule for this exact trailer, without changing planner/config/workflow. The [nightly documentation](https://github.com/trycua/cua/blob/22c99c02ff119344e746e19bf8ecc782dbd1f679/.github/releases/README.md#L164-L174) describes early attribution checks and PR-first release notes. These establish existing behavior and historical impact; explicit approval to extend the provenance rule into preflight remains a maintainer decision.

Preserve ddupont808's resolver and original tests, f-trycua's planner, injaneity's open #5072/#5075 validation work, and the original #4500 contributor credit to wszkxlllll and Dillon DuPont. No ignore/override, identity reassignment, implementation takeover, claim on origin, or new fix PR is included.

Last pre-execution main refresh was `72ad36c4ee711df7e4c71be3747082ad052770ed`; the two intervening commits changed Spaces clients and a desktop gate workflow, not these frozen attribution scripts. Execution remains attributed solely to the tested SHA. Pre-publication refresh then observed origin 4337bcbd23394bca64b28cbcd4a0c5479cf316ad. Seven relevant source/config/policy blobs matched the tested source; head-refresh.json records that bounded comparison, with no execution on newer main. The original 125/30/0 inventory counts are unchanged.

## Independent review
See `independent-review.md` and `logs/independent-*/` for the separately executed verdict, provenance checks, and limits.

