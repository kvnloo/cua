"""Temporary Unix-socket IPC for native OMP judgments during a guarded GUI run.

The listener lives only for one finite experiment. No daemon, credentials, or
Cua Driver changes: the guarded subprocess owns inference and the guest, while
OMP eval answers model-choice requests using its native judgment adapter.
"""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
import socket
import stat
import time


def make_channels(root):
    root=Path(root)
    root.mkdir(mode=0o700,parents=True,exist_ok=False)
    return root


def exchange(root,payload,timeout=60):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        deadline=time.monotonic()+timeout
        while True:
            try:
                client.connect(str(Path(root)/'router.sock'))
                break
            except (FileNotFoundError,ConnectionRefusedError):
                if time.monotonic()>=deadline:
                    raise TimeoutError('native routing socket did not become ready')
                time.sleep(.05)
        client.sendall((json.dumps(payload)+'\n').encode())
        with client.makefile('rb') as stream:
            response=stream.readline(65537)
        if not response.endswith(b'\n') or len(response)>65536:
            raise ValueError('missing or oversized native routing response')
    return json.loads(response)


def request_choice(root,state,available,timeout=60):
    started=time.perf_counter()
    result=exchange(root,{'state':state,'available':available},timeout)
    if result.get('error'):raise RuntimeError(result['error'])
    if result['choice'] not in available:raise ValueError('Jev selected outside live pool')
    return result['choice'],{'wall_s':time.perf_counter()-started,**result}


def stop_native(root):
    return exchange(root,{'stop':True})


def remove_channels(root):
    root=Path(root)
    path=root/'router.sock'
    if path.exists():
        if not stat.S_ISSOCK(path.stat().st_mode):
            raise ValueError('refusing to remove a non-socket bridge artifact')
        path.unlink()
    root.rmdir()


async def serve_native(judge,root,receipt):
    root=Path(root)
    rows=[]
    stopped=asyncio.Event()
    async def handle(reader,writer):
        try:
            line=await asyncio.wait_for(reader.readline(),timeout=60)
            request=json.loads(line)
            if request.get('stop'):
                writer.write(b'{"stopped":true}\n')
                await writer.drain()
                stopped.set()
                return
            available=request['available']
            question={'model':{'type':'choice',
                'instructions':'Choose one AVAILABLE local model before its GUI action. Maximize supplied training current-context correctness; break correctness ties with lower measured active-device latency. Do not answer the GUI task. No held-out outcomes are supplied.',
                'criteria':{m:'Choose this candidate when its training context quality is highest among available models, with active-device latency breaking ties.' for m in available}}}
            started=time.perf_counter()
            try:
                answer=await judge(request['state'],question)
                result={'choice':answer['model']['choice'],'native_judge_wall_s':time.perf_counter()-started,'answer':answer,
                        'backend_evidence':'native judge adapter; exact provider identity is available from neighboring judge_batch receipts, not direct judge answers'}
            except Exception as error:
                result={'error':type(error).__name__+': '+str(error),'native_judge_wall_s':time.perf_counter()-started}
            rows.append({'state':request['state'],**result})
            Path(receipt).write_text(json.dumps({'scope':'actual sequential model-choice requests through native judge; transport probe is not a GUI run','decisions':rows},indent=2))
            writer.write((json.dumps(result)+'\n').encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    server=await asyncio.start_unix_server(handle,path=str(root/'router.sock'),limit=65536)
    async with server:
        await stopped.wait()
    return {'decisions':len(rows),'receipt':str(receipt)}
