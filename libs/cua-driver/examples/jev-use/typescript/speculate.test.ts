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
    assert.deepEqual(speculator.stats(), { hits: 0, falsePositives: 0, misses: 0 });
  });

  it('is sticky: follows the previous step, not a longer history', () => {
    const speculator = new VisualSpeculator();
    speculator.observe(true);
    assert.equal(speculator.shouldSpeculate(), true);
    speculator.observe(true);
    assert.equal(speculator.shouldSpeculate(), true);
    speculator.observe(false);
    assert.equal(speculator.shouldSpeculate(), false);
    speculator.observe(false);
    assert.equal(speculator.shouldSpeculate(), false);
  });

  it('counts hits, false positives, and misses; the cold step counts none', () => {
    const speculator = new VisualSpeculator();
    speculator.observe(true); // cold step: predicts nothing, records nothing
    speculator.observe(true); // hit
    speculator.observe(false); // false positive
    speculator.observe(true); // miss
    assert.deepEqual(speculator.stats(), { hits: 1, falsePositives: 1, misses: 1 });
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
    assert.deepEqual(speculator.stats(), { hits: 1, falsePositives: 0, misses: 0 });
  });
});
