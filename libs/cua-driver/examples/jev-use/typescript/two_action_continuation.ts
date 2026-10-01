/**
 * Content-free journals for the narrow two-action guarded continuation.
 *
 * Extends trycua/cua#3963 / #4316 / kvnloo/cua#5 KEEP evidence.
 * Fork #79 owns single-resolve session authority; this leaf attributes the
 * full 2→1 continuation contract (provider→guarded-completion, one-shot
 * plan consume, fail-closed child-2).
 */
import {
  planGuardedCompletion,
  resolveGuardedCompletion,
  type GuardedCompletionPlan,
} from './guarded_completion.js';
import type { Candidate } from './sources.js';
import type { Task, TaskSources } from './tasks.js';

export type ContinuationRoute = 'provider' | 'guarded-completion' | 'chooser';

export type ContinuationStepReceipt = Readonly<{
  step: number;
  route: ContinuationRoute;
  candidate_id: string | null;
  provider_called: boolean;
  dispatch_attempted: boolean;
  plan_pending_after: boolean;
}>;

export type TwoActionContinuationJournal = Readonly<{
  provider_decisions: number;
  actions_dispatched: number;
  guarded_child_admitted: boolean;
  decision_routes: readonly string[];
  plan_consumed: boolean;
  second_dispatch_attempted: boolean;
  steps: readonly ContinuationStepReceipt[];
}>;

export function journalTwoActionContinuation(
  task: Task,
  initialSources: TaskSources,
  freshSources: TaskSources,
  session: string,
  thirdSources?: TaskSources
): TwoActionContinuationJournal {
  const steps: ContinuationStepReceipt[] = [];
  let providerDecisions = 0;
  let actionsDispatched = 0;
  let guardedChildAdmitted = false;
  let secondDispatchAttempted = false;
  let pending: GuardedCompletionPlan | undefined;

  const initialCandidates = task.candidates(initialSources);
  if (initialCandidates.length === 0) {
    throw new Error('initial step requires at least one candidate');
  }
  const first = initialCandidates[0];
  providerDecisions += 1;
  actionsDispatched += 1;
  pending = planGuardedCompletion(task, initialSources, first, session);
  steps.push(
    Object.freeze({
      step: 1,
      route: 'provider',
      candidate_id: first.id,
      provider_called: true,
      dispatch_attempted: true,
      plan_pending_after: pending !== undefined,
    })
  );

  const candidates = task.candidates(freshSources);
  let guarded: Candidate | undefined;
  if (pending) {
    const resolution = resolveGuardedCompletion(
      pending,
      task,
      freshSources,
      candidates,
      session
    );
    guarded = resolution.candidate;
  }
  // Mirror run.py: a failed proof never keeps authority alive.
  pending = undefined;

  if (guarded) {
    actionsDispatched += 1;
    guardedChildAdmitted = true;
    secondDispatchAttempted = true;
    steps.push(
      Object.freeze({
        step: 2,
        route: 'guarded-completion',
        candidate_id: guarded.id,
        provider_called: false,
        dispatch_attempted: true,
        plan_pending_after: false,
      })
    );
  } else {
    providerDecisions += 1;
    steps.push(
      Object.freeze({
        step: 2,
        route: 'chooser',
        candidate_id: null,
        provider_called: true,
        dispatch_attempted: false,
        plan_pending_after: false,
      })
    );
  }

  if (thirdSources) {
    steps.push(
      Object.freeze({
        step: 3,
        route: 'chooser',
        candidate_id: null,
        provider_called: true,
        dispatch_attempted: false,
        plan_pending_after: false,
      })
    );
    providerDecisions += 1;
  }

  return Object.freeze({
    provider_decisions: providerDecisions,
    actions_dispatched: actionsDispatched,
    guarded_child_admitted: guardedChildAdmitted,
    decision_routes: Object.freeze(steps.map((step) => step.route)),
    plan_consumed: true,
    second_dispatch_attempted: secondDispatchAttempted,
    steps: Object.freeze(steps),
  });
}
