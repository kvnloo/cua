/** Real loopback HTTP tests for the OpenJev adapter. */
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createServer } from 'node:http';
import test, { type TestContext } from 'node:test';

import { REQUEST_SCHEMA_V2 } from './choose_action.js';
import {
  MAX_OPENJEV_RESPONSE_BYTES,
  OpenJevDecisionModel,
  OpenJevError,
} from './openjev_model.js';

function request() {
  return {
    schema: REQUEST_SCHEMA_V2,
    goal: 'Submit.',
    capture_id: 'cap-1',
    snapshot_id: 'snap-1',
    regions: [],
    elements: [],
    progress: [],
    history: [],
    candidates: [
      { id: 'submit', description: 'Submit.', source: 'page' },
      { id: 'reobserve', description: 'Observe again.' },
      { id: 'abstain', description: 'Stop.' },
    ],
  };
}

function decision() {
  return {
    model: 'loopback-openjev',
    answers: {
      candidate: {
        type: 'choice',
        choice: 'submit',
        confidence: 0.9,
        probabilities: { submit: 0.9, reobserve: 0.05, abstain: 0.05 },
      },
    },
  };
}

type Mode = 'ok' | 'redirect' | '503' | 'malformed' | 'oversized' | 'stall';

async function fixture(t: TestContext, mode: Mode) {
  const received: Array<{ path?: string; authorization?: string; payload: unknown }> = [];
  const server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => chunks.push(chunk));
    req.on('end', () => {
      received.push({
        path: req.url,
        authorization: req.headers.authorization,
        payload: JSON.parse(Buffer.concat(chunks).toString('utf8')),
      });
      if (mode === 'stall') return;
      if (mode === 'redirect') {
        res.writeHead(307, { Location: '/other' });
        res.end();
        return;
      }
      if (mode === '503') {
        res.writeHead(503);
        res.end();
        return;
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      if (mode === 'malformed') res.end('not-json');
      else if (mode === 'oversized') res.end('{' + ' '.repeat(MAX_OPENJEV_RESPONSE_BYTES + 1) + '}');
      else res.end(JSON.stringify(decision()));
    });
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(async () => {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  });
  const address = server.address();
  assert.ok(address && typeof address !== 'string');
  return { url: 'http://127.0.0.1:' + address.port, received };
}

function model(url: string, timeoutMs = 1000) {
  return new OpenJevDecisionModel({
    baseUrl: url,
    apiKey: '',
    model: 'fixture-model',
    timeoutMs,
  });
}

test('real HTTP success posts current Cua request without credentials', { timeout: 5000 }, async (t) => {
  const f = await fixture(t, 'ok');
  const scores = await model(f.url).score(request());
  assert.equal(scores.selectedId, 'submit');
  assert.equal(scores.model, 'loopback-openjev');
  assert.equal(f.received.length, 1);
  assert.equal(f.received[0].path, '/v1/systemone');
  assert.equal(f.received[0].authorization, undefined);
  const sent = (f.received[0].payload as { state: { request: ReturnType<typeof request> } }).state.request;
  assert.equal(sent.schema, REQUEST_SCHEMA_V2);
  assert.deepEqual(sent.candidates.map(({ id }) => id), ['submit', 'reobserve', 'abstain']);
});

test('redirect is refused without repost', { timeout: 5000 }, async (t) => {
  const f = await fixture(t, 'redirect');
  await assert.rejects(
    model(f.url).score(request()),
    (error: unknown) => error instanceof OpenJevError && error.code === 'redirect_refused'
  );
  assert.equal(f.received.length, 1);
});

test('503 is bounded and not retried', { timeout: 5000 }, async (t) => {
  const f = await fixture(t, '503');
  await assert.rejects(
    model(f.url).score(request()),
    (error: unknown) => error instanceof OpenJevError && error.code === 'http_error'
  );
  assert.equal(f.received.length, 1);
});

for (const [mode, code] of [
  ['malformed', 'invalid_response'],
  ['oversized', 'response_too_large'],
] as const) {
  test(mode + ' response fails closed', { timeout: 5000 }, async (t) => {
    const f = await fixture(t, mode);
    await assert.rejects(
      model(f.url).score(request()),
      (error: unknown) => error instanceof OpenJevError && error.code === code
    );
  });
}

test('timeout is bounded and not retried', { timeout: 5000 }, async (t) => {
  const f = await fixture(t, 'stall');
  await assert.rejects(
    model(f.url, 100).score(request()),
    (error: unknown) => error instanceof OpenJevError && error.code === 'timeout'
  );
  assert.equal(f.received.length, 1);
});
