/**
 * Transport batching for the jev-use observation path.
 *
 * Chunk-4's stage profile found every TS-side stage sub-0.2ms; the per-step
 * cost is the RPC round trips themselves (one socket connection per call on
 * the daemon's JSONL protocol). Two client-side shapes, measured in
 * bench/observation-gating/batch_bench.ts:
 *
 * - parallel: fire independent observation RPCs concurrently. get_browser_state
 *   and get_window_state do not depend on each other, so they go out together
 *   over separate connections; parse_visual_regions still waits for the
 *   capture. Zero protocol change — works against the real daemon today.
 *
 * - combined: one `observe_visual` RPC that captures and parses daemon-side.
 *   PROTOTYPE protocol extension — only the mock daemon implements it. It
 *   measures the ceiling for a real daemon-side combined call; adopting it
 *   upstream would be a contract decision, not a recipe decision.
 *
 * Both compose a CallFn so tests run against a fake transport.
 */
import { parseVisualRegions, type VisualObservation } from './core.js';

export type CallFn = (
  name: string,
  args: Record<string, unknown>,
) => Promise<Record<string, any>>;

export type ObserveStepArgs = {
  targetId: string;
  tabId: string;
  pid: number;
  windowId: number;
};

/** Sequential baseline: snapshot, then capture, then parse — 3 round trips. */
export async function observeSequential(
  call: CallFn,
  args: ObserveStepArgs,
): Promise<{ snapshot: Record<string, any>; visual: VisualObservation }> {
  const snapshot = await call('get_browser_state', {
    target_id: args.targetId,
    tab_id: args.tabId,
    snapshot_format: 'semantic_v2',
  });
  const capture = await call('get_window_state', {
    pid: args.pid,
    window_id: args.windowId,
    include_accessibility_tree: false,
  });
  const wire = await call('parse_visual_regions', {
    capture_id: capture.capture_id,
    options: { kinds: ['text', 'icon'], min_confidence: 0.8, max_regions: 100 },
  });
  return {
    snapshot,
    visual: parseVisualRegions(wire, capture.capture_id, args.pid, args.windowId),
  };
}

/**
 * Parallel shape: snapshot and window capture fly concurrently; parse waits
 * for the capture only. 3 RPCs, 2 sequential groups. No protocol change.
 */
export async function observeParallel(
  call: CallFn,
  args: ObserveStepArgs,
): Promise<{ snapshot: Record<string, any>; visual: VisualObservation }> {
  const [snapshot, capture] = await Promise.all([
    call('get_browser_state', {
      target_id: args.targetId,
      tab_id: args.tabId,
      snapshot_format: 'semantic_v2',
    }),
    call('get_window_state', {
      pid: args.pid,
      window_id: args.windowId,
      include_accessibility_tree: false,
    }),
  ]);
  const wire = await call('parse_visual_regions', {
    capture_id: capture.capture_id,
    options: { kinds: ['text', 'icon'], min_confidence: 0.8, max_regions: 100 },
  });
  return {
    snapshot,
    visual: parseVisualRegions(wire, capture.capture_id, args.pid, args.windowId),
  };
}

/**
 * Combined shape: a single prototype `observe_visual` RPC returns the visual
 * payload (capture + regions) in one round trip. Daemon-side only the mock
 * implements this; treat numbers as the contract-change ceiling.
 */
export async function observeCombined(
  call: CallFn,
  args: ObserveStepArgs,
): Promise<{ snapshot: Record<string, any>; visual: VisualObservation }> {
  const snapshot = await call('get_browser_state', {
    target_id: args.targetId,
    tab_id: args.tabId,
    snapshot_format: 'semantic_v2',
  });
  const wire = await call('observe_visual', {
    pid: args.pid,
    window_id: args.windowId,
    options: { kinds: ['text', 'icon'], min_confidence: 0.8, max_regions: 100 },
  });
  if (typeof wire.capture_id !== 'string') {
    throw new Error('observe_visual returned no capture_id');
  }
  return {
    snapshot,
    visual: parseVisualRegions(wire, wire.capture_id, args.pid, args.windowId),
  };
}
