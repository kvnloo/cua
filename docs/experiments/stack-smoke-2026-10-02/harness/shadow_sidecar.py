"""Shadow sidecar: score Hermes observer events with one z0int backend, write z0int receipts.

Runs as its own process next to Hermes (never inside it). It only READS the observer spool
(kvnloo/hermes-agent#385) and only WRITES under --out, a directory the Hermes process cannot see
(the run launcher masks it with an empty tmpfs inside Hermes' sandbox). Nothing here can reach a
prompt, a tool choice or any other Hermes input.

Decision lanes (no new question family):
  * api.attempt_will_fail - request built by the #386 code (shadow_api_failure.request_for), one per
    physical provider attempt (pre_api_request).
  * verification_needed   - the decision-capability-v1 question verbatim, one per turn, asked at the
    turn's final response point (post_api_request with assistant_tool_call_count == 0, else
    on_session_end) over content-free turn counters.

Fail-open: a backend that cannot load or evaluate yields a receipt with status
"backend_unavailable"; the sidecar keeps consuming events and never signals Hermes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

VN_QUESTION = {
    "id": "verification_needed",
    "type": "boolean",
    "instructions": "Does this turn require an explicit verification pass before responding?",
    "criteria": {"false": "Safe to respond without extra verification", "true": "Run verification before responding"},
}


def canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj: Any) -> str:
    return hashlib.sha256(canon(obj).encode("utf-8")).hexdigest()


class Turn:
    """Content-free counters for one turn (trace_id), from observer rows only."""

    def __init__(self) -> None:
        self.c: dict[str, Any] = {"api_calls": 0, "api_errors": 0, "max_retry_count": 0, "tool_calls": 0,
                                  "tool_errors": 0, "subagents": 0, "prompt_tokens": 0, "completion_tokens": 0}
        self.tools: dict[str, int] = {}
        self.asked = False
        self.ident: dict[str, Any] = {}
        self.model = None

    def feed(self, row: dict[str, Any]) -> None:
        ev, f = row.get("event"), row.get("fields") or {}
        self.ident = {k: v for k, v in (row.get("identity") or {}).items() if v is not None} or self.ident
        self.model = f.get("model") or self.model
        if ev == "pre_api_request":
            self.c["max_retry_count"] = max(self.c["max_retry_count"], int(f.get("retry_count") or 0))
        elif ev == "post_api_request":
            self.c["api_calls"] += 1
            u = row.get("usage") or {}
            self.c["prompt_tokens"] += int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
            self.c["completion_tokens"] += int(u.get("completion_tokens") or u.get("output_tokens") or 0)
        elif ev == "api_request_error":
            self.c["api_errors"] += 1
        elif ev == "post_tool_call":
            t = row.get("tool") or {}
            self.c["tool_calls"] += 1
            self.tools[t.get("tool_name") or "?"] = self.tools.get(t.get("tool_name") or "?", 0) + 1
            if t.get("error_type") or (t.get("status") not in (None, "ok", "success")):
                self.c["tool_errors"] += 1
        elif ev == "subagent_stop":
            self.c["subagents"] += 1

    def state(self) -> dict[str, Any]:
        return {"harness": "hermes", "model": self.model, **self.c, "tools_used": dict(sorted(self.tools.items()))}


class Sidecar:
    def __init__(self, a: argparse.Namespace) -> None:
        self.a = a
        self.out = Path(a.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.full = (self.out / "decisions.full.jsonl").open("a", encoding="utf-8")
        self.backend = None
        self.backend_error: str | None = None
        self.ready = threading.Event()
        self.turns: dict[str, Turn] = {}
        self.counts = {"rows": 0, "opportunities": 0, "ok": 0, "backend_unavailable": 0, "eval_error": 0}
        sys.path[:0] = [a.hermes_lab, a.z0_wt, str(Path(a.z0_wt) / "src")]
        from shadow_api_failure import request_for  # #386, stdlib only
        from z0int import receipt as z0receipt
        from z0int.backends.base import request_from_mapping, result_to_dict
        self.request_for, self.z0receipt = request_for, z0receipt
        self.request_from_mapping, self.result_to_dict = request_from_mapping, result_to_dict

    def load(self) -> None:
        t0 = time.perf_counter()
        try:
            from z0int.backends.registry import create_backend
            b = create_backend(self.a.backend)
            if self.a.warm:  # force the model load now (cold start), outside any Hermes path
                b._ensure_loaded() if hasattr(b, "_ensure_loaded") else None
            self.backend = b
        except Exception as e:  # fail-open: record, keep consuming
            self.backend_error = f"{type(e).__name__}: {str(e)[:300]}"
        self.load_ms = (time.perf_counter() - t0) * 1000.0
        (self.out / "backend_load.json").write_text(canon({"backend_arg": self.a.backend, "load_ms": self.load_ms,
                                                           "error": self.backend_error, "at": time.time()}) + "\n")
        self.ready.set()

    def decide(self, *, qid: str, request: dict[str, Any], ident: dict[str, Any], opportunity_id: str,
               model: str | None, observed_at: float | None) -> None:
        self.counts["opportunities"] += 1
        status, decision, err = "ok", None, None
        t_wall = time.time()
        t0 = time.perf_counter()
        if self.backend is None:
            status, err = "backend_unavailable", self.backend_error or "backend not loaded"
        else:
            try:
                decision = self.result_to_dict(self.backend.evaluate(self.request_from_mapping(request)))
            except Exception as e:
                status, err = "eval_error", f"{type(e).__name__}: {str(e)[:300]}"
        wall_ms = (time.perf_counter() - t0) * 1000.0
        self.counts["ok" if status == "ok" else status] += 1
        q = request["questions"][0]
        ans = next((x for x in (decision or {}).get("answers", []) if x.get("question_id") == q["id"]), None)
        row = {
            "schema": "stack_smoke.shadow_decision.v1",
            "status": status, "error": err, "question_id": qid, "opportunity_id": opportunity_id,
            "trace_id": ident.get("trace_id"), "turn_id": ident.get("turn_id"), "session_id": ident.get("session_id"),
            "api_request_id": ident.get("api_request_id"), "backend_arg": self.a.backend,
            "candidates": sorted(q["criteria"].keys()), "request": request, "state_hash": sha(request["state"]),
            "decision": decision, "eval_wall_ms": wall_ms, "decided_at": t_wall,
            "event_observed_at": observed_at, "queue_delay_ms": (t_wall - observed_at) * 1000.0 if observed_at else None,
        }
        self.full.write(canon(row) + "\n"); self.full.flush()
        # Projection into the EXISTING z0int receipt schema (z0int.decision_receipt.v1), shadow execution.
        rec = self.z0receipt.build_receipt(
            trace_id=ident.get("trace_id"), session_id=ident.get("session_id"), capability_id=qid,
            provider=(decision or {}).get("backend") or self.a.backend, model=(decision or {}).get("model"),
            prediction=(ans or {}).get("value"), confidence=(ans or {}).get("confidence"),
            action_taken=None, route="shadow", execution="shadow",
            latency_ms=(decision or {}).get("latency_ms"),
            measurement_state="complete" if status == "ok" else "failed",
            state_reason=None if status == "ok" else f"{status}: {err}",
            extra={"turn_id": ident.get("turn_id"), "api_request_id": ident.get("api_request_id"),
                   "opportunity_id": opportunity_id, "backend_arg": self.a.backend,
                   "revision": (decision or {}).get("revision"), "candidates": row["candidates"],
                   "probabilities": (ans or {}).get("probabilities"), "state_hash": row["state_hash"],
                   "shadow_status": status, "experiment_id": self.a.experiment_id, "arm_id": self.a.arm},
        )
        self.z0receipt.append_receipt(rec, root=Path(self.a.z0int_home))

    def handle(self, row: dict[str, Any]) -> None:
        self.counts["rows"] += 1
        ev, ident, f = row.get("event"), row.get("identity") or {}, row.get("fields") or {}
        tid = ident.get("trace_id")
        if not tid:
            return
        turn = self.turns.setdefault(tid, Turn())
        turn.feed(row)
        if ev == "pre_api_request" and ident.get("api_request_id"):
            opp = f"{ident['api_request_id']}#r{int(f.get('retry_count') or 0)}"
            self.decide(qid="api.attempt_will_fail", request=self.request_for(row), ident=ident,
                        opportunity_id=opp, model=f.get("model"), observed_at=row.get("observed_at"))
        final = (ev == "post_api_request" and f.get("assistant_tool_call_count") == 0) or ev == "on_session_end"
        if final and not turn.asked and ident.get("turn_id"):
            turn.asked = True
            req = {"state": turn.state(), "questions": [VN_QUESTION], "request_id": tid}
            self.decide(qid="verification_needed", request=req, ident=ident, opportunity_id=tid,
                        model=turn.model, observed_at=row.get("observed_at"))

    def run(self) -> None:
        threading.Thread(target=self.load, daemon=True).start()
        events, stop = Path(self.a.events), Path(self.a.stop_file)
        (self.out / "sidecar_started").write_text(str(time.time()))
        self.ready.wait(self.a.ready_timeout)
        (self.out / "sidecar_ready").write_text(canon({"at": time.time(), "backend_error": self.backend_error}))
        pos, buf, deadline = 0, "", None
        while True:
            if events.exists():
                with events.open(encoding="utf-8") as fh:
                    fh.seek(pos)
                    chunk = fh.read()
                    pos = fh.tell()
                buf += chunk
                *lines, buf = buf.split("\n")
                for line in lines:
                    if line.strip():
                        try:
                            self.handle(json.loads(line))
                        except Exception:
                            (self.out / "sidecar_errors.log").open("a").write(traceback.format_exc())
                if lines:
                    continue
            if stop.exists():
                deadline = deadline or time.time() + 2.0  # drain grace after the run ends
                if time.time() > deadline:
                    break
            time.sleep(0.2)
        (self.out / "sidecar_summary.json").write_text(canon({"counts": self.counts, "backend_arg": self.a.backend,
                                                               "backend_error": self.backend_error,
                                                               "load_ms": getattr(self, "load_ms", None)}) + "\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--z0int-home", required=True)
    p.add_argument("--backend", required=True)
    p.add_argument("--stop-file", required=True)
    p.add_argument("--hermes-lab", required=True, help="lab/z0_hermes_observer dir of the Hermes worktree")
    p.add_argument("--z0-wt", required=True)
    p.add_argument("--experiment-id", default="stack-smoke-2026-10-02")
    p.add_argument("--arm", default="shadow_on")
    p.add_argument("--ready-timeout", type=float, default=120.0)
    p.add_argument("--warm", action="store_true", help="load the model before reporting ready")
    Sidecar(p.parse_args()).run()


if __name__ == "__main__":
    main()
