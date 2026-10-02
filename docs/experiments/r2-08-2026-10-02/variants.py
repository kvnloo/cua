"""R2-08 fixture variants and the documented form contract (experiment-owned).

Every variant subclasses the unmodified jev-use ``FixtureServer`` /
``FixtureHandler`` / ``FixtureState`` from ``fixture_server.py``. The base
variant serves the exact ``PAGE`` bytes and runs the unmodified POST /submit
handler; it only adds a server-side journal (request receipts and state
mutations, stamped with ``time.monotonic_ns()``). Nothing here changes the
jev-use fixture or the Driver.

Variants (each one documented in the packet README):

* ``base`` - the jev-use fixture as shipped, plus the journal.
* ``n1``   - authorization: every render of ``/`` embeds a fresh server nonce
             in a hidden form field; POST /submit without the current nonce is
             refused (HTTP 403) and the refusal is journaled.
* ``n2``   - constraint bypass: the field carries a client-side ``pattern``;
             the server keeps the base handler (no server-side check). A probe
             script reports the browser's ``invalid`` event to ``/probe``
             (instrumentation, not a task effect).
* ``n3``   - intermediate effect: a page script posts the field value to
             ``/validate`` on every ``input`` event; the server journals each
             ``validate`` as a server-side task effect. ``/state`` keeps the
             base shape (``{"submitted": ...}``).

The documented contract (``DOCUMENTED_CONTRACT``) comes from the fixture's own
source and test: ``fixture_server.py`` PAGE (``<form method="post"
action="/submit">`` with ``<input name="value" required>``) and
``python/tests/test_fixture_server.py`` (``POST /submit`` with
``urlencode({"value": ...})``). The programmatic request is built from that
contract only, never from captured traffic.
"""

from __future__ import annotations

import hashlib
import io
import re
import secrets
import threading
import time
from html.parser import HTMLParser
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from fixture_server import PAGE, FixtureHandler, FixtureServer, FixtureState

VARIANTS = ("base", "n1", "n2", "n3")
FORM_URLENCODED = "application/x-www-form-urlencoded"

DOCUMENTED_CONTRACT = {
    "action": "/submit",
    "method": "post",
    "field": "value",
    "enctype": FORM_URLENCODED,
    "source": [
        "libs/cua-driver/examples/jev-use/fixture_server.py PAGE: <form method=post action=/submit>, <input name=value required>",
        "libs/cua-driver/examples/jev-use/python/tests/test_fixture_server.py: POST /submit with urlencode({'value': ...})",
    ],
}

# N2: a valid token is r2-08-<12 lowercase hex>; the invalid N2 value breaks it.
N2_PATTERN = "r2-08-[0-9a-f]{12}"
_FIELD = b'<input name="value" required aria-label="verification value">'
assert PAGE.count(_FIELD) == 1


def sha16(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:16]


def now() -> int:
    return time.monotonic_ns()


N1_FIELD = (
    b'<input type="hidden" name="nonce" value="__NONCE__">'
    + _FIELD
)
N2_PAGE = PAGE.replace(
    _FIELD,
    b'<input name="value" required pattern="' + N2_PATTERN.encode() + b'" aria-label="verification value">',
).replace(
    b"</html>",
    b"<script>window.addEventListener('invalid',e=>{try{navigator.sendBeacon('/probe',"
    b"new URLSearchParams({kind:'invalid',name:(e.target&&e.target.name)||''}))}catch(_){}} ,true);"
    b"</script></html>",
)
N3_PAGE = PAGE.replace(
    b"</html>",
    b"<script>(()=>{const f=document.querySelector('input[name=value]');"
    b"f.addEventListener('input',()=>{fetch('/validate',{method:'POST',keepalive:true,"
    b"body:new URLSearchParams({value:f.value})}).catch(()=>{});});})();</script></html>",
)
assert N2_PAGE != PAGE and N3_PAGE != PAGE


class JournalState(FixtureState):
    """FixtureState that journals every mutation (target-owned record)."""

    def __init__(self) -> None:
        super().__init__()
        self.journal: list[dict[str, Any]] = []
        self.jlock = threading.Lock()

    def add(self, rec: dict[str, Any]) -> None:
        with self.jlock:
            self.journal.append({"t_mono_ns": now(), **rec})

    def submit(self, value: str) -> None:
        super().submit(value)
        self.add({"kind": "mutation", "event": "submit", "value_sha16": sha16(value)})

    def reset(self) -> None:
        super().reset()
        self.add({"kind": "mutation", "event": "reset"})

    def entries(self) -> list[dict[str, Any]]:
        with self.jlock:
            return list(self.journal)


