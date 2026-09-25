import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
  observeCombined,
  observeParallel,
  observeSequential,
  type CallFn,
  type ObserveStepArgs,
} from './batched.js';

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

/** Fake transport: records issuance order, resolves from a script. */
function fakeTransport(script: Record<string, Record<string, any>>, issued: string[]): CallFn {
  return async (name, args) => {
    issued.push(name);
    if (name === 'get_window_state') return { capture_id: 'cap-1' };
    if (name === 'parse_visual_regions') return visualWire(String(args.capture_id));
    if (name === 'observe_visual') return visualWire('cap-combined');
    const payload = script[name];
    if (!payload) throw new Error(`no script for ${name}`);
    return payload;
  };
}

describe('observeSequential', () => {
  it('issues snapshot, capture, parse in order and returns both', async () => {
    const issued: string[] = [];
    const call = fakeTransport({ get_browser_state: { target_id: 't', tab_id: 'tab', refs: [] } }, issued);
    const { snapshot, visual } = await observeSequential(call, ARGS);
    assert.deepEqual(issued, ['get_browser_state', 'get_window_state', 'parse_visual_regions']);
    assert.equal(snapshot.target_id, 't');
    assert.equal(visual.regions.length, 1);
    assert.equal(visual.captureId, 'cap-1');
  });
});

describe('observeParallel', () => {
  it('fires snapshot and capture before either resolves, and matches sequential output', async () => {
    const issued: string[] = [];
    // Deferred promises: capture must be issuable while snapshot is pending.
    const resolvers: Array<() => void> = [];
    const call: CallFn = async (name) => {
      issued.push(name);
      if (name === 'get_window_state') return { capture_id: 'cap-1' };
      if (name === 'parse_visual_regions') return visualWire('cap-1');
      return new Promise<Record<string, any>>((resolve) => {
        resolvers.push(() => resolve({ target_id: 't', tab_id: 'tab', refs: [] }));
      });
    };
    const pending = observeParallel(call, ARGS);
    // Let both concurrent calls issue before resolving the deferred snapshot.
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.ok(issued.includes('get_browser_state'), 'snapshot issued');
    assert.ok(issued.includes('get_window_state'), 'capture issued while snapshot pending');
    assert.ok(!issued.includes('parse_visual_regions'), 'parse waits for capture');
    for (const resolve of resolvers) resolve();
    const { snapshot, visual } = await pending;
    assert.deepEqual(issued, ['get_browser_state', 'get_window_state', 'parse_visual_regions']);
    assert.equal(snapshot.target_id, 't');
    assert.equal(visual.regions.length, 1);
  });

  it('propagates a capture failure instead of hanging on parse', async () => {
    const call: CallFn = async (name) => {
      if (name === 'get_window_state') throw new Error('capture failed');
      if (name === 'get_browser_state') return { target_id: 't', tab_id: 'tab', refs: [] };
      throw new Error(`unexpected ${name}`);
    };
    await assert.rejects(() => observeParallel(call, ARGS), /capture failed/);
  });
});

describe('observeCombined', () => {
  it('makes two calls and parses the combined payload', async () => {
    const issued: string[] = [];
    const call = fakeTransport({ get_browser_state: { target_id: 't', tab_id: 'tab', refs: [] } }, issued);
    const { snapshot, visual } = await observeCombined(call, ARGS);
    assert.deepEqual(issued, ['get_browser_state', 'observe_visual']);
    assert.equal(snapshot.target_id, 't');
    assert.equal(visual.regions.length, 1);
    assert.equal(visual.captureId, 'cap-combined');
  });

  it('rejects when the combined payload carries no capture_id', async () => {
    const call: CallFn = async (name) => {
      if (name === 'get_browser_state') return { target_id: 't' };
      return { regions: [] };
    };
    await assert.rejects(() => observeCombined(call, ARGS), /no capture_id/);
  });
});
