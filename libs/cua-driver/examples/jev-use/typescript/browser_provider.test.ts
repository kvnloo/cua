import assert from 'node:assert/strict';
import test from 'node:test';

import {
  backendName,
  browserDecisionRequest,
  chooseBrowserProvider,
} from './browser_provider.js';
import { FixtureFormTask, fixtureSources } from './tasks.js';
import type { BrowserSnapshot } from './core.js';

function fixture(token: string) {
  const snapshot: BrowserSnapshot = {
    target_id: 'target',
    tab_id: 'tab',
    capture_id: 'browser-capture-1',
    refs: [
      { role: 'textbox', name: 'verification value', ref: 'p1:0', value: '' },
      { role: 'button', name: 'Submit', ref: 'p1:1' },
    ],
  };
  const task = new FixtureFormTask(token);
  const sources = fixtureSources(snapshot);
  return { task, sources, candidates: task.candidates(sources) };
}

test('browser request is bounded and contains no action arguments or secret', () => {
  const token = 'secret-proof-token';
  const { task, sources, candidates } = fixture(token);
  const request = browserDecisionRequest(task, sources, candidates, []);
  assert.equal(request.schema, 'cua.jev_choice_request_v1');
  assert.equal(request.capture_id, 'browser-capture-1');
  assert.deepEqual(
    request.candidates.map(({ id }) => id),
    ['type-verification-value', 'reobserve', 'abstain']
  );
  const wire = JSON.stringify(request);
  assert.equal(wire.includes(token), false);
  assert.equal(wire.includes('arguments'), false);
  assert.equal(wire.includes('browser_type'), false);
});

test('mock keeps existing task policy and reports actual backend', async () => {
  const { task, sources, candidates } = fixture('proof-token');
  const result = await chooseBrowserProvider('mock', task, sources, candidates, []);
  assert.equal(result.choice, 'type-verification-value');
  assert.equal(result.confidence, 1);
  assert.equal(result.backend, 'mock');
  assert.equal(result.probabilities[result.choice!], 1);
  assert.equal(backendName('live'), 'typesafe');
  assert.equal(backendName('typesafe'), 'typesafe');
  assert.equal(backendName('openjev'), 'openjev');
  assert.equal(backendName('s1'), 's1');
});
