#!/usr/bin/env python3
"""Fork-only HTTP-to-browser evidence for Cua PR 3961.

Synthetic decisions, real HTTP and unmodified candidate runners/Driver/browser.
Not external-provider qualification, latency benchmarking, or native certification.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

CANDIDATE = "737cda114ae711713a3dbfa9c9ba76863dfd46b9"
MODEL = "wave1-owned-http-fixture"
EXPECTED_ACTIONS = ["type-verification-value", "submit-form"]
INPUT_TOOLS = frozenset({"browser_type", "browser_click", "click", "double_click",
    "right_click", "drag", "scroll", "type_text", "set_value", "press_key", "hotkey"})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def answer(payload: dict, index: int, invalid: bool) -> tuple[dict, dict]:
    if payload.get("model") != MODEL:
        raise ValueError("runner did not preserve the selected model")
    questions = payload.get("questions")
    if not isinstance(questions, dict) or set(questions) != {"candidate"}:
        raise ValueError("expected exactly the existing candidate question")
    question = questions["candidate"]
    if question.get("type") != "choice":
        raise ValueError("expected a choice question")
    criteria = question.get("criteria")
    if not isinstance(criteria, dict) or not criteria:
        raise ValueError("missing candidate IDs")
    intended = EXPECTED_ACTIONS[index] if index < len(EXPECTED_ACTIONS) else None
    if not invalid and intended not in criteria:
        raise ValueError("expected fixture action is not currently a supplied candidate")
    chosen = "wave1-not-a-supplied-candidate" if invalid else intended
    if invalid and chosen in criteria:
        raise ValueError("negative control is not outside the supplied candidate set")
    mass_key = next(iter(criteria)) if invalid else chosen
    response = {"model": MODEL, "answers": {"candidate": {
        "type": "choice", "choice": chosen, "confidence": 1.0,
        "probabilities": {key: float(key == mass_key) for key in criteria},
    }}}
    receipt = {"request_index": index + 1, "candidate_ids": list(criteria), "choice": chosen}
    return response, receipt


class Responder(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, invalid: bool):
        self.invalid = invalid
        self.requests: list[dict] = []
        self.errors: list[str] = []
        self.lock = threading.Lock()
        super().__init__(("127.0.0.1", 0), Handler)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if self.path != "/v1/systemone" or self.headers.get("Authorization"):
                raise ValueError("unexpected route or credentials on owned fixture")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1_000_000:
                raise ValueError("fixture request size out of bounds")
            payload = json.loads(self.rfile.read(length))
            with self.server.lock:
                result, receipt = answer(payload, len(self.server.requests), self.server.invalid)
                self.server.requests.append(receipt)
            raw = json.dumps(result).encode()
            self.send_response(200)
        except Exception as error:
            with self.server.lock:
                self.server.errors.append(type(error).__name__ + ": " + str(error))
            raw = b'{"error":"owned fixture rejected request"}'
            self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


@contextlib.contextmanager
def serving(server):
    with server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("owned HTTP server did not drain")


def proxy(driver: str, audit: Path, driver_args: list[str]) -> int:
    """Forward newline-framed MCP bytes unchanged; retain tool names, never arguments."""
    child = subprocess.Popen([driver, *driver_args], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    errors: list[BaseException] = []

    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)

    def send():
        try:
            with audit.open("a", encoding="utf-8") as trace:
                for line in sys.stdin.buffer:
                    try:
                        request = json.loads(line)
                    except (UnicodeError, ValueError):
                        request = None
                    if isinstance(request, dict) and request.get("method") == "tools/call":
                        params = request.get("params")
                        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                            raise ValueError("unclassifiable tools/call in audit proxy")
                        trace.write(json.dumps({"tool": params["name"]}) + "\n")
                        trace.flush()
                    child.stdin.write(line)
                    child.stdin.flush()
        except BaseException as error:
            errors.append(error)
            child.terminate()
        finally:
            with contextlib.suppress(BrokenPipeError, OSError):
                child.stdin.close()

    thread = threading.Thread(target=send, daemon=True)
    thread.start()
    try:
        for line in child.stdout:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
        code = child.wait(timeout=5)
        if errors:
            raise RuntimeError("MCP audit forwarding failed") from errors[0]
        return code
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


def validate_case(*, invalid: bool, code: int, events: list[dict], calls: list[dict],
                  observed: dict, token: str, requests: list[dict], errors: list[str]) -> dict:
    if errors:
        raise AssertionError(errors)
    actions = [event.get("candidate") for event in events if event.get("event") == "step"]
    inputs = [entry["tool"] for entry in calls if entry["tool"] in INPUT_TOOLS]
    if "browser_navigate" not in [entry["tool"] for entry in calls]:
        raise AssertionError("real browser setup was not observed at MCP ingress")
    if invalid:
        assert code == 1, code
        assert len(requests) == 1, requests
        assert events and events[-1].get("outcome") == "abstained", events
        assert events[-1].get("reason") == "invalid_response", events
        assert not actions and not inputs, (actions, inputs)
        assert observed == {"submitted": None}, observed
    else:
        assert code == 0, code
        assert len(requests) == 2, requests
        assert actions == EXPECTED_ACTIONS, actions
        assert inputs == ["browser_type", "browser_click"], inputs
        assert all(event.get("dry_run") is False for event in events if event.get("event") == "step")
        assert events[-1] == {"event": "outcome", "outcome": "verified", "token": token}, events
        assert observed == {"submitted": token}, observed
    return {"case_passed": True, "http_requests": len(requests), "candidate_actions": actions,
            "input_tools_at_mcp_ingress": inputs, "independent_fixture_state": observed}


def exercise(root: Path, out: Path, driver: Path) -> None:
    base = root / "libs/cua-driver/examples/jev-use"
    sys.path.insert(0, str(base))
    from fixture_server import FixtureServer
    out.mkdir(parents=True, exist_ok=False)
    summary = {"complete": False, "scope": "synthetic HTTP decisions with real runner/MCP/browser", "cases": []}
    clean_env = dict(os.environ)
    for key in list(clean_env):
        if key.startswith(("JEV_", "TYPESAFE_", "OPENJEV_")):
            clean_env.pop(key)
    clean_env.update(JEV_API_KEY="", TYPESAFE_API_KEY="")
    try:
        for language in ("python", "typescript"):
            for provider, invalid in (("local", False), ("openjev", False), ("local", True)):
                name = f"{language}-{provider}-{'invalid' if invalid else 'valid'}"
                case = out / name
                case.mkdir()
                record = {"name": name, "language": language, "provider": provider,
                          "invalid_choice": invalid, "case_passed": False}
                summary["cases"].append(record)
                responder = Responder(invalid)
                with serving(FixtureServer(("127.0.0.1", 0))) as fixture_url, serving(responder) as provider_url:
                    log, audit = case / "runner.jsonl", case / "mcp-tools.jsonl"
                    audit.touch()
                    wrapper = case / "driver-with-audit"
                    exports = []
                    for key in ("DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS",
                                "CUA_DRIVER_PERMISSION_MODE", "CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS",
                                "CUA_E2E_BROWSER_NO_SANDBOX", "CUA_E2E_BROWSER_STDERR"):
                        if key in clean_env:
                            exports.append(f"export {key}={shlex.quote(clean_env[key])}")
                    wrapper.write_text("#!/bin/bash\nset -euo pipefail\n" + "\n".join(exports) + "\nexec " +
                        shlex.join([sys.executable, str(Path(__file__).resolve()), "proxy", str(driver), str(audit)]) + ' "$@"\n')
                    wrapper.chmod(0o700)
                    env = {**clean_env, "CUA_DRIVER_BIN": str(wrapper)}
                    token = "wave1-" + name
                    command = ([sys.executable, "python/run.py"] if language == "python" else
                               ["node", "--import", "tsx", "typescript/run.ts"])
                    command += ["--provider", provider, "--jev-base-url", provider_url, "--jev-model", MODEL,
                                "--fixture-url", fixture_url + "/", "--token", token, "--max-steps", "3", "--log", str(log)]
                    started = time.monotonic()
                    with (case / "runner.log").open("w") as output:
                        process = subprocess.run(command, cwd=base, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=180)
                    events = [json.loads(line) for line in log.read_text().splitlines()]
                    calls = [json.loads(line) for line in audit.read_text().splitlines()]
                    with urlopen(fixture_url + "/state", timeout=2) as reply:
                        observed = json.load(reply)
                    (case / "http-requests.json").write_text(json.dumps(responder.requests, indent=2) + "\n")
                    record.update(validate_case(invalid=invalid, code=process.returncode, events=events, calls=calls,
                        observed=observed, token=token, requests=responder.requests, errors=responder.errors))
                    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
                    print(json.dumps(record), flush=True)
        summary["complete"] = True
    finally:
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


def bootstrap(root: Path, out: Path, workflow_sha: str) -> int:
    # Reuse the already-reviewed pinned recipe parser and first four run bodies.
    from run_canonical_jev_browser import recipe, git, CANONICAL_BLOB
    out.mkdir(parents=True, exist_ok=False)
    result = {"candidate_sha": CANDIDATE, "workflow_sha": workflow_sha, "canonical_recipe_blob": CANONICAL_BLOB,
              "controller_sha256": sha256(Path(__file__)), "stages": [], "complete": False,
              "scope": "adapted fork-only HTTP/browser integration; no external model or latency benchmark"}
    try:
        assert git(root, "rev-parse", "HEAD") == CANDIDATE
        assert not git(root, "status", "--porcelain")
        workflow, canonical = recipe(root)
        env = dict(os.environ)
        assert env.get("RUNNER_TEMP"), "requires disposable hosted runner"
        for key, value in workflow["jobs"]["mock-e2e-linux"]["env"].items():
            env[key] = str(value).replace("${{ github.workspace }}", str(root))
        env.update(JEV_API_KEY="", TYPESAFE_API_KEY="", PYTHONUNBUFFERED="1")
        default_dir = workflow["defaults"]["run"]["working-directory"]
        stages = list(canonical[:4])
        exercise_command = shlex.join(["uv", "run", "--frozen", "python", str(Path(__file__).resolve()), "exercise",
            "--candidate-dir", str(root), "--evidence-dir", str(out / "http-proof"), "--driver", env["CUA_DRIVER_BIN"]])
        session = out / "http-x11-session.sh"
        session.write_text("set -euo pipefail\n" +
            'openbox >"$RUNNER_TEMP/wave1-openbox.log" 2>&1 &\nwm=$!\n' +
            'picom --backend xrender --config /dev/null >"$RUNNER_TEMP/wave1-picom.log" 2>&1 &\ncompositor=$!\n' +
            "trap 'kill \"$wm\" \"$compositor\" 2>/dev/null || true' EXIT\nsleep 2\n" +
            f"cd {shlex.quote(str(root / default_dir))}\n{exercise_command}\n")
        stages.append({"name": "Adapted real-HTTP browser integration (six cases)", "working-directory": str(root),
            "run": shlex.join(["xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24", "dbus-run-session", "--", "bash", str(session)])})
        for index, step in enumerate(stages, 1):
            script = out / f"stage-{index:02d}.sh"
            script.write_text(step["run"])
            cwd = Path(step.get("working-directory", default_dir).replace("${{ github.workspace }}", str(root)))
            if not cwd.is_absolute():
                cwd = root / cwd
            assert cwd.is_relative_to(root)
            entry = {"name": step["name"], "script_sha256": sha256(script), "canonical_body_unchanged": index <= 4}
            result["stages"].append(entry)
            print("::group::" + step["name"], flush=True)
            start = time.monotonic()
            with (out / f"stage-{index:02d}.log").open("w") as log:
                with subprocess.Popen(["bash", "-e", str(script)], cwd=cwd, env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, bufsize=1) as child:
                    for line in child.stdout:
                        log.write(line)
                        print(line, end="", flush=True)
                    code = child.wait()
            entry.update(exit_code=code, elapsed_seconds=round(time.monotonic() - start, 3))
            print("::endgroup::", flush=True)
            if code:
                break
        result["tracked_candidate_source_unchanged"] = not git(root, "diff", "HEAD", "--")
        binary = Path(env["CUA_DRIVER_BIN"])
        if binary.is_file():
            result["driver_binary_sha256"] = sha256(binary)
        proof = out / "http-proof/summary.json"
        result["complete"] = (len(result["stages"]) == 5 and all(s.get("exit_code") == 0 for s in result["stages"])
            and result["tracked_candidate_source_unchanged"] and proof.is_file() and json.loads(proof.read_text())["complete"])
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)
        print(result["error"], file=sys.stderr)
    finally:
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
        (out / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.relative_to(out)}\n" for p in files))
    return 0 if result["complete"] else 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "proxy":
        return proxy(sys.argv[2], Path(sys.argv[3]), sys.argv[4:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["bootstrap", "exercise"])
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--workflow-sha")
    parser.add_argument("--driver", type=Path)
    args = parser.parse_args()
    root, out = args.candidate_dir.resolve(), args.evidence_dir.resolve()
    if args.mode == "bootstrap":
        if not args.workflow_sha:
            parser.error("bootstrap requires --workflow-sha")
        return bootstrap(root, out, args.workflow_sha)
    if args.driver is None:
        parser.error("exercise requires --driver")
    exercise(root, out, args.driver.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
