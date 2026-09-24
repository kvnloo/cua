from pathlib import Path
import difflib
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BASE_SHA = "072ceb73f9ce32e65b5280438040b59cb4da2794"
SOURCE_PATH = "libs/cua-s1/python/src/cua_s1/checkpoint.py"
TEST_PATH = "libs/cua-s1/python/tests/test_checkpoint.py"


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    original = (ROOT / "checkpoint_baseline.py").read_bytes()
    tests = (ROOT / "test_checkpoint_upstream.py").read_bytes()
    assert blob(original) == "0f4f7effe9226683e18df6ebb558148c77df2a86"
    assert blob(tests) == "80c7fbebe2124e571a69b1ef6d21367e19aaf268"
    text = original.decode()
    before = '        if path.name == "model.safetensors" and not path.with_suffix(".json").exists():'
    after = '''        if path.name == "model.safetensors" and (
            (path.parent / "config.json").exists() or not path.with_suffix(".json").exists()
        ):'''
    assert text.count(before) == 1
    text = text.replace(before, after)
    before = '        if path.name == "config.json" and not path.with_suffix(".safetensors").exists():'
    after = '''        if path.name == "config.json" and (
            (path.parent / "model.safetensors").exists()
            or not path.with_suffix(".safetensors").exists()
        ):'''
    assert text.count(before) == 1
    text = text.replace(before, after)
    candidate = text.encode()
    patch = ''.join(difflib.unified_diff(original.decode().splitlines(True), text.splitlines(True), fromfile='a/' + SOURCE_PATH, tofile='b/' + SOURCE_PATH))
    (ROOT / "checkpoint-canonical-precedence.patch").write_text(patch)
    results = []
    for name, source in (("baseline", original), ("candidate", candidate)):
        package = ROOT / name / "cua_s1"
        package.mkdir(parents=True, exist_ok=True)
        (package / "checkpoint.py").write_bytes(source)
        env = dict(os.environ, PYTHONPATH=str(package.parent), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                   str(ROOT / 'test_checkpoint_upstream.py'),
                   str(ROOT / 'test_checkpoint_locator_regressions.py'),
                   '--junitxml=' + str(ROOT / f'{name}.xml')]
        run = subprocess.run(command, env=env, text=True, capture_output=True, timeout=35)
        log = run.stdout + run.stderr
        (ROOT / f'{name}.log').write_text(log)
        print(f'=== {name} exit={run.returncode} ===\n{log}')
        import xml.etree.ElementTree as ET
        root = ET.parse(ROOT / f'{name}.xml').getroot()
        suites = root.findall('testsuite') if root.tag == 'testsuites' else [root]
        count = lambda key: sum(int(s.attrib.get(key, '0')) for s in suites)
        failures = [c.attrib['name'] for s in suites for c in s.findall('testcase') if c.find('failure') is not None or c.find('error') is not None]
        result = {'variant': name, 'exit_code': run.returncode, 'tests': count('tests'), 'failures': count('failures'), 'errors': count('errors'), 'skipped': count('skipped'), 'failing_cases': failures, 'source_git_blob': blob(source), 'source_sha256': hashlib.sha256(source).hexdigest()}
        results.append(result)
    assert results[0]['tests'] == 20 and results[0]['failures'] == 2 and results[0]['exit_code'] == 1, results[0]
    assert set(results[0]['failing_cases']) == {'test_returned_weights_path_ignores_stale_model_json', 'test_returned_config_path_ignores_stale_config_safetensors'}
    assert results[1]['tests'] == 20 and results[1]['failures'] == results[1]['errors'] == results[1]['skipped'] == results[1]['exit_code'] == 0, results[1]
    summary = {'source_commit': BASE_SHA, 'source_path': SOURCE_PATH, 'upstream_test_path': TEST_PATH, 'original_source_blob': blob(original), 'upstream_test_blob': blob(tests), 'python': sys.version, 'platform': platform.platform(), 'dependencies': {name: importlib.metadata.version(name) for name in ('torch', 'safetensors', 'pytest')}, 'results': results, 'scope': 'Complete unchanged checkpoint module and 11 unchanged upstream tests, plus 9 new integration tests; real CPU tensors and actual safetensors files; namespace-package staging only, no function mocks or extraction', 'full_project_suite': 'NOT_RUN', 'project_lockfile_environment': 'NOT_USED: installed CPU dependencies recorded above', 'candidate_status': 'Optional local patch; no contributor branch modified'}
    (ROOT / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
