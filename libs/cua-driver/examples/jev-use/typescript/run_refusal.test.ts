import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test, { mock } from 'node:test';
import { fileURLToPath } from 'node:url';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { FixtureFormTask } from './tasks.js';

const TOKEN = 'fix01-private-token';
const STALE_TEXT = "refused (browser_ref_stale): the ref's node is no longer connected to the document";

type Refusal =
  | 'stale'
  | 'trust_unknown'
  | 'not_retryable'
  | 'post_assignment'
  | 'post_assignment_f6'
  | 'delivery_unknown_only'
  | 'not_delivered';
type Scenario = {
  refuseClicks?: number;
  clickLands?: boolean;
  typeKept?: boolean;
  refusal?: Refusal;
  // The refused click's effect lands anyway (FIX-04 Part B).
  refusedLands?: boolean;
};

const TRUST_UNKNOWN_TEXT =
  'refused (browser_input_trust_unavailable): trusted click was acknowledged but CDP focus ' +
  'emulation could not be restored (x); delivery is unknown and must not be retried automatically';

const POST_ASSIGNMENT_TEXT =
  "refused (browser_ref_stale): the ref's node was not connected to the document after the " +
  'file assignment; the files may have been assigned to the detached node, so delivery is ' +
  'unknown and must not be retried automatically';

// A status-refused browser envelope with a refusal detail (FIX-03 F5 / FIX-04 shapes).
const detailRefusal = (detail: Record<string, unknown>, effect?: string, text = POST_ASSIGNMENT_TEXT) => ({
  content: [{ type: 'text', text }],
  structuredContent: {
    status: 'refused',
    refusal: { code: 'browser_ref_stale', detail },
    ...(effect ? { effect } : {}),
  },
});

// An action result as the Driver's MCP boundary emits it: not an MCP error.
const refusedResult = (kind: Refusal = 'stale') =>
  kind === 'post_assignment'
    ? detailRefusal({ delivery: 'unknown', retryable: false })
    : kind === 'post_assignment_f6'
      ? detailRefusal({ delivery: 'unknown', retryable: false }, 'unverifiable')
      : kind === 'delivery_unknown_only'
        ? detailRefusal({ delivery: 'unknown' })
        : kind === 'not_delivered'
          ? detailRefusal({ delivery: 'not_delivered' }, undefined, STALE_TEXT)
          : legacyRefusedResult(kind);

const legacyRefusedResult = (kind: Refusal) =>
  kind === 'not_retryable'
    ? {
        content: [{ type: 'text', text: 'refused (browser_reconnect_exhausted): x' }],
        structuredContent: {
          status: 'refused',
          refusal: { code: 'browser_reconnect_exhausted', detail: { retryable: false } },
        },
      }
    : {
        content: [{ type: 'text', text: kind === 'stale' ? STALE_TEXT : TRUST_UNKNOWN_TEXT }],
        structuredContent: { effect: 'refused', route: kind === 'stale' ? 'dom' : 'trusted_input' },
      };

async function runFixture(scenario: Scenario, log: string) {
  let value = '';
  let submitted: string | null = null;
  let observations = 0;
  let refuseClicks = scenario.refuseClicks ?? 0;
  const calls: string[] = [];

  mock.method(FixtureFormTask.prototype, 'reset', async () => {});
  mock.method(FixtureFormTask.prototype, 'readOracle', async () => ({ submitted }));
  mock.method(Client.prototype, 'connect', async () => {});
  mock.method(Client.prototype, 'listTools', async () => ({ tools: [] }));
  mock.method(Client.prototype, 'close', async () => {
    console.error(JSON.stringify({ closed: true, calls }));
  });
  mock.method(globalThis, 'setTimeout', (resolve: () => void) => {
    resolve();
    return 0;
  });
  mock.method(
    Client.prototype,
    'callTool',
    async (request: { name: string; arguments: Record<string, unknown> }) => {
      const { name, arguments: args } = request;
      calls.push(name);
      let data: Record<string, unknown> = {};
      if (name === 'browser_prepare') data = { prepared_pid: 42 };
      else if (name === 'list_windows') {
        data = {
          windows: [{ window_id: 7, is_on_screen: true, bounds: { width: 800, height: 600 } }],
        };
      } else if (name === 'get_browser_state') {
        if (args.snapshot_format !== 'semantic_v2') {
          data = { target_id: 'target', tabs: [{ tab_id: 'tab', active: true }] };
        } else {
          observations += 1;
          data = {
            target_id: 'target',
            tab_id: 'tab',
            refs: [
              { role: 'textbox', name: 'verification value', ref: `p${observations}:0`, value },
              { role: 'button', name: 'Submit', ref: `p${observations}:1` },
            ],
          };
        }
      } else if (name === 'browser_type') {
        if (scenario.typeKept !== false) value = String(args.text);
        data = { effect: 'unverifiable', route: 'trusted_input' };
      } else if (name === 'browser_click') {
        if (refuseClicks > 0) {
          refuseClicks -= 1;
          if (scenario.refusedLands) submitted = value;
          return refusedResult(scenario.refusal);
        }
        if (scenario.clickLands !== false) submitted = value;
        data = { effect: 'unverifiable', route: 'dom' };
      } else if (name !== 'browser_navigate') {
        throw new Error(`unexpected Driver tool ${name}`);
      }
      return { content: [], structuredContent: data };
    }
  );

  process.argv = [
    process.execPath,
    fileURLToPath(new URL('./run.ts', import.meta.url)),
    '--provider',
    'mock',
    '--visual-observation',
    'off',
    '--token',
    TOKEN,
    '--max-steps',
    '4',
    '--log',
    log,
  ];
  await import('./run.js');
}

