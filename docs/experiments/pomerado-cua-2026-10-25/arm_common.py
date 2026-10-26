"""Shared one-attempt machinery for arm B (Pomerado MCP) and arm C (opencli) runners.

Emits one cua.pomerado.trial.v1 receipt per attempt. It never retries, never falls
back to another route and fails closed on non-loopback origins. It does not start
the fixture, the browser, the minter or any model. Credit: Pomerado is MIT
(Pomerado AI, Inc.); opencli is jackwener/opencli.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SCHEMA = "cua.pomerado.trial.v1"
ARM_ROUTE = {"A": "cua-driver", "B": "pomerado-mcp", "C": "opencli-adapter-cdp"}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
EXACT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64}|sha256:[0-9a-f]{64})\Z")
PIN_FIELDS = ("fixture_sha", "caller_sha", "driver_sha", "pomerado_sha")


class AttemptError(Exception):
    """Configuration problem detected before any action; nothing was executed."""


def sha256_text(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return "sha256:" + hashlib.sha256(data).hexdigest()


def require_loopback(url: str, *, what: str) -> str:
    parts = urlsplit(url)
    try:
        host_ok = parts.hostname is not None and (
            parts.hostname == "localhost" or ipaddress.ip_address(parts.hostname).is_loopback)
    except ValueError:
        host_ok = False
    if parts.scheme != "http" or not host_ok or parts.port is None or parts.path not in ("", "/") \
            or parts.username or parts.password or parts.query or parts.fragment:
        raise AttemptError(f"{what} must be a bare http://127.0.0.1:PORT origin (fail closed)")
    return f"http://{parts.hostname}:{parts.port}"


def http(method: str, url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    request = Request(url, data=b"" if method == "POST" else None, method=method)
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 loopback only (validated)
        return response.status, response.read()


class Oracle:
    """Independent reset, /state and /audit reads against the audited fixture."""

    def __init__(self, base: str):
        self.base = base

    def state(self) -> dict:
        return json.loads(http("GET", self.base + "/state")[1])

    def audit(self) -> dict:
        return json.loads(http("GET", self.base + "/audit")[1])

    def reset_verified(self) -> tuple[bool, int, dict]:
        """POST /reset, then require an empty /state and zero /audit commits."""
        try:
            status, _ = http("POST", self.base + "/reset")
            audit = self.audit()
            ok = status == 204 and self.state() == {"submitted": None} \
                and audit.get("commit_count") == 0
        except (URLError, OSError, ValueError):
            return False, 0, {}
        return ok, int(audit.get("commit_count", 0)), audit


@dataclass
class Invocation:
    """What an arm-specific invoker reports about its single call."""
    ok: bool
    output: object = None
    route_evidence: str = ""
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    fallback_count: int = 0
    detail: str = ""


@dataclass
class AttemptSpec:
    arm: str
    block_id: str
    position: int
    workflow: str = "browser-fixture-form"
    variant: str = "default"
    effect_kind: str = "read"
    value: str | None = None
    evidence_class: str = "UNIT"
    pins: dict = field(default_factory=dict)
    browser_version: str = ""
    mint_ms: float = 0.0
    run_id: str | None = None
    extra: dict = field(default_factory=dict)


def check_spec(spec: AttemptSpec) -> None:
    if spec.arm not in ARM_ROUTE:
        raise AttemptError("unknown arm")
    if spec.effect_kind not in {"read", "write"}:
        raise AttemptError("effect_kind must be read or write")
    if spec.effect_kind == "write" and not spec.value:
        raise AttemptError("a write attempt needs a value")
    if not (1 <= spec.position <= 4):
        raise AttemptError("position must be 1..4")
    if spec.evidence_class not in {"REAL", "UNIT"}:
        raise AttemptError("evidence_class must be REAL or UNIT")
    missing = [k for k in PIN_FIELDS if not spec.pins.get(k)]
    if missing or not spec.browser_version:
        raise AttemptError(f"missing pins: {missing or ['browser_version']}")
    if spec.evidence_class == "REAL":
        bad = [k for k in PIN_FIELDS if not EXACT.fullmatch(spec.pins[k])]
        if bad:
            raise AttemptError(f"REAL evidence needs exact SHA pins; bad: {bad}")


def judge(spec: AttemptSpec, inv: Invocation, state_after: dict, before: int, after: int,
          expect: str) -> dict:
    """Outcome flags from the independent oracle, never from the arm's own claim."""
    delta = after - before
    submitted = state_after.get("submitted")
    flags = dict(wrong_target=False, unauthorized_effect=False, duplicate_effect=False,
                 uncertain_effect=False)
    if spec.effect_kind == "read":
        flags["unauthorized_effect"] = delta != 0 or submitted is not None
        text = json.dumps(inv.output, sort_keys=True) if inv.output is not None else ""
        if not inv.ok:
            outcome = "unknown" if delta else "abstained"
            flags["uncertain_effect"] = bool(delta)
        elif flags["unauthorized_effect"] or expect not in text:
            outcome = "refuted"
        else:
            outcome = "verified"
        return {**flags, "oracle_outcome": outcome}
    flags["duplicate_effect"] = delta > 1
    flags["wrong_target"] = submitted not in (None, spec.value)
    if not inv.ok:
        flags["uncertain_effect"] = delta >= 1
        outcome = "unknown" if delta >= 1 else "abstained"
    elif delta == 1 and submitted == spec.value and not flags["wrong_target"]:
        outcome = "verified"
    else:
        outcome = "refuted"
    return {**flags, "oracle_outcome": outcome}


