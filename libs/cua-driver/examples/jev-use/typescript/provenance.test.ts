import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { ProvenanceLedger } from './provenance.js';

function snapshot(step: number, latencyMs = 1.5) {
  return { kind: 'snapshot' as const, latencyMs, step };
}

describe('ProvenanceLedger', () => {
  it('collects observations per step in order', () => {
    const ledger = new ProvenanceLedger();
    ledger.recordObservation(2, { kind: 'snapshot', latencyMs: 1.0 });
    ledger.recordObservation(1, { kind: 'snapshot', latencyMs: 2.0 });
    ledger.recordObservation(1, { kind: 'visual', captureId: 'c1', latencyMs: 9.0 });
    const steps = ledger.steps();
    assert.equal(steps.length, 2);
    assert.equal(steps[0].step, 1);
    assert.equal(steps[0].observations.length, 2);
    assert.equal(steps[0].observations[1].kind, 'visual');
    assert.equal(steps[1].step, 2);
  });

  it('pairs dispatch and settlement notes with the step', () => {
    const ledger = new ProvenanceLedger();
    ledger.recordObservation(1, { kind: 'snapshot', latencyMs: 1.0 });
    ledger.noteDispatch(1, {
      candidateId: 'fill-form',
      tool: 'fill',
      evidenceKinds: ['snapshot'],
    });
    ledger.noteSettlement(1, { verifiedBy: 'snapshot-diff', latencyMs: 3.2 });
    assert.equal(ledger.settled(1), true);
    const record = ledger.step(1)!;
    assert.equal(record.dispatch!.candidateId, 'fill-form');
    assert.deepEqual(record.dispatch!.evidenceKinds, ['snapshot']);
    assert.equal(record.settlement!.verifiedBy, 'snapshot-diff');
  });

  it('treats an unverified step as not settled', () => {
    const ledger = new ProvenanceLedger();
    ledger.noteDispatch(1, { candidateId: 'click-x', tool: 'click', evidenceKinds: ['visual'] });
    ledger.noteSettlement(1, { verifiedBy: 'unverified', latencyMs: 0 });
    assert.equal(ledger.settled(1), false);
  });

  it('treats a step with no dispatch as not settled', () => {
    const ledger = new ProvenanceLedger();
    ledger.recordObservation(1, { kind: 'snapshot', latencyMs: 1.0 });
    assert.equal(ledger.settled(1), false);
  });

  it('noteDriverField promotes driver evidence into the dispatch record', () => {
    const ledger = new ProvenanceLedger();
    ledger.noteDispatch(1, { candidateId: 'click-x', tool: 'click', evidenceKinds: ['snapshot'] });
    ledger.noteSettlement(1, { verifiedBy: 'unverified', latencyMs: 0 });
    ledger.noteDriverField(1, {
      actionId: 'click-x',
      observedBeforeEffect: true,
      observedAfterEffect: true,
      effectConfirmedBy: 'tree-diff',
      status: 'completed',
    });
    const record = ledger.step(1)!;
    assert.deepEqual(record.dispatch!.evidenceKinds, ['snapshot', 'driver']);
    assert.equal(record.settlement!.verifiedBy, 'snapshot-diff');
    assert.equal(ledger.settled(1), true);
    assert.equal(record.postDispatch, 'completed');
  });

  it("noteDriverField 'skipped' records not-performed and touches nothing else", () => {
    const ledger = new ProvenanceLedger();
    ledger.noteDispatch(1, { candidateId: 'click-x', tool: 'click', evidenceKinds: ['snapshot'] });
    ledger.noteSettlement(1, { verifiedBy: 'unverified', latencyMs: 0 });
    ledger.noteDriverField(1, {
      actionId: 'click-x',
      observedBeforeEffect: false,
      observedAfterEffect: false,
      effectConfirmedBy: 'tree-diff',
      status: 'skipped',
    });
    const record = ledger.step(1)!;
    // "not performed" is recorded explicitly — it must not promote evidence
    // or settlement, and must not read as "performed and saw no change".
    assert.equal(record.postDispatch, 'skipped');
    assert.deepEqual(record.dispatch!.evidenceKinds, ['snapshot']);
    assert.equal(record.settlement!.verifiedBy, 'unverified');
    assert.equal(ledger.settled(1), false);
  });

  it("noteDriverField 'unavailable' records the absent capability", () => {
    const ledger = new ProvenanceLedger();
    ledger.noteDispatch(1, { candidateId: 'click-x', tool: 'click', evidenceKinds: ['snapshot'] });
    ledger.noteDriverField(1, {
      actionId: 'click-x',
      observedBeforeEffect: false,
      observedAfterEffect: false,
      effectConfirmedBy: 'none',
      status: 'unavailable',
    });
    const record = ledger.step(1)!;
    assert.equal(record.postDispatch, 'unavailable');
    assert.deepEqual(record.dispatch!.evidenceKinds, ['snapshot']);
    assert.equal(record.settlement, undefined);
  });

  it("noteDriverField 'completed' never promotes effect on status alone", () => {
    const ledger = new ProvenanceLedger();
    ledger.noteDispatch(1, { candidateId: 'click-x', tool: 'click', evidenceKinds: ['snapshot'] });
    ledger.noteDriverField(1, {
      actionId: 'click-x',
      observedBeforeEffect: true,
      observedAfterEffect: true,
      effectConfirmedBy: 'none',
      status: 'completed',
    });
    const record = ledger.step(1)!;
    // The poll ran, but effect confirmation is absent: status alone is not
    // settlement. This is #4009's "never promotes effect" rule.
    assert.equal(record.postDispatch, 'completed');
    assert.deepEqual(record.dispatch!.evidenceKinds, ['snapshot', 'driver']);
    assert.equal(record.settlement, undefined);
    assert.equal(ledger.settled(1), false);
  });

  it('noteDriverField with effectConfirmedBy none leaves settlement alone', () => {
    const ledger = new ProvenanceLedger();
    ledger.noteDispatch(1, { candidateId: 'click-x', tool: 'click', evidenceKinds: ['snapshot'] });
    ledger.noteDriverField(1, {
      actionId: 'click-x',
      observedBeforeEffect: false,
      observedAfterEffect: false,
      effectConfirmedBy: 'none',
      status: 'completed',
    });
    assert.equal(ledger.step(1)!.settlement, undefined);
    assert.equal(ledger.settled(1), false);
  });

  it('noteDriverField never demotes a fixture-confirmed settlement', () => {
    const ledger = new ProvenanceLedger();
    ledger.noteDispatch(1, { candidateId: 'submit-form', tool: 'click', evidenceKinds: ['visual'] });
    ledger.noteSettlement(1, { verifiedBy: 'fixture', latencyMs: 210.0 });
    ledger.noteDriverField(1, {
      actionId: 'submit-form',
      observedBeforeEffect: true,
      observedAfterEffect: true,
      effectConfirmedBy: 'capture-compare',
      status: 'completed',
    });
    assert.equal(ledger.step(1)!.settlement!.verifiedBy, 'fixture');
  });

  it('handoff serializes every step for a router', () => {
    const ledger = new ProvenanceLedger();
    ledger.recordObservation(1, { kind: 'snapshot', latencyMs: 1.0 });
    ledger.noteDispatch(1, { candidateId: 'fill-form', tool: 'fill', evidenceKinds: ['snapshot'] });
    ledger.noteSettlement(1, { verifiedBy: 'snapshot-diff', latencyMs: 2.0 });
    const json = JSON.parse(JSON.stringify(ledger.handoff()));
    assert.equal(json.length, 1);
    assert.equal(json[0].dispatch.candidateId, 'fill-form');
    assert.equal(json[0].settlement.verifiedBy, 'snapshot-diff');
  });

  it('returns undefined for an unrecorded step', () => {
    const ledger = new ProvenanceLedger();
    assert.equal(ledger.step(9), undefined);
    assert.equal(ledger.settled(9), false);
    assert.deepEqual(snapshot(1), { kind: 'snapshot', latencyMs: 1.5, step: 1 });
  });
});
