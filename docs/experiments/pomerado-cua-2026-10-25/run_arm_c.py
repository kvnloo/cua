#!/usr/bin/env python3
"""Arm C: run ONE attempt through an opencli adapter attached over CDP; emit one receipt.

Needs an already running fixture (audit_fixture.py) and a Chromium with
--remote-debugging-port (attach-only, same for every arm). opencli's extension and
daemon are bypassed because OPENCLI_CDP_ENDPOINT is set. No model, no token.
Credit: opencli is jackwener/opencli (fork kvnloo/opencli); Pomerado is MIT (Pomerado AI, Inc.).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys

from arm_common import (AttemptError, Invocation, add_common_args, append_receipt,
                        require_loopback, run_attempt, sha256_text, spec_from_args, EXACT)


def make_invoker(args):
    endpoint = require_loopback(args.cdp_endpoint, what="CDP endpoint")
    base_cmd = shlex.split(args.opencli_cmd)

    def invoke(base: str) -> Invocation:
        if args.effect == "read":
            argv = [*base_cmd, "jev", "read-status", "--origin", base, "-f", "json"]
        else:
            argv = [*base_cmd, "jev", "submit-value", "--value", args.value, "--origin", base,
                    "--confirm-write", "yes", "-f", "json"]
        env = {**os.environ, "OPENCLI_CDP_ENDPOINT": endpoint}
        if args.cdp_target:
            env["OPENCLI_CDP_TARGET"] = args.cdp_target
        env.pop("OPENCLI_DAEMON_PORT", None)
        try:
            done = subprocess.run(argv, env=env, capture_output=True, timeout=args.timeout,
                                  check=False)
        except subprocess.TimeoutExpired:
            return Invocation(ok=False, route_evidence="opencli-adapter-cdp:timeout",
                              detail="timeout")
        digest = sha256_text(done.stdout)
        evidence = (f"opencli-adapter-cdp:{args.effect}:exit={done.returncode}:"
                    f"stdout={digest}:argv={sha256_text(' '.join(argv))}")
        if done.returncode != 0:
            return Invocation(ok=False, route_evidence=evidence, detail=f"exit {done.returncode}")
        try:
            output = json.loads(done.stdout)
        except ValueError:
            return Invocation(ok=False, route_evidence=evidence, detail="unparseable output")
        # The JSON envelope's own timing is in-process only; wall time is measured by the caller.
        return Invocation(ok=True, output=output, route_evidence=evidence)

    return invoke


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--cdp-endpoint", required=True, help="http://127.0.0.1:PORT of Chromium")
    parser.add_argument("--cdp-target", help="substring pinning the tab, e.g. 127.0.0.1:8766")
    parser.add_argument("--opencli-cmd", default="opencli", help="command (may include args)")
    parser.add_argument("--opencli-sha", required=True, help="pinned opencli source/dist digest")
    args = parser.parse_args(argv)
    try:
        if args.evidence_class == "REAL" and not EXACT.fullmatch(args.opencli_sha):
            raise AttemptError("REAL evidence needs an exact --opencli-sha")
        spec = spec_from_args(args, "C", {"opencli_sha": args.opencli_sha})
        receipt = run_attempt(spec, args.base, make_invoker(args))
    except AttemptError as error:
        print(json.dumps({"status": "REFUSED_NOT_RUN", "error": str(error)}), file=sys.stderr)
        return 2
    append_receipt(args.out, receipt)
    return 0 if receipt["oracle_outcome"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