def run_attempt(spec: AttemptSpec, base: str, invoke, *, expect: str = "status=waiting") -> dict:
    """Reset, read oracle, run exactly one invocation, read oracle, build receipt."""
    check_spec(spec)
    base = require_loopback(base, what="fixture base")
    oracle = Oracle(base)
    reset_ok, before, audit0 = oracle.reset_verified()
    if not reset_ok:
        raise AttemptError("reset not independently verified (fail closed)")
    started = time.perf_counter()
    try:
        inv = invoke(base)
    except Exception as error:  # one attempt, no retry: record the failure honestly
        inv = Invocation(ok=False, detail=f"{type(error).__name__}")
    elapsed_ms = max((time.perf_counter() - started) * 1000.0, 0.001)
    try:
        state_after, audit1 = oracle.state(), oracle.audit()
        after = int(audit1.get("commit_count", -1))
    except (URLError, OSError, ValueError):
        state_after, audit1, after = {"submitted": "<oracle-unreachable>"}, {}, before
        inv = Invocation(ok=False, detail="oracle unreachable after attempt")
    verdict = judge(spec, inv, state_after, before, after, expect)
    if not inv.ok:
        route = "blocked"
    else:
        route = ARM_ROUTE[spec.arm]
    audit_ref = sha256_text(json.dumps({"before": audit0, "after": audit1, "state": state_after},
                                       sort_keys=True))
    fingerprint = sha256_text(f"{spec.effect_kind}:{spec.value or ''}:{spec.workflow}")
    receipt = {
        "schema": SCHEMA,
        "evidence_class": spec.evidence_class,
        "run_id": spec.run_id or f"{spec.block_id}-{spec.position}-{spec.arm}",
        "block_id": spec.block_id,
        "position": spec.position,
        "arm": spec.arm,
        "workflow": spec.workflow,
        "variant": spec.variant,
        "input_fingerprint": fingerprint,
        **{k: spec.pins[k] for k in PIN_FIELDS},
        "browser_version": spec.browser_version,
        "route_observed": route,
        "route_evidence": inv.route_evidence or f"{route}:no-trace",
        "reset_verified": True,
        "oracle_evidence": "state+audit:" + audit_ref,
        "elapsed_ms": elapsed_ms,
        "model_calls": inv.model_calls,
        "input_tokens": inv.input_tokens,
        "output_tokens": inv.output_tokens,
        "fallback_count": inv.fallback_count,
        "mint_ms": float(spec.mint_ms),
        "effect_kind": spec.effect_kind,
        "audit_before": before,
        "audit_after": after,
        "audit_evidence": "audit:" + audit_ref,
        **verdict,
        **spec.extra,
    }
    return receipt


def append_receipt(path: Path | None, receipt: dict) -> None:
    line = json.dumps(receipt, sort_keys=True)
    if path is None:
        print(line)
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def add_common_args(parser) -> None:
    parser.add_argument("--base", required=True, help="audited fixture origin http://127.0.0.1:PORT")
    parser.add_argument("--block-id", required=True)
    parser.add_argument("--position", type=int, required=True)
    parser.add_argument("--workflow", default="browser-fixture-form")
    parser.add_argument("--variant", default="default")
    parser.add_argument("--effect", choices=("read", "write"), default="read")
    parser.add_argument("--value", help="value to submit (write only)")
    parser.add_argument("--allow-write", action="store_true",
                        help="required for --effect write; also needs --read-only-proof-sha256")
    parser.add_argument("--read-only-proof-sha256")
    parser.add_argument("--evidence-class", choices=("REAL", "UNIT"), default="UNIT")
    for name in PIN_FIELDS:
        parser.add_argument("--" + name.replace("_", "-"), required=True)
    parser.add_argument("--browser-version", required=True)
    parser.add_argument("--mint-ms", type=float, default=0.0,
                        help="measured one-time preparation cost (build/mint/install)")
    parser.add_argument("--run-id")
    parser.add_argument("--out", type=Path, help="append the receipt to this JSONL (default stdout)")
    parser.add_argument("--timeout", type=float, default=60.0)


def spec_from_args(args, arm: str, extra: dict | None = None) -> AttemptSpec:
    if args.effect == "write":
        proof = args.read_only_proof_sha256 or ""
        if not args.allow_write or not re.fullmatch(r"[0-9a-f]{64}", proof):
            raise AttemptError("write needs --allow-write and a 64-hex read-only proof (fail closed)")
    return AttemptSpec(
        arm=arm, block_id=args.block_id, position=args.position, workflow=args.workflow,
        variant=args.variant, effect_kind=args.effect, value=args.value,
        evidence_class=args.evidence_class,
        pins={k: getattr(args, k) for k in PIN_FIELDS}, browser_version=args.browser_version,
        mint_ms=args.mint_ms, run_id=args.run_id, extra=extra or {})
