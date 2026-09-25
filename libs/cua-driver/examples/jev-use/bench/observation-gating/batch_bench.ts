/**
 * Transport-batching bench (paired/interleaved design).
 *
 * Chunk-4's profile found the per-step cost is the RPC round trips (one socket
 * connection per call), not client-side parsing. Loopback IPC on this box is
 * noisy (per-call medians swing 3-60ms between daemon runs), so this bench
 * measures all three shapes INTERLEAVED per iteration and reports PAIRED
 * per-iteration ratios, which cancel box-load drift:
 *   sequential — snapshot, capture, parse as 3 back-to-back round trips
 *   parallel   — snapshot + capture concurrently, then parse (no protocol change)
 *   combined   — snapshot, then prototype `observe_visual` (capture+parse in one)
 *
 * The parallel shape works against the real daemon today. The combined shape
 * is a mock-only protocol prototype: its numbers are the ceiling for a real
 * daemon-side combined call, which would be a contract decision upstream.
 *
 * Equivalence gate: all three shapes must produce identical candidate sets
 * and region counts on every iteration, or the bench fails.
 *
 * Run: node --import tsx bench/observation-gating/batch_bench.ts
 */
import net from "node:net";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildCandidates } from "../../typescript/core.js";
import {
  observeCombined,
  observeParallel,
  observeSequential,
  type CallFn,
} from "../../typescript/batched.js";

const BENCH_DIR = path.dirname(fileURLToPath(import.meta.url));
const DAEMON = path.join(BENCH_DIR, "mock_daemon.mjs");
const SOCKET = path.join(os.tmpdir(), `cua-batch-${process.pid}.sock`);

const TOKEN = "batch-token";
const PID = 4242;
const WINDOW_ID = 7;
const ITERS = 30;
const REGIONS = 50;

function startDaemon(): Promise<ChildProcess> {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [DAEMON, "--socket", SOCKET, "--scenario", "visual-fallback", "--regions", String(REGIONS)],
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

async function stopDaemon(child: ChildProcess): Promise<void> {
  child.kill();
  await new Promise((resolve) => child.on("exit", resolve));
  try {
    fs.unlinkSync(SOCKET);
  } catch {
    /* already gone */
  }
}

/** One request per connection, mirroring live_bench.ts. */
function socketCall(name: string, args: Record<string, unknown>): Promise<Record<string, any>> {
  return new Promise((resolve, reject) => {
    const connection = net.createConnection(SOCKET);
    let buffer = "";
    connection.setEncoding("utf8");
    const timer = setTimeout(() => {
      connection.destroy();
      reject(new Error(`daemon call timeout: ${name}`));
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
        const parsed = JSON.parse(buffer.slice(0, newline));
        if (!parsed.ok) reject(new Error(`daemon error on ${name}: ${parsed.error}`));
        else resolve(parsed.result.structuredContent);
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

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

function percentile(values: number[], p: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}

type Shape = "sequential" | "parallel" | "combined";

async function measureOne(
  shape: Shape,
  call: CallFn,
  args: { targetId: string; tabId: string; pid: number; windowId: number },
): Promise<{ ms: number; candidates: number; regions: number }> {
  const t0 = process.hrtime.bigint();
  const { snapshot, visual } =
    shape === "sequential"
      ? await observeSequential(call, args)
      : shape === "parallel"
        ? await observeParallel(call, args)
        : await observeCombined(call, args);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6;
  const built = buildCandidates(snapshot as any, TOKEN, visual, true);
  return { ms, candidates: built.length, regions: visual.regions.length };
}

async function main(): Promise<void> {
  const daemon = await startDaemon();
  try {
    const call: CallFn = socketCall;
    const args = { targetId: "t", tabId: "tab", pid: PID, windowId: WINDOW_ID };
    // Warmup: JIT + socket path, discarded.
    for (let i = 0; i < 3; i += 1) await measureOne("sequential", call, args);

    const byShape: Record<Shape, number[]> = { sequential: [], parallel: [], combined: [] };
    const parRatio: number[] = [];
    const combRatio: number[] = [];
    let refCandidates = -1;
    let refRegions = -1;

    for (let i = 0; i < ITERS; i += 1) {
      // Randomized per-iteration order cancels drift (JIT, box load).
      const order: Shape[] = ["sequential", "parallel", "combined"];
      for (let j = order.length - 1; j > 0; j -= 1) {
        const k = Math.floor(Math.random() * (j + 1));
        [order[j], order[k]] = [order[k], order[j]];
      }
      const ms: Record<Shape, number> = { sequential: 0, parallel: 0, combined: 0 };
      for (const shape of order) {
        const { ms: shapeMs, candidates, regions } = await measureOne(shape, call, args);
        if (refCandidates < 0) {
          refCandidates = candidates;
          refRegions = regions;
        }
        if (candidates !== refCandidates || regions !== refRegions) {
          throw new Error(`${shape} diverged: ${candidates}c/${regions}r vs ${refCandidates}c/${refRegions}r`);
        }
        ms[shape] = shapeMs;
        byShape[shape].push(shapeMs);
      }
      parRatio.push(ms.sequential / ms.parallel);
      combRatio.push(ms.sequential / ms.combined);
    }

    const summarize = (shape: Shape) => ({
      shape,
      round_trips: shape === "combined" ? 2 : 3,
      sequential_groups: shape === "sequential" ? 3 : 2,
      median_ms: Math.round(median(byShape[shape]) * 100) / 100,
      p90_ms: Math.round(percentile(byShape[shape], 90) * 100) / 100,
    });
    console.log(
      JSON.stringify(
        {
          transport: "unix-socket JSONL, one connection per call (real IPC)",
          design: "paired: 3 shapes interleaved per iteration, randomized order",
          iters: ITERS,
          regions: REGIONS,
          equivalence: { candidates: refCandidates, regions: refRegions, status: "identical all iters" },
          rows: [summarize("sequential"), summarize("parallel"), summarize("combined")],
          paired_speedup_vs_sequential: {
            parallel_median: Math.round(median(parRatio) * 100) / 100,
            parallel_p90: Math.round(percentile(parRatio, 90) * 100) / 100,
            combined_median: Math.round(median(combRatio) * 100) / 100,
            combined_p90: Math.round(percentile(combRatio, 90) * 100) / 100,
          },
        },
        null,
        2,
      ),
    );
  } finally {
    await stopDaemon(daemon);
  }
}

const GLOBAL_TIMEOUT = setTimeout(() => {
  console.error("batch_bench: global timeout");
  process.exit(2);
}, 180_000);
GLOBAL_TIMEOUT.unref?.();

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