class VariantHandler(FixtureHandler):
    server: "VariantServer"

    def send_response(self, code: int, message: str | None = None) -> None:  # noqa: D401
        self._status = int(code)
        super().send_response(code, message)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length)

    def _receipt(self, raw: bytes) -> dict[str, Any]:
        fields = parse_qs(raw.decode(errors="replace"), keep_blank_values=True)
        value = fields.get("value", [None])[0]
        return {
            "method": "POST",
            "path": self.path,
            "content_type": (self.headers.get("Content-Type") or "").split(";")[0].strip(),
            "fields": sorted(fields),
            "value_sha16": sha16(value),
            "has_origin": self.headers.get("Origin") is not None,
            "has_referer": self.headers.get("Referer") is not None,
            "has_cookie": self.headers.get("Cookie") is not None,
            "user_agent_is_browser": "Mozilla" in (self.headers.get("User-Agent") or ""),
        }

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            page = self.server.render()
            self.server.state.add({"kind": "render", "path": "/", "nonce_issued": self.server.variant == "n1",
                                   "user_agent_is_browser": "Mozilla" in (self.headers.get("User-Agent") or "")})
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", page)
            return
        if self.path != "/state":
            self.server.state.add({"kind": "get_other", "path": self.path})
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/probe":
            raw = self._read_body()
            fields = parse_qs(raw.decode(errors="replace"))
            self.server.state.add({"kind": "probe", "event": fields.get("kind", [""])[0], "name": fields.get("name", [""])[0]})
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path == "/validate" and self.server.variant == "n3":
            raw = self._read_body()
            value = parse_qs(raw.decode(errors="replace"), keep_blank_values=True).get("value", [""])[0]
            self.server.state.add({"kind": "validate", "value_sha16": sha16(value)})
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path == "/submit":
            raw = self._read_body()
            receipt = self._receipt(raw)
            if self.server.variant == "n1":
                fields = parse_qs(raw.decode(errors="replace"), keep_blank_values=True)
                nonce = fields.get("nonce", [None])[0]
                reason = self.server.check_nonce(nonce)
                if reason is not None:
                    body = b"nonce required"
                    self._send(HTTPStatus.FORBIDDEN, "text/plain", body)
                    self.server.state.add({"kind": "submit", **receipt, "status": 403, "effect": "refused", "reason": reason})
                    return
            self.rfile = io.BytesIO(raw)
            self._status = None
            super().do_POST()  # the unmodified jev-use handler decides and mutates
            status = self._status
            self.server.state.add({"kind": "submit", **receipt, "status": status,
                                   "effect": "accepted" if status == 200 else "rejected", "reason": None})
            return
        if self.path != "/reset":
            self.server.state.add({"kind": "post_other", "path": self.path})
        super().do_POST()


class VariantServer(FixtureServer):
    def __init__(self, address: tuple[str, int], variant: str) -> None:
        if variant not in VARIANTS:
            raise ValueError(variant)
        super().__init__(address)
        self.RequestHandlerClass = VariantHandler
        self.variant = variant
        self.state = JournalState()
        self._nlock = threading.Lock()
        self._nonce: str | None = None

    def render(self) -> bytes:
        if self.variant == "base":
            return PAGE
        if self.variant == "n1":
            with self._nlock:
                self._nonce = secrets.token_hex(8)
                nonce = self._nonce
            return PAGE.replace(_FIELD, N1_FIELD.replace(b"__NONCE__", nonce.encode()))
        if self.variant == "n2":
            return N2_PAGE
        return N3_PAGE

    def check_nonce(self, nonce: str | None) -> str | None:
        """Return a refusal reason, or None (and consume the nonce) when current."""
        with self._nlock:
            if nonce is None:
                return "missing_nonce"
            if self._nonce is None or not secrets.compare_digest(nonce, self._nonce):
                return "stale_nonce"
            self._nonce = None
            return None


# ------------------------------------------------------------ eligibility read
class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self.scripts = 0
        self.inline_handlers = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): v for k, v in attrs}
        self.inline_handlers += sum(1 for k in a if k.startswith("on"))
        if tag == "script":
            self.scripts += 1
        elif tag == "form":
            self.forms.append({"action": a.get("action"), "method": (a.get("method") or "get").lower(),
                               "enctype": a.get("enctype") or FORM_URLENCODED, "inputs": []})
        elif tag in ("input", "textarea", "select") and self.forms:
            self.forms[-1]["inputs"].append({
                "name": a.get("name"), "type": (a.get("type") or "text").lower(),
                "required": "required" in a, "pattern": a.get("pattern"),
                "maxlength": a.get("maxlength"), "minlength": a.get("minlength"),
            })


def eligibility(page_html: str, token: str) -> dict[str, Any]:
    """Check the page form against the documented contract (action, method, field name).

    The gate is exactly the spec's contract check. Everything else (extra
    fields, constraints, scripts) is recorded as descriptive data only.
    """
    p = FormParser()
    p.feed(page_html)
    c = DOCUMENTED_CONTRACT
    form = next((f for f in p.forms if f["action"] == c["action"]), None)
    field = None if form is None else next((i for i in form["inputs"] if i["name"] == c["field"]), None)
    eligible = bool(form and form["method"] == c["method"] and field is not None)
    constraints = None
    satisfies = None
    if field is not None:
        constraints = {k: field[k] for k in ("type", "required", "pattern", "maxlength", "minlength")}
        satisfies = True
        if field["required"] and not token:
            satisfies = False
        if field["pattern"] is not None and re.fullmatch(field["pattern"], token) is None:
            satisfies = False
        if field["maxlength"] is not None and len(token) > int(field["maxlength"]):
            satisfies = False
        if field["minlength"] is not None and len(token) < int(field["minlength"]):
            satisfies = False
    return {
        "eligible_by_contract": eligible,
        "form_count": len(p.forms),
        "action": None if form is None else form["action"],
        "method": None if form is None else form["method"],
        "enctype": None if form is None else form["enctype"],
        "field_present": field is not None,
        "extra_fields": [] if form is None else sorted(
            f"{i['name']}:{i['type']}" for i in form["inputs"] if i["name"] != c["field"]),
        "field_constraints": constraints,
        "token_satisfies_constraints": satisfies,
        "scripts": p.scripts,
        "inline_handlers": p.inline_handlers,
    }
