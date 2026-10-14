"""Bounded real-package replay. No site startup, network, process or native SDK calls."""
import sys
import os
import json
import pathlib
import hashlib
import importlib.abc
import importlib.metadata
import resource
import traceback

ROOT = pathlib.Path(__file__).resolve().parent
SITE = pathlib.Path(os.environ['CUA_EVIDENCE_SITE']).resolve()
variant, suite = sys.argv[1:3]
assert variant in {'head', 'base', 'no_context_cleanup', 'single_result_dict'}
assert suite in {'preflight', 'retained', 'original', 'controls'}
SOURCE = ROOT / 'source' / variant
resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
sys.path[:0] = [str(SOURCE), str(SITE)]
denials = []

def deny(message):
    denials.append({'message': message, 'stack': traceback.format_stack(limit=8)})
    raise RuntimeError(message)

class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'cua' or fullname.startswith(('cua.', 'cua_driver')):
            deny('native SDK import refused: ' + fullname)

sys.meta_path.insert(0, NoNative())

def audit(event, args):
    if event in {'subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn', 'socket.connect', 'socket.bind', 'socket.getaddrinfo'}:
        deny('external operation refused: ' + event)
    if event == 'socket.__new__' and args[1] in (2, 10):
        deny('IP socket refused')
    if event == 'open':
        path, mode, flags = args
        writes = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        if writes and not isinstance(path, int):
            p = pathlib.Path(path).resolve()
            if not p.is_relative_to(ROOT / 'tmp'):
                deny('filesystem write outside temporary directory refused: ' + str(p))

sys.addaudithook(audit)
import threading
def no_thread(self, *args, **kwargs):
    deny('background thread refused')
threading.Thread.start = no_thread

def provenance():
    modules = []
    for name, module in sorted(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        path = pathlib.Path(filename)
        if path.is_file() and (path.is_relative_to(SOURCE) or path.is_relative_to(SITE)):
            modules.append({'name': name, 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return modules

result = {'variant': variant, 'suite': suite, 'python': sys.version, 'source': str(SOURCE), 'site': str(SITE)}
try:
    import cua_sandbox
    from cua_sandbox.interfaces.tunnel import Tunnel, TunnelInfo
    from cua_sandbox.transport.base import Transport
    assert pathlib.Path(cua_sandbox.__file__).is_relative_to(SOURCE)
    assert pathlib.Path(sys.modules[Tunnel.__module__].__file__).is_relative_to(SOURCE)
    result['package_version'] = cua_sandbox.__version__
    result['distributions'] = {d.metadata['Name']: d.version for d in importlib.metadata.distributions(path=[str(SITE)])}
    if suite == 'preflight':
        status = 0
    else:
        import pytest
        test = ROOT / 'tests' / ('test_tunnel_retained.py' if suite == 'retained' else 'test_tunnel_original.py')
        args = [str(test), '-q', '--noconftest', '--assert=plain', '-p', 'no:cacheprovider', '-p', 'no:logging', '-p', 'pytest_asyncio.plugin', '-o', 'asyncio_mode=auto', '-o', 'asyncio_default_fixture_loop_scope=function']
        if suite == 'controls':
            args += ['-k', 'successful_context or successful_await']
        status = int(pytest.main(args))
    result['exit'] = status
finally:
    result['denials'] = denials
    result['threads'] = [t.name for t in threading.enumerate()]
    result['native_imported'] = any(k == 'cua' or k.startswith('cua.') for k in sys.modules)
    result['imports'] = provenance()
    print('PROVENANCE_JSON=' + json.dumps(result, sort_keys=True))
sys.exit(status)
