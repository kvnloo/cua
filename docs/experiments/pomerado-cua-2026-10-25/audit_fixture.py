"""Downstream-only auditable CUA synthetic fixture.

Preserves the original jev-use form and /state behavior, while adding an
independent, redacted /audit mutation journal. Only for isolated synthetic
reversible write experiments; never install in production or treat as a
second CUA Driver verification service.
"""
from __future__ import annotations

import hashlib
from http import HTTPStatus
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[3]
ORIGINAL = ROOT / "libs/cua-driver/examples/jev-use/fixture_server.py"
_spec = importlib.util.spec_from_file_location("cua_jev_fixture_audit", ORIGINAL)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


class AuditedState(_module.FixtureState):
    def __init__(self):
        super().__init__()
        self._commits = []
        self._inflight_submissions = 0
        self._reset_epoch = 0
        self._total_commit_count = 0

    def begin_submit(self) -> None:
        with self._lock:
            self._inflight_submissions += 1

    def end_submit(self) -> None:
        with self._lock:
            self._inflight_submissions -= 1

    def submit(self, value: str) -> None:
        fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()
        with self._lock:
            self._submitted = value
            self._total_commit_count += 1
            self._commits.append({"sequence": len(self._commits) + 1,
                                  "value_sha256": fingerprint})

    def try_reset(self) -> bool:
        # A concurrent delayed submit can otherwise commit into the *next*
        # trial and be mistaken for that arm's first write. Reject resets
        # until every observed in-flight submit has settled.
        with self._lock:
            if self._inflight_submissions:
                return False
            self._submitted = None
            self._commits = []
            self._reset_epoch += 1
            return True

    def reset(self) -> None:
        if not self.try_reset():
            raise RuntimeError("cannot reset with in-flight synthetic submissions")

    def audit(self):
        with self._lock:
            return {"commit_count": len(self._commits), "commits": list(self._commits),
                    "reset_epoch": self._reset_epoch,
                    "total_commit_count": self._total_commit_count}


class AuditedHandler(_module.FixtureHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/reset":
            if not self.server.state.try_reset():
                self._send(HTTPStatus.CONFLICT, "text/plain",
                           b"submit still in flight; reconcile before reset")
                return
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path != "/submit":
            super().do_POST()
            return
        self.server.state.begin_submit()
        try:
            if self.server.dispatch_delay_s:
                time.sleep(self.server.dispatch_delay_s)
            super().do_POST()
        finally:
            self.server.state.end_submit()

    def _send(self, status, content_type: str, body: bytes) -> None:
        # Synthetic fault: state.submit has already committed, but acknowledgement
        # may be delayed beyond the caller timeout. Never mutate after _send.
        if self.path == "/submit" and int(status) == 200 and self.server.ack_delay_s:
            time.sleep(self.server.ack_delay_s)
        try:
            super()._send(status, content_type, body)
        except (BrokenPipeError, ConnectionResetError):
            # The test caller deliberately dropped the acknowledgement.
            pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/audit":
            self._send(HTTPStatus.OK, "application/json",
                       json.dumps(self.server.state.audit(), sort_keys=True).encode("utf-8"))
        else:
            super().do_GET()


class AuditedFixtureServer(_module.FixtureServer):
    def __init__(self, address: tuple[str, int], *, visual: bool = False,
                 ack_delay_s: float = 0.0, dispatch_delay_s: float = 0.0):
        if not 0 <= ack_delay_s <= 2 or not 0 <= dispatch_delay_s <= 2:
            raise ValueError("synthetic delays must be within 0..2 seconds")
        super().__init__(address, visual=visual)
        self.ack_delay_s = ack_delay_s
        self.dispatch_delay_s = dispatch_delay_s
        self.state = AuditedState()
        self.RequestHandlerClass = AuditedHandler


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--visual-fixture", action="store_true")
    args = parser.parse_args()
    server = AuditedFixtureServer(("127.0.0.1", args.port), visual=args.visual_fixture)
    print(f"Audited fixture ready at http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
