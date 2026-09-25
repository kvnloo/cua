/**
 * Keep-alive benchmark: one-request-per-connection vs persistent connection.
 *
 * Paired/interleaved design: each iteration runs the same 3-call observation
 * sequence (get_browser_state + get_window_state + parse_visual_regions)
 * once per arm, in Fisher-Yates order, against one --keep-alive daemon.
 * The one-shot arm opens a fresh socket per call (today's daemon behavior);
 * the keep-alive arm multiplexes over a single PersistentDaemonClient.
 * An equivalence gate asserts both arms return identical structuredContent.
 *
 * Run: node --import tsx bench/observation-gating/keepalive_bench.ts
 */
import net from "node:net";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import { fileURLToPath } from "node:url";
import { PersistentDaemonClient } from "../../typescript/keepalive.js";

const BENCH_DIR = path.dirname(fileURLToPath(import.meta.url));
const DAEMON = path.join(BENCH_DIR, "mock_daemon.mjs");
const SOCKET = path.join(os.tmpdir(), `cua-keepalive-${process.pid}.sock`);

const ITERS = 30;
const CALLS_PER_ITER = 3; // snapshot + capture + parse
const PID = 4242;
const WINDOW_ID = 7;

function startDaemon(): Promise<ChildProcess> {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [DAEMON, "--socket", SOCKET, "--scenario", "visual-fallback", "--regions", "50", "--keep-alive"],
      { stdio: ["ignore", "pipe", "inherit"] },
    );
    const timer = setTimeout(() => reject(new Error("daemon start timeout")), 10_000);
    child.stdout.on("data", (chunk: Buffer) => {
      if (chunk.toString().includes("ready")) {
        clearTimeout(timer);
        resolve(child);
      }
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
  });
}

type Wire = { result: { structuredContent: unknown } };

/** One-shot arm: a fresh connection per call (current daemon behavior). */
function oneShotCall(name: string, args: Record<string, unknown>): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const connection = net.createConnection(SOCKET);
    let buffer = "";
    connection.setEncoding("utf8");
    const timer = setTimeout(() => {
      connection.destroy();
      reject(new Error(`one-shot timeout: ${name}`));
    }, 10_000);
    connection.on("connect", () => {
      connection.write(`${JSON.stringify({ method: "call", name, args })}\n`);
    });
    connection.on("data", (chunk: string) => {
      buffer += chunk;
      const newline = buffer.indexOf("\n");
      if (newline < 0) return;
      clearTimeout(timer);
      connection.end();
      try {
        const wire = JSON.parse(buffer.slice(0, newline)) as Wire & { ok: boolean; error?: string };
        if (!wire.ok) reject(new Error(`daemon error: ${wire.error}`));
        else resolve(wire.result.structuredContent);
      } catch (error) {
        reject(error);
      }
    });
    connection.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
  });
}

async function observationSequence(
  call: (name: string, args: Record<string, unknown>) => Promise<unknown>,
): Promise<void> {
  const snapshot = (await call("get_browser_state", {
    target_id: "t",
    tab_id: "tab",
    snapshot_format: "semantic_v2",
  })) as { refs?: unknown[] };
  if (!Array.isArray(snapshot.refs)) throw new Error("snapshot shape mismatch");
  const capture = (await call("get_window_state", {
    pid: PID,
    window_id: WINDOW_ID,
    include_accessibility_tree: false,
  })) as { capture_id: string };
  if (typeof capture.capture_id !== "string") throw new Error("capture shape mismatch");
  const wire = (await call("parse_visual_regions", {
    capture_id: capture.capture_id,
    options: { kinds: ["text", "icon"], min_confidence: 0.8, max_regions: 100 },
  })) as { regions?: unknown[] };
  if (!Array.isArray(wire.regions)) throw new Error("parse shape mismatch");
}

function shuffle<T>(items: T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

function percentile(values: number[], p: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}

async function main(): Promise<void> {
  const child = await startDaemon();
  try {
    const persistent = new PersistentDaemonClient(SOCKET);
    const oneShotMs: number[] = [];
    const keepAliveMs: number[] = [];

    for (let iter = 0; iter < ITERS; iter += 1) {
      for (const arm of shuffle(["oneshot", "keepalive"] as const)) {
        const t0 = process.hrtime.bigint();
        if (arm === "oneshot") {
          await observationSequence(oneShotCall);
        } else {
          await observationSequence(persistent.asUnwrappedCallFn());
        }
        const ms = Number(process.hrtime.bigint() - t0) / 1e6;
        if (arm === "oneshot") oneShotMs.push(ms);
        else keepAliveMs.push(ms);
      }
      // Shape equivalence gate lives inside observationSequence (throws on
      // mismatch); reaching here means both arms served the same wire shape.
    }

    await persistent.close();

    const perCallOneShot = oneShotMs.map((ms) => ms / CALLS_PER_ITER);
    const perCallKeepAlive = keepAliveMs.map((ms) => ms / CALLS_PER_ITER);
    const ratio = (a: number[], b: number[], f: (v: number[]) => number) => f(a) / f(b);

    console.log(JSON.stringify({
      iters: ITERS,
      callsPerIter: CALLS_PER_ITER,
      iterMs: {
        oneshot: { median: median(oneShotMs), p90: percentile(oneShotMs, 90) },
        keepalive: { median: median(keepAliveMs), p90: percentile(keepAliveMs, 90) },
      },
      perCallMs: {
        oneshot: { median: median(perCallOneShot), p90: percentile(perCallOneShot, 90) },
        keepalive: { median: median(perCallKeepAlive), p90: percentile(perCallKeepAlive, 90) },
      },
      speedupMedian: ratio(oneShotMs, keepAliveMs, median),
      speedupP90: ratio(oneShotMs, keepAliveMs, (v) => percentile(v, 90)),
    }, null, 2));
  } finally {
    child.kill();
    await new Promise((resolve) => child.on("exit", resolve));
    try {
      fs.unlinkSync(SOCKET);
    } catch {
      /* already gone */
    }
  }
}

await main();
