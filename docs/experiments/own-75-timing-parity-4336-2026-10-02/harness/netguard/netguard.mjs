// OWN-75 network guard for the TypeScript runner (node --import). Measurement harness only.
// Refuses every net.Socket connect to a non-loopback TCP host before it is attempted and appends
// {"kind":"refused"} to OWN75_NETGUARD_LOG; on load it appends {"kind":"armed"}. Unix-socket
// (path) connects and loopback connects are untouched. fetch/undici, http and tls all create
// their sockets through net.Socket.prototype.connect.
import { appendFileSync } from 'node:fs';
import net from 'node:net';
import process from 'node:process';

const LOG = process.env.OWN75_NETGUARD_LOG;
const LOOPBACK = new Set(['localhost', 'localhost.localdomain', '::1']);

function record(kind, fields = {}) {
  if (!LOG) return;
  appendFileSync(LOG, JSON.stringify({ kind, runtime: 'node', pid: process.pid, t: Date.now() / 1000, ...fields }) + '\n');
}

function isLoopback(host) {
  if (typeof host !== 'string') return false;
  if (LOOPBACK.has(host)) return true;
  if (net.isIPv4(host)) return host.startsWith('127.');
  if (net.isIPv6(host)) return host === '::1' || host.startsWith('::ffff:127.');
  return false;
}

if (LOG) {
  const original = net.Socket.prototype.connect;
  net.Socket.prototype.connect = function guardedConnect(...args) {
    let options = args[0];
    if (Array.isArray(options)) options = options[0];
    let host;
    let port;
    let path;
    if (options && typeof options === 'object') {
      ({ host, port, path } = options);
      if (path === undefined && host === undefined) host = 'localhost';
    } else if (typeof options === 'string' && Number.isNaN(Number(options))) {
      path = options;
    } else {
      port = options;
      host = typeof args[1] === 'string' ? args[1] : 'localhost';
    }
    if (path === undefined && !isLoopback(host)) {
      record('refused', { call: 'net.Socket.connect', host: String(host), port: port ?? null });
      const error = new Error(`OWN-75 netguard refused non-loopback connect to ${host}`);
      error.code = 'ECONNREFUSED';
      process.nextTick(() => this.destroy(error));
      return this;
    }
    return original.apply(this, args);
  };
  record('armed', { argv: [process.argv[1] ? process.argv[1].split('/').pop() : null] });
}
