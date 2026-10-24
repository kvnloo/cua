"""Finite JSONL inference over an admitted worker's stdin/stdout, without SSH forwarding."""
from __future__ import annotations
import argparse
from collections import deque
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
import collect

PREFIX = 'SLM_ROUTER_RPC '


def memory_snapshot():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in {'MemAvailable', 'SwapFree', 'SwapTotal'}:
            values[key + '_kib'] = int(value.split()[0])
    full = next(line for line in Path('/proc/pressure/memory').read_text().splitlines() if line.startswith('full '))
    values['memory_psi_full_avg60'] = float(dict(item.split('=') for item in full.split()[1:])['avg60'])
    return values


def serve(args):
    manifest = json.loads(args.manifest.read_text())
    models = {model['id']: model for model in manifest['models']}
    engine = None
    current = None
    def emit(value):
        print(PREFIX + json.dumps(value, allow_nan=False), flush=True)
    emit({'ready': True, 'memory': memory_snapshot()})
    try:
        for line in sys.stdin:
            request = json.loads(line)
            if request.get('stop'):
                emit({'stopped': True})
                break
            try:
                before = memory_snapshot()
                if before['memory_psi_full_avg60'] >= args.max_psi:
                    raise RuntimeError('remote memory PSI exceeds clean-run limit')
                selected = request['model']
                switch_s = 0.
                if selected != current:
                    if engine is not None:
                        engine.close()
                    engine = collect.Engine(manifest['server'], models[selected], 0, args.threads,
                                            log=args.out / (selected + '.log'))
                    started = time.perf_counter()
                    engine.start()
                    switch_s = time.perf_counter() - started
                    current = selected
                reply = engine.complete(request['node'])
                after = memory_snapshot()
                if after['memory_psi_full_avg60'] >= args.max_psi:
                    raise RuntimeError('remote memory PSI exceeds clean-run limit after generation')
                emit({'reply': reply, 'switch_load_s': switch_s, 'command': engine.command,
                      'backend_evidence': engine.backend_evidence, 'model_sha256': engine.model_sha256,
                      'memory_before': before, 'memory_after': after})
            except Exception as error:
                emit({'error': type(error).__name__ + ': ' + str(error)})
    finally:
        if engine is not None:
            engine.close()


class Client:
    def __init__(self, command, log, timeout=600):
        self.timeout = timeout
        self.log = Path(log).open('ab')
        self.pending = deque()
        self.buffer = b''
        # The command must include the owner's fleet admission and quiet locks.
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
        try:
            ready = self.receive()
            if not ready.get('ready'):
                raise RuntimeError('remote inference worker did not identify itself')
            self.ready = ready
        except BaseException:
            self.close()
            raise

    def receive(self):
        deadline = time.monotonic() + self.timeout
        while True:
            while self.pending:
                line = self.pending.popleft().decode()
                if line.startswith(PREFIX):
                    result = json.loads(line[len(PREFIX):])
                    if result.get('error'):
                        raise RuntimeError(result['error'])
                    return result
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError('admitted remote inference worker timed out')
            block = os.read(self.process.stdout.fileno(), 65536)
            if not block:
                code = self.process.wait()
                raise RuntimeError(f'admitted remote worker exited {code} before replying; see worker log')
            self.log.write(block)
            self.log.flush()
            self.buffer += block
            parts = self.buffer.split(b'\n')
            self.buffer = parts.pop()
            self.pending.extend(parts)

    def complete(self, model, node):
        self.process.stdin.write((json.dumps({'model': model, 'node': node}) + '\n').encode())
        self.process.stdin.flush()
        return self.receive()

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write(b'{"stop":true}\n')
                self.process.stdin.flush()
                response = self.receive()
                if not response.get('stopped'):
                    raise RuntimeError('remote worker failed to acknowledge stop')
            except (OSError, RuntimeError, TimeoutError):
                self.process.terminate()
            self.process.stdin.close()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--max-psi', type=float, default=5.)
    arguments = parser.parse_args()
    arguments.out.mkdir(parents=True, exist_ok=False)
    serve(arguments)
