"""JSONL chronology must agree with slot declarations; adjacent pairs only.

These are ledger-format tests, not evidence that a real Driver executed.
"""
import unittest

from paired_task_gate import analyze
from test_paired_task_gate import pairs


class ChronologyRegression(unittest.TestCase):
    def test_swapping_every_pairs_rows_cannot_forge_slot_zero(self):
        source = pairs(20)
        swapped = [r for i in range(0, len(source), 2) for r in (source[i + 1], source[i])]
        report = analyze(swapped)
        self.assertFalse(report['valid'])
        self.assertIn('JSONL row order disagrees with declared slot', ' '.join(report['errors']))

    def test_interleaved_pair_ids_are_not_complete_matched_tasks(self):
        source = pairs(20)
        # A0,A1,B0,B1: two overlapping pairs, despite intact reported slots.
        interleaved = source[:]
        interleaved[:4] = [source[0], source[2], source[1], source[3]]
        report = analyze(interleaved)
        self.assertFalse(report['valid'])
        self.assertIn('pair records are nonadjacent', ' '.join(report['errors']))

    def test_true_reverse_chronology_remains_valid(self):
        source = pairs(20)
        reversed_rows = []
        for i in range(0, len(source), 2):
            a, b = source[i : i + 2]
            reversed_rows.extend([dict(b, slot=0), dict(a, slot=1)])
        self.assertTrue(analyze(reversed_rows)['valid'])


if __name__ == '__main__':
    unittest.main()
