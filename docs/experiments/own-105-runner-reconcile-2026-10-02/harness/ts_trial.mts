/**
 * One OWN-105 trial in a child process: the jev-use TypeScript runner.
 *
 * The fault seam sits between the SDK Client and the real StdioClientTransport
 * (SDK 1.30.0): it patches the transport prototype's start/send/close, so every
 * byte still crosses the real stdio pipes of the real `$CUA_DRIVER_BIN mcp`.
 * run.ts is imported unmodified with its own CLI arguments. Faults:
 *
 * - none: pure relay.
 * - pre_dispatch: when the Driver answers the first semantic snapshot after a
 *   successful browser_type, mark the write side closed and deliver the answer.
 *   The next request (the Submit click) raises inside send() before anything is
 *   written (the SDK's own pre-write error, `Not connected`); EOF follows.
 * - closed_before_request: same placement, but EOF is delivered right after the
 *   snapshot answer, so the Submit request is refused by the SDK before it ever
 *   reaches send() (the realistic TypeScript connection-loss surface).
 * - ack_lost: forward the Submit click; hold the Driver's answer until the target
 *   journal reaches the barrier, drop it, deliver EOF.
 * - read_error: deliver the Submit answer; replace the next semantic snapshot
 *   answer with a tool error result (isError, no structured content).
 *
 * EOF is what the SDK does when the Driver's stdout closes: transport.onclose,
 * so pending requests fail with McpError(ConnectionClosed).
 *
 * usage: node --import tsx ts_trial.mts <config.json>   (cwd = jev-use root)
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const cfg = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const sdk = join(cfg.jev_root, 'node_modules/@modelcontextprotocol/sdk/dist/esm');
const { StdioClientTransport } = await import(pathToFileURL(join(sdk, 'client/stdio.js')).href);
const { Client } = await import(pathToFileURL(join(sdk, 'client/index.js')).href);

const RESULT_FIELDS = ['status', 'route', 'input_route', 'effect', 'delivery', 'producer'];
const events: Record<string, unknown>[] = [];
const t0 = performance.now();
let fired = false;
const transports: any[] = [];
const log = (kind: string, fields: Record<string, unknown> = {}) =>
  events.push({ kind, t_ms: Math.round((performance.now() - t0) * 1000) / 1000, ...fields });
const control = async (path: string) => (await fetch(`${cfg.control_url}${path}`)).json();

function describeRequest(message: any): Record<string, unknown> {
  const out: Record<string, unknown> = { id: message.id, method: message.method };
  if (message.method === 'tools/call') {
    const args = message.params?.arguments ?? {};
    out.tool = message.params?.name;
    out.arg_keys = Object.keys(args).sort();
    if ('snapshot_format' in args) out.snapshot_format = args.snapshot_format;
    if ('input_route' in args) out.input_route = args.input_route;
  }
  return out;
}

function describeResponse(message: any, req: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { id: message.id, for_tool: req.tool ?? req.method };
  if (message.error) {
    out.jsonrpc_error_code = message.error.code;
    return out;
  }
  out.is_error = Boolean(message.result?.isError);
  const structured = message.result?.structuredContent;
  if (structured && typeof structured === 'object') {
    const picked: Record<string, unknown> = {};
    for (const key of RESULT_FIELDS) {
      const value = structured[key];
      if (['boolean', 'number'].includes(typeof value) || (typeof value === 'string' && value.length <= 64)) {
        picked[key] = value;
      }
    }
    out.structured = picked;
  }
  return out;
}

const proto = StdioClientTransport.prototype as any;
const originalStart = proto.start;
const originalSend = proto.send;
const originalClose = proto.close;

proto.start = async function (this: any) {
  const st: any = { typedOk: false, clickId: undefined, clickDelivered: false, writeClosed: false, eof: false };
  st.pending = new Map();
  st.eofNow = (reason: string) => {
    if (st.eof) return;
    st.eof = true;
    log('caller_eof', { reason });
    this.onclose?.();
  };
  this.seam = st;
  transports.push(this);
  log('session_start');
  const deliver = this.onmessage;
  let queue: Promise<void> = Promise.resolve();
  const isSnapshotAfterType = (req: any) =>
    st.typedOk && req.tool === 'get_browser_state' && req.snapshot_format === 'semantic_v2';
  const handle = async (message: any, extra: any) => {
    if (st.eof) return;
    const isResponse = message.method === undefined && message.id !== undefined;
    const req = isResponse ? st.pending.get(message.id) : undefined;
    if (!req) {
      deliver?.(message, extra);
      return;
    }
    st.pending.delete(message.id);
    const desc = describeResponse(message, req);
    if (req.tool === 'browser_type' && !desc.is_error && !message.error) st.typedOk = true;
    if (cfg.fault === 'pre_dispatch' && !fired && isSnapshotAfterType(req)) {
      fired = true;
      st.writeClosed = true;
      log('write_closed_before_next_request', { after: desc, journal: await control('snapshot') });
      deliver?.(message, extra);
      return;
    }
    if (cfg.fault === 'closed_before_request' && !fired && isSnapshotAfterType(req)) {
      fired = true;
      log('transport_closed_before_next_request', { after: desc, journal: await control('snapshot') });
      deliver?.(message, extra);
      st.eofNow('closed_before_request');
      return;
    }
    if (cfg.fault === 'ack_lost' && !fired && message.id === st.clickId) {
      fired = true;
      log('driver_response_held', desc);
      const reached = Boolean((await control(`wait?kind=${cfg.barrier}&timeout=20`)).reached);
      log('target_barrier', { barrier: cfg.barrier, reached, journal: await control('snapshot') });
      log('driver_response_dropped', { id: message.id });
      st.eofNow('ack_lost');
      return;
    }
    if (
      cfg.fault === 'read_error' &&
      !fired &&
      st.clickDelivered &&
      req.tool === 'get_browser_state' &&
      req.snapshot_format === 'semantic_v2'
    ) {
      fired = true;
      log('read_error_injected', { replaced: desc, journal: await control('snapshot') });
      deliver?.(
        {
          jsonrpc: '2.0',
          id: message.id,
          result: { isError: true, content: [{ type: 'text', text: 'injected read failure' }] },
        },
        extra
      );
      return;
    }
    if (message.id === st.clickId) st.clickDelivered = true;
    log('delivered_response', desc);
    deliver?.(message, extra);
  };
  // Keep the Driver's message order while a fault awaits a barrier.
  this.onmessage = (message: any, extra: any) => {
    queue = queue.then(() => handle(message, extra)).catch((error) => {
      log('seam_error', { type: error instanceof Error ? error.name : 'unknown' });
    });
  };
  return originalStart.call(this);
};

proto.send = async function (this: any, message: any, options: any) {
  const st = this.seam;
  if (st && message.method !== undefined && message.id !== undefined) {
    const desc = describeRequest(message);
    if (st.writeClosed) {
      log('send_raised_before_write', desc);
      setImmediate(() => st.eofNow('pre_dispatch'));
      throw new Error('Not connected');
    }
    st.pending.set(message.id, desc);
    if (desc.tool === 'browser_click' && st.typedOk) st.clickId = message.id;
    log('forwarded_request', desc);
  } else if (st) {
    log('forwarded_other', { method: message.method ?? null });
  }
  return originalSend.call(this, message, options);
};

proto.close = async function (this: any) {
  this.seamClosed = true;
  return originalClose.call(this);
};

// After an EOF the Client no longer owns the transport, so close every real
// Driver process this trial started once the runner closes its client.
const originalClientClose = Client.prototype.close;
Client.prototype.close = async function (this: any) {
  await originalClientClose.call(this);
  for (const transport of transports) {
    if (!transport.seamClosed) {
      transport.seamClosed = true;
      await originalClose.call(transport).catch(() => {});
    }
  }
};

process.on('exit', (code) => {
  writeFileSync(
    cfg.result,
    JSON.stringify({ exit_code: code, seam_events: events, fault_fired: fired, transports: transports.length })
  );
});

const runTs = join(cfg.jev_root, 'typescript/run.ts');
process.argv = [
  process.execPath,
  runTs,
  '--provider',
  'mock',
  '--visual-observation',
  'off',
  '--token',
  cfg.token,
  '--max-steps',
  '4',
  '--log',
  cfg.log,
  '--guarded-completion',
  '--fixture-url',
  cfg.fixture_url,
];
await import(pathToFileURL(runTs).href);
