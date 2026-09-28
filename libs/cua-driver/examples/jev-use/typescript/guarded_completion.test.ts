import assert from 'node:assert/strict';
import test from 'node:test';

import {
  planGuardedCompletion,
  resolveGuardedCompletion,
} from './guarded_completion.js';
import { immutableCandidate } from './sources.js';
import { FixtureFormTask, fixtureSources } from './tasks.js';
import type { BrowserSnapshot } from './core.js';

function snapshot(value: string, submitRefs: string[]): BrowserSnapshot {
  return {
    target_id: 'target',
    tab_id: 'tab',
    refs: [
      { role: 'textbox', name: 'verification value', ref: 'p1:0', value },
      ...submitRefs.map((ref) => ({ role: 'button', name: 'Submit', ref })),
    ],
  };
}

test('guarded completion uses only the fresh ref', () => {
  const task = new FixtureFormTask('proof');
  const initial = fixtureSources(snapshot('', ['p1:1']));
  const selected = task.candidates(initial)[0];
  const plan = planGuardedCompletion(task, initial, selected, 'session-a');
  assert.ok(plan);

  const fresh = fixtureSources(snapshot('proof', ['p2:1']));
  const completion = resolveGuardedCompletion(
    plan,
    task,
    fresh,
    task.candidates(fresh),
    'session-a'
  );
  assert.ok(completion);
  assert.equal(completion.id, 'submit-form');
  assert.equal(completion.arguments.ref, 'p2:1');
  assert.notEqual(completion.arguments.ref, plan.priorRef);
});

test('guarded completion refuses a foreign session', () => {
  const task = new FixtureFormTask('proof');
  const initial = fixtureSources(snapshot('', ['p1:1']));
  const plan = planGuardedCompletion(task, initial, task.candidates(initial)[0], 'session-a');
  assert.ok(plan);
  const fresh = fixtureSources(snapshot('proof', ['p2:1']));
  assert.equal(
    resolveGuardedCompletion(plan, task, fresh, task.candidates(fresh), 'session-b'),
    undefined
  );
});

test('guarded completion refuses ambiguity, missing targets, and unverified state', () => {
  const task = new FixtureFormTask('proof');
  const initial = fixtureSources(snapshot('', ['p1:1']));
  const plan = planGuardedCompletion(task, initial, task.candidates(initial)[0], 'session-a');
  assert.ok(plan);

  for (const refs of [[], ['p2:1', 'p2:2']]) {
    const fresh = fixtureSources(snapshot('proof', refs));
    assert.equal(
      resolveGuardedCompletion(plan, task, fresh, task.candidates(fresh), 'session-a'),
      undefined
    );
  }

  const wrong = fixtureSources(snapshot('other', ['p2:1']));
  assert.equal(
    resolveGuardedCompletion(plan, task, wrong, task.candidates(wrong), 'session-a'),
    undefined
  );
});

test('guarded completion refuses old-ref reuse and requires a unique initial target', () => {
  const task = new FixtureFormTask('proof');
  const initial = fixtureSources(snapshot('', ['p1:1']));
  const plan = planGuardedCompletion(task, initial, task.candidates(initial)[0], 'session-a');
  assert.ok(plan);

  const fresh = fixtureSources(snapshot('proof', ['p2:1']));
  const bad = immutableCandidate({
    id: 'submit-form',
    description: 'tampered',
    tool: 'browser_click',
    arguments: { target_id: 'target', tab_id: 'tab', ref: plan.priorRef },
    source: 'page',
  });
  assert.equal(resolveGuardedCompletion(plan, task, fresh, [bad], 'session-a'), undefined);

  for (const refs of [[], ['p1:1', 'p1:2']]) {
    const sources = fixtureSources(snapshot('', refs));
    assert.equal(
      planGuardedCompletion(task, sources, task.candidates(sources)[0], 'session-a'),
      undefined
    );
  }
});
