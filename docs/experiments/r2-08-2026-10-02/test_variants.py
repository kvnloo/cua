"""UNIT tests for the R2-08 fixture variants (loopback HTTP only, no browser/Driver).

Run from the jev-use directory with its venv:
    .venv/bin/python -m unittest <packet>/test_variants.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
JEV = Path(os.environ.get("JEV_USE_DIR", HERE.parents[2] / "libs/cua-driver/examples/jev-use")).resolve()
sys.path[:0] = [str(HERE), str(JEV)]

from fixture_server import PAGE  # noqa: E402
from variants import N2_PATTERN, VariantServer, eligibility, sha16  # noqa: E402


class Base(unittest.TestCase):
    variant = "base"

    def setUp(self) -> None:
        self.server = VariantServer(("127.0.0.1", 0), self.variant)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def get(self, path: str) -> str:
        with urlopen(self.url + path, timeout=2) as r:
            return r.read().decode()

    def post(self, path: str, fields: dict[str, str]) -> int:
        req = Request(self.url + path, method="POST", data=urlencode(fields).encode(),
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(req, timeout=2) as r:
                return r.status
        except HTTPError as e:
            return e.code

    def state(self) -> dict:
        return json.loads(self.get("/state"))

    def kinds(self, kind: str) -> list[dict]:
        return [e for e in self.server.state.entries() if e["kind"] == kind]


class BaseVariantTest(Base):
    def test_base_page_is_the_shipped_page_and_contract_holds(self) -> None:
        page = self.get("/")
        self.assertEqual(page.encode(), PAGE)
        e = eligibility(page, "r2-08-0123456789ab")
        self.assertTrue(e["eligible_by_contract"])
        self.assertEqual(e["extra_fields"], [])
        self.assertEqual(e["field_constraints"], {"type": "text", "required": True, "pattern": None,
                                                  "maxlength": None, "minlength": None})
        self.assertTrue(e["token_satisfies_constraints"])
        self.assertEqual(e["scripts"], 0)

    def test_base_submit_journal_and_state(self) -> None:
        self.assertEqual(self.post("/submit", {"value": "tok"}), 200)
        self.assertEqual(self.state(), {"submitted": "tok"})
        [s] = self.kinds("submit")
        self.assertEqual((s["fields"], s["status"], s["effect"], s["value_sha16"], s["content_type"]),
                         (["value"], 200, "accepted", sha16("tok"), "application/x-www-form-urlencoded"))
        [m] = self.kinds("mutation")
        self.assertEqual(m["event"], "submit")

    def test_base_empty_value_rejected_without_mutation(self) -> None:
        self.assertEqual(self.post("/submit", {"value": ""}), 400)
        self.assertEqual(self.state(), {"submitted": None})
        self.assertEqual(self.kinds("submit")[0]["effect"], "rejected")
        self.assertEqual(self.kinds("mutation"), [])


class N1Test(Base):
    variant = "n1"

    def test_base_shape_refused_and_current_nonce_accepted(self) -> None:
        page = self.get("/")
        e = eligibility(page, "tok")
        self.assertTrue(e["eligible_by_contract"])  # contract check alone does not see authorization
        self.assertEqual(e["extra_fields"], ["nonce:hidden"])
        self.assertEqual(self.post("/submit", {"value": "tok"}), 403)
        self.assertEqual(self.state(), {"submitted": None})
        self.assertEqual(self.kinds("submit")[0]["reason"], "missing_nonce")
        nonce = page.split('name="nonce" value="')[1].split('"')[0]
        self.assertEqual(self.post("/submit", {"nonce": "0" * 16, "value": "tok"}), 403)
        self.assertEqual(self.kinds("submit")[1]["reason"], "stale_nonce")
        self.assertEqual(self.post("/submit", {"nonce": nonce, "value": "tok"}), 200)
        self.assertEqual(self.state(), {"submitted": "tok"})
        self.assertEqual(self.post("/submit", {"nonce": nonce, "value": "tok2"}), 403)  # single use
        self.assertEqual(self.state(), {"submitted": "tok"})


class N2Test(Base):
    variant = "n2"

    def test_pattern_is_client_side_only(self) -> None:
        page = self.get("/")
        self.assertIn(f'pattern="{N2_PATTERN}"', page)
        bad = "r2-08-INVALID-xyz"
        e = eligibility(page, bad)
        self.assertTrue(e["eligible_by_contract"])
        self.assertFalse(e["token_satisfies_constraints"])
        self.assertTrue(eligibility(page, "r2-08-0123456789ab")["token_satisfies_constraints"])
        self.assertEqual(self.post("/submit", {"value": bad}), 200)
        self.assertEqual(self.state(), {"submitted": bad})

    def test_probe_is_instrumentation(self) -> None:
        self.assertEqual(self.post("/probe", {"kind": "invalid", "name": "value"}), 204)
        self.assertEqual(self.kinds("probe")[0]["event"], "invalid")
        self.assertEqual(self.kinds("mutation"), [])


class N3Test(Base):
    variant = "n3"

    def test_validate_is_journaled_and_state_shape_unchanged(self) -> None:
        page = self.get("/")
        self.assertIn("/validate", page)
        self.assertEqual(eligibility(page, "tok")["scripts"], 1)
        self.assertEqual(self.post("/validate", {"value": "tok"}), 204)
        [v] = self.kinds("validate")
        self.assertEqual(v["value_sha16"], sha16("tok"))
        self.assertEqual(self.state(), {"submitted": None})
        self.assertEqual(self.post("/submit", {"value": "tok"}), 200)
        self.assertEqual(self.state(), {"submitted": "tok"})


class ValidateOnlyOnN3(Base):
    def test_validate_404_on_base(self) -> None:
        self.assertEqual(self.post("/validate", {"value": "x"}), 404)
        self.assertEqual(self.kinds("validate"), [])


if __name__ == "__main__":
    unittest.main()
