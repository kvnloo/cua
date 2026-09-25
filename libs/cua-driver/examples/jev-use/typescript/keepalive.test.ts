/**
 * Tests for typescript/keepalive.ts (PersistentDaemonClient).
 *
 * Spins up bench/observation-gating/mock_daemon.mjs in --keep-alive mode and
 * drives the real JSONL wire: multiple sequential requests over one
 * connection, response ordering, unwrapped call shape, and close().
 */
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import net from "node:net";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import { fileURLToPath } from "node:url";
import { PersistentDaemonClient } from "./keepalive.js";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const DAEMON = path.join(TEST_DIR, "..", "bench", "observation-gating", "mock_daemon.mjs");
const SOCKET = path.join(os.tmpdir(), `cua-keepalive-test-${process.pid}.sock`);

let child: ChildProcess;

before(async () => {
  child = spawn(
    process.execPath,
    [DAEMON, "--socket", SOCKET, "--scenario", "dom-complete", "--regions", "5", "--keep-alive"],
    { stdio: ["ignore", "pipe", "inherit"] },
  );
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("daemon start timeout")), 10_000);
    child.stdout!.on("data", (chunk: Buffer) => {
      if (chunk.toString().includes("ready")) {
        clearTimeout(timer);
        resolve();
      }
    });
    child.on("error", reject);
  });
});

after(async () => {
  child.kill();
  await new Promise((resolve) => child.on("exit", resolve));
  try {
    fs.unlinkSync(SOCKET);
  } catch {
    /* already gone */
  }
});

describe("PersistentDaemonClient", () => {
  it("serves multiple sequential calls over one connection", async () => {
    const client = new PersistentDaemonClient(SOCKET);
    try {
      const a = (await client.call("get_browser_state", {})) as { ok: boolean };
      const b = (await client.call("get_window_state", { pid: 4242, window_id: 7 })) as {
        ok: boolean;
      };
      assert.equal(a.ok, true);
      assert.equal(b.ok, true);
    } finally {
      await client.close();
    }
  });

  it("preserves request/response ordering across interleaved awaits", async () => {
    const client = new PersistentDaemonClient(SOCKET);
    try {
      const [first, second, third] = await Promise.all([
        client.asUnwrappedCallFn()("get_browser_state", {}),
        client.asUnwrappedCallFn()("get_window_state", { pid: 4242, window_id: 7 }),
        client.asUnwrappedCallFn()("fixture_submitted", {}),
      ]);
      assert.ok(Array.isArray((first as { refs: unknown[] }).refs));
      assert.equal(typeof (second as { capture_id: string }).capture_id, "string");
      assert.deepEqual(third, { submitted: null });
    } finally {
      await client.close();
    }
  });

  it("asCallFn returns the raw wire; asUnwrappedCallFn unwraps", async () => {
    const client = new PersistentDaemonClient(SOCKET);
    try {
      const raw = (await client.asCallFn()("get_browser_state", {})) as {
        ok: boolean;
        result: { structuredContent: { refs: unknown[] } };
      };
      assert.equal(raw.ok, true);
      assert.ok(Array.isArray(raw.result.structuredContent.refs));
      const unwrapped = (await client.asUnwrappedCallFn()("get_browser_state", {})) as {
        refs: unknown[];
      };
      assert.ok(Array.isArray(unwrapped.refs));
    } finally {
      await client.close();
    }
  });

  it("surfaces daemon-side errors as rejections", async () => {
    const client = new PersistentDaemonClient(SOCKET);
    try {
      await assert.rejects(
        client.asUnwrappedCallFn()("no_such_method", {}),
        /daemon has no handler/,
      );
    } finally {
      await client.close();
    }
  });

  it("the daemon answers a raw socket too (keep-alive flag is opt-in)", async () => {
    // Proves the one-shot path still works when the flag is absent would need
    // a second daemon; here we just confirm a plain net socket gets answers
    // on the keep-alive daemon — the protocol is unchanged.
    const wire = await new Promise<Record<string, unknown>>((resolve, reject) => {
      const connection = net.createConnection(SOCKET);
      let buffer = "";
      connection.setEncoding("utf8");
      connection.on("connect", () => {
        connection.write(`${JSON.stringify({ method: "call", name: "fixture_submitted", args: {} })}\n`);
      });
      connection.on("data", (chunk: string) => {
        buffer += chunk;
        if (buffer.indexOf("\n") >= 0) {
          connection.end();
          resolve(JSON.parse(buffer));
        }
      });
      connection.on("error", reject);
      setTimeout(() => reject(new Error("timeout")), 10_000);
    });
    assert.equal(wire.ok, true);
  });
});
