# jev-use: finite native geometry

## Scope

This small downstream correctness patch makes Python native candidate geometry match the existing TypeScript finite-number guard. Python now rejects nonfinite floats and catches integer-to-float overflow before rectangle eligibility. TypeScript production behavior is unchanged.

The frozen upstream base is `5274342fbf66ca2998325be5e900299406ca8650`. The independently reviewed local implementation is `73d2b2d36600294fb486ee7a8cece056ae29cf30`; its three source/test blobs are preserved in this publication. This receipt is a documentation-only addition after that review. The branch is `fix/jev-use-finite-native-geometry-20261010` in `kvnloo/cua`.

No maintainer selection, upstream acceptance, release readiness or performance improvement is claimed. Existing upstream contributions #4734, #4902 and #4316 and their downstream compositions are unchanged.

## Reproduction environment

- Python 3.12.14
- MCP 1.30.0
- TypeSafe SDK 0.6.0
- Pydantic 2.13.5
- Node 24.19.0
- Locked recipe dependencies: `uv.lock` and `package-lock.json`

The checks used these versions and the recipe's locked dependencies. Use a recipe-local `.venv` for the commands below. No model credentials or native Driver installation are required.

Clone the published branch, then work from the recipe directory:

```bash
git clone --branch fix/jev-use-finite-native-geometry-20261010 https://github.com/kvnloo/cua.git
cd cua/libs/cua-driver/examples/jev-use
uv sync --frozen --python 3.12.14
npm ci --ignore-scripts
.venv/bin/python --version
node --version
.venv/bin/python -c 'from importlib.metadata import version; print({name: version(name) for name in ("mcp", "typesafe-sdk", "pydantic")})'
```

With the recipe-local virtual environment active, the exact focused commands are:

```bash
. .venv/bin/activate
python -m unittest discover -s python/tests -p test_native_geometry.py -v
node --import tsx --test typescript/native_geometry.test.ts
```

Full adjacent package checks from the same directory:

```bash
python -m unittest discover -s python/tests -v
node --import tsx --test typescript/*.test.ts
node node_modules/typescript/bin/tsc --noEmit
```

The Python suite skips one optional `cua-s1` installation test when that package is absent.

### Reproduce RED without changing the published branch

From the cloned repository root, create a separate worktree at the frozen base and add only the published regression tests:

```bash
git worktree add --detach ../cua-native-geometry-red 5274342fbf66ca2998325be5e900299406ca8650
git show HEAD:libs/cua-driver/examples/jev-use/python/tests/test_native_geometry.py > ../cua-native-geometry-red/libs/cua-driver/examples/jev-use/python/tests/test_native_geometry.py
git show HEAD:libs/cua-driver/examples/jev-use/typescript/native_geometry.test.ts > ../cua-native-geometry-red/libs/cua-driver/examples/jev-use/typescript/native_geometry.test.ts
cd ../cua-native-geometry-red/libs/cua-driver/examples/jev-use
uv sync --frozen --python 3.12.14
npm ci --ignore-scripts
.venv/bin/python -m unittest discover -s python/tests -p test_native_geometry.py -v
node --import tsx --test typescript/native_geometry.test.ts
```

The Python focused command is expected to fail. The TypeScript focused command passes because its finite-number veto already exists at the base. The RED test-only development commit was `75705601716a3d57cf282ddabaf50dbc1bcace5e`; the portable worktree procedure above does not depend on that local commit being published.

## Executed results

| Gate                                      | Python PASS | Python SKIP | TypeScript PASS |
| ----------------------------------------- | ----------: | ----------: | --------------: |
| Frozen upstream base, full package        |         230 |           1 |             105 |
| Reviewed implementation, full package     |         234 |           1 |             113 |
| Reviewed implementation, focused geometry |           4 |           0 |               8 |

TypeScript typechecking passed on both the base and implementation. The full implementation checks used the final formatted source/test bytes; focused checks were repeated after the implementation commit.

Before the Python fix, four focused owner tests produced 37 failing subcases and 25 error subcases. The actual Python native runner dispatched an Increment whose width was parsed from legal JSON `1e309`; a 401-digit integer raised `OverflowError`. After the minimal fix, all focused tests pass.

In a separate TypeScript negative-control copy, removing only the existing `Number.isFinite` veto produces four failures and four passes. The failures include invalid geometry causing the actual runner to return `verified` after dispatch, where the intact guard returns `budget_exhausted` without any mutation. The published TypeScript production file was not changed.

## Coverage and limits

The tests decode actual MCP tool-result envelopes and pass their observations through the native candidate source. Every coordinate/dimension slot in frames and window bounds is covered across the macOS, Windows and Linux role tables. Invalid cases include legal JSON `1e309`, `-1e309`, a 401-digit integer, null, booleans and strings. Finite controls cover ordinary integers, negative origins, maximum finite binary64 and the smallest positive subnormal. Existing zero/negative-size and off-screen exclusions remain unchanged.

Python's MCP decoder accepts nonstandard `NaN`, `Infinity` and `-Infinity` tokens. Those are tested separately. JavaScript rejects those tokens at `JSON.parse`, before its MCP schema and native observation path; no common-transport acceptance is asserted.

Both actual native runners run against mocked MCP transports and an independently read local task-state file. Each of three invalid-width rows makes zero mutation calls, leaves counter zero and finishes with `budget_exhausted` after reobserving. The finite width-20 control makes one mutation call and verifies counter three.

This is parser, candidate-contract and simulated-transport runner evidence. No real Driver, native GUI, AT-SPI/DBus, Chromium, screenshot, clipboard or physical input certification was performed. Previously established Linux AF_UNIX/DBus restrictions were not rerun; macOS and Windows native environments were unavailable.

## Lint and content identity

Ruff 0.14.1 passed for the changed Python production file and new test. Black 25.9.0 and isort 7.0.0 passed for the new Python test. Prettier passed for the new TypeScript test. `git diff --check` passed.

Full-file Black refuses `native.py` on both the frozen base and candidate because of pre-existing formatting debt. Its candidate formatting diff does not touch the changed numeric helper. This narrow patch does not include unrelated production reformatting.

Reviewed Git blobs:

- `python/native.py`: `152085c772dc206885e9712768e16f8d8b47b046`
- `python/tests/test_native_geometry.py`: `fe22a3eabad30c54d8b8ec8279f61147839686ca`
- `typescript/native_geometry.test.ts`: `df37ca34ff63cac7a9f9667f29f8f61de5e5b9ff`

`SHA256SUMS` pins those three files and this receipt. From the repository root, verify it with:

```bash
sha256sum -c evidence/jev-use-native-geometry/SHA256SUMS
```

Only this sanitized, portable evidence is published. Raw execution logs are retained locally.

## Credit

Francesco Bonacci (@f-trycua) authored the original native candidate implementation (#4288), Windows/Linux parity (#4290) and existing TypeScript finite-number guard. This patch preserves that implementation and aligns Python with its existing behavior. Prior contributor authorship is unchanged.
