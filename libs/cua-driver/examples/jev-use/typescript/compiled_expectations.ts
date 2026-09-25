export type Candidate = Readonly<{
  id: string;
  description: string;
  tool: string | null;
  arguments: Readonly<Record<string, unknown>>;
}>;

export type Expectation = Readonly<{ kind: string; token: string }>;

export function compileExpectation(candidate: Candidate, token: string): Expectation | null {
  if (candidate.id === 'reobserve' || candidate.id === 'abstain' || candidate.tool == null) {
    return null;
  }
  if (candidate.id === 'type-verification-value') {
    return { kind: 'field_value_equals', token };
  }
  if (candidate.id === 'submit-form') {
    return { kind: 'fixture_submitted_equals', token };
  }
  return null;
}

export function providerCannotReplace(compiled: Expectation, _offered: Expectation | null): Expectation {
  return compiled;
}
