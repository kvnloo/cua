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

    def submit(self, value: str) -> None:
        fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()
        with self._lock:
            self._submitted = value
            self._commits.append({"sequence": len(self._commits) + 1,
                                  "value_sha256": fingerprint})

    def reset(self) -> None:
        with self._lock:
            self._submitted = None
            self._commits = []

    def audit(self):
        with self._lock:
            return {"commit_count": len(self._commits), "commits": list(self._commits)}


class AuditedHandler(_module.FixtureHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/audit":
            self._send(HTTPStatus.OK, "application/json",
                       json.dumps(self.server.state.audit(), sort_keys=True).encode("utf-8"))
        else:
            super().do_GET()


class AuditedFixtureServer(_module.FixtureServer):
    def __init__(self, address: tuple[str, int], *, visual: bool = False):
        super().__init__(address, visual=visual)
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
