"""Bounded, offline file-level evidence for CUA PR 4898; no environment creation."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.abc
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import resource
import socket
import sys
import threading
import time
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
DEPENDENCY = ROOT / 'dependency'
DEPENDENCY_PIN = '2600a2abb095a70e01a56bfe8f8308a03b4cdc67'
HEAD_BLOB = '524413d0cc3fbe662805010c320ba4f2537aa7a2'
HEAD_SHA256 = '60266d6a5ebd9aa05926c2f2fecc0ef9e96cb36264102b44dff6922647d4f68d'
MODULE_NAME = 'cua_4898_worker_server'
TRACE: list[dict] = []
DENIED: list[dict] = []
SUPPRESSED: list[dict] = []
ALLOWED_THREADS: set[int] = set()
IMPORTING = False


class GuardViolation(BaseException):
    pass


class EndSweep(BaseException):
    pass


def deny(kind, target):
    DENIED.append({'kind': kind, 'target': str(target)[:180]})
    raise GuardViolation(f'{kind} blocked: {target}')


def contained(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


READ_ROOTS = [ROOT, DEPENDENCY / 'cua_bench', Path(sys.base_prefix).resolve()]


def permitted_read(value):
    if isinstance(value, int):
        return value in (0, 1, 2)
    if value is None:
        return False
    path = Path(os.fsdecode(value)).resolve()
    return any(contained(path, root) for root in READ_ROOTS)


FORBIDDEN_MODULES = (
    'cua', 'cua_driver', 'cua_sandbox', 'computer', 'torch', 'datasets',
    'docker', 'paramiko', 'grpc', 'cua_bench.environment', 'cua_bench.runners',
    'cua_bench_rl.workers.worker_manager', 'cua_bench_rl.workers.worker_client',
)


def forbidden_module(name):
    return any(name == p or name.startswith(p + '.') for p in FORBIDDEN_MODULES)


def audit(event, args):
    if event in {'subprocess.Popen', 'os.system', 'os.fork', 'os.forkpty',
                 'os.posix_spawn', 'os.exec', 'pty.spawn', 'ctypes.dlopen'}:
        deny(event, args[0] if args else '')
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo',
                 'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.sendto'}:
        deny(event, 'network access')
    if event == 'socket.__new__' and len(args) > 1 and args[1] in (socket.AF_INET, socket.AF_INET6):
        deny(event, 'IP socket creation')
    if event == 'import' and args and forbidden_module(args[0]):
        deny(event, args[0])
    if event == 'open':
        path, mode, flags = args
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & write_flags):
            deny(event, 'filesystem write')
        if not permitted_read(path):
            deny(event, path)
    if event in {'os.listdir', 'os.scandir'} and args:
        # Importlib enumerates this exact approved package search directory.
        # This grants listing only; file reads remain confined to cua_bench/.
        package_search_listing = Path(os.fsdecode(args[0])).resolve() == DEPENDENCY.resolve()
        if not permitted_read(args[0]) and not package_search_listing:
            deny(event, args[0])
    if event in {'os.remove', 'os.rmdir', 'os.rename', 'os.mkdir', 'os.symlink',
                 'os.link', 'os.chmod', 'os.chown', 'os.truncate', 'shutil.rmtree'}:
        deny(event, 'filesystem mutation')


class ImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if forbidden_module(fullname):
            deny('module import', fullname)
        return None


REAL_THREAD_START = threading.Thread.start


def guarded_thread_start(thread, *args, **kwargs):
    target = getattr(thread, '_target', None)
    if IMPORTING and getattr(target, '__module__', None) == MODULE_NAME and getattr(target, '__name__', None) == '_timeout_checker' and thread.daemon:
        SUPPRESSED.append({'module': MODULE_NAME, 'function': '_timeout_checker', 'daemon': True})
        return None
    if id(thread) not in ALLOWED_THREADS:
        deny('thread start', getattr(target, '__qualname__', type(target).__name__))
    return REAL_THREAD_START(thread, *args, **kwargs)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_target(source: Path, mode: str):
    global IMPORTING
    payload = source.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
    if mode == 'head':
        assert blob == HEAD_BLOB and sha256(source) == HEAD_SHA256
    else:
        manifest = json.loads((ROOT / 'mutant' / 'mutation.json').read_text())
        assert sha256(source) == manifest['mutant_sha256']
        assert manifest['original_sha256'] == HEAD_SHA256
    # This is the genuine package dependency. Only a documented alias is disabled.
    sys.path.insert(0, str(DEPENDENCY))
    sys.meta_path.insert(0, ImportGuard())
    threading.Thread.start = guarded_thread_start
    sys.addaudithook(audit)
    spec = importlib.util.spec_from_file_location(MODULE_NAME, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    IMPORTING = True
    try:
        spec.loader.exec_module(module)
    finally:
        IMPORTING = False
    assert len(SUPPRESSED) == 1
    assert not module._timeout_thread.is_alive()
    # Factory is outside this test's scope; prohibit a future accidental call.
    def no_environment(*args, **kwargs):
        deny('environment factory', 'cua_bench.make')
    module.make = no_environment
    return module, blob


class InertEnvironment:
    def __init__(self):
        self.close_calls = 0
        self.closed = False

    async def close(self):
        self.close_calls += 1
        self.closed = True
        TRACE.append({'event': 'close', 'thread': threading.current_thread().name})


async def wait_for(predicate, description, seconds=4):
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(f'timeout: {description}')
        await asyncio.sleep(0.001)


async def run_case(module, name, refreshed_at, should_close):
    start = len(TRACE)
    selected, resume, finished = threading.Event(), threading.Event(), threading.Event()
    errors = []
    environment = InertEnvironment()
    state = module.EnvState(environment, 'inert:no-environment', 0, 'train', 300, 0.0)
    module.available_envs[:] = [1]
    module.active_envs[:] = [0]
    module.env_map.clear()
    module.env_map[0] = state
    module._server_loop = asyncio.get_running_loop()
    assert not module._pending_closes
    original_release = module._release_env
    original_time = module.time
    assert type(module.env_lock) is type(threading.Lock())

    class Clock:
        def __init__(self):
            self.sleeps = 0

        def sleep(self, duration):
            assert duration == 30
            self.sleeps += 1
            if self.sleeps == 2:
                raise EndSweep()
            assert self.sleeps == 1

        def time(self):
            if threading.current_thread() is checker:
                TRACE.append({'event': 'sweep_clock', 'value': 1000.0})
                return 1000.0
            assert refreshed_at is not None
            assert module.env_lock.locked()
            TRACE.append({'event': 'refresh_clock_under_real_lock', 'value': refreshed_at})
            return refreshed_at

    def release_barrier(env_id, expired_at=None):
        assert env_id == 0 and expired_at == 1000.0
        assert not module.env_lock.locked(), 'checker must drop env_lock before release'
        assert module.env_map[0] is state and state.last_accessed == 0.0
        TRACE.append({'event': 'selected_before_release', 'env_id': env_id, 'cutoff': expired_at, 'last_accessed': state.last_accessed, 'lock_held': False})
        selected.set()
        if not resume.wait(4):
            raise AssertionError('release barrier was not resumed')
        TRACE.append({'event': 'enter_real_release', 'last_accessed': state.last_accessed})
        original_release(env_id, expired_at=expired_at)
        TRACE.append({'event': 'real_release_returned'})

    def sweep():
        try:
            module._timeout_checker()
        except EndSweep:
            pass
        except BaseException as error:
            errors.append((type(error).__name__, str(error)))
        finally:
            finished.set()

    checker = threading.Thread(target=sweep, name='evidence-one-sweep', daemon=True)
    ALLOWED_THREADS.add(id(checker))
    module.time = Clock()
    module._release_env = release_barrier
    try:
        checker.start()
        await wait_for(lambda: selected.is_set() or finished.is_set(), 'sweep selection')
        assert selected.is_set(), errors
        if refreshed_at is not None:
            assert module._get_env(0) is state
            assert state.last_accessed == refreshed_at
            TRACE.append({'event': 'refresh_completed', 'same_state': True, 'last_accessed': state.last_accessed})
        resume.set()
        await wait_for(finished.is_set, 'one sweep completion')
        checker.join(timeout=0.1)
        assert not checker.is_alive()
        assert not errors, errors
        await wait_for(lambda: not module._pending_closes, 'close callbacks drained')
        await asyncio.sleep(0)
        observed = {'close_calls': environment.close_calls, 'closed': environment.closed,
                    'same_state_registered': module.env_map.get(0) is state,
                    'active': 0 in module.active_envs, 'available': 0 in module.available_envs,
                    'last_accessed': state.last_accessed, 'pending_closes': len(module._pending_closes)}
        expected = {'close_calls': int(should_close), 'closed': should_close,
                    'same_state_registered': not should_close, 'active': not should_close,
                    'available': should_close,
                    'last_accessed': refreshed_at if refreshed_at is not None else 0.0, 'pending_closes': 0}
        failures = [key for key in expected if observed[key] != expected[key]]
        return {'name': name, 'status': 'FAIL' if failures else 'PASS', 'failed_assertions': failures,
                'expected': expected, 'observed': observed, 'trace': TRACE[start:]}
    finally:
        resume.set()
        module._release_env = original_release
        module.time = original_time
        ALLOWED_THREADS.discard(id(checker))


async def cases(module):
    results = []
    for arguments in [('expired', None, True), ('refreshed', 1000.0, False),
                      ('exact_timeout_boundary', 700.0, False), ('still_expired_after_touch', 699.0, True)]:
        results.append(await run_case(module, *arguments))
    assert not module._pending_closes
    module.env_map.clear()
    module.active_envs.clear()
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['head', 'mutant'], required=True)
    parser.add_argument('--import-only', action='store_true')
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    assert os.environ.get('CUA_BENCH_COMPUTER_ALIAS') == '0'
    assert os.environ.get('CUA_TELEMETRY_ENABLED') == 'false'
    assert set(os.environ) <= {'PATH', 'HOME', 'LC_ALL', 'CUA_BENCH_COMPUTER_ALIAS', 'CUA_TELEMETRY_ENABLED'}
    source = ROOT / ('source' if args.mode == 'head' else 'mutant') / 'worker_server.py'
    result = {'mode': args.mode, 'qualification': 'file-level, genuine dependency import closure verified against existing checkout/index',
              'python': sys.version, 'dependency_checkout_reported_commit': DEPENDENCY_PIN,
              'isolation': 'sanitized environment, bounded process, Python defense-in-depth guards'}
    try:
        module, blob = load_target(source, args.mode)
        result['source'] = {'git_blob': blob, 'sha256': sha256(source), 'path': str(source)}
        result['imports'] = [{'module': name, 'path': str(Path(m.__file__).resolve()),
                              'sha256': sha256(Path(m.__file__))}
                             for name, m in sorted(sys.modules.items())
                             if name.startswith('cua_bench') and getattr(m, '__file__', None)]
        result['cases'] = [] if args.import_only else asyncio.run(cases(module))
        assert not DENIED, DENIED
        assert not any(forbidden_module(name) for name in sys.modules)
        result['status'] = 'IMPORT_ONLY_PASS' if args.import_only else ('FAIL' if any(c['status'] == 'FAIL' for c in result['cases']) else 'PASS')
    except BaseException as error:
        result['status'] = 'GUARD_STOP' if isinstance(error, GuardViolation) or DENIED else 'ERROR'
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    result['suppressed_import_threads'] = SUPPRESSED
    result['guard_denials'] = DENIED
    result['live_threads'] = [t.name for t in threading.enumerate()]
    print(json.dumps(result, indent=2))
    return 0 if result['status'] in {'PASS', 'IMPORT_ONLY_PASS'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
