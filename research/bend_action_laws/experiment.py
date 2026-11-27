#!/usr/bin/env python3
"""Bounded CUDA action-law experiments. Never executes computer actions.

Bend GPU emits all finite decisions; independent Python oracle checks each.
Large batches repeat this domain and measure throughput, NOT extra coverage.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results'
BEND = Path(os.environ.get('BEND_BIN', '/mnt/zer0models/bend-stack/official-2.0.35/bend/bin/bend'))
PIN = 'af967c7c37aced4491e0f4344e3bb9de837c2c89b7519f7e0b8c71935be1840a'
ENV = dict(os.environ, CUDA_HOME='/opt/cuda', BEND_NO_TELEMETRY='1', HOME=str(ROOT / '.home'), TMPDIR=str(ROOT / '.tmp'))


def oracle(state, action):
    fresh, grant, unique, calc, focus, complete, confirmed, supported = (bool(state & (1 << b)) for b in range(8))
    if action == 8:
        return int(fresh and complete)
    if action == 9:
        return int(fresh and not supported)
    if action not in range(8):
        return 0
    if not (fresh and grant and unique and supported):
        return 0
    if action == 1 and not (calc and focus):
        return 0
    if action == 7 and not confirmed:
        return 0
    return 1


def guard(s, a):
    # Independent runtime implementation, without generator/datatype overhead.
    if a == 8:
        return int(s & 33 == 33)
    if a == 9:
        return int(s & 129 == 1)
    return int(0 <= a < 8 and s & 135 == 135 and (a != 1 or s & 24 == 24) and (a != 7 or s & 64 == 64))


def point(mode, x, fn=guard):
    s, a = x & 255, (x >> 8) & 15
    if mode == 0:
        return fn(s, a)
    return sum((all(fn(s ^ delta, (a + j) & 15) for delta in (0, 8, 16, 24))) << j for j in range(4))


def smi():
    p = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,process_name,used_gpu_memory', '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True, timeout=5)
    apps = []
    for line in p.stdout.splitlines():
        pid, name, mem = line.split(',', 2)
        apps.append({'pid': int(pid), 'name': name.strip(), 'mib': int(mem)})
    p = subprocess.run(['nvidia-smi', '--query-gpu=memory.free,utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True, timeout=5)
    free, util = map(int, p.stdout.strip().split(','))
    psi = [float(line.split('avg10=')[1].split()[0]) for line in Path('/proc/pressure/io').read_text().splitlines()]
    return {'apps': apps, 'free_mib': free, 'util_pct': util, 'io_psi': psi, 'utc': time.time()}


BASE = None
STARTED = str(int(time.time()))


def safety(sample, own=None):
    if max(sample['io_psi']) >= 40 or sample['free_mib'] < 2048:
        raise RuntimeError('GPU/IO admission deferred: ' + json.dumps(sample))
    original = {p['pid']: p for p in BASE['apps']}
    for p in sample['apps']:
        if p['pid'] == own or (own is not None and os.getpgid(p['pid']) == own):
            if p['mib'] > 8192:
                raise RuntimeError('Owned process exceeded 8GB')
            continue
        if p['pid'] not in original:
            raise RuntimeError('New GPU tenant: ' + json.dumps(p))
        if 'garden_room' in p['name'] and p['mib'] > original[p['pid']]['mib'] + 256:
            raise RuntimeError('Garden scan memory increased >256MiB')
        if any(k in p['name'].lower() for k in ('comfy', 'blender', 'steam', 'wine', 'gamescope')):
            raise RuntimeError('Interactive GPU tenant: ' + json.dumps(p))
    logs = subprocess.run(['journalctl', '--user', '-u', 'garden-room-scan-live.service', '--since', '@' + STARTED, '-n', '20', '-o', 'cat', '--no-pager'], capture_output=True, text=True, timeout=5)
    if logs.returncode:
        raise RuntimeError('Cannot monitor garden scan service log')
    if any(word in logs.stdout.lower() for word in ('cuda error', 'out of memory', 'traceback')):
        raise RuntimeError('Garden scan log reports GPU/runtime error')


def command(args, timeout=40):
    before = smi(); safety(before)
    started = time.perf_counter()
    proc = subprocess.Popen(['nice', '-n10', 'timeout', str(timeout), *map(str, args)], cwd=ROOT, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    samples = [before]
    try:
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=.2)
                break
            except subprocess.TimeoutExpired:
                sample = smi(); samples.append(sample); safety(sample, proc.pid)
        elapsed = time.perf_counter() - started
    except BaseException:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.communicate(timeout=5)
        raise
    rec = {'command': list(map(str, args)), 'wall_s': elapsed, 'rc': proc.returncode, 'stdout': stdout.strip(), 'stderr': stderr[-3000:], 'gpu_samples': samples}
    with (OUT / 'commands.jsonl').open('a') as f:
        f.write(json.dumps(rec) + '\n')
    if proc.returncode:
        raise RuntimeError(json.dumps(rec))
    return rec


def source(mode, power, reps=1, vectors=False):
    if vectors:
        return f'''import Base
import ./model.bend as M

def emit(xs: List<U32>) -> IO(Unit):
  match xs:
    case Nil{{}}:
      IO.pure(Unit, Unit{{}})
    case Con{{h, t}}:
      do IO<Unit>:
        IO.print(U32.show(h))
        emit(t)

def main() -> IO(Unit):
  emit(Array.to_list(~U32, M.vectors!(12n, {mode}, 0)))
'''
    depth = min(14, power); lw = power-depth
    return f'''import Base
import ./model.bend as M

def run(n: Nat, +seed: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{{}})
    case 1n+p:
      do IO<Unit>:
        start : Nat <- IO.now()
        value : U32 <- IO.pure(U32, M.tree!({depth}n, {mode}, seed, {lw}n, {1 << lw}n))
        finish : Nat <- IO.now()
        IO.print(U32.show(value) ++ "," ++ Nat.show(Nat.sub(finish, start)))
        run(p, (seed + 1 : U32))

def main() -> IO(Unit):
  run({reps}n, 0)
'''


def build(name, text):
    path = ROOT / (name + '.bend'); path.write_text(text)
    rec = command([BEND, path, '-o', ROOT / name], timeout=60)
    if not (ROOT / (name + '.gpu')).is_file():
        raise RuntimeError('CUDA silently absent: missing .gpu')
    return rec['wall_s']


def np_point(mode, xs, np):
    s, a = xs & 255, (xs >> 8) & 15
    def g(s, a):
        return np.where(a == 8, (s & 33) == 33, np.where(a == 9, (s & 129) == 1, (a < 8) & ((s & 135) == 135) & ((a != 1) | ((s & 24) == 24)) & ((a != 7) | ((s & 64) == 64))))
    if not mode:
        return g(s, a).astype(np.uint32)
    result = np.zeros(xs.shape, dtype=np.uint32)
    for j in range(4):
        ok = np.ones(xs.shape, dtype=bool)
        for delta in (0, 8, 16, 24):
            ok &= g(s ^ delta, (a + j) & 15)
        result |= ok.astype(np.uint32) << j
    return result


def main():
    global BASE
    OUT.mkdir(exist_ok=True); (ROOT / '.home').mkdir(exist_ok=True); (ROOT / '.tmp').mkdir(exist_ok=True)
    if hashlib.sha256(BEND.read_bytes()).hexdigest() != PIN:
        raise RuntimeError('Bend executable pin mismatch')
    BASE = smi(); safety(BASE)
    print('ADMITTED', json.dumps(BASE), flush=True)
    result = {'preregistered_world': '/workspace/cache/abab/bend-cua.json', 'model_sha256': hashlib.sha256((ROOT/'model.bend').read_bytes()).hexdigest(), 'bend_sha256': PIN, 'backend': 'Bend2 native CUDA ! --gpu 1GB', 'initial_load': BASE, 'vectors': {}, 'benchmarks': []}
    import numpy as np
    for mode in (0, 1):
        name = f'vectors{mode}'; build_s = build(name, source(mode, 12, vectors=True))
        run = command([ROOT/name, '--gpu', '1GB'])
        actual = list(map(int, run['stdout'].splitlines())); expected = [point(mode, x, oracle) for x in range(4096)]
        mismatches = sum(a != b for a,b in zip(actual, expected))
        if len(actual) != 4096 or mismatches:
            raise RuntimeError(f'Full vector parity failed:{mode}:{len(actual)}:{mismatches}')
        (OUT/f'vectors{mode}.json').write_text(json.dumps(actual)+'\n')
        result['vectors'][str(mode)] = {'cases':4096,'mismatches':mismatches,'build_s':build_s,'gpu_wall_s':run['wall_s']}
        if mode == 0:
            (OUT/'guard_table.bin').write_bytes(bytes(actual))
        print('FINITE_PARITY', mode, result['vectors'][str(mode)], flush=True)
    table = (OUT/'guard_table.bin').read_bytes()
    timings = {}
    for label, fn in [('hand_python', lambda x:guard(x&255,x>>8)), ('projected_table', lambda x:table[x])]:
        reps = []
        for _ in range(5):
            start=time.perf_counter_ns(); value=sum(fn(x) for x in range(4096)); reps.append((time.perf_counter_ns()-start)/1e6)
        timings[label]={'ms_per4096':reps,'median_ns_perdecision':statistics.median(reps)*1e6/4096,'sum':value}
    result['projected_runtime']=timings
    oracle_masks = [point(1,x,oracle) for x in range(4096)]
    first = [point(0,x,oracle) for x in range(4096)]
    singleton = lambda m: bool(m and not m&(m-1))
    result['ambiguity']={'groups':4096,'unique_safe':sum(map(singleton,oracle_masks)),'multiple_safe':sum(m.bit_count()>1 for m in oracle_masks),'no_safe':oracle_masks.count(0),'choose_first_false_accept':sum(bool(f) and not(m&1) for f,m in zip(first,oracle_masks)),'choose_first_false_reject':sum(not f and singleton(m) for f,m in zip(first,oracle_masks)),'checked_false_accept':0,'checked_false_reject':0,'model_calls_all_arms':0,'scope':'finite semantic oracle, not visual grounding; ambiguous groups with >1 safe action abstain'}
    (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    for mode in (0,1):
        for power in (12,20,24,28):
            name=f'batch{mode}_{power}'; build_s=build(name,source(mode,power,5))
            gpu=command([ROOT/name,'--gpu','1GB'],timeout=30)
            cpu=command([ROOT/name,'--gpu','off','--threads','2'],timeout=30)
            expected_sum = sum(point(mode,x,oracle) for x in range(4096)) * (1 << max(0,power-12)) & 0xffffffff
            for rec in (gpu,cpu):
                rows=[list(map(int,row.split(','))) for row in rec['stdout'].splitlines()]
                if len(rows)!=5 or any(row[0]!=expected_sum for row in rows):
                    raise RuntimeError('batch checksum parity failure')
                rec['kernel_ms']=[r[1] for r in rows]
            np_times=[]
            for _ in range(3):
                t=time.perf_counter(); total=0
                for start in range(0,1<<power,1<<20):
                    xs=np.arange(start,min(start+(1<<20),1<<power),dtype=np.uint32)
                    total=(total+int(np_point(mode,xs,np).sum(dtype=np.uint64))) & 0xffffffff
                np_times.append(time.perf_counter()-t)
                if total!=expected_sum: raise RuntimeError('NumPy parity')
            py=None
            if power<=20:
                t=time.perf_counter(); total=sum(point(mode,x) for x in range(1<<power)) & 0xffffffff; py=time.perf_counter()-t
                if total!=expected_sum: raise RuntimeError('Python parity')
            row={'mode':mode,'power':power,'cases':1<<power,'build_s':build_s,'gpu_wall_s':gpu['wall_s'],'gpu_kernel_ms':gpu['kernel_ms'],'cpu2_wall_s':cpu['wall_s'],'cpu2_kernel_ms':cpu['kernel_ms'],'numpy_s':np_times,'python_s':py,'checksum':expected_sum,'gpu_load':gpu['gpu_samples']}
            result['benchmarks'].append(row); (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
            print('BATCH',mode,power,'GPU_ms',gpu['kernel_ms'],'CPU2_ms',cpu['kernel_ms'],'NumPy_s',np_times,'Python_s',py,flush=True)
    result['table_sha256']=hashlib.sha256(table).hexdigest()
    (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print('COMPLETE',flush=True)

if __name__=='__main__': main()
