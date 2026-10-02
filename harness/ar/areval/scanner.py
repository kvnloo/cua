"""Diff scanner for gate G0 (pure: unified diff text + rule file -> hits)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "scanner_rules.json"


def load_rules(path: Path = RULES_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_diff(diff: str) -> dict[str, dict[str, list[str]]]:
    """Unified diff -> {path: {"added": [...], "removed": [...]}} (b/ path; a/ for deletions)."""
    files: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] | None = None
    old_path = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            current = None
            old_path = None
            continue
        if line.startswith("--- "):
            old_path = line[4:].removeprefix("a/")
            continue
        if line.startswith("+++ "):
            new_path = line[4:].removeprefix("b/")
            path = old_path if new_path == "/dev/null" else new_path
            current = files.setdefault(path or new_path, {"added": [], "removed": []})
            continue
        if current is None or line.startswith("@@"):
            continue
        if line.startswith("+"):
            current["added"].append(line[1:])
        elif line.startswith("-"):
            current["removed"].append(line[1:])
    return files


def scan(diff: str, rules: dict[str, Any]) -> list[dict[str, Any]]:
    hits = []
    for path, lines in parse_diff(diff).items():
        for rule in rules["rules"]:
            rx = re.compile(rule["pattern"])
            added = [x for x in lines["added"] if rx.search(x)]
            removed = [x for x in lines["removed"] if rx.search(x)]
            net = len(added) - len(removed) if rule["side"] == "added" else len(removed) - len(added)
            if net > 0:
                sample = added if rule["side"] == "added" else removed
                hits.append({"rule": rule["id"], "file": path, "net": net,
                             "sample": [s.strip()[:160] for s in sample[:3]]})
    return hits
