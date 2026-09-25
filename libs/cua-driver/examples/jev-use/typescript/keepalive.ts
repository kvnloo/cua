/**
 * Keep-alive (persistent connection) client for the daemon's JSONL socket
 * protocol — a fork research prototype, NOT an upstream proposal.
 *
 * The real daemon speaks one-request-per-connection: every RPC pays a full
 * socket connect + handshake + teardown. This client opens ONE connection
 * and sends every request down it, reading one response line per request.
 * Requests are serialized (the daemon answers in order), matching how the
 * synchronous recipe loop issues calls.
 *
 * What it is NOT: a protocol change to the daemon. The daemon side is
 * `mock_daemon.mjs --keep-alive`. Upstream, this would require the
 * auth-lifetime contract question in dq-3383 (authenticate once per
 * connection vs per request) to be answered first — see REPORT-keepalive.md.
 */
import net from "node:net";
import type { CallFn } from "./batched.js";

const CALL_TIMEOUT_MS = 10_000;

export class PersistentDaemonClient {
  private readonly socketPath: string;
  private connection: net.Socket | null = null;
  private buffer = "";
  private waiters: Array<{
    resolve: (value: Record<string, any>) => void;
    reject: (error: Error) => void;
  }> = [];
  private tail: Promise<void> = Promise.resolve();
  private closed = false;

  constructor(socketPath: string) {
    this.socketPath = socketPath;
  }

  private ensureConnected(): Promise<net.Socket> {
    if (this.connection) return Promise.resolve(this.connection);
    if (this.closed) return Promise.reject(new Error("client is closed"));
    return new Promise((resolve, reject) => {
      const connection = net.createConnection(this.socketPath);
      connection.setEncoding("utf8");
      const timer = setTimeout(() => {
        connection.destroy();
        reject(new Error("daemon connect timeout"));
      }, CALL_TIMEOUT_MS);
      connection.on("connect", () => {
        clearTimeout(timer);
        this.connection = connection;
        resolve(connection);
      });
      connection.on("data", (chunk: string) => this.onData(chunk));
      connection.on("error", (error) => this.onFatal(error));
      connection.on("close", () =>
        this.onFatal(new Error("daemon closed the connection")),
      );
    });
  }

  private onData(chunk: string): void {
    this.buffer += chunk;
    for (;;) {
      const newline = this.buffer.indexOf("\n");
      if (newline < 0) return;
      const line = this.buffer.slice(0, newline);
      this.buffer = this.buffer.slice(newline + 1);
      const waiter = this.waiters.shift();
      if (!waiter) continue; // stray line; keep the buffer moving
      try {
        waiter.resolve(JSON.parse(line));
      } catch (error) {
        waiter.reject(
          error instanceof Error ? error : new Error(String(error)),
        );
      }
    }
  }

  private onFatal(error: Error): void {
    this.connection = null;
    this.buffer = "";
    const waiters = this.waiters;
    this.waiters = [];
    for (const waiter of waiters) waiter.reject(error);
  }

  /** One serialized call over the persistent connection. */
  call(name: string, args: Record<string, unknown>): Promise<Record<string, any>> {
    const run = this.tail.then(async () => {
      const connection = await this.ensureConnected();
      return new Promise<Record<string, any>>((resolve, reject) => {
        const timer = setTimeout(() => {
          this.waiters = this.waiters.filter((w) => w.resolve !== resolve);
          reject(new Error(`daemon call timeout: ${name}`));
        }, CALL_TIMEOUT_MS);
        this.waiters.push({
          resolve: (value) => {
            clearTimeout(timer);
            resolve(value);
          },
          reject: (error) => {
            clearTimeout(timer);
            reject(error);
          },
        });
        connection.write(`${JSON.stringify({ method: "call", name, args })}\n`);
      });
    });
    // Keep the chain alive even if this call fails; next call reconnects.
    this.tail = run.then(
      () => undefined,
      () => undefined,
    );
    return run;
  }

  /** The CallFn shape the observation-path code already consumes (raw wire). */
  asCallFn(): CallFn {
    return (name, args) => this.call(name, args);
  }

  /**
   * Bench-convention CallFn: same unwrapping as the one-shot bench clients —
   * throws on !ok, returns result.structuredContent. Use this when comparing
   * arms, so both arms see identical payloads.
   */
  asUnwrappedCallFn(): (name: string, args: Record<string, unknown>) => Promise<unknown> {
    return async (name, args) => {
      const wire = (await this.call(name, args)) as {
        ok: boolean;
        error?: string;
        result?: { structuredContent: { error?: string } & Record<string, unknown> };
      };
      if (!wire.ok) throw new Error(`daemon error on ${name}: ${wire.error}`);
      const sc = wire.result?.structuredContent;
      if (sc && typeof sc.error === "string") {
        throw new Error(`daemon error on ${name}: ${sc.error}`);
      }
      return sc;
    };
  }

  async close(): Promise<void> {
    this.closed = true;
    const connection = this.connection;
    this.connection = null;
    if (connection) {
      await new Promise<void>((resolve) => {
        connection.on("close", () => resolve());
        connection.end();
        setTimeout(resolve, 1000).unref?.();
      });
    }
  }
}
