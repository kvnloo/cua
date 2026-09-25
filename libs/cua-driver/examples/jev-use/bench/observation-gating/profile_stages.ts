/**
 * Stage profiler: after observation gating, where does the TS loop's
 * remaining per-step time go? Drives the visual-fallback scenario through
 * the mock daemon (real JSONL socket IPC) and times each stage with
 * hrtime: snapshot fetch, DOM candidate build, visual fetch (capture +
 * wire parse RPC), client parseVisualRegions, visual candidate rebuild,
 * chooseMock, and ledger/gate bookkeeping.
 *
 * Run: node --import tsx bench/observation-gating/profile_stages.ts
 * Time-bounded: daemon calls have a 10s timeout; script exits after N iters.
 */
import net from "node:net";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildCandidates, chooseMock, parseVisualRegions } from "../../typescript/core.js";
import { needsVisualObservation, ObservationLedger } from "../../typescript/observation.js";

const BENCH_DIR = path.dirname(fileURLToPath(import.meta.url));
const DAEMON = path.join(BENCH_DIR, "mock_daemon.mjs");
const TOKEN = "bench-token";
const PID = 4242;
const WINDOW_ID = 7;
const SOCKET = path.join(os.tmpdir(), `cua-profile-${process.pid}.sock`);

function startDaemon(regions: number): Promise<ChildProcess> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [DAEMON, "--socket", SOCKET, "--scenario", "visual-fallback", "--regions", String(regions)], {
      stdio: ["ignore", "pipe", "inherit"],
    });
    const timer = setTimeout(() => reject(new Error("daemon start timeout")), 10_000);
    child.stdout.on("data", (chunk: Buffer) => {
      if (chunk.toString().includes("ready")) { clearTimeout(timer); resolve(child); }
    });
    child.on("error", (error) => { clearTimeout(timer); reject(error); });
  });
}

async function stopDaemon(child: ChildProcess): Promise<void> {
  child.kill();
  await new Promise((resolve) => child.on("exit", resolve));
  try { fs.unlinkSync(SOCKET); } catch { /* gone */ }
}

async function daemonCall(name: string, args: Record<string, unknown>): Promise<{ result: Record<string, any>; latencyMs: number }> {
  const started = process.hrtime.bigint();
  const result = await new Promise<Record<string, any>>((resolve, reject) => {
    const connection = net.createConnection(SOCKET);
    let buffer = "";
    connection.setEncoding("utf8");
    const timer = setTimeout(() => { connection.destroy(); reject(new Error(`daemon call timeout: ${name}`)); }, 10_000);
    connection.on("connect", () => connection.write(`${JSON.stringify({ method: "call", name, args })}\n`));
    connection.on("data", (chunk: string) => {
      buffer += chunk;
      const newline = buffer.indexOf("\n");
      if (newline < 0) return;
      clearTimeout(timer);
      connection.end();
      try { resolve(JSON.parse(buffer.slice(0, newline))); }
      catch (error) { reject(error); }
    });
    connection.on("error", (error) => { clearTimeout(timer); reject(error); });
  });
  const latencyMs = Number(process.hrtime.bigint() - started) / 1e6;
  if (!result.ok) throw new Error(`daemon error on ${name}: ${result.error}`);
  return { result: result.result.structuredContent, latencyMs };
}

function ms(fn: () => void): number {
  const t0 = process.hrtime.bigint();
  fn();
  return Number(process.hrtime.bigint() - t0) / 1e6;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}
function p95(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))];
}

async function profile(regions: number, iters: number) {
  const daemon = await startDaemon(regions);
  const stages: Record<string, number[]> = {
    snapshot_fetch: [], build_candidates_dom: [], visual_fetch_rpc: [],
    parse_visual_regions: [], build_candidates_visual: [], choose: [], ledger_gate: [],
  };
  try {
    for (let i = 0; i < iters; i += 1) {
      const ledger = new ObservationLedger();
      let visual: any;
      let candidates: any[];

      const { result: snapshot, latencyMs: snapMs } = await daemonCall("get_browser_state",
        { target_id: "t", tab_id: "tab", snapshot_format: "semantic_v2" });
      stages.snapshot_fetch.push(snapMs);
      stages.build_candidates_dom.push(ms(() => { candidates = buildCandidates(snapshot, TOKEN, undefined, true); }));

      const t0 = process.hrtime.bigint();
      const { result: capture } = await daemonCall("get_window_state", { pid: PID, window_id: WINDOW_ID });
      const { result: wire } = await daemonCall("parse_visual_regions", {
        capture_id: capture.capture_id,
        options: { kinds: ["text", "icon"], min_confidence: 0.8, max_regions: 100 },
      });
      stages.visual_fetch_rpc.push(Number(process.hrtime.bigint() - t0) / 1e6);

      let parsed: any;
      stages.parse_visual_regions.push(ms(() => { parsed = parseVisualRegions(wire, capture.capture_id, PID, WINDOW_ID); }));
      stages.build_candidates_visual.push(ms(() => { candidates = buildCandidates(snapshot, TOKEN, parsed, true); }));

      const ledger0 = process.hrtime.bigint();
      ledger.record({ kind: "snapshot", latencyMs: snapMs }, i);
      ledger.record({ kind: "visual", captureId: capture.capture_id, latencyMs: 0 }, i);
      needsVisualObservation(candidates);
      stages.ledger_gate.push(Number(process.hrtime.bigint() - ledger0) / 1e6);

      stages.choose.push(ms(() => { chooseMock(candidates); }));
    }
  } finally {
    await stopDaemon(daemon);
  }
  const rows: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(stages)) {
    rows[k] = { median_ms: Math.round(median(v) * 1000) / 1000, p95_ms: Math.round(p95(v) * 1000) / 1000 };
  }
  return { regions, iters, rows };
}

async function main(): Promise<void> {
  const out: unknown[] = [];
  for (const regions of [50, 500]) out.push(await profile(regions, 30));
  console.log(JSON.stringify(out, null, 2));
}

main().catch((e) => { console.error(e); process.exit(1); });
