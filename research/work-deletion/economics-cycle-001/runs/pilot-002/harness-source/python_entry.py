"""Evidence-only provider entry hook; the exact run.py file is executed unchanged."""
import hashlib
import json
import os
import runpy
import sys
import time
from pathlib import Path

root=Path(os.environ['ECON_EXAMPLES'])
sys.path.insert(0,str(root/'python'))
import jev_adapter
original=jev_adapter.choose_mock_for_task
journal=Path(os.environ['ECON_PROVIDER_JOURNAL'])
count=0

def record(row):
    with journal.open('a') as f: f.write(json.dumps(row)+'\n')

def instrumented(*args,**kwargs):
    global count
    count+=1; index=count
    record({'event':'provider_enter','index':index,'ns':time.monotonic_ns()})
    try:
        time.sleep(float(os.environ['ECON_PROVIDER_MS'])/1000)
        return original(*args,**kwargs)
    finally:
        record({'event':'provider_exit','index':index,'ns':time.monotonic_ns()})

jev_adapter.choose_mock_for_task=instrumented
secret=json.load(sys.stdin)['token']
entry=root/'python/run.py'
sys.argv=[str(entry),*sys.argv[1:],'--token',secret]
print(json.dumps({'event':'bootstrap','guarded_flag':'--guarded-completion' in sys.argv,
                  'source_file_sha256':hashlib.sha256(entry.read_bytes()).hexdigest()}),flush=True)
runpy.run_path(str(entry),run_name='__main__')
