#!/usr/bin/env python3
"""Run the two matched local arms and retain exact controller wall times."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    python = "/workspace/cache/hobbylm-cua/venv-harness/bin/python"
    model_python = "/workspace/cache/hobbylm-cua/venv/bin/python"
    models = Path("/workspace/cache/hobbylm-cua/models")
    environment = os.environ.copy()
    environment.update(CUA_TELEMETRY="0", CUA_TELEMETRY_ENABLED="false",
                       HOBBY_SOURCE_SHA=args.source_sha,
                       HOBBYLM_EVAL_TOKEN="hobbylm-owned-local-eval")
    receipts = []
    for name, runtime in (("hobbylm", "hobbylm"), ("qwen", "small-local")):
        output = args.output / name
        command = [python, str(here / "harness.py"), "--endpoint", "http://127.0.0.1:13211",
                   "--ownership-id", "HobbyCuaEval", "--runtime", runtime,
                   "--output", str(output)]
        command += ["--device", "cuda", "--runtime-python", model_python,
                    "--base", str(models / "hobbylm-1B-instruct"),
                    "--adapter", str(models / "hobbylm-1B-computer-use")]
        if runtime == "small-local":
            command += ["--model", str(models / "Qwen2.5-0.5B-Instruct")]
        command = [python, str(here / "bounded-gpu.py"), "--", *command]
        reference = args.output / "hobbylm" / "summary.json"
        if name != "hobbylm" and reference.exists():
            command += ["--compare-to", str(reference)]
        started = time.monotonic()
        with (args.output / f"{name}.console.log").open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       env=environment, start_new_session=True)
            timed_out = False
            while True:
                try:
                    code = process.wait(timeout=60)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.monotonic() - started
                    print(json.dumps({"arm": name, "elapsed_seconds": elapsed}), flush=True)
                    if elapsed >= 1800:
                        timed_out = True
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
                        code = 124
                        break
        receipt = {"arm": name, "exit_code": code, "timed_out": timed_out,
                   "controller_wall_seconds": time.monotonic() - started,
                   "summary_exists": (output / "summary.json").exists(),
                   "source_revision": args.source_sha}
        receipts.append(receipt)
        (args.output / "matrix.json").write_text(json.dumps(receipts, indent=2) + "\n")
        print(json.dumps(receipt), flush=True)
    return int(any(row["exit_code"] for row in receipts))


if __name__ == "__main__":
    raise SystemExit(main())
