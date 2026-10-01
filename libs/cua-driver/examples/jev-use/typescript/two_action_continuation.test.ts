import assert from 'node:assert/strict';
import test from 'node:test';

import { journalTwoActionContinuation } from './two_action_continuation.js';
import { FixtureFormTask, fixtureSources } from './tasks.js';
import type { BrowserSnapshot } from './core.js';

function snapshot(
  value: string,
  submitRefs: string[],
  fieldRef = 'p1:0'
): BrowserSnapshot {
  return {
    target_id: 'target',
    tab_id: 'tab',
    refs: [
      { role: 'textbox', name: 'verification value', ref: fieldRef, value },
      ...submitRefs.map((ref) => ({ role: 'button', name: 'Submit', ref })),
    ],
  };
}

test('happy path attributes provider then guarded-completion', () => {
  const task = new FixtureFormTask('proof-token');
  const initial = fixtureSources(snapshot('', ['p1:1']));
  const fresh = fixtureSources(snapshot('proof-token', ['p2:1']));
  const journal = journalTwoActionContinuation(task, initial, fresh, 'session-a');
  assert.deepEqual(journal.decision_routes, ['provider', 'guarded-completion']);
  assert.equal(journal.provider_decisions, 1);
  assert.equal(journal.actions_dispatched, 2);
  assert.equal(journal.guarded_child_admitted, true);
  assert.equal(journal.second_dispatch_attempted, true);
  assert.equal(journal.plan_consumed, true);
  assert.equal(journal.steps[0].candidate_id, 'type-verification-value');
  assert.equal(journal.steps[1].candidate_id, 'submit-form');
  assert.equal(journal.steps[0].plan_pending_after, true);
  assert.equal(journal.steps[1].plan_pending_after, false);
  assert.equal(journal.steps[1].provider_called, false);
});

test('failed postcondition clears authority with no second dispatch', () => {
  const task = new FixtureFormTask('proof-token');
  const initial = fixtureSources(snapshot('', ['p1:1']));
  const fresh = fixtureSources(snapshot('wrong-token', ['p2:1']));
  const journal = journalTwoActionContinuation(task, initial, fresh, 'session-a');
  assert.deepEqual(journal.decision_routes, ['provider', 'chooser']);
  assert.equal(journal.provider_decisions, 2);
  assert.equal(journal.actions_dispatched, 1);
  assert.equal(journal.guarded_child_admitted, false);
  assert.equal(journal.second_dispatch_attempted, false);
  assert.equal(journal.plan_consumed, true);
  assert.equal(journal.steps[1].dispatch_attempted, false);
});

test('stale ref clears authority with no second dispatch', () => {
  const task = new FixtureFormTask('proof-token');
  const initial = fixtureSources(snapshot('', ['p1:1']));
  const fresh = fixtureSources(snapshot('proof-token', ['p1:1']));
  const journal = journalTwoActionContinuation(task, initial, fresh, 'session-a');
  assert.deepEqual(journal.decision_routes, ['provider', 'chooser']);
  assert.equal(journal.actions_dispatched, 1);
  assert.equal(journal.guarded_child_admitted, false);
  assert.equal(journal.second_dispatch_attempted, false);
  assert.equal(journal.plan_consumed, true);
});

test('consumed plan does not authorize a third step', () => {
  const task = new FixtureFormTask('proof-token');
  const initial = fixtureSources(snapshot('', ['p1:1']));
  const fresh = fixtureSources(snapshot('proof-token', ['p2:1']));
  const third = fixtureSources(snapshot('proof-token', ['p3:1']));
  const journal = journalTwoActionContinuation(
    task,
    initial,
    fresh,
    'session-a',
    third
  );
  assert.deepEqual(journal.decision_routes, [
    'provider',
    'guarded-completion',
    'chooser',
  ]);
  assert.equal(journal.provider_decisions, 2);
  assert.equal(journal.actions_dispatched, 2);
  assert.equal(journal.guarded_child_admitted, true);
  assert.equal(journal.plan_consumed, true);
  assert.equal(journal.steps[2].route, 'chooser');
  assert.equal(journal.steps[2].dispatch_attempted, false);
  assert.equal(journal.steps[2].provider_called, true);
});
