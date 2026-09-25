"""Generate a fork-only instrumented copy; refuse source drift."""
from pathlib import Path
import ast, difflib, hashlib
root = Path(__file__).resolve().parent
p = root.parents[1] / 'python' / 'run.py'
raw = p.read_bytes()
source = raw.decode('utf-8')
blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
if blob != '003bdf23d41e7fa71a74583bb760d576503e908f':
    raise SystemExit(f'Refusing source drift: expected pinned #4052 runner, got {blob}')
tree=ast.parse(source)
run=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='run')
spans=[]
for n in ast.walk(run):
    if not isinstance(n,(ast.Assign, ast.Expr, ast.If)): continue
    segment=ast.get_source_segment(source,n)
    if isinstance(n,ast.If):
        if ast.unparse(n.test)=='args.provider == \'mock\'': spans.append((n,'provider_decision'))
        continue
    value=n.value
    if isinstance(value,ast.Await): value=value.value
    if not isinstance(value,ast.Call): continue
    name=ast.unparse(value.func)
    phase={
      'reset_fixture':'setup.reset', 'session.initialize':'setup.initialize',
      'wait_for_window':'setup.window_ready','fixture_state':'verify',
      'optional_visual_observation':'visual_observe','build_candidates':'candidate_build',
      'validate_choice':'validate_choice','asyncio.sleep':'wait'
    }.get(name)
    if name=='driver.call':
        op=ast.literal_eval(value.args[0]) if isinstance(value.args[0],ast.Constant) else 'action'
        phase={'browser_prepare':'setup.prepare','browser_navigate':'setup.navigate',
          'get_browser_state': 'setup.bind' if 'snapshot_format' not in segment else 'semantic_observe',
          'action':'act'}[op]
    if phase: spans.append((n,phase))
# list_tools is wrapped inside attribute access, not a direct await value.
for n in ast.walk(run):
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='advertised_tools' for t in n.targets):
        spans.append((n,'setup.tools'))
if len(spans) != 17:
    raise SystemExit(f'Refusing unexpected instrumentation shape: {len(spans)} regions')
lines=source.splitlines(keepends=True)
for n,phase in sorted(spans,key=lambda x:x[0].lineno,reverse=True):
    indent=' '*n.col_offset
    old=lines[n.lineno-1:n.end_lineno]
    lines[n.lineno-1:n.end_lineno]=[f'{indent}with task_timing.span("{phase}"):\n']+['    '+line if line.strip() else line for line in old]
out=''.join(lines)
out=out.replace('from jev_adapter import choose_live, choose_mock_adapter\n',
 'from jev_adapter import choose_live, choose_mock_adapter\nfrom task_timing import TaskTiming\n')
out=out.replace('async def run(args: argparse.Namespace) -> str:',
 'async def _run(args: argparse.Namespace, task_timing: TaskTiming) -> str:')
out=out.replace('            for step in range(1, args.max_steps + 1):',
 '            task_timing.setup_complete()\n            for step in range(1, args.max_steps + 1):')
wrapper='''async def run(args: argparse.Namespace) -> str:
    task_timing = TaskTiming()
    outcome = "unknown"
    error_type = None
    try:
        outcome = await _run(args, task_timing)
        return outcome
    except BaseException as error:
        error_type = type(error).__name__
        if isinstance(error, asyncio.CancelledError):
            outcome = "cancelled"
        raise
    finally:
        # Extra telemetry must not replace the recipe result or exception.
        try:
            events = task_timing.finish(outcome, dry_run=args.dry_run, error_type=error_type)
            log_path = Path(args.log) if args.log else None
            for event in events:
                write_event(log_path, event)
        except Exception:
            pass


'''
out=out.replace('def parse_args() -> argparse.Namespace:',wrapper+'def parse_args() -> argparse.Namespace:')
# Mark each existing classify result, not the runner return. A later cleanup
# exception must not erase a fixture verdict already observed.
parsed = ast.parse(out)
marks = []
for n in ast.walk(parsed):
    if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name) and n.value.func.id == 'classify'):
        target = n.targets[0]
        if not isinstance(target, ast.Name):
            raise SystemExit('Unexpected classifier target')
        marks.append((n.end_lineno, n.col_offset, target.id))
if len(marks) != 3:
    raise SystemExit(f'Refusing classifier drift: {len(marks)} sites')
lines = out.splitlines(keepends=True)
for end, indent, name in sorted(marks, reverse=True):
    lines.insert(end, ' ' * indent + f'task_timing.observe_classification({name})\n')
out = ''.join(lines)
ast.parse(out)
(root/'baseline.py').write_text(source)
(root/'run.py').write_text(out)
diff=''.join(difflib.unified_diff(source.splitlines(True),out.splitlines(True),
 fromfile='a/libs/cua-driver/examples/jev-use/python/run.py',tofile='b/libs/cua-driver/examples/jev-use/python/run.py'))
(root/'runner-timing.patch').write_text(diff)
print('instrumented',len(spans),'statement regions; patch lines',len(diff.splitlines()))
