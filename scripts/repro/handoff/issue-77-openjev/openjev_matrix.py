#!/usr/bin/env python3
"""Exact-head OpenJev (trycua/cua#3961) transport matrix against a REAL owned loopback responder.

Drives the real CLI `python/choose_decision.py --model openjev` (real urllib transport) against an
HTTP/HTTPS server this script owns. Records, per row: CLI exit code, stdout/stderr summary, how many
requests the responder actually saw, whether an Authorization header arrived, and (for the key rows)
that the synthetic key value never appears in any recorded artifact.

usage: openjev_matrix.py --examples-dir DIR --out-dir DIR
"""
import argparse
import json
import os
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SECRET = "sk-test-" + "0123456789abcdef" * 2  # synthetic; never a real key
GOOD = {
    "model": "openjev-fixture",
    "answers": {"candidate": {
        "type": "choice", "choice": "ax:button:increment", "confidence": 0.93,
        "probabilities": {"ax:button:increment": 0.93, "reobserve": 0.05, "abstain": 0.02}}},
}
SEEN: list = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        mode = self.path.split("/")[1]
        SEEN.append({"mode": mode, "path": self.path,
                     "authorization_present": "Authorization" in self.headers,
                     "authorization_matches_secret": self.headers.get("Authorization") == f"Bearer {SECRET}",
                     "body_bytes": len(body)})

        def send(code, payload, extra=None):
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        if mode in ("valid", "https"):
            send(200, GOOD)
        elif mode == "unknown":
            answer = {**GOOD["answers"]["candidate"], "choice": "not-a-candidate",
                      "probabilities": {"not-a-candidate": 1.0}}
            send(200, {**GOOD, "answers": {"candidate": answer}})
        elif mode == "malformed":
            send(200, b"{not json")
        elif mode == "503":
            send(503, {"error": "unavailable"})
        elif mode == "redirect":
            send(302, b"", extra={"Location": "/valid/v1/systemone"})
        elif mode == "timeout":
            time.sleep(3)
            try:
                send(200, GOOD)
            except OSError:
                pass
        elif mode == "oversized":
            send(200, b'{"pad":"' + b"x" * (300 * 1024) + b'"}')
        else:
            send(404, {})


def serve(cert=None):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    if cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(*cert)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    ex = args.examples_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    request = (ex / "fixtures/jev-choice-request-v2.json").read_text()
    tmp = Path(tempfile.mkdtemp())
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(tmp / "k.pem"),
                    "-out", str(tmp / "c.pem"), "-days", "1", "-subj", "/CN=localhost",
                    "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True, capture_output=True)
    _, http_port = serve()
    _, tls_port = serve((str(tmp / "c.pem"), str(tmp / "k.pem")))
    rows = [
        ("valid", f"http://127.0.0.1:{http_port}/valid", "", {}),
        ("unknown_candidate_id", f"http://127.0.0.1:{http_port}/unknown", "", {}),
        ("malformed_response", f"http://127.0.0.1:{http_port}/malformed", "", {}),
        ("http_503", f"http://127.0.0.1:{http_port}/503", "", {}),
        ("redirect_refused", f"http://127.0.0.1:{http_port}/redirect", "", {}),
        ("timeout", f"http://127.0.0.1:{http_port}/timeout", "", {"OPENJEV_TIMEOUT_MS": "300"}),
        ("oversized_response", f"http://127.0.0.1:{http_port}/oversized", "", {}),
        ("url_credentials_rejected", f"http://user:pw@127.0.0.1:{http_port}/valid", "", {}),
        ("api_key_over_http_rejected", f"http://127.0.0.1:{http_port}/valid", SECRET, {}),
        ("api_key_over_https_accepted", f"https://localhost:{tls_port}/https", SECRET,
         {"SSL_CERT_FILE": str(tmp / "c.pem")}),
    ]
    results = []
    for name, base, key, extra in rows:
        SEEN.clear()
        env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"),
               "OPENJEV_BASE_URL": base, **extra}
        if key:
            env["OPENJEV_API_KEY"] = key
        started = time.perf_counter()
        proc = subprocess.run(
            [str(ex / ".venv/bin/python"), str(ex / "python/choose_decision.py"), "--model", "openjev"],
            input=request, capture_output=True, text=True, env=env, cwd=ex / "python", timeout=30)
        row = {"row": name, "exit_code": proc.returncode,
               "wall_ms": round((time.perf_counter() - started) * 1000),
               "stdout": proc.stdout.strip()[:400], "stderr_tail": proc.stderr.strip()[-300:],
               "responder_requests": [dict(item) for item in SEEN]}
        row["secret_in_recorded_row"] = SECRET in json.dumps(row)
        results.append(row)
        print(json.dumps({"row": name, "exit": row["exit_code"], "wall_ms": row["wall_ms"],
                          "requests": len(SEEN), "stdout": row["stdout"][:120],
                          "stderr": row["stderr_tail"][-120:]}))
    (args.out_dir / "results.json").write_text(json.dumps({"synthetic_key_used": True, "rows": results}, indent=1) + "\n")
    assert not any(row["secret_in_recorded_row"] for row in results), "secret leaked into evidence"


if __name__ == "__main__":
    main()
