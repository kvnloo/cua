"""Bounded resident llama.cpp subprocess collector; no persistent service or desktop access."""
from __future__ import annotations
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
import urllib.request

_VERIFIED = {}

def model_identity(model):
    path = Path(model['path']).expanduser().resolve(strict=True)
    info = path.stat()
    key = (str(path), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if key not in _VERIFIED:
        with path.open('rb') as stream:
            _VERIFIED[key] = hashlib.file_digest(stream, 'sha256').hexdigest()
    digest = _VERIFIED[key]
    if model.get('sha256') and digest != model['sha256']:
        raise ValueError('model SHA256 mismatch before loading: ' + model['id'])
    return digest

class Engine:
    def __init__(self, server, model, gpu_layers=0, threads=2, context=1024, log=None):
        self.model = model
        self.process = None
        self.command = []
        self.log = log or Path('model.log')
        self.server = server
        self.gpu_layers = gpu_layers
        self.threads = threads
        self.context = context

    def start(self):
        self.model_sha256 = model_identity(self.model)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.command = [str(Path(self.server).expanduser()), '-m', str(Path(self.model['path']).expanduser()),
                        '--host', '127.0.0.1', '--port', str(self.port), '-ngl', str(self.gpu_layers),
                        '-c', str(self.context), '-b', '128', '-ub', '128', '-t', str(self.threads),
                        '-tb', str(self.threads), '--parallel', '1', '--no-warmup', '-lv', '4']
        env = os.environ.copy()
        binary = Path(self.server).expanduser()
        env['LD_LIBRARY_PATH'] = str(binary.parent) + ':' + str(binary.parent.parent / 'lib') + ':' + env.get('LD_LIBRARY_PATH', '')
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.log.open('w')
        started = time.perf_counter()
        # Remain inside the caller's resource-guard process group.
        self.process = subprocess.Popen(self.command, stdout=self.stream, stderr=subprocess.STDOUT, env=env)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'model exited {self.process.returncode}: {self.log}')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/health', timeout=1) as reply:
                    if reply.status == 200:
                        self.load_s = time.perf_counter() - started
                        log_text = self.log.read_text()
                        matches = re.findall(r'offloaded (\d+)/(\d+) layers to GPU', log_text)
                        self.backend_evidence = {'log': str(self.log),
                            'offloaded_layers': int(matches[-1][0]) if matches else 0,
                            'total_layers': int(matches[-1][1]) if matches else None,
                            'requested_gpu_layers': self.gpu_layers}
                        if self.gpu_layers > 0 and not self.backend_evidence['offloaded_layers']:
                            raise RuntimeError('GPU requested but no actual layer offload in server log')
                        return
            except OSError:
                time.sleep(.1)
        raise TimeoutError('model not ready after 180 seconds')

    def prompt(self, node):
        if self.model['template'] == 'hobby':
            return f"SYSTEM: {node['system']}\nUSER: {node['user']}\nASSISTANT:"
        text = f"<|im_start|>system\n{node['system']}<|im_end|>\n<|im_start|>user\n{node['user']}<|im_end|>\n<|im_start|>assistant\n"
        if self.model['template'] == 'qwen3':
            text += '<think>\n\n</think>\n\n'
        return text

    def complete(self, node):
        body = {'prompt': self.prompt(node), 'n_predict': 64, 'temperature': 0,
                'seed': 1729, 'stream': True, 'cache_prompt': False,
                'stop': ['<|im_end|>', '<|endoftext|>']}
        started = time.perf_counter()
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=180)
        try:
            connection.request('POST', '/completion', json.dumps(body), {'Content-Type': 'application/json'})
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError(f'completion HTTP {response.status}: ' + response.read().decode()[:500])
            first, output, timings = None, '', {}
            for line in response:
                if not line.startswith(b'data: '):
                    continue
                text = line[6:].decode().strip()
                if text == '[DONE]':
                    break
                event = json.loads(text)
                if event.get('content'):
                    first = first or time.perf_counter()
                    output += event['content']
                if event.get('timings'):
                    timings = event['timings']
            return {'output': output, 'latency_s': time.perf_counter() - started,
                    'ttft_s': None if first is None else first - started, 'timings': timings}
        finally:
            connection.close()

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if hasattr(self, 'stream'):
            self.stream.close()


def collect(args):
    corpus_path = Path(args.corpus)
    corpus = json.loads(corpus_path.read_text())
    digest = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    manifest = json.loads(Path(args.manifest).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ledger = out / 'matrix.jsonl'
    existing = {(r['model'], r['node_id']) for r in map(json.loads, ledger.read_text().splitlines()) if r.get('status') == 'ok' and r['corpus_sha256'] == digest} if ledger.exists() else set()
    models = [m for m in manifest['models'] if not args.only or m['id'] in args.only]
    owned = [None]
    def stop(signum, frame):
        if owned[0] is not None:
            owned[0].close()
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stop)
    for model in models:
        nodes = [n for n in corpus['nodes'] if (model['id'], n['id']) not in existing]
        if not nodes:
            continue
        engine = Engine(manifest['server'], model, args.gpu_layers, args.threads, log=out / (model['id'] + '.log'))
        owned[0] = engine
        try:
            engine.start()
            engine.complete(nodes[0])  # explicit warmup, excluded from matrix
            model_sha = engine.model_sha256
            for node in nodes:
                row = {'schema_version': 1, 'node_id': node['id'], 'task': node['task'],
                       'model': model['id'], 'model_sha256': model_sha, 'device': args.device,
                       'runtime': manifest.get('runtime', 'llama.cpp'), 'command': engine.command,
                       'backend_evidence': engine.backend_evidence,
                       'config': {'gpu_layers': args.gpu_layers, 'threads': args.threads, 'context': 1024, 'max_new': 64, 'seed': 1729, 'cache_prompt': False},
                       'corpus_sha256': digest, 'load_s': engine.load_s, 'started_unix': time.time()}
                try:
                    row.update(engine.complete(node), status='ok')
                except Exception as error:
                    row.update(status='error', error=type(error).__name__ + ': ' + str(error))
                with ledger.open('a') as stream:
                    stream.write(json.dumps(row, allow_nan=False) + '\n')
                print(json.dumps({k: row[k] for k in ('model', 'node_id', 'task', 'status')}), flush=True)
        finally:
            engine.close()
            owned[0] = None
    print(json.dumps({'ledger': str(ledger), 'corpus_sha256': digest, 'models': [m['id'] for m in models]}), flush=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--corpus', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--device', required=True)
    p.add_argument('--gpu-layers', type=int, default=0)
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--only', action='append')
    collect(p.parse_args())
