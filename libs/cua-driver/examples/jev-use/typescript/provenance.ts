import type { ObservationRecord } from './observation.js';

/**
 * What evidence the loop consumed to reach a dispatch decision at a step.
 * 'snapshot' / 'visual' are recorded by the loop itself today; 'driver'
 * marks evidence that came back inside a driver response — the field the
 * driver cannot yet send (#4009).
 */
export type EvidenceKind = 'snapshot' | 'visual' | 'driver';

/**
 * How the loop confirmed an action's effect took hold.
 * 'fixture' is what the jev-use loop does today (polls the oracle after
 * submit-form); 'snapshot-diff' is the loop's normal confirmation path
 * (the next step's snapshot is a fresh observation of the world the action
 * acted on); 'unverified' means nothing confirmed it — a downstream
 * consumer must treat the step as unknown, not settled.
 */
export type Settlement = 'fixture' | 'snapshot-diff' | 'unverified';

export type DispatchRecord = Readonly<{
  candidateId: string;
  tool: string | null;
  /** Every evidence kind consumed to reach this dispatch decision. */
  evidenceKinds: readonly EvidenceKind[];
}>;

export type SettlementRecord = Readonly<{
  verifiedBy: Settlement;
  latencyMs: number;
}>;

export type StepProvenance = Readonly<{
  step: number;
  observations: readonly ObservationRecord[];
  dispatch?: DispatchRecord;
  settlement?: SettlementRecord;
  /** #4009 post_dispatch_observation status, once the driver reports it. */
  postDispatch?: PostDispatchStatus;
}>;

/**
 * The post_dispatch_observation status vocabulary from #4009's proposal
 * (folded in 2026-09-25): the driver reports whether post-dispatch
 * observation ran, and the field NEVER promotes `effect`.
 *
 * - `completed`: the poll ran to its bound (including a timeout). The
 *   observation happened; nothing is claimed about the effect.
 * - `skipped`: the observation was NOT performed. This is the distinction
 *   Kevin's #4009 comment required: "not performed" must stay different
 *   from "performed and saw no relevant change."
 * - `unavailable`: the driver cannot do post-dispatch observation at all.
 */
export type PostDispatchStatus = 'completed' | 'skipped' | 'unavailable';

/**
 * Adapter for the driver-reported post-dispatch observation field
 * (the ActionResult vocabulary thread, #4009).
 *
 * The driver never sends this field today — there is no field on
 * `ActionResult` for it — so nothing in this module can be fed by the
 * driver yet. This type pins the SHAPE the ledger will consume when it
 * lands, keeping the example-side contract from drifting against the
 * contract-crate design while it is under discussion:
 * - `observedBeforeEffect`: the driver captured a pre-action observation.
 * - `observedAfterEffect`: the driver captured a post-action observation.
 * - `effectConfirmedBy`: how the driver knows the effect happened —
 *   tree diff, capture comparison, or nothing.
 * - `status`: the #4009 post_dispatch_observation status. A `completed`
 *   status never promotes `effect` — effect confirmation comes only from
 *   `effectConfirmedBy`, never from the poll having run.
 *
 * `ProvenanceLedger.noteDriverField` is the only entry point that accepts
 * this type; wiring it to the real MCP response belongs in run.ts when
 * #4009 resolves (see PROVENANCE.md).
 */
export type PostDispatchObservation = Readonly<{
  actionId: string;
  observedBeforeEffect: boolean;
  observedAfterEffect: boolean;
  effectConfirmedBy: 'tree-diff' | 'capture-compare' | 'none';
  status: PostDispatchStatus;
}>;

/**
 * Per-step provenance of what the loop observed, what it dispatched, and
 * how settlement was confirmed — the record a router or a handoff consumer
 * needs to distinguish "observed and settled" from "not observed".
 *
 * Today this is filled entirely from loop-side bookkeeping (the
 * ObservationLedger plus dispatch/settlement notes in run.ts). When #4009
 * lands, `noteDriverField` folds driver-reported provenance into the same
 * per-step record without changing its consumers.
 */
