/**
 * Content-free route receipts for bound-completion session authority.
 *
 * Extends trycua/cua#3963 / #4316 / kvnloo/cua#36.
 * Exact one session-bound completion candidate may skip the provider;
 * foreign-session or non-unique completion falls closed to the chooser.
 */
import {
  resolveGuardedCompletion,
  type GuardedCompletionPlan,
} from './guarded_completion.js';
import type { Candidate } from './sources.js';
import { FIXTURE_TASK_ID, type Task, type TaskSources } from './tasks.js';

export type BoundCompletionRoute = 'guarded-completion' | 'chooser';
export type BoundCompletionReason =
  | 'allowed'
  | 'session_mismatch'
  | 'missing_session'
  | 'task_mismatch'
  | 'missing_page'
  | 'postcondition_unverified'
  | 'non_unique_target'
  | 'stale_or_reused_ref'
  | 'non_unique_completion'
  | 'ref_mismatch';

export type BoundCompletionEvidence = Readonly<{
  route: BoundCompletionRoute;
  reason: BoundCompletionReason;
  executable_count: number;
  provider_called: boolean;
  plan_session: string;
  resolve_session: string;
  selected_id: string | null;
  dispatch_attempted: boolean;
}>;

function matchingRefs(
  snapshot: Readonly<Record<string, unknown>>,
  role: string,
  name: string
): Readonly<Record<string, unknown>>[] {
  const refs = Array.isArray(snapshot.refs) ? snapshot.refs : [];
  return refs.filter(
    (item): item is Readonly<Record<string, unknown>> =>
      Boolean(item) &&
      typeof item === 'object' &&
      !Array.isArray(item) &&
      (item as Record<string, unknown>).role === role &&
      (item as Record<string, unknown>).name === name &&
      typeof (item as Record<string, unknown>).ref === 'string' &&
      Boolean((item as Record<string, unknown>).ref)
  );
}

function closed(
  planSession: string,
  resolveSession: string,
  reason: BoundCompletionReason,
  executableCount = 0
): BoundCompletionEvidence {
  return Object.freeze({
    route: 'chooser',
    reason,
    executable_count: executableCount,
    provider_called: true,
    plan_session: planSession,
    resolve_session: resolveSession,
    selected_id: null,
    dispatch_attempted: false,
  });
}

export function explainBoundCompletion(
  plan: GuardedCompletionPlan,
  task: Task,
  sources: TaskSources,
  candidates: readonly Candidate[],
  session: string
): BoundCompletionEvidence {
  const planSession = plan.session;
  const resolveSession = session || '';

  if (!resolveSession) return closed(planSession, resolveSession, 'missing_session');
  if (resolveSession !== planSession) {
    return closed(planSession, resolveSession, 'session_mismatch');
  }
  if (task.id !== FIXTURE_TASK_ID) {
    return closed(planSession, resolveSession, 'task_mismatch');
  }
  if (!sources.page) return closed(planSession, resolveSession, 'missing_page');

  const state = task.stateSummary(sources);
  if (state.verification_field !== 'contains_required_token') {
    return closed(planSession, resolveSession, 'postcondition_unverified');
  }

  const matches = matchingRefs(
    sources.page.snapshot,
    plan.targetRole,
    plan.targetName
  );
  if (matches.length !== 1) {
    return closed(planSession, resolveSession, 'non_unique_target');
  }
  const freshRef = String(matches[0].ref);
  if (freshRef === plan.priorRef) {
    return closed(planSession, resolveSession, 'stale_or_reused_ref');
  }

  const executable = candidates.filter(
    (candidate) =>
      candidate.id === plan.completionCandidateId &&
      candidate.tool === 'browser_click' &&
      candidate.source === 'page'
  );
  const executableCount = executable.length;
  if (executableCount !== 1) {
    return closed(
      planSession,
      resolveSession,
      'non_unique_completion',
      executableCount
    );
  }

  const candidate = executable[0];
  if (candidate.arguments.ref !== freshRef) {
    return closed(planSession, resolveSession, 'ref_mismatch', 1);
  }

  const resolution = resolveGuardedCompletion(
    plan,
    task,
    sources,
    candidates,
    resolveSession
  );
  const resolved = resolution.candidate;
  if (
    !resolved ||
    resolution.telemetry.status !== 'accepted' ||
    resolved.id !== candidate.id
  ) {
    return closed(planSession, resolveSession, 'ref_mismatch', 1);
  }

  return Object.freeze({
    route: 'guarded-completion',
    reason: 'allowed',
    executable_count: 1,
    provider_called: false,
    plan_session: planSession,
    resolve_session: resolveSession,
    selected_id: candidate.id,
    dispatch_attempted: true,
  });
}
