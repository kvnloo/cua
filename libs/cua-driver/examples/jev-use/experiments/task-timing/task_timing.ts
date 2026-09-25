/** Fork-only timing; fixture observations and runner outcomes are separate facts. */
import { randomUUID } from 'node:crypto';

export type TerminalObservation = {
  verdict: 'verified' | 'refuted';
  at_ms: number;
  source: 'existing_fixture_state_classification';
};
type Event = Record<string, unknown>;

export class TaskTiming {
  readonly taskId = randomUUID();
  readonly clockId = `performance.now:${this.taskId}`;
  private readonly start: number;
  private readonly spans: Event[] = [];
  private dropped = 0;
  private setupEnd: number | null = null;
  private terminal: TerminalObservation | null = null;
  private closed = false;

  constructor(private readonly clock: () => number = () => performance.now(),
              private readonly maxSpans = 512) {
    if (!Number.isInteger(maxSpans) || maxSpans < 0) {
      throw new RangeError('maxSpans must be a nonnegative integer');
    }
    this.start = clock();
  }
  private elapsed(): number { return this.clock() - this.start; }
  setupComplete(): void {
    if (this.setupEnd === null) this.setupEnd = this.elapsed();
  }
  classified<T extends string>(verdict: T): T {
    if ((verdict === 'verified' || verdict === 'refuted') && this.terminal === null) {
      this.terminal = { verdict: verdict === 'verified' ? 'verified' : 'refuted', at_ms: this.elapsed(),
        source: 'existing_fixture_state_classification' };
    }
    return verdict;
  }
  private record(phase: string, start: number, errorType: string | null): void {
    const event = { event: 'span', task_id: this.taskId, clock_id: this.clockId,
      phase, start_ms: start, end_ms: this.elapsed(), error_type: errorType };
    if (this.spans.length < this.maxSpans) this.spans.push(event);
    else this.dropped += 1;
  }
  measureSync<T>(phase: string, operation: () => T): T {
    const start = this.elapsed();
    let errorType: string | null = null;
    try { return operation(); }
    catch (error: unknown) {
      errorType = error instanceof Error ? error.name : 'UnknownError';
      throw error;
    } finally { this.record(phase, start, errorType); }
  }
  async measureAsync<T>(phase: string, operation: () => Promise<T>): Promise<T> {
    const start = this.elapsed();
    let errorType: string | null = null;
    try { return await operation(); }
    catch (error: unknown) {
      errorType = error instanceof Error ? error.name : 'UnknownError';
      throw error;
    } finally { this.record(phase, start, errorType); }
  }
  finish(outcome: string, dryRun = false, errorType: string | null = null): Event[] {
    if (this.closed) throw new Error('task timing already closed');
    this.closed = true;
    const end = this.elapsed();
    return [...this.spans, {
      event: 'task_root', schema_version: 2, task_id: this.taskId, clock_id: this.clockId,
      start_ms: 0, end_ms: end, setup_ms: this.setupEnd, outcome,
      outcome_source: 'recipe_return_not_independent_oracle', error_type: errorType,
      dry_run: dryRun, dropped_spans: this.dropped,
      scope: 'run_entry_through_context_cleanup_before_timing_flush',
      terminal_observation: this.terminal,
      post_terminal_observation_ms: this.terminal === null ? null : end - this.terminal.at_ms,
    }];
  }
}
