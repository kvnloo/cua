"""Consumer-only evidence. Imports the installed official wheel; never creates a driver."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import platform
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import cua_driver
from cua_driver import GetWindowStateInput, ToolResult

ROOT = Path(__file__).resolve().parent
rows = []


def expect_error(name, function, exception, message):
    try:
        function()
    except exception as error:
        assert str(error) == message, (name, str(error), message)
        rows.append({"name": name, "expected": exception.__name__, "message": str(error), "pass": True})
    else:
        raise AssertionError(f"{name}: expected {exception.__name__}")


guide_bytes = (ROOT / "source-use-the-sdk.mdx").read_bytes()
assert hashlib.sha1(b"blob " + str(len(guide_bytes)).encode() + b"\0" + guide_bytes).hexdigest() == "b707577d18521010a759de8cd7dc4a9cb5be3583"
guide = guide_bytes.decode()
block = next(b for b in re.findall(r"```python[^\n]*\n(.*?)```", guide, re.S) if "capture = GetWindowStateInput(" in b)
call = next(node.value for node in ast.walk(ast.parse(block)) if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "capture" for t in node.targets))
assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "GetWindowStateInput"
expression = ast.Expression(call)
namespace = {"GetWindowStateInput": GetWindowStateInput, "app": SimpleNamespace(pid=1), "window": SimpleNamespace(window_id=1)}
expect_error("4683_printed_constructor", lambda: eval(compile(expression, "printed-guide-constructor", "eval"), namespace), TypeError,
             "GetWindowStateInput.__init__() missing 1 required keyword-only argument: 'max_image_dimension'")
kwargs = {kw.arg: eval(compile(ast.Expression(kw.value), "printed-guide-argument", "eval"), namespace) for kw in call.keywords}
assert "max_image_dimension" not in kwargs
control = GetWindowStateInput(**kwargs, max_image_dimension=None)
assert control.max_image_dimension is None
assert all(getattr(control, key) == value for key, value in kwargs.items())
rows.append({"name": "4683_add_only_none", "pass": True, "values": vars(control)})
zero = GetWindowStateInput(**kwargs, max_image_dimension=0)
assert zero.max_image_dimension == 0
rows.append({"name": "4683_zero_is_distinct_from_none", "pass": True, "max_image_dimension": zero.max_image_dimension, "scope": "record storage only, no capture behavior exercised"})
without_pid = dict(kwargs, max_image_dimension=None)
del without_pid["pid"]
expect_error("4683_missing_pid_control", lambda: GetWindowStateInput(**without_pid), TypeError,
             "GetWindowStateInput.__init__() missing 1 required keyword-only argument: 'pid'")

result_kwargs = dict(text="fixture", images=[], structured_json=None, is_error=False, error_code=None, action=None, verification=None, degraded=False, raw_json="{}")
result = ToolResult(**result_kwargs)
expect_error("4684_verified_attribute", lambda: result.verified, AttributeError,
             "'ToolResult' object has no attribute 'verified'")
assert result.action is None and result.verification is None and result.raw_json == "{}"
assert set(vars(result)) == set(result_kwargs)
rows.append({"name": "4684_real_fields", "pass": True, "fields": list(vars(result)), "values": vars(result)})
expect_error("4684_verified_keyword_control", lambda: ToolResult(**result_kwargs, verified=True), TypeError,
             "ToolResult.__init__() got an unexpected keyword argument 'verified'")
missing_verification = dict(result_kwargs)
del missing_verification["verification"]
expect_error("4684_missing_verification_control", lambda: ToolResult(**missing_verification), TypeError,
             "ToolResult.__init__() missing 1 required keyword-only argument: 'verification'")

package = Path(cua_driver.__file__).parent
files = {}
for name in ["_native.py", "_native_contract.py", "libcua_driver_sdk.so"]:
    data = (package / name).read_bytes()
    files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "git_blob_sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}
assert files["_native.py"]["git_blob_sha"] == "829ecf0ef305901e28a9c27219496dd96a81e96b"
assert files["_native_contract.py"]["git_blob_sha"] == "ce424c1cefdc2dd7e9a5244dce7a7daf780b0499"
loaded = sorted({line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines() if "libcua_driver_sdk.so" in line})
assert loaded == [str(package / "libcua_driver_sdk.so")]
output = {"status": "PASS", "python": sys.version, "platform": platform.platform(), "package_version": cua_driver.__version__, "package_path": str(package), "loaded_library": loaded, "source_files": files, "constructor_signature": str(inspect.signature(GetWindowStateInput)), "result_signature": str(inspect.signature(ToolResult)), "rows": rows, "rows_passed": len(rows), "not_run": ["CuaDriver.create", "native driver operations", "GUI", "daemon", "capture", "input", "full documentation example", "native build", "upstream test suite"]}
print(json.dumps(output, indent=2))
