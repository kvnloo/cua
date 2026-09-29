"""Execute the registered verifier/consumer tests without changing their sources."""

import os
from pathlib import Path
import subprocess
from prepare import HERE, EXAMPLE, PYTHON, PIN, dump, sha

NODE = Path("/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin/node")
DONOR = Path("/mnt/zer0models/github/cua-lanes/c4316/libs/cua-driver/examples/jev-use")


def main():
    (HERE / "tmp").mkdir(exist_ok=True)
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(HERE / "tmp"),
        "TSX_DISABLE_CACHE": "1",
        "PATH": str(NODE.parent) + os.pathsep + os.environ["PATH"],
    }
    for key in ("TYPESAFE_API_KEY", "PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    # Child TS tests use --import tsx; resolve it without installing or writing
    # into the retained worktree. The audit-local link is removed after the run.
    (HERE / "node_modules").symlink_to(DONOR / "node_modules", target_is_directory=True)
    for p in (EXAMPLE / "typescript").glob("*.ts"):
        assert sha(p) == sha(DONOR / "typescript" / p.name), p.name
    assert sha(EXAMPLE / "package-lock.json") == sha(DONOR / "package-lock.json")
    jobs = [
        (
            "verifier-focused",
            [
                str(PYTHON),
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                str(EXAMPLE / "python/tests"),
                "-p",
                "test_verify_setup.py",
                "-v",
            ],
        ),
        (
            "python-consumer",
            [
                str(PYTHON),
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                str(EXAMPLE / "python/tests"),
                "-p",
                "test_guarded_runner.py",
                "-v",
            ],
        ),
        (
            "typescript-consumer",
            [
                str(NODE),
                "--import",
                str(DONOR / "node_modules/tsx/dist/loader.mjs"),
                "--test",
                str(DONOR / "typescript/run_guarded_completion.test.ts"),
            ],
        ),
    ]
    results = []
    for name, cmd in jobs:
        result = subprocess.run(cmd, cwd=HERE, env=env, capture_output=True, text=True, timeout=180)
        (HERE / (name + ".log")).write_text(result.stdout + result.stderr)
        results.append(
            {
                "name": name,
                "exact_head": PIN,
                "command": cmd,
                "cwd": str(HERE),
                "environment_overrides": {
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "TMPDIR": str(HERE / "tmp"),
                    "TSX_DISABLE_CACHE": "1",
                    "TYPESAFE_API_KEY": "removed",
                },
                "exit_code": result.returncode,
                "log": name + ".log",
                "sha256": sha(HERE / (name + ".log")),
            }
        )
        print(name, result.returncode, (result.stdout + result.stderr)[-500:])
    dump(HERE / "retained-tests.json", results)
    assert all(r["exit_code"] == 0 for r in results)


if __name__ == "__main__":
    try:
        main()
    finally:
        if (HERE / "node_modules").is_symlink():
            (HERE / "node_modules").unlink()
