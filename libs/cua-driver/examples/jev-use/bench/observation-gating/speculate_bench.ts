/**
 * Speculation-policy bench (paired design).
 *
 * Wires the chunk-6/8 speculation policy (typescript/speculate.ts) through the
 * real mock-daemon socket and compares three shapes against the
 * gated-sequential loop across scripted visual-need sequences:
 *   gated     — sequential baseline (no speculation)
 *   sticky    — sticky predictor, confirmation 1 (fires on previous need)
 *   confirmed — miss-rate gate, confirmation 2 (needs a confirmed run)
 *
 * Sequences:
 *   every      — visual needed on all 20 steps (fallback-heavy task)
 *   bursty     — 5 steps need visual, 5 don't, alternating (sticky runs)
 *   sparse     — visual needed on steps 1, 8, 15 (isolated misses)
 *   never      — 20 DOM-complete steps (predictor never fires)
 *   flicker    — T,F,T,F... (isolated needs; gate must suppress all waste)
 *   shortbursts— runs of 2 (shows the gate's run-start cost, not to flatter it)
 *
 * Each (sequence, iteration) runs all three shapes in randomized order
 * against a fresh daemon; per-iteration paired ratios cancel box-load drift.
 * The set_scenario and set_field calls are harness control and are not counted
 * as loop RPCs: set_field presets the verification field so each step's
 * visual need is deterministic — a "needed" step has the token already typed,
 * i.e. the loop is sitting in the visual-submit fallback exactly as it is
 * after the type action on a visual-fallback page.
 *
 * Equivalence gate: identical candidate and region counts per step across
 * shapes, or the bench fails.
 *
 * Env: BENCH_ONLY=sparse,flicker BENCH_ITERS=10 for subset re-runs.
 *
 * Run: node --import tsx bench/observation-gating/speculate_bench.ts
 */
import net from "node:net";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildCandidates, parseVisualRegions } from "../../typescript/core.js";
import { needsVisualObservation } from "../../typescript/observation.js";
import {
  discardCapture,
  startSpeculativeCapture,
  visualFromCapture,
  VisualSpeculator,
  type CallFn,
  type ObserveStepArgs,
} from "../../typescript/speculate.js";

const BENCH_DIR = path.dirname(fileURLToPath(import.meta.url));
const DAEMON = path.join(BENCH_DIR, "mock_daemon.mjs");
const SOCKET = path.join(os.tmpdir(), `cua-speculate-${process.pid}.sock`);

const TOKEN = "speculate-token";
const PID = 4242;
const WINDOW_ID = 7;
const ITERS = 20;
const REGIONS = 50;
const STEPS = 20;

const DOM = "dom-complete";
const FALLBACK = "visual-fallback";

const SEQUENCES: Record<string, Array<{ scenario: string; need: boolean }>> = {
  every: Array.from({ length: STEPS }, () => ({ scenario: FALLBACK, need: true })),
  bursty: Array.from({ length: STEPS }, (_, i) => {
    const need = Math.floor(i / 5) % 2 === 0;
    return { scenario: need ? FALLBACK : DOM, need };
  }),
  sparse: Array.from({ length: STEPS }, (_, i) => {
    const need = i === 0 || i === 7 || i === 14;
    return { scenario: need ? FALLBACK : DOM, need };
  }),
  never: Array.from({ length: STEPS }, () => ({ scenario: DOM, need: false })),
  // Isolated needs never confirm: the miss-rate gate should suppress every
  // wasted capture here while sticky wastes one per alternation.
  flicker: Array.from({ length: STEPS }, (_, i) => {
    const need = i % 2 === 0;
    return { scenario: need ? FALLBACK : DOM, need };
  }),
  // Runs of exactly 2: sticky fires on the run start (hit) and pays a
  // trailing false positive; the gate's confirmation cost shows up here —
  // this sequence exists to make the gate's loss visible, not to flatter it.
  shortbursts: Array.from({ length: STEPS }, (_, i) => {
    const need = i % 3 !== 2;
    return { scenario: need ? FALLBACK : DOM, need };
  }),
};

