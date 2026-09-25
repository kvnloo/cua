import type { BrowserSnapshot, Candidate, VisualObservation } from './core.js';

export type ObservationKind = 'snapshot' | 'visual';

export type ObservationRecord = Readonly<{
  step: number;
  kind: ObservationKind;
  captureId?: string;
  latencyMs: number;
}>;

/**
 * Provenance ledger for what the loop actually observed each step.
 *
 * Today the driver cannot report post-dispatch observation provenance
 * (see #4009 / #3971), so the loop records its own: which observation
 * modalities it paid for, per step. The ledger is what a future
 * `post_dispatch_observation` field would feed; the gating decision below
 * consumes it.
 */
export class ObservationLedger {
  private readonly records: ObservationRecord[] = [];

  record(entry: Omit<ObservationRecord, 'step'>, step: number): void;
  record(entry: ObservationRecord): void;
  record(entry: Omit<ObservationRecord, 'step'> | ObservationRecord, step?: number): void {
    const resolved =
      step === undefined
        ? (entry as ObservationRecord)
        : { ...(entry as Omit<ObservationRecord, 'step'>), step };
    this.records.push(Object.freeze(resolved));
  }

  entries(): readonly ObservationRecord[] {
    return this.records;
  }

  count(kind: ObservationKind): number {
    return this.records.filter((record) => record.kind === kind).length;
  }

  totalLatencyMs(kind?: ObservationKind): number {
    return this.records
      .filter((record) => kind === undefined || record.kind === kind)
      .reduce((sum, record) => sum + record.latencyMs, 0);
  }
}

/**
 * True when the candidate set already contains something the loop can
 * execute. The reserved `reobserve` / `abstain` candidates carry no tool;
 * their presence alone must not trigger the visual path.
 */
export function hasActionableCandidate(candidates: readonly Candidate[]): boolean {
  return candidates.some((candidate) => candidate.tool !== null);
}

/**
 * Whether the expensive visual observation (get_window_state +
 * parse_visual_regions) is worth paying for this step.
 *
 * Mirrors the only consumer of the visual result in `buildCandidates`:
 * the visual-submit fallback, which fires only when the DOM refs cannot
 * produce the submit candidate. When the snapshot already yields an
 * actionable candidate, the visual observation is pure overhead.
 */
export function needsVisualObservation(candidates: readonly Candidate[]): boolean {
  return !hasActionableCandidate(candidates);
}

export type { BrowserSnapshot, Candidate, VisualObservation };
