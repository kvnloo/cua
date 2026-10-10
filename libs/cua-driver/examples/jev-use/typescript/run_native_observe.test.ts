import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { DriverToolError, type Driver } from './run.js';
import { observe } from './run_native.js';
import { eligibleControls } from './native.js';
import type { NativeTask } from './native_tasks.js';

const fixture = JSON.parse(
  readFileSync(new URL('../fixtures/native/appkit-window-state-initial-v1.json', import.meta.url), 'utf8')
) as Record<string, any>;
const pid = Number(fixture.pid);
const windowId = Number(fixture.window_id);
const task = { scope: { windowTitle: 'Fixture' } } as unknown as NativeTask;

function mockDriver(rejectFull = false, rejectOther = false) {
  const calls: Record<string, unknown>[] = [];
  const driver = {
    async call(name: string, args: Record<string, unknown>) {
      assert.equal(name, 'get_window_state');
      calls.push({ ...args });
      if (rejectOther) throw new DriverToolError('get_window_state failed: permission denied', 'permission_denied');
      if (rejectFull && args.full_output === true) {
        throw new DriverToolError('get_window_state failed: unknown argument full_output');
      }
      return fixture;
    },
  } as unknown as Driver;
  return { driver, calls };
}

test('native observe requests a full 0.35 window response', async () => {
  const { driver, calls } = mockDriver();
  const result = await observe(driver, task, pid, windowId, 5000);
  assert.ok(result.elements.length > 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].full_output, true);
  assert.equal(calls[0].timeout_ms, 5000);
  assert.equal(calls[0].include_screenshot, true);
});

test('native observe falls back only for pre-0.35 unknown full_output', async () => {
  const { driver, calls } = mockDriver(true);
  const result = await observe(driver, task, pid, windowId, 5000);
  assert.ok(result.elements.length > 0);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].full_output, true);
  assert.equal(Object.hasOwn(calls[1], 'full_output'), false);
  assert.equal(calls[1].timeout_ms, 5000);
  assert.equal(calls[1].include_accessibility_tree, true);
});

test('native observe does not retry unrelated Driver refusals', async () => {
  const { driver, calls } = mockDriver(false, true);
  await assert.rejects(observe(driver, task, pid, windowId), (error: unknown) =>
    error instanceof DriverToolError && error.code === 'permission_denied'
  );
  assert.equal(calls.length, 1);
});

// Same synthetic observation as Python: the lean default must not lose candidates.
test('native observe preserves candidates against a lean-by-default 0.35 Driver', async () => {
  const calls: Record<string, unknown>[] = [];
  const driver = {
    async call(_name: string, args: Record<string, unknown>) {
      calls.push({ ...args });
      const payload = structuredClone(fixture);
      if (!args.full_output) {
        delete payload.elements;
        delete payload.elements_complete;
      }
      return payload;
    },
  } as unknown as Driver;
  const result = await observe(driver, task, pid, windowId);
  assert.ok(eligibleControls(result, 'macos').controls.some((c) => c.id === 'ax:button:increment'));
  assert.equal(calls.length, 1);
});
