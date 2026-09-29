#!/usr/bin/env python3
"""No GUI: contract tests, exact-source hermetic runner tests, receipt audits.
Raw real GUI/process output is never run here. Source unit tests mock the MCP
transport and provider; their output is reduced to counts/exit status only.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
EXAMPLES=Path('/mnt/zer0models/github/cua-lanes/c4316/libs/cua-driver/examples/jev-use')
NODE='/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin/node'


def execute(name,command,cwd):
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    # No GUI authority forwarded even though these tests patch all transports.
    for key in ('DISPLAY','WAYLAND_DISPLAY','HYPRLAND_INSTANCE_SIGNATURE','SWAYSOCK','DBUS_SESSION_BUS_ADDRESS','CUA_DRIVER_BIN','PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'):
        env.pop(key,None)
    disabled=ROOT/'INTENTIONALLY_NONEXISTENT_GUI_DRIVER'
    assert not disabled.exists()
    env['CUA_DRIVER_BIN']=str(disabled)
    started=time.monotonic_ns()
    result=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,timeout=180)
    text=result.stdout+'\n'+result.stderr
    python=re.search(r'Ran (\d+) tests?',text)
    node=re.search(r'(?:#|ℹ) tests (\d+)',text)
    receipt={'name':name,'command':command,'cwd':str(cwd),'exit_code':result.returncode,
             'elapsed_ms':(time.monotonic_ns()-started)/1e6,'tests':int((python or node).group(1)) if python or node else None,
             'stdout_bytes':len(result.stdout.encode()),'stderr_bytes':len(result.stderr.encode()),
             'passed':result.returncode==0,'raw_output_persisted':False}
    print(json.dumps(receipt),flush=True)
    return receipt


def main():
    assert (ROOT/'SAFETY_HALT.json').exists()
    commands=[
        ('evidence-contract-tests',[sys.executable,'-m','unittest','test_contract','-v'],HERE),
        ('exact-c78-python-hermetic-runner',[str(EXAMPLES/'.venv/bin/python'),'-m','unittest','discover','-s','python/tests','-p','test_guarded_runner.py','-v'],EXAMPLES),
        ('exact-c78-typescript-hermetic-runner',[NODE,'--import',str(EXAMPLES/'node_modules/tsx/dist/esm/index.mjs'),'--test','typescript/run_guarded_completion.test.ts'],EXAMPLES),
        ('offline-analysis',[sys.executable,str(HERE/'analyze.py')],HERE),
        ('offline-count-surface',[sys.executable,str(HERE/'count_surface.py'),str(ROOT/'runs/repeat-001'),'--out',str(ROOT/'deterministic-count-surface-qualified-offline.json')],HERE),
    ]
    receipts=[execute(*entry) for entry in commands]
    result={'scope':'hermetic/offline only; live focus isolation remains unqualified','passed':all(r['passed'] for r in receipts),
            'receipts':receipts,'tool_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir() if p.suffix in ('.py','.mjs')}}
    (ROOT/'offline-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
