import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
  discardCapture,
  startSpeculativeCapture,
  visualFromCapture,
  VisualSpeculator,
  type CallFn,
  type ObserveStepArgs,
} from './speculate.js';

const ARGS: ObserveStepArgs = { targetId: 't', tabId: 'tab', pid: 4242, windowId: 7 };

function visualWire(captureId: string) {
  return {
    schema: 'cua.visual_regions_v1',
    capture_id: captureId,
    capture: {
      capture_id: captureId,
      source: { kind: 'window', pid: 4242, window_id: 7 },
      screenshot: {
        mime_type: 'image/png',
        reference: 'sha256:test',
        width: 1280,
        height: 800,
      },
      action_coordinate_space: { kind: 'screenshot_pixels' },
    },
    regions: [
      {
        id: 'v0',
        kind: 'text',
        text: 'Submit',
        confidence: 0.9,
        interactive: true,
        bounds: { x: 10, y: 20, width: 80, height: 30 },
      },
    ],
  };
}

describe('VisualSpeculator', () => {
  it('starts cold: no speculation before any observation', () => {
    const speculator = new VisualSpeculator();
    assert.equal(speculator.shouldSpeculate(), false);
    assert.deepEqual(speculator.stats(), { hits: 0, falsePositives: 0, misses: 0, suppressed: 0 });
    assert.equal(speculator.missRate(), undefined);
  });

  it('is sticky: follows the previous step, not a longer history', () => {
    const speculator = new VisualSpeculator();
    speculator.shouldSpeculate();
    speculator.observe(true);
    assert.equal(speculator.shouldSpeculate(), true);
    speculator.shouldSpeculate();
    speculator.observe(true);
    assert.equal(speculator.shouldSpeculate(), true);
    speculator.shouldSpeculate();
    speculator.observe(false);
    assert.equal(speculator.shouldSpeculate(), false);
    speculator.shouldSpeculate();
    speculator.observe(false);
    assert.equal(speculator.shouldSpeculate(), false);
  });

  it('counts hits, false positives, and misses against the actual decision', () => {
    const speculator = new VisualSpeculator();
    speculator.shouldSpeculate();
    speculator.observe(true); // cold step: nothing speculated -> miss
    speculator.shouldSpeculate();
    speculator.observe(true); // sticky yes -> hit
    speculator.shouldSpeculate();
    speculator.observe(false); // sticky yes, not needed -> false positive
    speculator.shouldSpeculate();
    speculator.observe(true); // sticky no, needed -> miss
    assert.deepEqual(speculator.stats(), { hits: 1, falsePositives: 1, misses: 2, suppressed: 0 });
    assert.equal(speculator.missRate(), 0.5);
  });

  it('a lone missRate of 1.0 after pure false positives', () => {
    const speculator = new VisualSpeculator();
    speculator.shouldSpeculate();
    speculator.observe(true);
    speculator.shouldSpeculate();
    speculator.observe(false); // false positive
    assert.equal(speculator.missRate(), 1);
  });
});

describe('miss-rate gate (confirmationSteps)', () => {
  it('clamps confirmationSteps to a positive integer', () => {
    assert.equal(new VisualSpeculator(0).confirmationSteps, 1);
    assert.equal(new VisualSpeculator(-3).confirmationSteps, 1);
    assert.equal(new VisualSpeculator(2.7).confirmationSteps, 2);
    assert.equal(new VisualSpeculator().confirmationSteps, 1);
  });

  it('with 2: an isolated visual need never triggers a wasted capture', () => {
    const speculator = new VisualSpeculator(2);
    speculator.shouldSpeculate();
    speculator.observe(true); // cold miss, one confirmed need
    assert.equal(speculator.shouldSpeculate(), false); // gate blocks the sticky yes
    speculator.observe(false); // nothing was speculated: no false positive
    assert.deepEqual(speculator.stats(), { hits: 0, falsePositives: 0, misses: 1, suppressed: 1 });
  });

  it('with 2: fires on a confirmed run, at the cost of one sequential step', () => {
    const speculator = new VisualSpeculator(2);
    speculator.shouldSpeculate();
    speculator.observe(true); // cold miss
    assert.equal(speculator.shouldSpeculate(), false); // suppressed: only one confirmed
    speculator.observe(true); // sequential miss
    assert.equal(speculator.shouldSpeculate(), true); // two confirmed -> fire
    speculator.observe(true); // hit
    assert.deepEqual(speculator.stats(), { hits: 1, falsePositives: 0, misses: 2, suppressed: 1 });
    assert.equal(speculator.missRate(), 0);
  });

  it('with 2: flickering need never fires (no repeated false positives)', () => {
    const speculator = new VisualSpeculator(2);
    for (let i = 0; i < 6; i += 1) {
      speculator.shouldSpeculate();
      speculator.observe(i % 2 === 0); // T,F,T,F,T,F
    }
    assert.deepEqual(speculator.stats(), { hits: 0, falsePositives: 0, misses: 3, suppressed: 3 });
  });

  it('with 2: still fires after the run ends (trailing false positive unchanged)', () => {
    const speculator = new VisualSpeculator(2);
    speculator.shouldSpeculate();
    speculator.observe(true);
    speculator.shouldSpeculate();
    speculator.observe(true);
    assert.equal(speculator.shouldSpeculate(), true); // run of 2 confirmed
    speculator.observe(false); // the run ended: one unavoidable false positive
    assert.deepEqual(speculator.stats(), { hits: 0, falsePositives: 1, misses: 2, suppressed: 1 });
  });
});

