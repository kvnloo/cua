# CUA #4562 independent CLI import-precedence evidence — 2026-10-12

Evidence-only owner: ayo, with OpenAI Codex. Production owner: c8dhjp4tyv-bit. Assigned reviewer: ddupont808. Canonical claim/work item: [kvnloo/cua#129](https://github.com/kvnloo/cua/issues/129). Origin metadata, conversation/submitted reviews and known downstream/factory claims were refreshed before claiming; no equivalent active evidence contribution was found. No production implementation was claimed.

Tested head `65b7ec52e774216fceb8b6afb146e60472a63069`; exact PR base `35751f65f121ccb93bf4434bb453b97b58ad4ca7`. Observed current main `d6174517b4a9f70f5626ed176a02340ff825f5d0` is source-only here, not executed. Publication SHA is distinct from all product SHAs.

| Independent execution | Head | Base |
| --- | --- | --- |
| Revision's own test_config_loader suite | 13 PASS | 6 PASS |
| Identical CLI-to-class probe | 1 FAIL / 2 controls PASS | 1 FAIL / 2 controls PASS |

The failing case is **inherited**, not a new regression introduced by #4562 and not RED-to-GREEN evidence. Preserve the owner's loader improvements and human credit. This probe adds coverage beyond the owner's configuration-layer tests; it does not establish that their focused tests failed.

## Reproduced behavior

Disposable project `.cua/config.yaml` selects `agent.name: first`; `.cua/agents.yaml` registers first with `selected_agent:RegisteredAgent`. The only explicit agent selector is `--agent-import-path selected_agent:CliAgent`.

The genuine path is `build_parser → _apply_config_defaults_for_task → agent_options → load_agent_class`, followed by constructing the selected inert class. Parsing and configuration application both retain `selected_agent:CliAgent`. `agent_options` replaces that explicit import with `selected_agent:RegisteredAgent`, and the genuine class loader loads RegisteredAgent; its constructed instance reports marker `registered`. The test first asserts the explicit parsed/configured import and non-oracle selection, then fails at the selected-class assertion.

Controls pass on both revisions: without a default selected agent, the explicit CLI import loads/constructs CliAgent; with the default only and no explicit import, it loads/constructs RegisteredAgent. The synthetic module is a real Python file containing two inert classes, not an import stub or fabricated result. No shipped function is extracted, replaced or monkeypatched.

## Requirement and source evidence

The loader's public method documents CLI arguments as the highest-priority source at [loader.py:133](https://github.com/trycua/cua/blob/65b7ec52e774216fceb8b6afb146e60472a63069/libs/cua-bench/cua_bench/config/loader.py#L133). The [benchmarks guide](https://github.com/trycua/cua/blob/65b7ec52e774216fceb8b6afb146e60472a63069/docs/content/docs/cua-bench/guides/benchmarks.mdx#L63) documents custom agents through `--agent-import-path module:Class`.

[run.py:379](https://github.com/trycua/cua/blob/65b7ec52e774216fceb8b6afb146e60472a63069/libs/cua-bench/cua_bench/cli/commands/run.py#L379) initializes from the CLI import but then unconditionally chooses the registered import when a default agent name exists. `_cmd_execute` applies config and builds these options before jobs. [episode.py:80](https://github.com/trycua/cua/blob/65b7ec52e774216fceb8b6afb146e60472a63069/libs/cua-bench/cua_bench/runner/episode.py#L80) loads the selected import, and its later episode path instantiates it. The latter routing is source evidence; no full episode/provider run occurred.

The CLI command file Git blob is `147f8944143a25e9799ae379ec32f4299b383197` on head, base and observed main, supporting the inherited distinction. Full snapshot/source hashes and installed dependency versions are in `environment-source-hashes.json`.

## Reproduction and limits

`commands.txt` contains the exact four test invocations, interpreter/import preflight and root mappings. Reused official PyPI wheels: Python3.12.14, PyYAML6.0.3, pytest9.1.1, pytest-asyncio1.4.0. Genuine cua-bench imports through worktree PYTHONPATH. No new packages, package/helper extraction, SDK compilation or frozen uv synchronization. Passing imports/tests do not certify installed snapshot metadata or the full owner-reported suite.

Every probe case sets disposable HOME and CUA_HOME, writes project YAML beneath HOME, and exposes a temporary inert module through pytest's path fixture. No real user config, provider, VM, desktop or paid calls. The genuine parser/helpers/loader run in pytest; this is not an invocation of the complete cb executable or `_cmd_execute`, a full task episode, or a live registered-agent performance test. The inert constructor observes class selection only and need not implement the production agent protocol.

Raw logs preserve assertions, source excerpts, exact test IDs/results and timings. Machine roots map to HEAD_WORKTREE, BASE_WORKTREE, RESULTS_ROOT and ENV_ROOT; volatile object addresses are redacted. No environments, caches, private generated task state or credentials are included. The manifest hashes all payload files except itself.

Independent xhigh critic scope and verdict are in `critic-receipt.txt`. No competing fix, upstream comment/PR, main/force push, destructive cleanup, human signoff or change to unrelated denied/cancelled work. Owner/reviewer acceptance and hosted CI remain separate gates. Existing #4930 receipts remain unchanged.
