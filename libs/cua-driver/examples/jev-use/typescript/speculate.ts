/**
 * Speculative visual capture for the jev-use observation path.
 *
 * Chunk-5 measured the per-step cost as the RPC round trips themselves:
 * gated-sequential pays snapshot, then (when the visual fallback fires)
 * capture + parse as two more sequential groups. The capture does not depend
 * on the snapshot, so it can fly alongside it — but only the visual-submit
 * fallback consumes it, so firing it unconditionally wastes an RPC on every
 * DOM-complete step.
 *
 * The speculation policy: a sticky predictor. The visual need is sticky in
 * practice — when the DOM lacks an actionable candidate on step N, step N+1
 * usually needs the visual path too (the loop is still in the visual-submit
 * fallback). So: if the previous step needed visual, fire get_window_state
 * concurrently with this step's get_browser_state; when the fallback fires
 * again, only parse_visual_regions remains (2 round-trip groups instead of
 * 3). On a mispredicted step the capture is discarded (one wasted RPC);
 * on a missed prediction the loop falls back to the sequential path.
 *
 * Measured in bench/observation-gating/speculate_bench.ts against the mock
 * daemon with scripted visual-need sequences. Zero protocol change — works
 * against the real daemon today.
 */
import { parseVisualRegions, type VisualObservation } from './core.js';
import type { CallFn, ObserveStepArgs } from './batched.js';

export type { CallFn, ObserveStepArgs };

export const VISUAL_PARSE_OPTIONS = {
  kinds: ['text', 'icon'],
  min_confidence: 0.8,
  max_regions: 100,
} as const;

/**
 * Sticky predictor for "will this step need the visual path?".
 * Starts cold (no speculation on the first step); thereafter follows the
 * previous step's outcome. Also tracks prediction accuracy so the loop's
 * ledger can report how often speculation paid off.
 */
export class VisualSpeculator {
  private lastNeeded: boolean | undefined;
  private hits = 0;
  private falsePositives = 0;
  private misses = 0;

  shouldSpeculate(): boolean {
    return this.lastNeeded === true;
  }

  observe(needed: boolean): void {
    if (this.lastNeeded === true && needed) this.hits += 1;
    else if (this.lastNeeded === true) this.falsePositives += 1;
    else if (this.lastNeeded === false && needed) this.misses += 1;
    this.lastNeeded = needed;
  }

  stats(): { hits: number; falsePositives: number; misses: number } {
    return {
      hits: this.hits,
      falsePositives: this.falsePositives,
      misses: this.misses,
    };
  }
}

export type CaptureHandle = Promise<Record<string, any>>;

/**
 * Fire get_window_state alongside the snapshot when the predictor says yes.
 * The caller still issues get_browser_state itself so both fly concurrently.
 */
export function startSpeculativeCapture(
  call: CallFn,
  args: ObserveStepArgs,
  speculate: boolean,
): CaptureHandle | undefined {
  if (!speculate) return undefined;
  return call('get_window_state', {
    pid: args.pid,
    window_id: args.windowId,
    include_accessibility_tree: false,
  });
}

/**
 * Complete the visual observation from an in-flight speculative capture:
 * await the capture, then parse. One more round trip instead of two.
 */
export async function visualFromCapture(
  call: CallFn,
  capture: CaptureHandle,
  args: ObserveStepArgs,
): Promise<VisualObservation> {
  const resolved = await capture;
  if (typeof resolved.capture_id !== 'string') {
    throw new Error('capture returned no capture_id');
  }
  const wire = await call('parse_visual_regions', {
    capture_id: resolved.capture_id,
    options: { ...VISUAL_PARSE_OPTIONS },
  });
  return parseVisualRegions(wire, resolved.capture_id, args.pid, args.windowId);
}

/**
 * Discard an unused speculative capture. The RPC already flew, so this is
 * pure hygiene: without a rejection handler an in-flight failure becomes an
 * unhandled promise rejection. The loop records the waste in its ledger
 * (ObservationRecord.discarded), never as consumed evidence.
 */
export function discardCapture(capture: CaptureHandle | undefined): void {
  capture?.catch(() => {
    /* the RPC was paid for; its failure is irrelevant when unused */
  });
}
