"""Controller/oracle checks only; these do not stand in for browser execution."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import fixture_server
import jev_post_progress as proof


def payload(index):
    return {"model": proof.MODEL, "questions": {"candidate": {
        "type": "choice", "criteria": {proof.EXPECTED[index]: "fixture", "abstain": "stop"},
    }}}


def completed(mode):
    valid = mode == "valid"
    reason = "invalid_response" if mode == "invalid-second" else "http_error"
    return dict(mode=mode, code=0 if valid else 1, token="token",
        events=[{"event": "step", "candidate": name, "dry_run": False}
                for name in (proof.EXPECTED if valid else proof.EXPECTED[:1])] +
               ([{"event": "outcome", "outcome": "verified", "token": "token"}] if valid else
                [{"event": "outcome", "outcome": "abstained", "reason": reason}]),
        calls=[{"tool": tool} for tool in (["browser_navigate", "browser_type", "browser_click"]
                                          if valid else ["browser_navigate", "browser_type"])],
        observed={"submitted": "token" if valid else None},
        requests=[{"request_index": 1, "choice": proof.EXPECTED[0], "status": 200,
                   "typing_observed_before_response": False, "response_ns": 1},
                  {"request_index": 2, "choice": proof.EXPECTED[1] if valid else None,
                   "status": 503 if mode == "http-error-second" else 200,
                   "typing_observed_before_response": True, "response_ns": 3}],
        inputs=[{"value": "token", "received_ns": 2}], errors=[])


class OracleTest(unittest.TestCase):
    def test_all_three_expected_outcomes(self):
        for mode in proof.MODES:
            with self.subTest(mode=mode):
                self.assertTrue(proof.validate_case(**completed(mode))["case_passed"])

    def test_rejects_missing_or_wrong_independent_typing(self):
        for value in ([], [{"value": "wrong", "received_ns": 2}],
                      [{"value": "token", "received_ns": 4}]):
            case = completed("invalid-second")
            case["inputs"] = value
            with self.assertRaises(AssertionError):
                proof.validate_case(**case)

    def test_rejects_submit_or_duplicate_input_after_failure(self):
        for tool in ("browser_click", "browser_type", "type_text", "click", "page", "browser_navigate"):
            case = completed("http-error-second")
            case["calls"].append({"tool": tool})
            with self.assertRaises(AssertionError):
                proof.validate_case(**case)

    def test_rejects_false_recovery_or_missing_native_work(self):
        mutations = [lambda c: c.update(observed={"submitted": "token"}),
                     lambda c: c.update(code=0),
                     lambda c: c["events"][-1].update(reason="wrong"),
                     lambda c: c["requests"].append(copy.deepcopy(c["requests"][-1])),
                     lambda c: c["requests"][1].update(typing_observed_before_response=False),
                     lambda c: c["events"][0].update(dry_run=True),
                     lambda c: c.update(calls=[{"tool": "browser_navigate"}]),
                     lambda c: c["errors"].append("fixture failed")]
        for mutate in mutations:
            case = completed("invalid-second")
            mutate(case)
            with self.assertRaises(AssertionError):
                proof.validate_case(**case)

    def test_responder_faults_only_the_second_decision(self):
        for mode in proof.MODES:
            status, _, choice = proof.provider_reply(payload(0), 0, mode)
            self.assertEqual((status, choice), (200, proof.EXPECTED[0]))
        self.assertEqual(proof.provider_reply(payload(1), 1, "valid")[2], proof.EXPECTED[1])
        self.assertEqual(proof.provider_reply(payload(1), 1, "invalid-second")[2], "not-a-supplied-candidate")
        self.assertEqual(proof.provider_reply(payload(1), 1, "http-error-second")[0], 503)
        with self.assertRaises(ValueError):
            proof.provider_reply(payload(1), 2, "valid")


class FixtureTest(unittest.TestCase):
    def test_uses_the_exact_candidate_fixture(self):
        from pathlib import Path
        data = Path(fixture_server.__file__).read_bytes()
        digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        self.assertEqual(digest, "c30aea8a2629f52b74f1314b53fe9bfdd8a3cde3")

    def test_page_receipt_is_independent_of_form_submission(self):
        server, receipts = proof.audited_fixture(fixture_server)
        with proof.serving(server) as url:
            with urlopen(url) as response:
                page = response.read()
            self.assertTrue(page.startswith(fixture_server.PAGE))
            self.assertIn(proof.AUDIT_SCRIPT, page)
            body = json.dumps({"sequence": 1, "event": "input", "value": "token"}).encode()
            with urlopen(Request(url + "/input-audit", body)) as response:
                self.assertEqual(response.status, 200)
            self.assertTrue(receipts.await_value("token"))
            with urlopen(url + "/state") as response:
                self.assertEqual(json.load(response), {"submitted": None})
            with urlopen(Request(url + "/submit", b"value=token")):
                pass
            with urlopen(url + "/state") as response:
                self.assertEqual(json.load(response), {"submitted": "token"})

    def test_actual_http_fault_follows_a_separate_input_receipt(self):
        for mode in ("invalid-second", "http-error-second"):
            receipt = proof.InputReceipt()
            server = proof.Responder(mode, receipt, "token")
            with proof.serving(server) as url:
                with urlopen(Request(url + "/v1/systemone", json.dumps(payload(0)).encode())) as response:
                    self.assertEqual(response.status, 200)
                receipt.receive({"sequence": 1, "event": "input", "value": "token"})
                request = Request(url + "/v1/systemone", json.dumps(payload(1)).encode())
                if mode == "http-error-second":
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request)
                    self.assertEqual(error.exception.code, 503)
                    error.exception.close()
                else:
                    with urlopen(request) as response:
                        self.assertEqual(json.load(response)["answers"]["candidate"]["choice"],
                                         "not-a-supplied-candidate")
                self.assertEqual(len(server.requests), 2)
                self.assertTrue(server.requests[1]["typing_observed_before_response"])
                self.assertEqual(server.errors, [])


if __name__ == "__main__":
    unittest.main()
