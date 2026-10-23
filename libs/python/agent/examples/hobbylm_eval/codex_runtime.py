"""Existing ChatGPT subscription control via Codex CLI, never an API key.

Native agent/tool discovery is disabled. The matched semantic action prompt is
passed as developer instructions. Latency includes CLI startup and the network.
No local model-only latency or seeded decoding is claimed for this control.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


class CodexRuntime:
    def __init__(self, max_calls: int, *, executable: str = "codex", timeout: int = 90):
        if type(max_calls) is not int or max_calls < 1:
            raise ValueError("A positive fixed call cap is required")
        self.max_calls = max_calls
        self.calls = 0
        self.executable = executable
        self.timeout = timeout
        self.directory = Path("/workspace/cache/hobbylm-cua/codex-empty")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.identity = {"provider": "existing ChatGPT login via codex exec", "model": "gpt-6.1-sol",
                         "timing_regime": "CLI startup plus network and generation",
                         "seeded_decoding": False, "model_only_seconds": None}

    def complete(self, system: str, user: str, max_new: int = 64) -> dict:
        if self.calls >= self.max_calls:
            raise RuntimeError("Subscription baseline call cap reached")
        if not isinstance(system, str) or not isinstance(user, str):
            raise TypeError("system and user must be strings")
        self.calls += 1
        argv = [self.executable, "--no-daemon", "-a", "never", "exec",
                "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--ephemeral",
                "--sandbox", "read-only", "--model", "gpt-6.1-sol", "--json", "--color", "never",
                "--cd", str(self.directory), "-c", "web_search=\"disabled\"",
                "-c", "model_reasoning_effort=\"low\"",
                "-c", "developer_instructions=" + json.dumps(system)]
        for feature in ("shell_tool", "unified_exec", "multi_agent", "apps", "browser_use",
                        "browser_use_external", "computer_use", "view_image", "image_generation",
                        "tool_suggest", "sleep_tool", "skill_search", "code_mode_host", "plugins",
                        "hooks", "memories", "workspace_dependencies"):
            argv.extend(["--disable", feature])
        argv.extend(["--enable", "skip_host_skill_discovery",
                     "-c", "suppress_unstable_features_warning=true", "-"])
        environment = os.environ.copy()
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "SWAYSOCK", "HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_SOCKET"):
            environment.pop(key, None)
        started = time.perf_counter()
        result = subprocess.run(argv, input=user, text=True, capture_output=True,
                                timeout=self.timeout, check=False, env=environment)
        seconds = time.perf_counter() - started
        if result.returncode:
            # Provider diagnostics can contain account metadata. Do not persist
            # or expose raw stderr. The exit code remains reproducible evidence.
            raise RuntimeError(f"Codex subscription control exited {result.returncode}")
        messages = []
        usage = {}
        allowed = {"agent_message", "reasoning"}
        for line in result.stdout.splitlines():
            event = json.loads(line)
            if event.get("type") == "error":
                raise RuntimeError("Codex subscription control returned a provider error")
            if event.get("type") in {"item.started", "item.updated", "item.completed"}:
                item = event.get("item", {})
                if item.get("type") not in allowed:
                    raise RuntimeError("Subscription control attempted a forbidden tool or non-text item")
                if event["type"] == "item.completed" and item.get("type") == "agent_message":
                    messages.append(item.get("text", ""))
            if event.get("type") == "turn.completed":
                usage = event.get("usage", {})
            if event.get("type") == "turn.failed":
                raise RuntimeError("Codex subscription control failed its turn")
        if len(messages) != 1 or not messages[0].strip() or len(messages[0]) > 1024:
            raise RuntimeError("Subscription control must return exactly one bounded action")
        return {"raw": messages[0].strip(), "seconds": seconds,
                "prompt_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "model_only_seconds": None, "tools_used": False,
                "timing_regime": "codex_cli_startup_plus_network",
                "max_new_caveat": "Codex exec does not expose an equivalent output-token cap",
                "seed_caveat": "Subscription provider does not expose seeded decoding"}

    def close(self):
        pass