function startDaemon(): Promise<ChildProcess> {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [DAEMON, "--socket", SOCKET, "--scenario", DOM, "--regions", String(REGIONS)],
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

/** One request per connection, mirroring batch_bench.ts. */
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

type Shape = "gated" | "sticky" | "confirmed";

/** Policy per shape: gated = sequential baseline, sticky = confirmation 1,
 *  confirmed = the miss-rate gate (confirmation 2). */
function policyFor(shape: Shape): number | null {
  if (shape === "sticky") return 1;
  if (shape === "confirmed") return 2;
  return null;
}

type StepFingerprint = { candidates: number; regions: number };

type SequenceResult = {
  ms: number;
  rpcs: number;
  steps: StepFingerprint[];
  predictor: { hits: number; falsePositives: number; misses: number; suppressed: number };
};

/**
 * One pass of the scripted sequence through the per-step loop, mirroring
 * run.ts: snapshot, gate on candidates, visual path when needed. The
 * speculate shapes fire the capture alongside the snapshot when the
 * (possibly gated) predictor says yes.
 */
async function runSequence(
  shape: Shape,
  call: CallFn,
  scripted: Array<{ scenario: string; need: boolean }>,
): Promise<SequenceResult> {
  const confirmation = policyFor(shape);
  const speculator = confirmation === null ? null : new VisualSpeculator(confirmation);
  const args: ObserveStepArgs = { targetId: "t", tabId: "tab", pid: PID, windowId: WINDOW_ID };
  const steps: StepFingerprint[] = [];
  let rpcs = 0;
  const t0 = process.hrtime.bigint();
  for (const step of scripted) {
    // Harness control (not loop RPCs): put the loop in the exact observation
    // state the scripted sequence demands. A "needed" step has the token
    // already typed (the loop is sitting in the visual-submit fallback, as it
    // is after the type action on a visual-fallback page); an unneeded step
    // has the field still holding its previous value.
    await call("set_scenario", { scenario: step.scenario });
    await call("set_field", { value: step.need ? TOKEN : "other" });
    // Snapshot first: it is the critical path. The speculative capture then
    // fires alongside it — on a FIFO transport the snapshot must not queue
    // behind the capture.
    const snapshotPromise = call("get_browser_state", {
      target_id: args.targetId,
      tab_id: args.tabId,
      snapshot_format: "semantic_v2",
    });
    const capturePromise =
      speculator !== null
        ? startSpeculativeCapture(call, args, speculator.shouldSpeculate())
        : undefined;
    if (capturePromise) rpcs += 1;
    const snapshot = await snapshotPromise;
    rpcs += 1;
    let candidates = buildCandidates(snapshot as any, TOKEN, undefined, true);
    const needed = needsVisualObservation(candidates);
    let visual;
    if (needed) {
      if (capturePromise) {
        visual = await visualFromCapture(call, capturePromise, args);
        rpcs += 1; // parse only — the capture flew with the snapshot
      } else {
        const capture = await call("get_window_state", {
          pid: args.pid,
          window_id: args.windowId,
          include_accessibility_tree: false,
        });
        rpcs += 1;
        const wire = await call("parse_visual_regions", {
          capture_id: capture.capture_id,
          options: { kinds: ["text", "icon"], min_confidence: 0.8, max_regions: 100 },
        });
        rpcs += 1;
        visual = parseVisualRegions(wire, capture.capture_id, args.pid, args.windowId);
      }
      candidates = buildCandidates(snapshot as any, TOKEN, visual, true);
    } else {
      discardCapture(capturePromise);
    }
    speculator?.observe(needed);
    steps.push({ candidates: candidates.length, regions: visual ? visual.regions.length : 0 });
  }
  const ms = Number(process.hrtime.bigint() - t0) / 1e6;
  return { ms, rpcs, steps, predictor: speculator?.stats() ?? { hits: 0, falsePositives: 0, misses: 0, suppressed: 0 } };
}

async function main(): Promise<void> {
  const call: CallFn = socketCall;
  // Env overrides for contention re-runs (see daemon_load.mjs): run a
  // subset of sequences/fewer iters under load without editing the bench.
  const ONLY = (process.env.BENCH_ONLY ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  const iters = Math.max(1, parseInt(process.env.BENCH_ITERS ?? String(ITERS), 10) || ITERS);
  const SHAPES: Shape[] = ["gated", "sticky", "confirmed"];
  const report: Record<string, unknown> = {
    transport: "unix-socket JSONL, one connection per call (real IPC)",
    design: "paired: gated vs sticky vs confirmed interleaved per iteration on one daemon, Fisher-Yates order, warmup discarded",
    iters,
    steps_per_sequence: STEPS,
    regions: REGIONS,
    only: ONLY.length > 0 ? ONLY : "all",
  };
  const sequences: Record<string, unknown> = {};

  // One daemon for the whole run (like batch_bench.ts): per-step set_field
  // makes every step deterministic, so cross-iteration state is harmless.
  const daemon = await startDaemon();
  try {
    // Warmup: JIT + socket path, discarded.
    await runSequence("gated", call, SEQUENCES.bursty);
    await runSequence("sticky", call, SEQUENCES.bursty);
    await runSequence("confirmed", call, SEQUENCES.bursty);

    for (const [name, scripted] of Object.entries(SEQUENCES)) {
      if (ONLY.length > 0 && !ONLY.includes(name)) continue;
      const msByShape: Record<Shape, number[]> = { gated: [], sticky: [], confirmed: [] };
      const ratios: Record<string, number[]> = { "gated/sticky": [], "gated/confirmed": [], "sticky/confirmed": [] };
      let refSteps: StepFingerprint[] | null = null;
      const rpcs: Record<Shape, number> = { gated: -1, sticky: -1, confirmed: -1 };
      const predictors: Record<Shape, { hits: number; falsePositives: number; misses: number; suppressed: number }> = {
        gated: { hits: 0, falsePositives: 0, misses: 0, suppressed: 0 },
        sticky: { hits: 0, falsePositives: 0, misses: 0, suppressed: 0 },
        confirmed: { hits: 0, falsePositives: 0, misses: 0, suppressed: 0 },
      };
      for (let i = 0; i < iters; i += 1) {
        // Randomized per-iteration order cancels drift (JIT, box load).
        const order: Shape[] = [...SHAPES];
        for (let j = order.length - 1; j > 0; j -= 1) {
          const k = Math.floor(Math.random() * (j + 1));
          [order[j], order[k]] = [order[k], order[j]];
        }
        const results: Record<Shape, SequenceResult> = {
          gated: { ms: 0, rpcs: 0, steps: [], predictor: { hits: 0, falsePositives: 0, misses: 0, suppressed: 0 } },
          sticky: { ms: 0, rpcs: 0, steps: [], predictor: { hits: 0, falsePositives: 0, misses: 0, suppressed: 0 } },
          confirmed: { ms: 0, rpcs: 0, steps: [], predictor: { hits: 0, falsePositives: 0, misses: 0, suppressed: 0 } },
        };
        for (const shape of order) {
          results[shape] = await runSequence(shape, call, scripted);
        }
        // Equivalence gate: identical fingerprints across shapes.
        const fingerprints = SHAPES.map((s) => JSON.stringify(results[s].steps));
        if (!fingerprints.every((f) => f === fingerprints[0])) {
          throw new Error(`${name} iter ${i}: shapes diverged`);
        }
        if (!refSteps) refSteps = results.gated.steps;
        for (const s of SHAPES) {
          msByShape[s].push(results[s].ms);
          rpcs[s] = results[s].rpcs;
          predictors[s] = results[s].predictor;
        }
        ratios["gated/sticky"].push(results.gated.ms / results.sticky.ms);
        ratios["gated/confirmed"].push(results.gated.ms / results.confirmed.ms);
        ratios["sticky/confirmed"].push(results.sticky.ms / results.confirmed.ms);
      }
      const r = (v: number) => Math.round(v * 100) / 100;
      const shapeStats = (s: Shape) => ({
        rpcs_per_sequence: rpcs[s],
        median_ms: r(median(msByShape[s])),
        p90_ms: r(percentile(msByShape[s], 90)),
        predictor: predictors[s],
      });
      sequences[name] = {
        steps: scripted.filter((s) => s.need).length + " of " + STEPS + " need visual",
        shapes: { gated: shapeStats("gated"), sticky: shapeStats("sticky"), confirmed: shapeStats("confirmed") },
        paired_speedup_median: {
          "gated/sticky": r(median(ratios["gated/sticky"])),
          "gated/confirmed": r(median(ratios["gated/confirmed"])),
          "sticky/confirmed": r(median(ratios["sticky/confirmed"])),
        },
        paired_speedup_p90: {
          "gated/sticky": r(percentile(ratios["gated/sticky"], 90)),
          "gated/confirmed": r(percentile(ratios["gated/confirmed"], 90)),
          "sticky/confirmed": r(percentile(ratios["sticky/confirmed"], 90)),
        },
        per_iteration_ratios: Object.fromEntries(
          Object.entries(ratios).map(([k, v]) => [k, v.map(r)]),
        ),
        equivalence: "identical candidates/regions every step, all iters, all shapes",
      };
    }
  } finally {
    await stopDaemon(daemon);
  }
  report.sequences = sequences;
  console.log(JSON.stringify(report, null, 2));
}

const GLOBAL_TIMEOUT = setTimeout(() => {
  console.error("speculate_bench: global timeout");
  process.exit(2);
}, 900_000);
GLOBAL_TIMEOUT.unref?.();

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
