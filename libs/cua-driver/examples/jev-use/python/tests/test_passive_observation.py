from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from passive_observation import AuthorityError, Row, action_target, verification_text


class PassiveObservationTest(unittest.TestCase):
    def test_passive_result_is_readable_and_not_actionable(self) -> None:
        result = Row("calc-result", "6", passive=True)
        button = Row("calc-equals", "=", passive=False)
        self.assertEqual(verification_text([result, button], "calc-result"), "6")
        with self.assertRaises(AuthorityError):
            action_target(result)
        self.assertEqual(action_target(button), "calc-equals")


if __name__ == "__main__":
    unittest.main()