describe('startSpeculativeCapture', () => {
  it('returns undefined when the predictor says no', async () => {
    const issued: string[] = [];
    const call: CallFn = async (name: string) => {
      issued.push(name);
      return {};
    };
    const handle = startSpeculativeCapture(call, ARGS, false);
    assert.equal(handle, undefined);
    assert.deepEqual(issued, []);
  });

  it('fires get_window_state immediately when the predictor says yes', async () => {
    const issued: string[] = [];
    const call: CallFn = async (name: string) => {
      issued.push(name);
      return { capture_id: 'cap-9' };
    };
    const handle = startSpeculativeCapture(call, ARGS, true);
    assert.ok(handle instanceof Promise);
    assert.deepEqual(issued, ['get_window_state']);
    assert.equal((await handle).capture_id, 'cap-9');
  });
});

describe('visualFromCapture', () => {
  it('awaits the in-flight capture, then parses — one more RPC', async () => {
    const issued: string[] = [];
    const call: CallFn = async (name: string, args: Record<string, unknown>) => {
      issued.push(name);
      if (name === 'parse_visual_regions') return visualWire(String(args.capture_id));
      throw new Error(`unexpected ${name}`);
    };
    const capture = Promise.resolve({ capture_id: 'cap-3' });
    const visual = await visualFromCapture(call, capture, ARGS);
    assert.deepEqual(issued, ['parse_visual_regions']);
    assert.equal(visual.captureId, 'cap-3');
    assert.equal(visual.regions.length, 1);
  });

  it('rejects when the capture carried no capture_id', async () => {
    const call: CallFn = async () => ({});
    await assert.rejects(
      () => visualFromCapture(call, Promise.resolve({}), ARGS),
      /no capture_id/,
    );
  });

  it('propagates a capture failure to the caller', async () => {
    const call: CallFn = async () => ({});
    await assert.rejects(
      () => visualFromCapture(call, Promise.reject(new Error('capture died')), ARGS),
      /capture died/,
    );
  });
});

describe('discardCapture', () => {
  it('swallows a rejected unused capture: no unhandled rejection', async () => {
    let unhandled = 0;
    const listener = () => {
      unhandled += 1;
    };
    process.on('unhandledRejection', listener);
    try {
      discardCapture(Promise.reject(new Error('unused capture failed')));
      await new Promise((resolve) => setTimeout(resolve, 50));
      assert.equal(unhandled, 0);
    } finally {
      process.removeListener('unhandledRejection', listener);
    }
  });

  it('is a no-op on undefined', () => {
    discardCapture(undefined);
  });
});

describe('speculation policy over two steps', () => {
  it('step 2 fires the capture while the snapshot is still pending', async () => {
    const issued: string[] = [];
    const resolvers: Array<() => void> = [];
    const call: CallFn = async (name: string) => {
      issued.push(name);
      if (name === 'get_window_state') return { capture_id: 'cap-1' };
      if (name === 'parse_visual_regions') return visualWire('cap-1');
      return new Promise<Record<string, any>>((resolve) => {
        resolvers.push(() => resolve({ target_id: 't', tab_id: 'tab', refs: [] }));
      });
    };
    const speculator = new VisualSpeculator();

    // Step 1: cold, no speculation.
    const capture1 = startSpeculativeCapture(call, ARGS, speculator.shouldSpeculate());
    assert.equal(capture1, undefined);
    speculator.observe(true); // the step needed visual

    // Step 2: capture must issue while the snapshot is still deferred.
    const capture2 = startSpeculativeCapture(call, ARGS, speculator.shouldSpeculate());
    assert.ok(capture2 instanceof Promise);
    const snapshotPending = call('get_browser_state', {});
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.ok(issued.includes('get_window_state'), 'capture issued while snapshot pending');
    assert.ok(!issued.includes('parse_visual_regions'), 'parse waits for the visual decision');
    for (const resolve of resolvers) resolve();
    await snapshotPending;
    const visual = await visualFromCapture(call, capture2 as Promise<Record<string, any>>, ARGS);
    assert.equal(visual.regions.length, 1);
    speculator.observe(true);
    assert.deepEqual(speculator.stats(), { hits: 1, falsePositives: 0, misses: 1, suppressed: 0 });
  });
});
