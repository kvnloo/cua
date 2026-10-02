/**
 * Runner hardening for a possibly landed completion (kvnloo/cua#105).
 *
 * The Driver is an in-memory double, but every tools/call is first handed to
 * the runner's StdioClientTransport.send, exactly where the SDK writes it. That
 * send is the simulated seam. The fixture oracle counts every submission.
 * Rows mirror python/tests/test_runner_reconcile.py.
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test, { mock } from 'node:test';
import { fileURLToPath } from 'node:url';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { FixtureFormTask } from './tasks.js';

const TOKEN = 'private-reconcile-canary-105';

type Click =
  | 'ok'
  | 'ack-lost'
  | 'ack-lost-late'
  | 'ack-lost-never'
  | 'withheld'
  | 'pre-write'
  | 'pre-write-twice'
  | 'post-write-raise';

type Scenario = { click: Click; readErrorAfterClick?: boolean };

async function runFixture(scenario: Scenario, log: string) {
  let value = '';
  let submitted: string | null = null;
  let prepares = 0;
  let observations = 0;
  let clicksWritten = 0;
  let clicked = false;
  let latePending = false;
  let oracleReadsAfterClick = 0;
  let requestId = 0;

  mock.method(FixtureFormTask.prototype, 'reset', async () => {});
  mock.method(FixtureFormTask.prototype, 'readOracle', async () => {
    if (clicked) oracleReadsAfterClick += 1;
    const state = { submitted };
    // The first unchanged read has been served; now the effect lands.
    if (latePending && submitted === null) {
      latePending = false;
      submitted = value;
    }
    return state;
  });
  mock.method(Client.prototype, 'connect', async function (this: any, transport: unknown) {
    this.seamTransport = transport;
  });
  mock.method(Client.prototype, 'listTools', async () => ({ tools: [] }));
  let closes = 0;
  mock.method(Client.prototype, 'close', async () => {
    closes += 1;
  });
  // Report the target counters once the run is over, after any reconciliation.
  process.on('exit', () => {
    console.error(
      JSON.stringify({ closes, prepares, clicksWritten, oracleReadsAfterClick, submitted })
    );
  });
  mock.method(
    StdioClientTransport.prototype,
    'send',
    async (message: { method?: string; params?: { name?: string } }) => {
      if (
        message.params?.name === 'browser_click' &&
        (scenario.click === 'pre-write-twice' || (scenario.click === 'pre-write' && prepares === 1))
      ) {
        // StdioClientTransport.send throws this before writing when stdin is gone.
        throw new Error('Not connected');
      }
    }
  );
  mock.method(
    Client.prototype,
    'callTool',
    async function (this: any, request: { name: string; arguments: Record<string, unknown> }) {
      const { name, arguments: args } = request;
      requestId += 1;
      await this.seamTransport.send({
        jsonrpc: '2.0',
        id: requestId,
        method: 'tools/call',
        params: { name },
      });
      let data: Record<string, unknown> = {};
      if (name === 'browser_prepare') {
        prepares += 1;
        value = ''; // a fresh session launches a fresh browser
        data = { prepared_pid: prepares };
      } else if (name === 'list_windows') {
        data = {
          windows: [{ window_id: 7, is_on_screen: true, bounds: { width: 800, height: 600 } }],
        };
      } else if (name === 'get_browser_state') {
        if (args.snapshot_format !== 'semantic_v2') {
          data = { target_id: 'target', tabs: [{ tab_id: 'tab', active: true }] };
        } else {
          observations += 1;
          if (clicked && scenario.readErrorAfterClick) {
            return { isError: true, content: [{ type: 'text', text: 'injected read failure' }] };
          }
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
        value = String(args.text);
      } else if (name === 'browser_click') {
        clicksWritten += 1;
        clicked = true;
        if (['ok', 'ack-lost', 'post-write-raise', 'pre-write'].includes(scenario.click)) {
          submitted = value;
        }
        if (scenario.click === 'ack-lost-late') latePending = true;
        if (['ack-lost', 'ack-lost-late', 'ack-lost-never'].includes(scenario.click)) {
          return {
            isError: true,
            content: [{ type: 'text', text: 'simulated acknowledgement loss' }],
          };
        }
        // Same class and message as the pre-write failure, but after the write.
        if (scenario.click === 'post-write-raise') throw new Error('Not connected');
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
    '--guarded-completion',
  ];
  await import('./run.js');
}

function runScenario(scenario: Scenario) {
  const directory = mkdtempSync(join(tmpdir(), 'jev-reconcile-run-'));
  try {
    const log = join(directory, 'events.jsonl');
    const child = spawnSync(
      process.execPath,
      [
        '--import',
        'tsx',
        fileURLToPath(import.meta.url),
        '--fixture-run',
        JSON.stringify(scenario),
        log,
      ],
      { encoding: 'utf8', timeout: 30_000 }
    );
    assert.equal(child.error, undefined);
    const jsonl = readFileSync(log, 'utf8');
    const events: Record<string, any>[] = jsonl
      .trim()
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line));
    const target = JSON.parse(
      child.stderr
        .trim()
        .split('\n')
        .filter((line) => line.startsWith('{'))
        .at(-1) ?? '{}'
    );
    // Every attempt closes its client.
    assert.equal(target.closes, target.prepares, child.stderr);
    assert.equal(jsonl.includes(TOKEN), false);
    return { events, target, status: child.status, stderr: child.stderr };
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

function assertReceipt(
  event: Record<string, any>,
  resolution: string,
  fields: Record<string, unknown> = {}
) {
  const receipt = event.mutation_outcome;
  assert.ok(receipt, JSON.stringify(event));
  assert.equal(receipt.receiptKind, 'mutation-outcome/v0');
  assert.equal(receipt.mutationKey, '2:submit-form');
  assert.match(receipt.authorityScope, /^jev-typescript-/);
  assert.equal(receipt.resolution, resolution);
  for (const [key, value] of Object.entries(fields)) assert.equal(receipt[key], value, key);
}

if (process.argv[2] === '--fixture-run') {
  await runFixture(JSON.parse(process.argv[3]), process.argv[4]);
} else {
  test('R0 acknowledged completion ends with a verified receipt', () => {
    const { events, target, status, stderr } = runScenario({ click: 'ok' });
    assert.equal(status, 0, stderr);
    assert.equal(target.submitted, TOKEN);
    assert.equal(target.clicksWritten, 1);
    assert.equal(events.at(-1)!.outcome, 'verified');
    assertReceipt(events.at(-1)!, 'verified', {
      attempted: true,
      effect: 'applied',
      verification: 'verified',
      retryDisposition: 'none',
    });
  });

  test('R1 acknowledgement lost after the effect reconciles to verified', () => {
    const { events, target, status } = runScenario({ click: 'ack-lost' });
    assert.equal(status, 0);
    assert.equal(target.submitted, TOKEN);
    assert.equal(target.clicksWritten, 1);
    assert.ok(target.oracleReadsAfterClick >= 1);
    assert.equal(events.at(-1)!.phase, 'action');
    assertReceipt(events.at(-1)!, 'verified', { effect: 'applied' });
  });

  test('R2 effect after the first unchanged read is reconciled without a second dispatch', () => {
    const { events, target, status } = runScenario({ click: 'ack-lost-late' });
    assert.equal(status, 0);
    assert.equal(target.submitted, TOKEN);
    assert.equal(target.clicksWritten, 1);
    assert.ok(target.oracleReadsAfterClick >= 2);
    assertReceipt(events.at(-1)!, 'verified');
  });

  test('R3 effect past the deadline stays unresolved without retry', () => {
    const { events, target, status } = runScenario({ click: 'ack-lost-never' });
    assert.equal(status, 1);
    assert.equal(target.submitted, null);
    assert.equal(target.clicksWritten, 1);
    assert.equal(target.prepares, 1);
    assert.ok(target.oracleReadsAfterClick > 2);
    assert.equal(events.at(-1)!.outcome, 'unknown');
    assertReceipt(events.at(-1)!, 'unresolved_unknown', {
      attempted: true,
      effect: 'unknown',
      verification: 'unverified',
      retryDisposition: 'observe',
    });
  });

  test('R4 read failure after an unverified completion emits a receipt', () => {
    const { events, target, status } = runScenario({ click: 'withheld', readErrorAfterClick: true });
    assert.equal(status, 1);
    assert.equal(target.clicksWritten, 1);
    assert.equal(events.at(-1)!.event, 'outcome');
    assert.equal(events.at(-1)!.outcome, 'unknown');
    assert.equal(events.at(-1)!.error, 'DriverToolError');
    assertReceipt(events.at(-1)!, 'unresolved_unknown', { effect: 'unknown' });
  });

  test('R5 re-planned completion is not dispatched while unresolved', () => {
    const { events, target, status } = runScenario({ click: 'withheld' });
    assert.equal(status, 1);
    assert.equal(target.clicksWritten, 1);
    assert.equal(events.at(-1)!.phase, 'completion_blocked');
    assertReceipt(events.at(-1)!, 'unresolved_unknown', { retryDisposition: 'observe' });
  });

  test('R6 own write raised allows exactly one reconsideration', () => {
    const { events, target, status } = runScenario({ click: 'pre-write' });
    assert.equal(status, 0);
    assert.equal(target.submitted, TOKEN);
    assert.equal(target.prepares, 2);
    assert.equal(target.clicksWritten, 1);
    const reconsider = events.filter((event) => event.event === 'reconsider');
    assert.equal(reconsider.length, 1);
    assertReceipt(reconsider[0], 'pre_write_failed', {
      attempted: false,
      effect: 'none',
      retryDisposition: 'reconsider',
    });
    assert.equal(events.at(-1)!.outcome, 'verified');
  });

  test('second pre-write failure is not reconsidered again', () => {
    const { events, target, status } = runScenario({ click: 'pre-write-twice' });
    assert.equal(status, 1);
    assert.equal(target.submitted, null);
    assert.equal(target.prepares, 2);
    assert.equal(target.clicksWritten, 0);
    assert.equal(events.filter((event) => event.event === 'reconsider').length, 1);
    assertReceipt(events.at(-1)!, 'pre_write_failed', { retryDisposition: 'none' });
  });

  test('the same error after the write is not pre-write proof', () => {
    const { events, target, status } = runScenario({ click: 'post-write-raise' });
    assert.equal(status, 0);
    assert.equal(target.submitted, TOKEN);
    assert.equal(target.prepares, 1);
    assert.equal(target.clicksWritten, 1);
    assert.equal(events.some((event) => event.event === 'reconsider'), false);
    assertReceipt(events.at(-1)!, 'verified');
  });
}