function runScenario(scenario: Scenario = {}) {
  const directory = mkdtempSync(join(tmpdir(), 'jev-refusal-run-'));
  try {
    const log = join(directory, 'events.jsonl');
    const child = spawnSync(
      process.execPath,
      ['--import', 'tsx', fileURLToPath(import.meta.url), '--fixture-run', JSON.stringify(scenario), log],
      { encoding: 'utf8', timeout: 15_000 }
    );
    assert.equal(child.error, undefined);
    const events: Record<string, any>[] = readFileSync(log, 'utf8')
      .trim()
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line));
    const receipt = JSON.parse(
      child.stderr
        .trim()
        .split('\n')
        .find((line) => line.startsWith('{')) ?? '{}'
    );
    assert.equal(receipt.closed, true, child.stderr);
    const mutations = (receipt.calls as string[]).filter((name) =>
      ['browser_type', 'browser_click'].includes(name)
    );
    return { events, calls: receipt.calls as string[], mutations, status: child.status };
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

if (process.argv[2] === '--fixture-run') {
  await runFixture(JSON.parse(process.argv[3]), process.argv[4]);
} else {
  const { Driver, DriverToolError } = await import('./run.js');
  const driverFor = (result: Record<string, unknown>) =>
    new Driver({ callTool: async () => result } as unknown as Client, 'jev-ts-test');

  test('effect refused without isError is a refusal, not success', async () => {
    await assert.rejects(
      driverFor(refusedResult()).call('browser_click', { ref: 'p1:1' }),
      (error: unknown) =>
        error instanceof DriverToolError && error.refused && error.code === 'browser_ref_stale'
    );
  });

  test('status refused envelope keeps its structured code', async () => {
    await assert.rejects(
      driverFor({
        content: [],
        structuredContent: { status: 'refused', refusal: { code: 'browser_binding_stale' } },
      }).call('browser_click', {}),
      (error: unknown) =>
        error instanceof DriverToolError && error.refused && error.code === 'browser_binding_stale'
    );
  });

  test('accepted unverifiable result is returned and MCP errors are not refusals', async () => {
    const data = await driverFor({
      content: [],
      structuredContent: { effect: 'unverifiable', route: 'dom' },
    }).call('browser_click', {});
    assert.equal(data.effect, 'unverifiable');
    await assert.rejects(
      driverFor({ isError: true, content: [], structuredContent: { code: 'x' } }).call('browser_click', {}),
      (error: unknown) => error instanceof DriverToolError && !error.refused
    );
  });

  test('one refusal gets one fresh observation and one fresh dispatch', () => {
    const { events, calls, mutations, status } = runScenario({ refuseClicks: 1 });
    assert.equal(status, 0);
    assert.deepEqual(mutations, ['browser_type', 'browser_click', 'browser_click']);
    const refused = events.filter((event) => event.action_refused);
    assert.equal(refused.length, 1);
    assert.equal(refused[0].event, 'step');
    assert.equal(refused[0].action_refused, 'browser_ref_stale');
    const clicks = calls.flatMap((name, index) => (name === 'browser_click' ? [index] : []));
    assert.ok(calls.slice(clicks[0] + 1, clicks[1]).includes('get_browser_state'));
  });

  test('retryable is read from the refusal detail', async () => {
    await assert.rejects(
      driverFor(refusedResult('not_retryable')).call('browser_click', {}),
      (error: unknown) =>
        error instanceof DriverToolError &&
        error.refused &&
        error.code === 'browser_reconnect_exhausted' &&
        error.retryable === false
    );
  });

  test('a refusal whose delivery is unknown ends unknown without a re-dispatch', () => {
    const { events, mutations, status } = runScenario({ refuseClicks: 1, refusal: 'trust_unknown' });
    assert.equal(status, 1);
    assert.deepEqual(mutations, ['browser_type', 'browser_click']);
    assert.equal(events.at(-1)?.outcome, 'unknown');
    assert.equal(events.at(-1)?.action_refused, 'browser_input_trust_unavailable');
  });

  test('a refusal marked not retryable ends unknown without a re-dispatch', () => {
    const { events, mutations, status } = runScenario({ refuseClicks: 1, refusal: 'not_retryable' });
    assert.equal(status, 1);
    assert.deepEqual(mutations, ['browser_type', 'browser_click']);
    assert.equal(events.at(-1)?.outcome, 'unknown');
    assert.equal(events.at(-1)?.action_refused, 'browser_reconnect_exhausted');
  });

  test('second refusal stops without another dispatch', () => {
    const { events, mutations, status } = runScenario({ refuseClicks: 2 });
    assert.equal(status, 1);
    assert.deepEqual(mutations, ['browser_type', 'browser_click', 'browser_click']);
    assert.equal(events.at(-1)?.phase, 'refused');
    assert.equal(events.at(-1)?.outcome, 'unknown');
  });

  test('unconfirmed accepted click is never dispatched again', () => {
    const { events, mutations, status } = runScenario({ clickLands: false });
    assert.equal(status, 1);
    assert.deepEqual(mutations, ['browser_type', 'browser_click']);
    assert.deepEqual(events.at(-1), { event: 'outcome', outcome: 'unknown', step: 2, phase: 'reconcile' });
  });

  test('accepted mutation is not repeated on a fresh ref', () => {
    const { events, mutations, status } = runScenario({ typeKept: false });
    assert.equal(status, 1);
    assert.deepEqual(mutations, ['browser_type']);
    assert.equal(events.at(-1)?.phase, 'redispatch_blocked');
  });

  // FIX-04 Part B (kvnloo/cua#105): a post-assignment refusal may have landed.
  for (const refusal of ['post_assignment', 'post_assignment_f6'] as const) {
    test(`a ${refusal} refusal is reconciled from state, not re-dispatched`, () => {
      const { events, mutations, status } = runScenario({ refuseClicks: 1, refusal, refusedLands: true });
      assert.equal(status, 0);
      assert.deepEqual(mutations, ['browser_type', 'browser_click']);
      assert.equal(events.at(-1)?.outcome, 'verified');
      assert.equal(events.at(-1)?.phase, 'reconcile');
      assert.equal(events.at(-1)?.action_refused, 'browser_ref_stale');
    });
  }

  test('a post-assignment refusal that did not land ends unknown after reconcile', () => {
    const { events, mutations, status } = runScenario({ refuseClicks: 1, refusal: 'post_assignment' });
    assert.equal(status, 1);
    assert.deepEqual(mutations, ['browser_type', 'browser_click']);
    assert.equal(events.at(-1)?.outcome, 'unknown');
    assert.equal(events.at(-1)?.phase, 'reconcile');
  });

  test('a declared unknown delivery without retryable is never re-dispatched', () => {
    const { events, mutations, status } = runScenario({ refuseClicks: 1, refusal: 'delivery_unknown_only' });
    assert.equal(status, 1);
    assert.deepEqual(mutations, ['browser_type', 'browser_click']);
    assert.equal(events.at(-1)?.outcome, 'unknown');
  });

  test('a pre-dispatch refusal declared not delivered may be rebound once', () => {
    const { events, mutations, status } = runScenario({ refuseClicks: 1, refusal: 'not_delivered' });
    assert.equal(status, 0);
    assert.deepEqual(mutations, ['browser_type', 'browser_click', 'browser_click']);
    assert.deepEqual(
      events.filter((event) => event.action_refused).map((event) => event.event),
      ['step']
    );
  });

  test('ordinary path is unchanged', () => {
    const { events, mutations, status } = runScenario();
    assert.equal(status, 0);
    assert.deepEqual(mutations, ['browser_type', 'browser_click']);
    assert.equal(
      events.some((event) => event.action_refused),
      false
    );
  });
}
