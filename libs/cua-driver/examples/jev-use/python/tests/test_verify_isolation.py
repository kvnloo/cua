"""Verifier contract tests using real loopback HTTP and real child processes.

Children are deliberately controlled verifier inputs, not browser simulations.
No Driver, browser, model, or complete runner integration is certified here.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verify_setup import fixture, verify

CHILD = r'''
import json, sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
url, token, mode, log = sys.argv[1:]
if mode == 'submit':
    with urlopen(Request(url + 'submit', data=urlencode({'value': token}).encode()), timeout=2):
        pass
elif mode != 'report_only':
    raise SystemExit('unknown fixture-child mode')
Path(log).write_text(json.dumps({'event': 'outcome', 'outcome': 'verified', 'token': token}) + '\n')
'''


def seed(url: str, token: str) -> None:
    with urlopen(Request(url + 'submit', data=urlencode({'value': token}).encode()), timeout=2):
        pass


def command(url: str, token: str, mode: str, log: Path) -> list[str]:
    return [sys.executable, '-c', CHILD, url, token, mode, str(log)]


class VerifyIsolationTests(unittest.TestCase):
    def test_claim_without_submission_is_rejected_on_fresh_fixture(self):
        with tempfile.TemporaryDirectory() as directory, fixture() as url:
            log = Path(directory) / 'fresh.jsonl'
            with self.assertRaisesRegex(RuntimeError, 'Independent'):
                verify(command(url, 'proof', 'report_only', log), url, 'proof', log)

    def test_stale_matching_state_cannot_certify_a_noop(self):
        with tempfile.TemporaryDirectory() as directory, fixture() as url:
            seed(url, 'proof')
            log = Path(directory) / 'stale.jsonl'
            with self.assertRaisesRegex(RuntimeError, 'Independent'):
                verify(command(url, 'proof', 'report_only', log), url, 'proof', log)

    def test_first_runner_success_cannot_certify_second_runner_noop(self):
        with tempfile.TemporaryDirectory() as directory, fixture() as url:
            first, second = Path(directory) / 'python.jsonl', Path(directory) / 'typescript.jsonl'
            self.assertEqual(
                verify(command(url, 'proof', 'submit', first), url, 'proof', first)['observed'],
                {'submitted': 'proof'},
            )
            with self.assertRaisesRegex(RuntimeError, 'Independent'):
                verify(command(url, 'proof', 'report_only', second), url, 'proof', second)

    def test_two_genuine_submissions_with_same_token_still_pass(self):
        with tempfile.TemporaryDirectory() as directory, fixture() as url:
            for name in ('python', 'typescript'):
                log = Path(directory) / f'{name}.jsonl'
                self.assertEqual(
                    verify(command(url, 'proof', 'submit', log), url, 'proof', log)['observed'],
                    {'submitted': 'proof'},
                )

    def test_stale_state_does_not_prevent_a_new_valid_submission(self):
        with tempfile.TemporaryDirectory() as directory, fixture() as url:
            seed(url, 'old-proof')
            log = Path(directory) / 'new.jsonl'
            self.assertEqual(
                verify(command(url, 'new-proof', 'submit', log), url, 'new-proof', log)['observed'],
                {'submitted': 'new-proof'},
            )


if __name__ == '__main__':
    unittest.main()
