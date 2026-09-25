/**
 * Live-protocol benchmark: modality-gated observation through the real wire format.
 *
 * bench.ts measured the gating policy's call pattern with a fake in-process
 * driver and virtual latencies. This bench goes one step stronger: the loop
 * talks to mock_daemon.mjs over the daemon's newline-delimited JSON socket
 * protocol, so every observation call pays REAL serialization, REAL socket
 * IPC, and REAL client-side parsing (parseVisualRegions over the wire
 * payload). The driver behind the socket is still a fixture (no browser),
 * but the observation path the gate skips is byte-for-byte the real one.
 *
 * Run: node --import tsx bench/observation-gating/live_bench.ts
 * (starts/restarts the daemon itself; keep runs time-bounded)
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
const SOCKET = path.join(os.tmpdir(), `cua-mock-${process.pid}.sock`);

type Scenario = "dom-complete" | "visual-fallback";
type Policy = "baseline" | "gated";

function startDaemon(scenario: Scenario, regions: number): Promise<ChildProcess> {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [DAEMON, "--socket", SOCKET, "--scenario", scenario, "--regions", String(regions)],
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
    child.on("exit", (code) => {
      if (code !== 0 && code !== null) {
        clearTimeout(timer);
        reject(new Error(`daemon exited with ${code}`));
      }
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

/** Minimal client for the daemon's JSONL socket protocol. */
async function daemonCall(
  name: string,
  args: Record<string, unknown>,
): Promise<{ result: Record<string, any>; latencyMs: number }> {
  const started = process.hrtime.bigint();
  const result = await new Promise<Record<string, any>>((resolve, reject) => {
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
        resolve(JSON.parse(buffer.slice(0, newline)));
      } catch (error) {
        reject(error);
      }
    });
    connection.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
  });
  const latencyMs = Number(process.hrtime.bigint() - started) / 1e6;
  if (!result.ok) throw new Error(`daemon error on ${name}: ${result.error}`);
  return { result: result.result.structuredContent, latencyMs };
}

type StepSummary = {
  verified: boolean;
  steps: number;
  observationCalls: number;
  visualCalls: number;
  observationMsReal: number;
  ledger: ObservationLedger;
};

async function runTask(policy: Policy, scenario: Scenario, regions: number): Promise<StepSummary> {
  const daemon = await startDaemon(scenario, regions);
  try {
    const ledger = new ObservationLedger();
    let observationCalls = 0;
    let visualCalls = 0;
    let observationMsReal = 0;
    let steps = 0;

    const observe = async (
      kind: "snapshot" | "visual",
      name: string,
      args: Record<string, unknown>,
      step: number,
      captureId?: string,
    ) => {
      const { result, latencyMs } = await daemonCall(name, args);
      observationCalls += 1;
      observationMsReal += latencyMs;
      ledger.record({ kind, captureId, latencyMs: Math.round(latencyMs * 100) / 100 }, step);
      return result;
    };

    for (let step = 1; step <= 6; step += 1) {
      steps = step;
      const { result: submitted } = await daemonCall("fixture_submitted", {});
      if (submitted.submitted === TOKEN) return { verified: true, steps, observationCalls, visualCalls, observationMsReal, ledger };

      const snapshot: any = await observe("snapshot", "get_browser_state",
        { target_id: "t", tab_id: "tab", snapshot_format: "semantic_v2" }, step);
      let candidates = buildCandidates(snapshot, TOKEN, undefined, true);
      if (policy === "baseline" || needsVisualObservation(candidates)) {
        const capture: any = await observe("visual", "get_window_state",
          { pid: PID, window_id: WINDOW_ID }, step);
        const wire: any = await observe("visual", "parse_visual_regions",
          {
            capture_id: capture.capture_id,
            options: { kinds: ["text", "icon"], min_confidence: 0.8, max_regions: 100 },
          },
          step,
          capture.capture_id,
        );
        visualCalls += 1;
        const visual = parseVisualRegions(wire, capture.capture_id, PID, WINDOW_ID);
        candidates = buildCandidates(snapshot, TOKEN, visual, true);
      }
      const answer = chooseMock(candidates);
      if (!answer.choice || answer.choice === "abstain" || answer.choice === "reobserve") {
        return { verified: false, steps, observationCalls, visualCalls, observationMsReal, ledger };
      }
      const candidate = candidates.find((item) => item.id === answer.choice)!;
      if (!candidate.tool) return { verified: false, steps, observationCalls, visualCalls, observationMsReal, ledger };
      await daemonCall(candidate.tool, candidate.arguments as Record<string, unknown>);
    }
    const { result: submitted } = await daemonCall("fixture_submitted", {});
    return { verified: submitted.submitted === TOKEN, steps, observationCalls, visualCalls, observationMsReal, ledger };
  } finally {
    await stopDaemon(daemon);
  }
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

async function main(): Promise<void> {
  const regions = 50;
  const rows: Record<string, unknown>[] = [];
  for (const scenario of ["dom-complete", "visual-fallback"] as Scenario[]) {
    for (const policy of ["baseline", "gated"] as Policy[]) {
      const samples: StepSummary[] = [];
      for (let i = 0; i < 3; i += 1) samples.push(await runTask(policy, scenario, regions));
      if (!samples.every((s) => s.verified)) {
        throw new Error(`${policy}/${scenario} did not verify`);
      }
      rows.push({
        scenario,
        policy,
        regions,
        steps: samples[0].steps,
        observation_calls: samples[0].observationCalls,
        visual_calls: samples[0].visualCalls,
        observation_ms_real_median: Math.round(median(samples.map((s) => s.observationMsReal)) * 100) / 100,
        ledger_visual_count: samples[0].ledger.count("visual"),
      });
    }
  }
  console.log(JSON.stringify({ transport: "unix-socket JSONL (real IPC)", rows }, null, 2));

  // Region-count scaling: what the gate skips grows with payload size.
  console.log("--- visual-path cost vs region count (dom-complete, real IPC) ---");
  for (const count of [10, 100, 500]) {
    const daemon = await startDaemon("dom-complete", count);
    try {
      const t0 = process.hrtime.bigint();
      const { result: capture } = await daemonCall("get_window_state", { pid: PID, window_id: WINDOW_ID });
      const { result: wire } = await daemonCall("parse_visual_regions", {
        capture_id: capture.capture_id,
        options: { kinds: ["text", "icon"], min_confidence: 0.8, max_regions: 100 },
      });
      const wireMs = Number(process.hrtime.bigint() - t0) / 1e6;
      const p0 = process.hrtime.bigint();
      const visual = parseVisualRegions(wire, capture.capture_id, PID, WINDOW_ID);
      const parseMs = Number(process.hrtime.bigint() - p0) / 1e6;
      console.log(
        `regions=${count}: wire_roundtrip=${wireMs.toFixed(2)}ms ` +
        `client_parse=${parseMs.toFixed(2)}ms parsed_regions=${visual.regions.length}`,
      );
    } finally {
      await stopDaemon(daemon);
    }
  }
}

const GLOBAL_TIMEOUT = setTimeout(() => {
  console.error("live_bench: global timeout");
  process.exit(2);
}, 120_000);
GLOBAL_TIMEOUT.unref?.();

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
