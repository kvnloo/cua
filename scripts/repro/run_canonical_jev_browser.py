#!/usr/bin/env python3
"""Fork-only executor for the pinned canonical Jev Linux browser/MCP recipe.

The six production recipe bodies are read verbatim from the candidate checkout.
This wrapper records provenance and failure stages; it adds no browser simulator,
retry, relaxed assertion, or live-provider call. Use only on a disposable hosted
runner: the canonical bootstrap installs desktop packages and uses its existing
explicit test-only permission/browser-sandbox settings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import yaml

CANONICAL_PATH = ".github/workflows/ci-jev-use.yml"
CANONICAL_BLOB = "7ea76b00fc0ffdb5141062e594af12709a40f49c"
STAGES = (
    "Install Linux desktop dependencies",
    "Build the exact candidate Driver",
    "Install locked example dependencies",
    "Record candidate and verify advertised tools",
    "Run both mock agents through MCP on X11",
    "Audit redacted E2E evidence",
)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def recipe(root: Path) -> tuple[dict, list[dict]]:
    raw = (root / CANONICAL_PATH).read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != CANONICAL_BLOB:
        raise RuntimeError(f"Canonical workflow differs: {actual}")
    workflow = yaml.safe_load(raw)
    job = workflow["jobs"]["mock-e2e-linux"]
    steps = [step for step in job["steps"] if "run" in step]
    if tuple(step["name"] for step in steps) != STAGES:
        raise RuntimeError("Canonical stage list changed")
    return workflow, steps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.candidate_dir.resolve(), args.evidence_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {
        "candidate_sha": args.expected_sha,
        "workflow_sha": args.workflow_sha,
        "canonical_recipe_blob": CANONICAL_BLOB,
        "controller_sha256": digest(Path(__file__)),
        "stages": [],
        "complete": False,
        "scope": "Canonical Linux X11 browser/MCP deterministic-provider integration; not live Jev or full desktop certification",
        "live_provider_requested": False,
    }
    exit_code = 1
    try:
        if git(root, "rev-parse", "HEAD") != args.expected_sha:
            raise RuntimeError("Candidate checkout does not match requested SHA")
        if git(root, "status", "--porcelain"):
            raise RuntimeError("Candidate checkout is not clean")
        workflow, steps = recipe(root)
        job = workflow["jobs"]["mock-e2e-linux"]
        env = dict(os.environ)
        for key, value in job["env"].items():
            env[key] = str(value).replace("${{ github.workspace }}", str(root))
        env.update(TYPESAFE_API_KEY="", JEV_API_KEY="", PYTHONUNBUFFERED="1")
        env.pop("JEV_BACKEND", None)
        if "RUNNER_TEMP" not in env:
            raise RuntimeError("A disposable GitHub-hosted runner is required")
        result["recipe_run_bodies_sha256"] = {
            step["name"]: hashlib.sha256(step["run"].encode()).hexdigest() for step in steps
        }
        default_dir = workflow["defaults"]["run"]["working-directory"]
        for index, step in enumerate(steps, 1):
            script = out / f"stage-{index:02d}.sh"
            script.write_text(step["run"])
            directory = step.get("working-directory", default_dir)
            directory = directory.replace("${{ github.workspace }}", str(root))
            cwd = Path(directory)
            if not cwd.is_absolute():
                cwd = root / cwd
            if not cwd.is_relative_to(root):
                raise RuntimeError("Recipe working directory escapes candidate")
            entry = {"name": step["name"], "status": "running"}
            result["stages"].append(entry)
            (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(f"::group::{step['name']}", flush=True)
            start = time.monotonic()
            with (out / f"stage-{index:02d}.log").open("w") as log:
                # Same bash -e execution policy as an unspecified Linux run shell.
                with subprocess.Popen(
                    ["bash", "-e", str(script)], cwd=cwd, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                ) as child:
                    assert child.stdout is not None
                    for line in child.stdout:
                        log.write(line)
                        print(line, end="", flush=True)
                    code = child.wait()
            entry.update(status="passed" if code == 0 else "failed", exit_code=code,
                         elapsed_seconds=round(time.monotonic() - start, 3))
            print("::endgroup::", flush=True)
            if code:
                break
        unchanged = not git(root, "diff", "HEAD", "--")
        result["tracked_candidate_source_unchanged"] = unchanged
        result["complete"] = (len(result["stages"]) == len(STAGES)
                              and all(s["status"] == "passed" for s in result["stages"])
                              and unchanged)
        binary = Path(env["CUA_DRIVER_BIN"])
        if binary.is_file():
            result["driver_binary_sha256"] = digest(binary)
        proof = Path(env["RUNNER_TEMP"]) / "jev-use-mock-proof"
        if proof.is_dir():
            dest = out / "mock-proof"
            dest.mkdir()
            for name in ("summary.json", "python-mock.jsonl", "typescript-mock.jsonl"):
                if (proof / name).is_file():
                    shutil.copyfile(proof / name, dest / name)
        exit_code = 0 if result["complete"] else 1
    except Exception as error:
        result["controller_error"] = f"{type(error).__name__}: {error}"
        print(result["controller_error"], file=sys.stderr)
    finally:
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        inventory = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
        (out / "SHA256SUMS").write_text("".join(f"{digest(p)}  {p.relative_to(out)}\n" for p in inventory))
        print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
