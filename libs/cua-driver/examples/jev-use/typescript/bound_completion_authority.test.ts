import assert from 'node:assert/strict';
import test from 'node:test';

import { explainBoundCompletion } from './bound_completion_authority.js';
import { planGuardedCompletion } from './guarded_completion.js';
import { immutableCandidate } from './sources.js';
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

function planFor(task: FixtureFormTask, session: string, priorRef = 'p1:1') {
  const initial = fixtureSources(snapshot('', [priorRef]));
  const selected = task.candidates(initial)[0];
  const plan = planGuardedCompletion(task, initial, selected, session);
  assert.ok(plan);
  return plan;
}

test('exact single candidate admits guarded-completion route', () => {
  const task = new FixtureFormTask('token-a');
  const plan = planFor(task, 'session-a');
  const fresh = fixtureSources(snapshot('token-a', ['p2:1']));
  const evidence = explainBoundCompletion(
    plan,
    task,
    fresh,
    task.candidates(fresh),
    'session-a'
  );
  assert.equal(evidence.route, 'guarded-completion');
  assert.equal(evidence.reason, 'allowed');
  assert.equal(evidence.executable_count, 1);
  assert.equal(evidence.provider_called, false);
  assert.equal(evidence.dispatch_attempted, true);
  assert.equal(evidence.selected_id, 'submit-form');
});

test('non-unique completion falls to chooser', () => {
  const task = new FixtureFormTask('token-a');
  const plan = planFor(task, 'session-a');
  const fresh = fixtureSources(snapshot('token-a', ['p2:1']));
  const cases = [
    { candidates: [] as ReturnType<typeof task.candidates>, count: 0 },
    {
      candidates: [
        immutableCandidate({
          id: 'submit-form',
          description: 'a',
          tool: 'browser_click',
          arguments: { target_id: 'target', tab_id: 'tab', ref: 'p2:1' },
          source: 'page',
        }),
        immutableCandidate({
          id: 'submit-form',
          description: 'b',
          tool: 'browser_click',
          arguments: { target_id: 'target', tab_id: 'tab', ref: 'p2:1' },
          source: 'page',
        }),
      ],
      count: 2,
    },
  ];
  for (const row of cases) {
    const evidence = explainBoundCompletion(
      plan,
      task,
      fresh,
      row.candidates,
      'session-a'
    );
    assert.equal(evidence.route, 'chooser');
    assert.equal(evidence.reason, 'non_unique_completion');
    assert.equal(evidence.executable_count, row.count);
    assert.equal(evidence.provider_called, true);
    assert.equal(evidence.dispatch_attempted, false);
  }
});

test('bidirectional session mismatch never dispatches', () => {
  const taskA = new FixtureFormTask('token-a');
  const taskB = new FixtureFormTask('token-b');
  const planA = planFor(taskA, 'session-a', 'p1:a');
  const planB = planFor(taskB, 'session-b', 'p1:b');
  const freshA = fixtureSources(snapshot('token-a', ['p2:a']));
  const freshB = fixtureSources(snapshot('token-b', ['p2:b']));
  const journalA = { submitted: null, owner: 'A' };
  const journalB = { submitted: null, owner: 'B' };

  const aToB = explainBoundCompletion(
    planA,
    taskA,
    freshA,
    taskA.candidates(freshA),
    'session-b'
  );
  const bToA = explainBoundCompletion(
    planB,
    taskB,
    freshB,
    taskB.candidates(freshB),
    'session-a'
  );
  for (const evidence of [aToB, bToA]) {
    assert.equal(evidence.route, 'chooser');
    assert.equal(evidence.reason, 'session_mismatch');
    assert.equal(evidence.dispatch_attempted, false);
    assert.equal(evidence.provider_called, true);
  }
  assert.deepEqual(journalA, { submitted: null, owner: 'A' });
  assert.deepEqual(journalB, { submitted: null, owner: 'B' });
});

test('foreign attempt does not poison owning plan', () => {
  const task = new FixtureFormTask('token-a');
  const plan = planFor(task, 'session-a');
  const fresh = fixtureSources(snapshot('token-a', ['p2:1']));
  const foreign = explainBoundCompletion(
    plan,
    task,
    fresh,
    task.candidates(fresh),
    'session-b'
  );
  assert.equal(foreign.reason, 'session_mismatch');
  const own = explainBoundCompletion(
    plan,
    task,
    fresh,
    task.candidates(fresh),
    'session-a'
  );
  assert.equal(own.route, 'guarded-completion');
  assert.equal(own.reason, 'allowed');
  assert.equal(own.dispatch_attempted, true);
});
