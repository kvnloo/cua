import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { compileExpectation, providerCannotReplace, type Candidate } from './compiled_expectations.ts';

const fixture = JSON.parse(
  readFileSync(new URL('../../../../../scripts/repro/handoff/issue-40-fixture.json', import.meta.url), 'utf8'),
) as Array<{ id: string; tool: string | null; token: string; expect: { kind: string; token: string } | null }>;

function candidate(id: string, tool: string | null): Candidate {
  return { id, description: id, tool, arguments: {} };
}

test('shared fixture matches compileExpectation', () => {
  for (const row of fixture) {
    const compiled = compileExpectation(candidate(row.id, row.tool), row.token);
    assert.deepEqual(compiled, row.expect);
  }
});

test('type and submit compile the same expectations as the Python module', () => {
  assert.deepEqual(compileExpectation(candidate('type-verification-value', 'browser_type'), 'proof'), {
    kind: 'field_value_equals',
    token: 'proof',
  });
  assert.deepEqual(compileExpectation(candidate('submit-form', 'browser_click'), 'proof'), {
    kind: 'fixture_submitted_equals',
    token: 'proof',
  });
  assert.equal(compileExpectation(candidate('reobserve', null), 'proof'), null);
});

test('provider output does not replace the compiled expectation', () => {
  const compiled = { kind: 'field_value_equals', token: 'proof' };
  assert.deepEqual(providerCannotReplace(compiled, { kind: 'field_value_equals', token: 'attacker' }), compiled);
});
