/**
 * Narrow caller-side guarded completion for the built-in browser fixture.
 *
 * The provider still chooses the first mutation. The caller may skip exactly
 * one later provider decision only when a fresh semantic snapshot re-proves
 * the completion target. The plan binds the Cua session and logical target; it
 * never carries an old page ref forward as action authority.
 */
import type { Candidate } from './sources.js';
import {
  FIXTURE_TASK_ID,
  SUBMIT_NAME,
  type Task,
  type TaskSources,
} from './tasks.js';

export const TYPE_CANDIDATE_ID = 'type-verification-value';
export const SUBMIT_CANDIDATE_ID = 'submit-form';

export type GuardedCompletionPlan = Readonly<{
  session: string;
  firstCandidateId: string;
  completionCandidateId: string;
  targetRole: string;
  targetName: string;
  priorRef: string;
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

export function planGuardedCompletion(
  task: Task,
  sources: TaskSources,
  selected: Candidate,
  session: string
): GuardedCompletionPlan | undefined {
  if (
    !session ||
    task.id !== FIXTURE_TASK_ID ||
    selected.id !== TYPE_CANDIDATE_ID ||
    selected.tool !== 'browser_type' ||
    selected.source !== 'page' ||
    !sources.page
  ) {
    return undefined;
  }
  const matches = matchingRefs(sources.page.snapshot, 'button', SUBMIT_NAME);
  if (matches.length !== 1) return undefined;
  return Object.freeze({
    session,
    firstCandidateId: selected.id,
    completionCandidateId: SUBMIT_CANDIDATE_ID,
    targetRole: 'button',
    targetName: SUBMIT_NAME,
    priorRef: String(matches[0].ref),
  });
}

export function resolveGuardedCompletion(
  plan: GuardedCompletionPlan,
  task: Task,
  sources: TaskSources,
  candidates: readonly Candidate[],
  session: string
): Candidate | undefined {
  if (!session || session !== plan.session || task.id !== FIXTURE_TASK_ID || !sources.page) {
    return undefined;
  }
  const state = task.stateSummary(sources);
  if (state.verification_field !== 'contains_required_token') return undefined;

  const matches = matchingRefs(sources.page.snapshot, plan.targetRole, plan.targetName);
  if (matches.length !== 1) return undefined;
  const freshRef = String(matches[0].ref);

  const executable = candidates.filter(
    (candidate) =>
      candidate.id === plan.completionCandidateId &&
      candidate.tool === 'browser_click' &&
      candidate.source === 'page'
  );
  if (executable.length !== 1) return undefined;
  const candidate = executable[0];
  if (candidate.arguments.ref !== freshRef) return undefined;
  return candidate;
}
