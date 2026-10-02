// Measurement-only preload for the unmodified jev-use TypeScript browser runner (OWN-78).
//
// usage: node --import tsx --import <this file> typescript/run.ts [args...]   (cwd = examples dir)
//
// Without OWN78_RECEIPT_LOG this module does nothing. With it, in this process only:
//   * globalThis.fetch: one `http_attempt` receipt per provider HTTP attempt (method, host, path,
//     status, request-id presence and sha256 prefix, error class). The TypeSafe SDK calls
//     globalThis.fetch once per attempt (its defaultFetch is `(i, o) => globalThis.fetch(i, o)`).
//     Requests to the fixture origin (OWN78_FIXTURE_ORIGIN) are counted, not recorded as attempts.
//     For a 200 provider response a clone is parsed and ONLY model, usage token counts and
//     answers.candidate.choice are kept (`provider_response`, evidence = HTTP body whitelist).
//   * MCP SDK Client.prototype.callTool (same module URL the runner resolves): one `driver_call`
//     receipt per Driver call (tool, ok/error, the `ref` argument only, whitelisted scalars).
// Seams (env-gated): OWN78_SWITCH_BASE_URL (after the first ok browser_type, set
// process.env.TYPESAFE_BASE_URL; the runner builds a new TypeSafeClient per decision) and
// OWN78_PROVIDER_REACH_ALLOWANCE (refuse non-loopback provider attempts beyond the allowance).
// No headers, bodies, typed text or credentials are recorded. Timestamps: process.hrtime.bigint()
// (CLOCK_MONOTONIC on Linux).
import { appendFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const LOG = process.env.OWN78_RECEIPT_LOG;
const LOOPBACK = new Set(['127.0.0.1', 'localhost', '[::1]', '::1']);
const RESULT_SCALAR_KEYS = new Set(['effect', 'route', 'status', 'action', 'prepared_pid', 'refs_invalidated', 'code']);
let seq = 0;
const state = { reached: 0, switched: false, fixtureFetches: 0 };

const now = () => process.hrtime.bigint().toString();
const hash16 = (value) => (value ? createHash('sha256').update(value).digest('hex').slice(0, 16) : null);
// Whitelisted result scalars never carry paths; anything path-like is replaced.
const sanitize = (value) => (typeof value === 'string' && value.includes('/') ? '<path-like>' : value);

function emit(record) {
  if (!LOG) return;
  seq += 1;
  const ordered = Object.fromEntries(Object.entries({ seq, runtime: 'typescript', ...record }).sort(([a], [b]) => a.localeCompare(b)));
  appendFileSync(LOG, JSON.stringify(ordered) + '\n');
}

if (LOG) {
  const fixtureOrigin = process.env.OWN78_FIXTURE_ORIGIN ? new URL(process.env.OWN78_FIXTURE_ORIGIN).origin : null;
  const allowance = process.env.OWN78_PROVIDER_REACH_ALLOWANCE ? Number(process.env.OWN78_PROVIDER_REACH_ALLOWANCE) : null;
  const switchUrl = process.env.OWN78_SWITCH_BASE_URL || null;
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async function own78Fetch(input, init) {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url);
    if (fixtureOrigin && url.origin === fixtureOrigin) {
      state.fixtureFetches += 1;
      return originalFetch(input, init);
    }
    const method = (init && init.method) || (typeof input === 'object' && input.method) || 'GET';
    const host = url.hostname;
    const record = { kind: 'http_attempt', method, host, loopback: LOOPBACK.has(host), path: url.pathname, t_start_ns: now() };
    if (allowance !== null && !LOOPBACK.has(host) && state.reached >= allowance) {
      emit({ ...record, t_end_ns: now(), error: 'BudgetGuardRefused', guard_refused: true });
      throw new TypeError('own78 budget guard: provider allowance used');
    }
    let response;
    try {
      response = await originalFetch(input, init);
    } catch (error) {
      emit({
        ...record,
        t_end_ns: now(),
        error: error && error.name ? error.name : 'Error',
        error_cause_code: error && error.cause && typeof error.cause.code === 'string' ? error.cause.code : null,
      });
      throw error;
    }
    if (!LOOPBACK.has(host)) state.reached += 1;
    const requestId = response.headers.get('x-typesafe-request-id');
    emit({ ...record, t_end_ns: now(), status: response.status, request_id_present: Boolean(requestId), request_id_sha256_16: hash16(requestId) });
    if (response.status === 200 && url.pathname === '/v1/systemone') {
      try {
        const parsed = await response.clone().json();
        const answer = parsed && parsed.answers ? parsed.answers.candidate : undefined;
        emit({
          kind: 'provider_response',
          responder: host === 'api.typesafe.ai' ? 'typesafe' : LOOPBACK.has(host) ? 'loopback_stub' : 'other_host',
          evidence: 'HTTP 200 body from responder_host (whitelisted fields only)',
          responder_host: host,
          ok: true,
          model: typeof parsed.model === 'string' ? parsed.model : null,
          input_tokens: parsed.usage && Number.isFinite(parsed.usage.input_tokens) ? parsed.usage.input_tokens : null,
          output_tokens: parsed.usage && Number.isFinite(parsed.usage.output_tokens) ? parsed.usage.output_tokens : null,
          request_id_sha256_16: hash16(requestId),
          selected_id: answer && typeof answer.choice === 'string' ? answer.choice : null,
          t_end_ns: now(),
        });
      } catch (error) {
        emit({ kind: 'provider_response_parse_error', error: error && error.name ? error.name : 'Error' });
      }
    }
    return response;
  };

  const examples = process.cwd();
  const clientUrl = pathToFileURL(join(examples, 'node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js')).href;
  const { Client } = await import(clientUrl);
  const originalCallTool = Client.prototype.callTool;
  Client.prototype.callTool = async function own78CallTool(params, ...rest) {
    const name = params && params.name;
    const args = (params && params.arguments) || {};
    const record = { kind: 'driver_call', tool: name, t_start_ns: now() };
    if (typeof args.ref === 'string') record.arg_ref = args.ref;
    let result;
    try {
      result = await originalCallTool.call(this, params, ...rest);
    } catch (error) {
      emit({ ...record, t_end_ns: now(), ok: false, error: error && error.name ? error.name : 'Error' });
      throw error;
    }
    const data = result && result.structuredContent;
    const ok = !(result && result.isError) && !(data && (data.status === 'refused' || data.refusal));
    const scalars = {};
    if (data && typeof data === 'object') {
      for (const [key, value] of Object.entries(data)) {
        if (RESULT_SCALAR_KEYS.has(key) && (value === null || ['string', 'number', 'boolean'].includes(typeof value))) scalars[key] = sanitize(value);
      }
    }
    emit({ ...record, t_end_ns: now(), ok, result: scalars });
    if (switchUrl && name === 'browser_type' && ok && !state.switched) {
      state.switched = true;
      process.env.TYPESAFE_BASE_URL = switchUrl;
      emit({ kind: 'seam_switch', after_tool: 'browser_type', to_host: new URL(switchUrl).hostname, t_ns: now() });
    }
    return result;
  };

  process.on('exit', () => emit({ kind: 'launcher_exit', fixture_fetches: state.fixtureFetches, reached: state.reached, t_ns: now() }));
  emit({
    kind: 'launcher_start',
    t_ns: now(),
    argv_flags: process.argv.slice(2).filter((a) => a.startsWith('--')),
    base_url_host_at_start: process.env.TYPESAFE_BASE_URL ? new URL(process.env.TYPESAFE_BASE_URL).hostname : null,
    switch_armed: Boolean(switchUrl),
  });
}
