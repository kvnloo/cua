import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { buildCandidates, type BrowserSnapshot, type Candidate } from './core.js';
import {
  ObservationLedger,
  hasActionableCandidate,
  needsVisualObservation,
} from './observation.js';

function snapshotWithRefs(
  refs: BrowserSnapshot['refs'],
): BrowserSnapshot {
  return { target_id: 't', tab_id: 'tab', refs };
}

const TOKEN = 'tok';

describe('hasActionableCandidate', () => {
  it('is true when a DOM candidate carries a tool', () => {
    const candidates = buildCandidates(
      snapshotWithRefs([
        { role: 'textbox', name: 'verification value', ref: 'r1', value: 'other' },
      ]),
      TOKEN,
      undefined,
      false,
    );
    assert.equal(hasActionableCandidate(candidates), true);
    assert.ok(candidates.some((candidate) => candidate.id === 'type-verification-value'));
  });

  it('is false when only reserved candidates exist', () => {
    const reservedOnly: Candidate[] = [
      { id: 'reobserve', description: 'x', tool: null, arguments: {} },
      { id: 'abstain', description: 'y', tool: null, arguments: {} },
    ];
    assert.equal(hasActionableCandidate(reservedOnly), false);
  });
});

describe('needsVisualObservation', () => {
  it('is false when the snapshot yields the type candidate', () => {
    const candidates = buildCandidates(
      snapshotWithRefs([
        { role: 'textbox', name: 'verification value', ref: 'r1', value: 'other' },
      ]),
      TOKEN,
      undefined,
      false,
    );
    assert.equal(needsVisualObservation(candidates), false);
  });

  it('is false when the snapshot yields the DOM submit candidate', () => {
    const candidates = buildCandidates(
      snapshotWithRefs([
        { role: 'textbox', name: 'verification value', ref: 'r1', value: TOKEN },
        { role: 'button', name: 'Submit', ref: 'r2' },
      ]),
      TOKEN,
      undefined,
      true,
    );
    assert.equal(needsVisualObservation(candidates), false);
    assert.ok(candidates.some((candidate) => candidate.id === 'submit-form'));
  });

  it('is true when only the visual fallback could produce submit', () => {
    const candidates = buildCandidates(
      snapshotWithRefs([
        { role: 'textbox', name: 'verification value', ref: 'r1', value: TOKEN },
      ]),
      TOKEN,
      undefined,
      true,
    );
    assert.equal(hasActionableCandidate(candidates), false);
    assert.equal(needsVisualObservation(candidates), true);
  });
});

describe('ObservationLedger', () => {
  it('counts and sums per kind', () => {
    const ledger = new ObservationLedger();
    ledger.record({ kind: 'snapshot', latencyMs: 180 }, 1);
    ledger.record({ kind: 'visual', captureId: 'c1', latencyMs: 860 }, 1);
    ledger.record({ kind: 'snapshot', latencyMs: 175 }, 2);
    assert.equal(ledger.count('snapshot'), 2);
    assert.equal(ledger.count('visual'), 1);
    assert.equal(ledger.totalLatencyMs(), 1215);
    assert.equal(ledger.totalLatencyMs('visual'), 860);
    assert.equal(ledger.entries().length, 3);
  });
});
