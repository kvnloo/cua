import { compileExpectation, type Candidate } from './compiled_expectations.ts';

type Kind = 'run' | 'single' | 'reobserve' | 'abstain';
type Status = 'verified' | 'refuted' | 'unknown' | 'stale' | 'rebound' | 'refused';
type FastPathRoute = 'fast-path' | 'chooser';
type SecondReason =
  | 'allowed'
  | 'refuted'
  | 'unknown'
  | 'stale'
  | 'rebound'
  | 'refused'
  | 'missing_observation'
  | 'missing_capture'
  | 'field_mismatch'
  | 'submit_ref_mismatch';

type Fresh = { field_value: string | null; submit_ref: string | null; capture_id: string | null };

export type ParityRow = {
  case: string;
  fast_path_id: string | null;
  fast_path_route: FastPathRoute;
  executable_count: number;
  provider_called: boolean;
  run_admitted: boolean;
  second_dispatch: boolean;
  second_reason: SecondReason | null;
  expectation_kind: string | null;
};

const RESERVED = new Set(['reobserve', 'abstain']);

function candidate(id: string, tool: string | null, captureId?: string | null): Candidate {
  return { id, description: id, tool, arguments: {}, capture_id: captureId ?? null };
}

function explainFastPath(candidates: Candidate[]): {
  route: FastPathRoute;
  executableCount: number;
  candidateId: string | null;
  providerCalled: boolean;
} {
  const executable = candidates.filter((item) => !RESERVED.has(item.id) && item.tool != null);
  if (executable.length === 1) {
    return {
      route: 'fast-path',
      executableCount: 1,
      candidateId: executable[0].id,
      providerCalled: false,
    };
  }
  return {
    route: 'chooser',
    executableCount: executable.length,
    candidateId: null,
    providerCalled: true,
  };
}

function admit(
  candidates: Candidate[],
  kind: Kind,
  childIds: string[],
  token: string,
  submitRef: string,
): { token: string; submitRef: string } | null {
  if (kind !== 'run' || childIds.length !== 2 || !token || !submitRef) return null;
  const byId = new Map(candidates.map((item) => [item.id, item]));
  for (const id of childIds) {
    const item = byId.get(id);
    if (item == null || RESERVED.has(item.id) || item.tool == null) return null;
  }
  return { token, submitRef };
}

function explainSecond(
  status: Status,
  fresh: Fresh | null,
  plan: { token: string; submitRef: string },
): { allowed: boolean; reason: SecondReason } {
  if (status !== 'verified') return { allowed: false, reason: status };
  if (fresh == null) return { allowed: false, reason: 'missing_observation' };
  if (!fresh.capture_id) return { allowed: false, reason: 'missing_capture' };
  if (fresh.field_value !== plan.token) return { allowed: false, reason: 'field_mismatch' };
  if (fresh.submit_ref !== plan.submitRef) {
    return { allowed: false, reason: 'submit_ref_mismatch' };
  }
  return { allowed: true, reason: 'allowed' };
}

export function parityCorpus(): ParityRow[] {
  const typeC = candidate('type-verification-value', 'browser_type');
  const submit = candidate('submit-form', 'browser_click');
  const reobserve = candidate('reobserve', null);
  const abstain = candidate('abstain', null);
  const visual = candidate('visual-submit', 'browser_click', 'cap-1');
  const visualBare = candidate('visual-submit', 'browser_click', null);
  const fresh: Fresh = { field_value: 'proof', submit_ref: 'ref-submit', capture_id: 'cap-2' };
  const rebound: Fresh = { field_value: 'proof', submit_ref: 'other-ref', capture_id: 'cap-2' };
  const missingCapture: Fresh = { field_value: 'proof', submit_ref: 'ref-submit', capture_id: null };
  const cases: Array<{
    case: string;
    candidates: Candidate[];
    kind: Kind;
    childIds: string[];
    status: Status;
    fresh: Fresh | null;
    focus: Candidate;
  }> = [
    {
      case: 'one executable candidate',
      candidates: [typeC, reobserve],
      kind: 'single',
      childIds: ['type-verification-value'],
      status: 'verified',
      fresh,
      focus: typeC,
    },
    {
      case: 'reserved reobserve and abstain',
      candidates: [reobserve, abstain],
      kind: 'reobserve',
      childIds: [],
      status: 'verified',
      fresh,
      focus: reobserve,
    },
    {
      case: 'provider would reobserve',
      candidates: [typeC, reobserve],
      kind: 'reobserve',
      childIds: [],
      status: 'verified',
      fresh,
      focus: typeC,
    },
    {
      case: 'guarded continuation admitted',
      candidates: [typeC, submit],
      kind: 'run',
      childIds: ['type-verification-value', 'submit-form'],
      status: 'verified',
      fresh,
      focus: submit,
    },
    {
      case: 'guarded continuation refused',
      candidates: [typeC, submit],
      kind: 'single',
      childIds: ['type-verification-value'],
      status: 'verified',
      fresh,
      focus: submit,
    },
    {
      case: 'fresh target',
      candidates: [typeC, submit],
      kind: 'run',
      childIds: ['type-verification-value', 'submit-form'],
      status: 'verified',
      fresh,
      focus: submit,
    },
    {
      case: 'stale observation',
      candidates: [typeC, submit],
      kind: 'run',
      childIds: ['type-verification-value', 'submit-form'],
      status: 'verified',
      fresh: null,
      focus: submit,
    },
    {
      case: 'rebound ref',
      candidates: [typeC, submit],
      kind: 'run',
      childIds: ['type-verification-value', 'submit-form'],
      status: 'verified',
      fresh: rebound,
      focus: submit,
    },
    {
      case: 'missing capture',
      candidates: [typeC, submit],
      kind: 'run',
      childIds: ['type-verification-value', 'submit-form'],
      status: 'verified',
      fresh: missingCapture,
      focus: submit,
    },
    {
      case: 'postcondition refuted',
      candidates: [typeC, submit],
      kind: 'run',
      childIds: ['type-verification-value', 'submit-form'],
      status: 'refuted',
      fresh,
      focus: submit,
    },
    {
      case: 'postcondition unknown',
      candidates: [typeC, submit],
      kind: 'run',
      childIds: ['type-verification-value', 'submit-form'],
      status: 'unknown',
      fresh,
      focus: submit,
    },
    {
      case: 'visual submit expectation',
      candidates: [visual, reobserve],
      kind: 'single',
      childIds: ['visual-submit'],
      status: 'verified',
      fresh,
      focus: visual,
    },
    {
      case: 'visual submit without capture',
      candidates: [visualBare, reobserve],
      kind: 'single',
      childIds: ['visual-submit'],
      status: 'verified',
      fresh,
      focus: visualBare,
    },
  ];
  return cases.map((item) => {
    const fast = explainFastPath(item.candidates);
    const plan = admit(item.candidates, item.kind, item.childIds, 'proof', 'ref-submit');
    const second = plan == null ? null : explainSecond(item.status, item.fresh, plan);
    const compiled = compileExpectation(item.focus, 'proof');
    return {
      case: item.case,
      fast_path_id: fast.candidateId,
      fast_path_route: fast.route,
      executable_count: fast.executableCount,
      provider_called: fast.providerCalled,
      run_admitted: plan != null,
      second_dispatch: second?.allowed ?? false,
      second_reason: second?.reason ?? null,
      expectation_kind: compiled == null ? null : compiled.kind,
    };
  });
}
