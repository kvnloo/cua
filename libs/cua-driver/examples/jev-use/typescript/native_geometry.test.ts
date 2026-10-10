// Mirrors python/tests/test_native_geometry.py. No native Driver or host input.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { CallToolResultSchema } from '@modelcontextprotocol/sdk/types.js';
import { parseWindowState } from './native.js';
import type { Platform } from './native_roles.js';
import { nativeTask } from './native_tasks.js';
import { runTask } from './run_native.js';
import { NativeAccessibilitySource } from './sources.js';

const MARKER = '__geometry_number__';
const INVALID_JSON_NUMBERS = ['1e309', '-1e309', `1${'0'.repeat(400)}`];
const INVALID_JSON_TYPES = ['null', 'true', 'false', '"20"'];
const PLATFORMS: Platform[] = ['macos', 'windows', 'linux'];

function resultFromWire(payload: Record<string, any>, valueJson: string) {
  const wire = JSON.stringify({ isError: false, structuredContent: payload, content: [] });
  return CallToolResultSchema.parse(JSON.parse(wire.replace(JSON.stringify(MARKER), valueJson)));
}

function windowState(): Record<string, any> {
  return {
    pid: 7,
    window_id: 9,
    snapshot_id: 's1',
    capture_id: 'cap-1',
    elements_complete: true,
    window_bounds: { x: 0, y: 0, width: 100, height: 100 },
    elements: [
      {
        element_index: 0,
        role: 'button',
        label: 'Increment',
        enabled: true,
        element_token: 's1:0',
        frame: { x: 0, y: 0, w: 20, h: 20 },
      },
    ],
  };
}

function sourceFromWire(payload: Record<string, any>, valueJson: string, platform: Platform) {
  const data = resultFromWire(payload, valueJson).structuredContent!;
  return NativeAccessibilitySource.fromObservation(parseWindowState(data, 7, 9), platform);
}

test('invalid JSON numbers and types cannot supply native candidates', () => {
  for (const valueJson of [...INVALID_JSON_NUMBERS, ...INVALID_JSON_TYPES]) {
    for (const platform of PLATFORMS) {
      for (const [owner, fields] of [
        ['frame', ['x', 'y', 'w', 'h']],
        ['window_bounds', ['x', 'y', 'width', 'height']],
      ] as const) {
        for (const field of fields) {
          const payload = windowState();
          const rect = owner === 'frame' ? payload.elements[0].frame : payload[owner];
          rect[field] = MARKER;
          const source = sourceFromWire(payload, valueJson, platform);
          assert.equal(
            source.find('button', 'Increment'),
            undefined,
            `${platform}:${owner}:${field}:${valueJson}`
          );
          assert.deepEqual(source.native.excluded, { off_screen: 1 });
        }
      }
    }
  }
});

test('nonstandard numbers are rejected by JavaScript before the MCP schema', () => {
  for (const valueJson of ['NaN', 'Infinity', '-Infinity']) {
    const payload = windowState();
    payload.elements[0].frame.w = MARKER;
    assert.throws(() => resultFromWire(payload, valueJson), SyntaxError);
  }
});

test('finite native frames retain existing geometry rules', () => {
  const cases: [Record<string, number>, boolean][] = [
    [{ x: 0, y: 0, w: 20, h: 20 }, true],
    [{ x: -5, y: -5, w: 20, h: 20 }, true],
    [{ x: 0, y: 0, w: Number.MAX_VALUE, h: 20 }, true],
    [{ x: 0, y: 0, w: Number.MIN_VALUE, h: Number.MIN_VALUE }, true],
    [{ x: 0, y: 0, w: 0, h: 20 }, false],
    [{ x: 0, y: 0, w: 20, h: -1 }, false],
    [{ x: 101, y: 0, w: 20, h: 20 }, false],
  ];
  for (const platform of PLATFORMS) {
    for (const [frame, expected] of cases) {
      const payload = windowState();
      payload.elements[0].frame = frame;
      const source = sourceFromWire(payload, '0', platform);
      const control = source.find('button', 'Increment');
      assert.equal(Boolean(control), expected, `${platform}:${JSON.stringify(frame)}`);
      if (control) {
        assert.deepEqual(source.click(control, 'increment', 'Increment').arguments, {
          pid: 7,
          window_id: 9,
          element_token: 's1:0',
          delivery_mode: 'background',
        });
      }
    }
  }
});

test('native runner never dispatches invalid geometry and finite control does', async (context) => {
  for (const valueJson of [...INVALID_JSON_NUMBERS, '20']) {
    await context.test(valueJson.slice(0, 24), async (t) => {
      const directory = await mkdtemp(join(tmpdir(), 'jev-native-geometry-'));
      try {
        const payload = JSON.parse(
          readFileSync(
            new URL('../fixtures/native/gtk3-window-state-initial-v1.json', import.meta.url),
            'utf8'
          )
        );
        payload.elements.find((item: any) => item.label === 'Increment').frame.w = MARKER;
        const statePath = join(directory, 'state.json');
        const logPath = join(directory, 'run.jsonl');
        const task = nativeTask('gtk3-counter', statePath, { pid: payload.pid });
        const state = { schema: task.oracle.schema, pid: payload.pid, counter: 0 };
        await writeFile(statePath, JSON.stringify(state));
        const actions: Record<string, any>[] = [];
        const reads: Record<string, any>[] = [];
        t.mock.method(Client.prototype, 'connect', async () => {});
        t.mock.method(Client.prototype, 'close', async () => {});
        t.mock.method(Client.prototype, 'listTools', async () => ({ tools: [] }));
        t.mock.method(console, 'log', () => {});
        t.mock.method(
          Client.prototype,
          'callTool',
          async (request: { name: string; arguments?: Record<string, any> }) => {
            let data: Record<string, any>;
            if (request.name === 'list_windows') {
              data = { windows: [{ window_id: payload.window_id, title: task.scope.windowTitle }] };
            } else if (request.name === 'get_window_state') {
              reads.push({ ...request.arguments });
              return resultFromWire(structuredClone(payload), valueJson);
            } else if (request.name === 'click') {
              actions.push({ ...request.arguments });
              state.counter = 3;
              await writeFile(statePath, JSON.stringify(state));
              data = { effect: 'confirmed' };
            } else {
              throw new Error(`unexpected tool ${request.name}`);
            }
            return resultFromWire(data, '0');
          }
        );
        const outcome = await runTask(
          {
            task: task.id,
            provider: 'mock',
            pid: payload.pid,
            stateFile: statePath,
            allowForeground: false,
            platform: 'linux',
            log: logPath,
          },
          task
        );
        const finite = valueJson === '20';
        assert.equal(outcome, finite ? 'verified' : 'budget_exhausted');
        assert.equal(actions.length, finite ? 1 : 0);
        assert.equal(reads.length, finite ? 1 : task.maxSteps);
        assert.equal(JSON.parse(await readFile(statePath, 'utf8')).counter, finite ? 3 : 0);
        const events = (await readFile(logPath, 'utf8'))
          .trim()
          .split('\n')
          .map((line) => JSON.parse(line));
        const steps = events.filter((event) => event.event === 'step');
        assert.deepEqual(
          steps.map((event) => event.candidate),
          finite ? ['ax:button:increment'] : Array(task.maxSteps).fill('reobserve')
        );
        if (!finite) assert.ok(steps.every((event) => event.expected_offered === false));
      } finally {
        await rm(directory, { recursive: true, force: true });
      }
    });
  }
});