export class ProvenanceLedger {
  private readonly records = new Map<number, StepProvenance>();

  private entry(step: number): StepProvenance {
    let found = this.records.get(step);
    if (!found) {
      found = { step, observations: [] };
      this.records.set(step, found);
    }
    return found;
  }

  recordObservation(step: number, record: Omit<ObservationRecord, 'step'>): void {
    const existing = this.entry(step);
    const observations = [
      ...existing.observations,
      Object.freeze({ ...record, step }),
    ];
    this.records.set(step, { ...existing, observations });
  }

  noteDispatch(step: number, dispatch: DispatchRecord): void {
    const existing = this.entry(step);
    this.records.set(step, {
      ...existing,
      dispatch: Object.freeze({ ...dispatch, evidenceKinds: [...dispatch.evidenceKinds] }),
    });
  }

  noteSettlement(step: number, settlement: SettlementRecord): void {
    const existing = this.entry(step);
    this.records.set(step, { ...existing, settlement: Object.freeze({ ...settlement }) });
  }

  /**
   * Fold a driver-reported post-dispatch observation into the step that
   * dispatched the action, using #4009's post_dispatch_observation status:
   *
   * - `completed`: the poll ran to its bound. Folds 'driver' into the
   *   evidence kinds and applies the existing effectConfirmedBy promotion —
   *   but NEVER promotes `effect` on status alone: a completed poll is not
   *   effect confirmation.
   * - `skipped`: the observation was NOT performed. Recorded explicitly so
   *   "not performed" can never be read as "performed and saw no change";
   *   settlement is untouched.
   * - `unavailable`: the capability is absent. Recorded; settlement
   *   untouched.
   */
  noteDriverField(step: number, field: PostDispatchObservation): void {
    const existing = this.entry(step);
    const status = field.status;
    if (status === 'completed') {
      const dispatch = existing.dispatch
        ? {
            ...existing.dispatch,
            evidenceKinds: existing.dispatch.evidenceKinds.includes('driver')
              ? existing.dispatch.evidenceKinds
              : [...existing.dispatch.evidenceKinds, 'driver'],
          }
        : undefined;
      const settlement: SettlementRecord | undefined =
        field.effectConfirmedBy === 'none'
          ? existing.settlement
          : { verifiedBy: existing.settlement?.verifiedBy === 'fixture' ? 'fixture' : 'snapshot-diff', latencyMs: 0 };
      this.records.set(
        step,
        Object.freeze({
          ...existing,
          postDispatch: status,
          ...(dispatch ? { dispatch: Object.freeze(dispatch) } : {}),
          ...(settlement ? { settlement: Object.freeze(settlement) } : {}),
        }) as StepProvenance,
      );
      return;
    }
    // skipped / unavailable: record the status, touch nothing else.
    this.records.set(
      step,
      Object.freeze({ ...existing, postDispatch: status }) as StepProvenance,
    );
  }

  step(step: number): StepProvenance | undefined {
    return this.records.get(step);
  }

  steps(): readonly StepProvenance[] {
    return [...this.records.values()].sort((a, b) => a.step - b.step);
  }

  /**
   * True when the step dispatched an action AND the loop confirmed the
   * effect through some channel. An unverified step is not settled —
   * a consumer must re-observe rather than assume.
   */
  settled(step: number): boolean {
    const record = this.records.get(step);
    return (
      record?.dispatch !== undefined &&
      record.settlement !== undefined &&
      record.settlement.verifiedBy !== 'unverified'
    );
  }

  /**
   * Serializable handoff record: what was observed at each step, what was
   * dispatched on that evidence, and how settlement was confirmed. A router
   * consuming this can skip re-observation for steps whose evidence kinds
   * are fresh and whose settlement is confirmed, and must re-observe for
   * anything unverified.
   */
  handoff(): readonly StepProvenance[] {
    return this.steps();
  }
}
