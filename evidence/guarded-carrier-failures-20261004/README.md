# Current carrier failed checks: 2026-10-04

All rows report head `b2ae7cb934403f2585c7d3ed23a188b44264f293`. Direct job log downloads returned Forbidden; failed-step metadata and annotations remain available. Failure does not by itself identify root cause.

| Job | Failed step | Cause status |
| --- | --- | --- |
| [Docs image refs have passing doctor reports](https://github.com/kvnloo/cua/actions/runs/37159068542/job/111308485028) | Every image ref passed the doctor (baseline shrinks only) | Annotation confirms missing image-doctor-ledger branch. Exact ref(s) outside baseline unknown without job log. |
| [Image doctor (overlaid cua-spacesd and cua-driver)](https://github.com/kvnloo/cua/actions/runs/37159068295/job/111308483730) | Run ./.github/actions/cua-sandbox | Unknown: annotations report process exit only; exact job stderr unavailable. |
| [Catalog images on the current cua-spacesd (warning only)](https://github.com/kvnloo/cua/actions/runs/37159068555/job/111308484971) | Does this PR release cua-spacesd itself? | Base VERSION absence confirmed via API and reproduced locally (exit128); exact hosted stderr unavailable. Candidate019c26f fixes this missing-file case. |
| [signed 0.28.2 passes / Windows Authenticode (0.28.2, expect pass)](https://github.com/kvnloo/cua/actions/runs/37159068647/job/111308485884) | Download published Windows archives | Unknown: annotations report process exit only; exact job stderr unavailable. |
| [installer smoke (Linux containers) (debian:12)](https://github.com/kvnloo/cua/actions/runs/37159068481/job/111308484433) | install.sh --yes --no-onboarding against a served release dir | Unknown: annotations report process exit only; exact job stderr unavailable. |
| [Portable contract parity (ubuntu-latest)](https://github.com/kvnloo/cua/actions/runs/37159069425/job/111308487547) | Prove portable contracts match the live registry | Unknown: annotations report process exit only; exact job stderr unavailable. |
| [installer smoke (Linux containers) (ubuntu:24.04)](https://github.com/kvnloo/cua/actions/runs/37159068481/job/111308484495) | install.sh --yes --no-onboarding against a served release dir | Unknown: annotations report process exit only; exact job stderr unavailable. |
| [installer smoke (Linux containers) (alpine:3)](https://github.com/kvnloo/cua/actions/runs/37159068481/job/111308484478) | install.sh --yes --no-onboarding against a served release dir | Unknown: annotations report process exit only; exact job stderr unavailable. |
| [Reference / cua-cli / linux](https://github.com/kvnloo/cua/actions/runs/37159068246/job/111320078935) | Check generated reference | Unknown: annotations report process exit only; exact job stderr unavailable. |
| [Reference / cua-sdk / linux](https://github.com/kvnloo/cua/actions/runs/37159068246/job/111320079006) | Check generated reference | Unknown: annotations report process exit only; exact job stderr unavailable. |
| [Reference / cua-proto / linux](https://github.com/kvnloo/cua/actions/runs/37159068246/job/111320079029) | Check generated reference | Unknown: annotations report process exit only; exact job stderr unavailable. |
| [Check Documentation Sync](https://github.com/kvnloo/cua/actions/runs/37159068246/job/111336146122) | Require routing and every selected check to pass | Aggregate selected-check gate failed after three reference failures; no separate generator root cause established. |
| [validate](https://github.com/kvnloo/cua/actions/runs/37159068582/job/111335844883) | Validate squash-release title | Current exact-head release-title script rejects the PR ci title when release is required; reproduced locally. No owner title change made. |

Independent repair: `019c26f65e0e59f8a8661321d63c5fb1fb105000` on upstream `0335d5a5e0fd197522365fef3487a279be94ad4f`; exact committed code: 26 tests pass, whitespace clean. H4 independent review approved. Hosted candidate CI NOT_RUN. The code preserves #4574 author ancestry and changes no active guarded/outcome/motion implementation.

#87 targets base `2ca90d33857fdb4813ecc8d12c2058be7d4ebcc4`; GitHub comparison is 186 commits ahead, 0 behind and PR reports 5,511 changed files. Owner must choose intended comparison/title. No PR was edited. #111 reconciliation remains with its existing owner.

No live registry, desktop, provider, installer, container, merge, deployment or CI rerun was executed. Cargo is unavailable locally; no dependency was installed.
