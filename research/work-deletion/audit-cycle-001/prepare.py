"""Read-only source inventory; create new audit evidence only in this directory."""

from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXAMPLE = ROOT / "libs/cua-driver/examples/jev-use"
EVIDENCE = Path("/mnt/zer0models/github/cua-lanes/evidence/4316-maintainer-proof-review")
PIN = "c78f50efed1ee7b289ab8947ec997904ea18fd72"
PYTHON = Path(
    "/mnt/zer0models/github/cua-lanes/c4316/libs/cua-driver/examples/jev-use/.venv/bin/python"
)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args):
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}, text=True
    ).strip()


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def main():
    if (HERE / "source-inventory.json").exists():
        raise SystemExit("Refusing to replace the initial preservation snapshot")
    assert git("rev-parse", "HEAD") == PIN
    assert git("branch", "--show-current") == "research/guarded-receipt-audit-20260929"
    sources = [
        p
        for p in EXAMPLE.rglob("*")
        if p.is_file() and not any(x in p.parts for x in ["node_modules", ".venv", "__pycache__"])
    ]
    snapshot = {
        "base_head": PIN,
        "branch": git("branch", "--show-current"),
        "source_rust_tree": git("rev-parse", f"{PIN}:libs/cua-driver/rust"),
        "source_example_tree": git("rev-parse", f"{PIN}:libs/cua-driver/examples/jev-use"),
        "retained_evidence_root": str(EVIDENCE),
        "retained_files": {
            str(p.relative_to(EVIDENCE)): {"sha256": sha(p), "size": p.stat().st_size}
            for p in sorted(EVIDENCE.rglob("*"))
            if p.is_file()
        },
        "example_files": {str(p.relative_to(ROOT)): sha(p) for p in sorted(sources)},
        "python": str(PYTHON),
        "python_executable_sha256": sha(PYTHON.resolve()),
        "python_version": subprocess.check_output([str(PYTHON), "--version"], text=True).strip(),
    }
    dump(HERE / "source-inventory.json", snapshot)
    paths = [
        "python/tests/test_verify_setup.py",
        "python/tests/test_guarded_completion.py",
        "python/tests/test_guarded_runner.py",
        "typescript/guarded_completion.test.ts",
        "typescript/run_guarded_completion.test.ts",
    ]
    registry = []
    for rel in paths:
        path = EXAMPLE / rel
        text = path.read_text()
        if path.suffix == ".py":
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.ClassDef):
                    for method in node.body:
                        if isinstance(method, ast.FunctionDef) and method.name.startswith("test_"):
                            registry.append(
                                {
                                    "id": f"{path.stem}.{node.name}.{method.name}",
                                    "source": str(path.relative_to(ROOT)),
                                    "line": method.lineno,
                                    "end_line": method.end_lineno,
                                    "source_sha256": sha(path),
                                    "tier": "verifier"
                                    if "verify_setup" in rel
                                    else "consumer"
                                    if "runner" in rel
                                    else "guard-unit",
                                    "registration": "existing; not reimplemented",
                                }
                            )
        else:
            for i, line in enumerate(text.splitlines(), 1):
                match = re.search(r"\btest\((.+)", line)
                if match:
                    registry.append(
                        {
                            "id": f"{rel}:{i}",
                            "declaration": match.group(1),
                            "source": str(path.relative_to(ROOT)),
                            "line": i,
                            "source_sha256": sha(path),
                            "tier": "consumer" if "run_guarded" in rel else "guard-unit",
                            "registration": "existing template; runtime count may expand",
                        }
                    )
    dump(
        HERE / "existing-controls.json",
        {
            "pin": PIN,
            "controls": registry,
            "scope_note": "Register existing controls before new corrupt-evidence cases. Source registration is not fresh execution. Verifier/consumer runtime results live in retained-tests.json. Guard logic is not the audit subject.",
            "explicit_verifier_negatives": [
                "wrong independent submission despite verified event",
                "missing verified outcome",
                "nonzero child exit",
                "wrong accepted route",
                "missing proof",
                "equal prior/fresh ref",
                "nonnull confidence",
                "nonnull probabilities",
                "missing declined proof",
                "wrong decline reason",
                "wrong declined route",
                "missing decline oracle submission",
                "wrong visual path/status",
                "visual fallback unexpected submission",
            ],
        },
    )
    print(
        json.dumps(
            {
                "preserved_files": len(snapshot["retained_files"]),
                "registered_controls": len(registry),
            }
        )
    )


if __name__ == "__main__":
    main()
