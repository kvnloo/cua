/** Generate a separate pinned TS runner. No tracked runner is edited. */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const ts = require('typescript');
const sourcePath = path.join(__dirname, '../../typescript/run.ts');
const raw = fs.readFileSync(sourcePath);
const hash = crypto.createHash('sha1').update(`blob ${raw.length}\0`).update(raw).digest('hex');
if (hash !== 'dbb26b67143b425b21d26ebb257e1e76f7cc25c3') {
  throw new Error(`Refusing pinned runner drift: ${hash}`);
}
const source = ts.createSourceFile('run.ts', raw.toString(), ts.ScriptTarget.Latest, true);
const f = ts.factory;
const counts = {};
let classifications = 0;
const ident = (s) => f.createIdentifier(s);
function wrapped(phase, expression, async) {
  counts[phase] = (counts[phase] || 0) + 1;
  const operation = f.createArrowFunction(undefined, undefined, [], undefined,
    f.createToken(ts.SyntaxKind.EqualsGreaterThanToken), expression);
  const call = f.createCallExpression(f.createPropertyAccessExpression(ident('taskTiming'),
    async ? 'measureAsync' : 'measureSync'), undefined, [f.createStringLiteral(phase), operation]);
  return async ? f.createAwaitExpression(call) : call;
}
const transformer = (context) => {
  function inside(node) {
    if (ts.isAwaitExpression(node)) {
      const e = node.expression;
      const name = ts.isCallExpression(e) ? e.expression.getText(source) : '';
      const phase = { 'resetFixture':'setup.reset', 'client.connect':'setup.initialize',
        'client.listTools':'setup.tools', 'waitForWindow':'setup.window_ready',
        'fixtureState':'verify', 'optionalVisualObservation':'visual_observe',
        'chooseLive':'provider_decision', 'client.close':'cleanup' }[name];
      if (phase) return wrapped(phase, e, true);
      if (name === 'driver.call') {
        const op = e.arguments[0];
        const value = ts.isStringLiteral(op) ? op.text : 'action';
        const p = { browser_prepare:'setup.prepare', browser_navigate:'setup.navigate',
          get_browser_state:e.getText(source).includes('snapshot_format') ? 'semantic_observe':'setup.bind',
          action:'act' }[value];
        if (!p) throw new Error(`Unexpected Driver call: ${value}`);
        return wrapped(p, e, true);
      }
      if (ts.isNewExpression(e) && e.expression.getText(source) === 'Promise') {
        return wrapped('wait', e, true);
      }
    }
    if (ts.isCallExpression(node)) {
      const name = node.expression.getText(source);
      const p = { buildCandidates:'candidate_build', chooseMockAdapter:'provider_decision',
        validateChoice:'validate_choice' }[name];
      if (p) return wrapped(p, node, false);
      if (name === 'classify') {
        classifications++;
        return f.createCallExpression(f.createPropertyAccessExpression(ident('taskTiming'), 'classified'),
          undefined, [node]);
      }
    }
    if (ts.isBlock(node)) {
      const statements = [];
      for (const statement of node.statements) {
        statements.push(ts.visitNode(statement, inside));
        if (ts.isExpressionStatement(statement) && statement.getText(source).startsWith("await driver.call('browser_navigate'")) {
          statements.push(f.createExpressionStatement(f.createCallExpression(
            f.createPropertyAccessExpression(ident('taskTiming'),'setupComplete'), undefined, [])));
        }
      }
      return f.updateBlock(node, statements);
    }
    return ts.visitEachChild(node, inside, context);
  }
  return (root) => f.updateSourceFile(root, root.statements.map((node) => {
    if (!ts.isFunctionDeclaration(node) || node.name?.text !== 'run') return node;
    const body = ts.visitNode(node.body, inside);
    return f.updateFunctionDeclaration(node, node.modifiers, node.asteriskToken, ident('_run'),
      node.typeParameters, [...node.parameters, f.createParameterDeclaration(undefined, undefined,
        'taskTiming', undefined, f.createTypeReferenceNode('TaskTiming'))], node.type, body);
  }));
};
const transformed = ts.transform(source, [transformer]);
let out = ts.createPrinter().printFile(transformed.transformed[0]);
transformed.dispose();
if (classifications !== 3 || counts.verify !== 3 || counts.provider_decision !== 2 || counts.wait !== 1) {
  throw new Error(`Unexpected instrumentation shape: ${JSON.stringify({counts, classifications})}`);
}
out = "import { TaskTiming } from './task_timing.js';\n" + out;
const wrapper = `
async function run(args: Arguments): Promise<Outcome> {
  const taskTiming = new TaskTiming();
  let outcome: Outcome = 'unknown';
  let errorType: string | null = null;
  try {
    outcome = await _run(args, taskTiming);
    return outcome;
  } catch (error: unknown) {
    errorType = error instanceof Error ? error.name : 'UnknownError';
    throw error;
  } finally {
    try {
      const events = taskTiming.finish(outcome, args.dryRun, errorType);
      for (const event of events) await writeEvent(args.log, event);
    } catch { /* Extra timing output must not replace the original outcome. */ }
  }
}
`;
out += wrapper;
fs.writeFileSync(path.join(__dirname, 'baseline-ts.ts'), raw);
fs.writeFileSync(path.join(__dirname, 'run-ts.ts'), out);
console.log(JSON.stringify({blob:hash, phases:counts, classifications}));
