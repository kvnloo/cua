"""Run the recorded TypeScript probes against two unchanged source checkouts.

Usage: python run_typechecks.py BASE_CHECKOUT CANDIDATE_CHECKOUT TOOLS_NODE_MODULES
Each source package must resolve its declared @ubjs dependencies; a task-local
node_modules symlink suffices. The tools directory supplies TypeScript and @types/node.
No native library, mocked transport, or Driver action is used by these checks.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    baseline, candidate, modules = (Path(p).resolve() for p in sys.argv[1:])
    cases = [
        ("legacy-bool-baseline", baseline, False, "{trail: true, glow: false}", 0),
        ("legacy-bool-candidate", candidate, False, "{trail: true, glow: false}", 2),
        ("omitted-baseline", baseline, False, "{}", 0),
        ("omitted-candidate", candidate, False, "{}", 0),
        ("enum-candidate", candidate, True,
         "{trail: CursorEffectSetting.On, glow: CursorEffectSetting.Off, ripple: CursorEffectSetting.Default}", 0),
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix="cua-compat-typechecks-") as temp:
        for name, checkout, use_enum, value, expected in cases:
            module = checkout / "libs/cua-driver/typescript/src/native/cua_driver_contract.js"
            names = "CursorMotionEffects" + (", CursorEffectSetting" if use_enum else "")
            source = Path(temp) / (name + ".mts")
            source.write_text(
                f"import {{ {names} }} from {json.dumps(str(module))};\n"
                f"const effects: CursorMotionEffects = {value};\n"
                "CursorMotionEffects.create(effects);\n"
            )
            command = [str(modules / ".bin/tsc"), "--noEmit", "--strict", "--skipLibCheck",
                       "--target", "ES2022", "--module", "NodeNext",
                       "--typeRoots", str(modules / "@types"), str(source)]
            completed = subprocess.run(command, capture_output=True, text=True)
            results.append({"case": name, "command": command, "returncode": completed.returncode,
                            "expected": expected, "stdout": completed.stdout, "stderr": completed.stderr})
    print(json.dumps(results, indent=2))
    assert all(row["returncode"] == row["expected"] for row in results)
    errors = results[1]["stdout"]
    assert errors.count("TS2322") == 2 and errors.count("error TS") == 2, errors


if __name__ == "__main__":
    main()
