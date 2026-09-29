"""Real Driver stdio pass-through. Raw bytes ONLY in memory, NEVER persisted.
A deterministic delay is applied before forwarding semantic observation requests;
all other bytes are passed unchanged. No request injection or oracle mutation.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
import safe


def main():
    p=argparse.ArgumentParser(); p.add_argument('--real',required=True); p.add_argument('--trace',required=True)
    p.add_argument('--observe-ms',type=float,default=0); p.add_argument('args',nargs='*'); a=p.parse_args()
    log=Path(a.trace).open('a'); lock=threading.Lock(); pending={}; last_typed=None
    def write(row):
        with lock:
            log.write(json.dumps(row,separators=(',',':'))+'\n'); log.flush()
    env=dict(os.environ); env.update(CUA_E2E_BROWSER_NO_SANDBOX='1',CUA_E2E_BROWSER_STDERR='1')
    started=time.monotonic_ns()
    proc=subprocess.Popen([a.real,*a.args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,bufsize=0)
    write({'event':'driver_spawn','ns':started})
    stderr_bytes=[0]
    def drain():
        while chunk:=proc.stderr.read(65536): stderr_bytes[0]+=len(chunk)
    threading.Thread(target=drain,daemon=True).start()
    def terminate(*_):
        try: proc.terminate()
        except ProcessLookupError: pass
    signal.signal(signal.SIGTERM,terminate); signal.signal(signal.SIGINT,terminate)
    def send():
        nonlocal last_typed
        try:
            for raw in iter(sys.stdin.buffer.readline,b''):
                message=json.loads(raw); method=message.get('method','unknown')
                name=message.get('params',{}).get('name',method)
                args=message.get('params',{}).get('arguments',{})
                if name=='browser_type': last_typed=args.get('text')
                if 'id' in message:
                    safe_name=name if name in safe.TOOLS or name in ('initialize','tools/list') else 'other'
                    pending[message['id']]={'event':'mcp_call','id':message['id'],'name':safe_name,'start_ns':time.monotonic_ns(),'request':safe.request(args)}
                if name=='get_browser_state' and args.get('snapshot_format')=='semantic_v2': time.sleep(a.observe_ms/1000)
                proc.stdin.write(raw); proc.stdin.flush()
        except (BrokenPipeError,ValueError): pass
        finally:
            try: proc.stdin.close()
            except Exception: pass
    threading.Thread(target=send,daemon=True).start()
    for raw in iter(proc.stdout.readline,b''):
        try:
            message=json.loads(raw)
            row=pending.pop(message.get('id'),None)
            if row is not None:
                row.update(end_ns=time.monotonic_ns(),result=safe.result(message,row['name'],last_typed))
                write(row)
        except (ValueError,TypeError,KeyError):
            write({'event':'parse_error','ns':time.monotonic_ns()})
        sys.stdout.buffer.write(raw); sys.stdout.buffer.flush()
    rc=proc.wait()
    for row in pending.values(): write({**row,'end_ns':None,'result':{'error':True}})
    write({'event':'driver_exit','ns':time.monotonic_ns(),'rc':rc,'discarded_stderr_bytes':stderr_bytes[0]})
    log.close(); return rc

if __name__=='__main__': raise SystemExit(main())
