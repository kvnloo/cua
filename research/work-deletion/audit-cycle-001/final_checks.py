"""Record reproducible final RED/GREEN and read-only lint checks."""

from __future__ import annotations
import json
import os
import subprocess
import sys
from prepare import HERE, ROOT, PIN, dump, sha


def main():
    scripts = sorted(str(p) for p in HERE.glob("*.py"))
    jobs = [
        (
            "red-final",
            [
                sys.executable,
                "-B",
                str(HERE / "test_auditor.py"),
                "AuditorTests.test_success_with_unobserved_fresh_ref_is_nonqualifying",
            ],
            1,
            {"AUDIT_CHECKER": "retained"},
        ),
        ("green-final", [sys.executable, "-B", str(HERE / "test_auditor.py")], 0, {}),
        (
            "lint-final",
            ["ruff", "check", "--no-fix", "--no-cache", "--select", "E4,E7,E9,F", *scripts],
            0,
            {},
        ),
        ("format-final", ["ruff", "format", "--no-cache", "--check", *scripts], 0, {}),
    ]
    receipts = []
    for name, command, expected, extra in jobs:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("AUDIT_CHECKER", "PYTHONPATH", "PYTHONHOME")
        }
        env.update(extra)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=60
        )
        log = HERE / (name + ".log")
        log.write_text(result.stdout + result.stderr)
        assert result.returncode == expected, (name, result.returncode, result.stderr)
        if name == "red-final":
            assert "AssertionError: True is not false" in result.stderr
        receipts.append(
            {
                "name": name,
                "command": command,
                "cwd": str(ROOT),
                "environment_overrides": extra,
                "expected_exit": expected,
                "actual_exit": result.returncode,
                "log": log.name,
                "log_sha256": sha(log),
                "exact_retained_pin": PIN,
                "auditor_sha256": sha(HERE / "auditor.py"),
                "test_sha256": sha(HERE / "test_auditor.py"),
            }
        )
    dump(HERE / "final-test-receipts.json", receipts)
    print(
        json.dumps(
            {"checks": len(receipts), "expected_red_observed": True, "green_and_lints_passed": True}
        )
    )


if __name__ == "__main__":
    main()
