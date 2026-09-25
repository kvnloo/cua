"""Existing fixture verdict is independent of later cleanup and telemetry errors."""
import json
import unittest
from test_task_timing import HERE, BASELINE, run_case
from task_timing import TaskTiming

class TerminalTimingTests(unittest.TestCase):
    def test_cleanup_failure_retains_prior_fixture_verdict(self):
        before = run_case(BASELINE, 'baseline', 'cleanup_error')
        after = run_case(HERE/'run.py', 'treatment', 'cleanup_error')
        self.assertEqual(before['error'], after['error'])
        root = next(e for e in after['events'] if e['event']=='task_root')
        self.assertEqual(root['outcome'],'unknown')
        self.assertEqual(root['error_type'],'RuntimeError')
        self.assertIsNotNone(root['terminal_observation'])
        self.assertEqual(root['terminal_observation']['verdict'],'verified')
        self.assertLess(root['terminal_observation']['at_ms'],root['end_ms'])

    def test_unknown_and_abstention_do_not_invent_completion(self):
        for scenario in ('provider_none','abstain','empty_candidates','reobserve','dry_run',
                         'action_error','observe_error','verify_error','reset_error','cancel_action'):
            with self.subTest(scenario=scenario):
                after=run_case(HERE/'run.py','treatment',scenario)
                root=next(e for e in after['events'] if e['event']=='task_root')
                self.assertIsNone(root['terminal_observation'])
                self.assertIsNone(root['post_terminal_observation_ms'])

    def test_refutation_is_terminal_but_not_success(self):
        after=run_case(HERE/'run.py','treatment','refuted')
        root=next(e for e in after['events'] if e['event']=='task_root')
        self.assertIsNotNone(root['terminal_observation'])
        self.assertEqual(root['terminal_observation']['verdict'],'refuted')
        self.assertEqual(root['outcome'],'refuted')

    def test_exact_marker_and_root_intervals(self):
        ticks=iter([0,1_000_000,5_000_000,7_000_000,11_000_000])
        timer=TaskTiming(clock=lambda:next(ticks))
        with timer.span('verify'): pass
        timer.observe_classification('verified')
        rows=timer.finish('unknown',error_type='CleanupError')
        self.assertIsNotNone(rows[-1]['terminal_observation'])
        self.assertEqual(rows[-1]['terminal_observation']['at_ms'],7)
        self.assertEqual(rows[-1]['end_ms'],11)
        self.assertEqual(rows[-1]['post_terminal_observation_ms'],4)

    def test_runner_return_alone_is_not_a_fixture_observation(self):
        timer=TaskTiming(); root=timer.finish('verified')[-1]
        self.assertIsNone(root['terminal_observation'])

if __name__=='__main__':unittest.main()
