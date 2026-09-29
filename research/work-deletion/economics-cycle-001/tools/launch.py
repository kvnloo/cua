#!/usr/bin/env python3
"""Own a disposable private-session root; erase browser profiles after exit.
Only allowlisted harness summaries reach stdout; launcher stderr is discarded.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
LAUNCHER='/home/kvn/.hermes/profiles/clean/cache/scratch/cua-4316-x11-session.sh'


def owned(root):
    found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:
            env=(p/'environ').read_bytes().split(b'\0')
            if any(s.startswith(b'XDG_RUNTIME_DIR='+str(root).encode()+b'/') for s in env):
                if (p/'stat').read_text().rsplit(')',1)[1].split()[0]!='Z':found.append(int(p.name))
        except OSError:pass
    return found


def main():
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True,type=Path); p.add_argument('--phase',required=True,choices=['pilot','fallback','repeat','grid']); a=p.parse_args()
    assert a.out.is_absolute() and not a.out.exists()
    if (HERE.parent/'SAFETY_HALT.json').exists():
        print(json.dumps({'blocked':True,'reason':'verified_headless_sway_required'})); return 4
    root=Path(tempfile.mkdtemp(prefix='economics-private-',dir=os.environ['TMPDIR']))
    env=dict(os.environ,TMPDIR=str(root))
    start=time.monotonic_ns()
    cmd=[LAUNCHER,'/usr/bin/python3',str(HERE/'harness.py'),'--phase',a.phase,'--out',str(a.out)]
    result=subprocess.run(cmd,env=env,capture_output=True)
    finish=time.monotonic_ns()
    for raw in result.stdout.splitlines():
        try:
            row=json.loads(raw)
            allowed={'trial_id','qualifies','errors','routes','provider_entries','observations','verified_ms'}
            if set(row)<=allowed: print(json.dumps(row),flush=True)
        except (ValueError,TypeError):pass
    leftovers=owned(root)
    for pid in leftovers:
        try:os.kill(pid,signal.SIGTERM)
        except ProcessLookupError:pass
    deadline=time.monotonic()+3
    while owned(root) and time.monotonic()<deadline:time.sleep(.03)
    for pid in owned(root):
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass
    survivors=owned(root)
    if not survivors:shutil.rmtree(root)
    receipt={'rc':result.returncode,'phase':a.phase,'private_root_erased':not root.exists(),
             'session_daemons_terminated':len(leftovers),'session_survivors':len(survivors),
             'session_envelope_ms':(finish-start)/1e6,'discarded_launcher_stderr_bytes':len(result.stderr),
             'command':cmd,'host_display_inherited':False}
    if a.out.exists():(a.out/'launcher-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)
    return result.returncode if not survivors else 3

if __name__=='__main__':raise SystemExit(main())
