# Cua Agent

> [!WARNING]
> **Deprecated:** `cua-agent` is no longer maintained by Cua and will not receive updates or fixes. For desktop control, connect your coding agent to [Cua Driver](https://cua.ai/docs/cua-driver/guides/connect-your-agent) over MCP. For sandboxes, use the [`cua` SDK and CLI](https://cua.ai/docs/cua-sdk/quickstart) (`pip install cua`) and [run a coding agent in a sandbox](https://cua.ai/docs/cua-sdk/guides/run-a-coding-agent). See [Migrate from deprecated packages](https://cua.ai/docs/cua-sdk/guides/cua-cloud-ended#deprecated-packages). Existing releases stay on PyPI, so current installs keep working.

Computer-Use framework with liteLLM integration for running agentic workflows on macOS, Windows, and Linux sandboxes.

**[Documentation](https://cua.ai/docs/cua/reference/agent-sdk)** - Installation, guides, and configuration.

> [!WARNING]
> **Removed:** the `omni` extra (`cua-agent[omni]`) is gone. It pulled in `cua-som`, which is deprecated, no longer maintained and licensed under AGPL-3.0. The omniparser loop still works if you install `cua-som` yourself (`pip install cua-som`); it will not receive updates or fixes.

## Downstream HobbyLM experiment

This fork includes a [HobbyLM-1B experiment](examples/hobbylm_eval/README.md).
The `hobbylm/local` loop uses semantic text state and ten allowlisted actions.
It does not consume screenshots or predict arbitrary desktop interactions.
The experiment includes a pinned offline runtime, Linux sandbox tasks, matched
small-model and subscription controls, independent state checks, and run traces.
This does not change the package's upstream deprecation status.
