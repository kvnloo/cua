"""Freeze recorded states; score progress from task specifications, never model imitation."""
from __future__ import annotations
import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
import operator
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

HARNESS = load_module('router_source_harness', HERE.parent / 'hobbylm_eval/harness.py')
import sys
sys.path.insert(0, str(HERE.parents[1]))
from cua_agent.loops import hobbylm as ACTIONS

def arithmetic(text):
    """Bounded four-operation expression, not eval or model-provided code."""
    if len(text) > 128 or not re.fullmatch(r'[0-9. +*/=\-]+', text) or not text.endswith('='):
        raise ValueError('not a calculator expression')
    tree = ast.parse(text[:-1], mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError('expression too large')
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -visit(node.operand) if isinstance(node.op, ast.USub) else visit(node.operand)
        raise ValueError('unsupported arithmetic')
    return visit(tree.body)

def correct(node, raw):
    """One-step progress/termination oracle; not a native environment-effect oracle."""
    try:
        action = ACTIONS.parse_action(raw)
        # Reuse the actual executor's limits and exact calendar-confirmation match.
        HARNESS.action_command(action.name, action.argument, node['task_spec'].get('confirmation'))
        target = node['task_spec']['oracle']
        kind = target['kind']
        before, initial = node['snapshot'], node['initial_snapshot']
        if kind == 'refusal':
            return action.name == 'UNKNOWN' and before == initial
        satisfied = HARNESS.oracle(node['task_spec'], initial, before, None)
        if action.name == 'DONE':
            return satisfied
        if action.name == 'UNKNOWN' or satisfied:
            return False
        if kind == 'calculator':
            if before.get('front_app') != 'Calculator':
                return str(action) == 'OPEN Calculator'
            return action.name == 'TYPE' and abs(arithmetic(action.argument) - float(target['value'])) < 1e-8
        if kind in ('volume', 'volume_exact'):
            direction = target.get('direction', 1 if target.get('value', 100) > before['volume'] else -1)
            return str(action) == ('KEY VOLUME_UP' if direction > 0 else 'KEY VOLUME_DOWN')
        if kind == 'mute':
            return str(action) == 'KEY MUTE'
        if kind == 'dark':
            return str(action) == ('DARK_MODE ON' if target['value'] else 'DARK_MODE OFF')
        if kind == 'folder':
            return str(action) == 'FOLDER ' + target['value']
        if kind == 'app':
            return str(action) == 'OPEN ' + target['value']
        if kind == 'timer':
            return action.name == 'TIMER' and int(action.argument) == target['minutes']
        if kind == 'screenshot':
            return action.name == 'SCREENSHOT'
        if kind == 'event' and action.name == 'EVENT':
            title, day, clock, person = [x.strip() for x in action.argument.split('|')]
            return (title == target['title'] and day == target['day']
                    and clock in {target['time'], target['time'] + ' UTC'}
                    and person in {target['person'], target.get('contact_name', target['person'])})
    except (ValueError, TypeError, KeyError, ZeroDivisionError, SyntaxError, OverflowError, NotImplementedError):
        return False
    return False

def family(request):
    text = request.lower()
    for label, words in [('calculator', ['plus', 'times', 'split ', 'spent ']),
                         ('audio', ['volume', 'audio', 'sound', 'sleeping']),
                         ('theme', ['theme']), ('timer', ['timer']),
                         ('folder', ['folder']), ('calendar', ['add sandbox', 'add synthetic']),
                         ('app', ['open notes', 'open calendar', 'open finder', 'open music', 'open reminders'])]:
        if any(word in text for word in words):
            return label
    return 'other'

def features(node, pool_size=3, device='groot', budget=2.0):
    """Only public decision-time context. Labels/snapshots are deliberately excluded."""
    user = node['user']
    last = user.split('Last action:', 1)[1].split('. Result:', 1)[0].strip() if 'Last action:' in user else ''
    return {'family': family(node['request']), 'decision_type': 'verify' if last else 'action',
            'option_count': 10, 'pool_size': pool_size, 'observation_chars': len(user),
            'dag_depth': node['depth'], 'prior_failures': int('Error:' in user or 'error' in user.lower()),
            'device': device, 'latency_budget_s': budget, 'last_action': last.split(' ', 1)[0] or 'none'}

def build(roots, destination):
    nodes = {}
    tasks = {}
    source_hashes = {}
    for root in roots:
        summary = json.loads((root / 'summary.json').read_text())
        for task in summary['supported_tasks']:
            trace = root / task / 'trace.jsonl'
            records = [json.loads(line) for line in trace.read_text().splitlines()]
            initial = records[0]
            tasks[task] = initial['task']
            previous = initial['snapshot']
            digest = hashlib.sha256(trace.read_bytes()).hexdigest()
            source_hashes[str(trace)] = digest
            for record in records:
                if record['type'] != 'step':
                    continue
                key = hashlib.sha256((task + '\0' + record['system'] + '\0' + record['user']).encode()).hexdigest()[:20]
                source = {'trace_sha256': digest, 'source_model': root.name, 'index': record['index']}
                if key in nodes:
                    nodes[key]['sources'].append(source)
                else:
                    nodes[key] = {'id': key, 'task': task, 'request': initial['task']['request'],
                                  'task_spec': initial['task'], 'system': record['system'], 'user': record['user'],
                                  'depth': record['index'], 'initial_snapshot': initial['snapshot'],
                                  'snapshot': previous, 'sources': [source]}
                previous = record['snapshot']
    # Stable by task ID, independent of candidate outputs and correctness. Related nodes never cross partitions.
    ordered = sorted(tasks, key=lambda t: hashlib.sha256(('slm-router-1729:' + t).encode()).hexdigest())
    heldout = set(ordered[:11])
    for node in nodes.values():
        node['split'] = 'test' if node['task'] in heldout else 'train'
    corpus = {'schema_version': 1, 'scope': 'frozen semantic-state replay; not live GUI task success',
              'label_method': 'task-specification and pre-action state progress predicate',
              'split_seed': 1729, 'train_tasks': sorted(set(tasks) - heldout), 'test_tasks': sorted(heldout),
              'source_hashes': source_hashes, 'nodes': list(nodes.values())}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(corpus, indent=2))
    print(json.dumps({'corpus': str(destination), 'tasks': len(tasks), 'nodes': len(nodes),
                      'splits': dict(Counter(n['split'] for n in nodes.values())),
                      'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    build(args.source, args.out)
