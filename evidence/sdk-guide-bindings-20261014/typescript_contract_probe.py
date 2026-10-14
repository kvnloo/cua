"""Run the real TypeScript compiler against unchanged published declarations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--tsc", type=Path, required=True)
parser.add_argument("--type-roots", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
cwd = root / "typescript"
env = dict(os.environ, NODE_DISABLE_COMPILE_CACHE="1")
base = ["node", str(args.tsc), "--noEmit", "--strict", "--target", "ES2022", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--skipLibCheck", "false", "--typeRoots", str(args.type_roots), "--types", "node"]
version = subprocess.run(["node", str(args.tsc), "--version"], text=True, capture_output=True, check=True, env=env).stdout.strip()
assert version == "Version 5.9.3"
cases = [("valid_fields", 0, None), ("bad_verified", 2, "TS2339"), ("bad_boolean_verification", 2, "TS2322"), ("missing_raw_json", 2, "TS2741")]
rows = []
for case, expected_exit, expected_code in cases:
    command = base + [case + ".mts"]
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=60)
    output = completed.stdout + completed.stderr
    (root / "logs" / ("ts-" + case + ".log")).write_text(output)
    codes = re.findall(r"error (TS\d+):", output)
    assert completed.returncode == expected_exit, (case, completed.returncode, output)
    assert codes == ([] if expected_code is None else [expected_code]), (case, codes, output)
    if case == "bad_verified":
        assert "Property 'verified' does not exist on type 'ToolResult'." in output
    if case == "bad_boolean_verification":
        assert "VerifyStateOutput | undefined" in output and "boolean" in output
    if case == "missing_raw_json":
        assert "Property 'rawJson' is missing" in output
    rows.append({"name": case, "command": command, "exit_code": completed.returncode, "diagnostic_codes": codes, "output": output, "pass": True})
hashes = {}
for path in sorted(cwd.glob("package/**/*.d.ts")):
    hashes[str(path.relative_to(cwd))] = hashlib.sha256(path.read_bytes()).hexdigest()
toolchain = {}
for path in [args.tsc, args.tsc.parent / "_tsc.js", args.tsc.parent.parent / "package.json", args.type_roots / "node/package.json", args.type_roots.parent / "undici-types/package.json"]:
    toolchain[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps({"status": "PASS", "compiler": version, "package_version": "0.33.4", "node_types_version": json.loads((args.type_roots / "node/package.json").read_text())["version"], "undici_types_version": json.loads((args.type_roots.parent / "undici-types/package.json").read_text())["version"], "ubjs_core_version": "0.31.0-3", "skip_lib_check": False, "declaration_sha256": hashes, "toolchain_sha256": toolchain, "rows": rows, "rows_passed": len(rows), "not_run": ["JavaScript SDK runtime import", "native Node FFI", "driver instance", "desktop operations", "exact-main TypeScript package build"]}, indent=2))
