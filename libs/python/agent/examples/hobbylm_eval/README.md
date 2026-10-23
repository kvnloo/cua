# HobbyLM-1B downstream experiment

This is an opt-in experiment, not a general screenshot-based computer-use agent.
It preserves the released model's semantic observation format and ten actions.
The `hobbylm/local` loop registers through the existing Cua Agent loop registry.
It emits the existing function-tool contract. It does not change Cua protocols.
The package remains deprecated upstream.

## Measured results

The primary matrix ran at `461f073b759ca18b71f8af0d3bca26b1bd3f0924`.
All local arms used the same owned desktop, initial states, capabilities, seeds,
semantic prompt, and action allowlist. Each attempted 28 post-derived cases and
three existing OSWorld cases. Four other tasks remain explicitly unsupported.

| Arm | Supported success | Correct refusals | Decisions | Model p50 / p95 | Controller wall | Attributed GPU peak |
|---|---:|---:|---:|---:|---:|---:|
| HobbyLM FP32, RTX 3080 Ti | 22/31 (71.0%) | 4/6 | 58 | 1.194 / 3.464 s | 275.67 s | 4666 MiB |
| Qwen2.5-0.5B FP32, same GPU | 9/31 (29.0%) | 0/6 | 186 | 0.247 / 0.705 s | 340.20 s | 2388 MiB |
| GPT-6.1-Sol subscription | Unavailable, not a model score | Unmeasured | 0 | Unmeasured | 888.79 s of failed routing attempts | Remote memory unmeasured |

The subscription CLI reported an existing ChatGPT login, but all 31 task attempts
failed before generation. A bounded diagnostic identified workspace-routing
discovery `unauthorized (401)`. No new login, token transfer, or account change
was attempted. Do not interpret its raw zero-success summary as model performance.

The MacBook Air claim is a **0.262 s MLX replay median** and **0.806 s live mean**.
Our HobbyLM mean is 1.492 s. These are not same-hardware or same-task comparisons.
An exploratory richer-state prompt produced 1/31. Restoring the released
four-line observation improved transfer. Those exploratory runs are separate.

[The archive manifest](results/archive-manifest.json) links the 3.2 MB archive of
all JSONL traces, actual initial/per-step/final PNGs, controller receipts, and
exploratory runs. Raw summaries and the authentication classification are adjacent.
After the matrix, only the deterministic screenshot destination changed from the
private fixture root to its owned Desktop. The real destination and PNG were
requalified without new model inference. Model inputs and SHA-only feedback did
not change. Formatting-only changes also preserve the evaluated Python AST.

## Artifacts and provenance

- Source: [Fuel Labs HobbyLM](https://github.com/fuellabs-ai/hobbylm-1b/tree/98cca6f3bb128251d6204038cdc37ef4597b8388/computer-use).
- Adapter: [HobbyLM computer use](https://huggingface.co/Hobbylm/hobbylm-1B-computer-use).
- Base: `harims95/hobbylm-1B-instruct`, revision `8a90f6eb6a3d7c7eb952fd01b512a406821366ab`.
- The base, adapter, and native prompt use Apache-2.0. The attributed prompt's
  license is retained in `../../cua_agent/loops/LICENSE-HobbyLM.txt`.
- `artifact_manifest.json` pins repository revisions, file sizes, and SHA256 hashes.
  `fetch_models.py` downloads only these artifacts, under `/workspace/cache`.
- The adapter contains FP32 PEFT LoRA tensors, rank 16, alpha 32, and 83 module pairs.
  The Linux runtime merges these matrices without pickle or remote-code loaders.
- The runtime keeps FP32, greedy decoding, a KV cache, and a 1,024-token combined
  context limit. The exact prompt is `SYSTEM: {system}\nUSER: {user}\nASSISTANT:`.
  `SYSTEM_V2` and `format_user` in `../../cua_agent/loops/hobbylm.py` define its content.

The model receives calculator state, front application, volume, brightness, and
appearance as text. It does not receive PNGs or an unrestricted accessibility tree.
Screenshots in run directories are evidence only.

## Prepare

Run from the repository root. Use Python 3.11 for the two isolated environments:

```sh
uv venv --python 3.11 /workspace/cache/hobbylm-cua/venv
uv pip install --python /workspace/cache/hobbylm-cua/venv/bin/python \
  -r libs/python/agent/examples/hobbylm_eval/requirements-runtime.txt
/workspace/cache/hobbylm-cua/venv/bin/python \
  libs/python/agent/examples/hobbylm_eval/fetch_models.py

uv venv --python 3.11 /workspace/cache/hobbylm-cua/venv-harness
uv pip install --python /workspace/cache/hobbylm-cua/venv-harness/bin/python \
  'cua==0.2.0' -e libs/python/core -e libs/python/agent -e libs/python/cua-sandbox
libs/python/agent/examples/hobbylm_eval/setup-sandbox.sh
```

The runtime lock describes Linux x86-64 with CUDA 12.4 wheels. CPU use on another
architecture needs the corresponding PyTorch wheel, not NVIDIA x86-64 wheels.
The SDK and model environments are separate because LiteLLM's Tokenizers version
conflicts with the release's Transformers 4.46.3 requirement.

The setup script uses the official pinned Cua Linux image. It overrides its
Xvfb entrypoint and starts private headless Sway with XWayland disabled.
All package/data directories are bound to the NVMe cache. It mounts no host
compositor socket, input device, browser profile, or audio server.
Read the owned output/socket evidence before evaluation:

```sh
docker exec hobbylm-cua-eval-owned cat \
  /tmp/hobbylm-outputs.json /tmp/hobbylm-desktop.env /tmp/hobbylm-spacesd.log
```

## Run matched controls

Every model receives the same task suite, semantic input, action allowlist, and
initial state. Local models use FP32 and greedy decoding. Tasks use seed 1729,
with a deterministic per-task offset. No fine-tuning uses these tasks.

```sh
export HOBBYLM_EVAL_TOKEN=hobbylm-owned-local-eval
EXPERIMENT=libs/python/agent/examples/hobbylm_eval
PY=/workspace/cache/hobbylm-cua/venv-harness/bin/python
MODELS=/workspace/cache/hobbylm-cua/models

python3 "$EXPERIMENT/bounded-gpu.py" -- "$PY" "$EXPERIMENT/harness.py" \
  --endpoint http://127.0.0.1:13211 --ownership-id HobbyCuaEval \
  --runtime hobbylm --runtime-python /workspace/cache/hobbylm-cua/venv/bin/python \
  --base "$MODELS/hobbylm-1B-instruct" --adapter "$MODELS/hobbylm-1B-computer-use" \
  --device cuda --output /workspace/cache/hobbylm-cua/results/hobbylm

python3 "$EXPERIMENT/bounded-gpu.py" -- "$PY" "$EXPERIMENT/harness.py" \
  --endpoint http://127.0.0.1:13211 --ownership-id HobbyCuaEval \
  --runtime small-local --runtime-python /workspace/cache/hobbylm-cua/venv/bin/python \
  --model "$MODELS/Qwen2.5-0.5B-Instruct" --device cuda \
  --output /workspace/cache/hobbylm-cua/results/qwen \
  --compare-to /workspace/cache/hobbylm-cua/results/hobbylm/summary.json

"$PY" "$EXPERIMENT/harness.py" \
  --endpoint http://127.0.0.1:13211 --ownership-id HobbyCuaEval \
  --runtime codex --device cpu --output /workspace/cache/hobbylm-cua/results/codex \
  --compare-to /workspace/cache/hobbylm-cua/results/hobbylm/summary.json
```

The GPU wrapper checks IO pressure, applies `nice -n10`, limits the run to 1,800
seconds, and stops only its process group if a new GPU process appears. It also
stops at 4,768 MiB of attributed VRAM. Existing user processes are never stopped.
CPU runs use `--device cpu` without that wrapper.

The subscription control uses an existing ChatGPT login through `codex exec`,
model `gpt-6.1-sol`, a read-only sandbox, disabled native tools/config discovery,
and bounded calls. It must not initiate a new login. Its latency includes CLI
startup and network time. Remote model memory, seeded decoding, and a matching
output-token cap are not available. The Qwen control is a small text model, not
Qwen-VL and not a standard screenshot-conditioned Cua baseline.

## Evidence and limitations

Each task writes JSONL decisions, raw actions, independent state snapshots, and
PNG screenshots. The summary includes success/refusal rates, steps, generation
p50/p95, task wall time, and scoped process/allocator memory. A `DONE` message is
never a success oracle. Unsupported tasks remain in the denominator and report.

Linux mapping uses Mate Calculator, Mousepad, Orage, Thunar, Parole, a private
null audio sink, and real countdown processes. Media actions use guest `pactl`,
not macOS hardware keys. Headless physical brightness is unsupported.
Calculator `TYPE` invokes the owned application's accessible buttons. Calculator
performs the arithmetic. Its current editbar supplies the independent result,
not its history. The image's spacesd 0.6.0 keyboard route requires X11 even with
the Wayland flag. No X11 fallback or host input is used. This is a semantic
command adapter, not proof of native key-event or screenshot-driven parity.
Calendar events use an owned local calendar and synthetic contacts. They require
an exact preconfirmed fixture and never send invitations. This does not prove
macOS Contacts/Calendar permissions, a real y/n interaction, or invitation delivery.
The two existing Wordpad benchmark questions exceed the frozen calculator-only
`TYPE` action space. They are coverage failures, not benchmark successes.
Three pinned OSWorld instructions also run: maximum volume, infeasible Bluetooth,
and infeasible Python 4. They come from Cua Bench's pinned OSWorld revision.
`osworld-source.json` retains their original configurations and expected predicates.
The maximum-volume task retains its exact 100% target. Six 5% decisions from
the fixed 50% initial state cannot reach that target. This structural failure is
not removed or relabeled as success. These three adapted cases do not establish
an official OSWorld aggregate score or general GUI competence.

The published 0.262-second figure is MLX replay **median**, not live mean.
The replay mean is 0.455 seconds. The published live mean is 0.806 seconds.
These MacBook Air measurements are context, not same-hardware Linux baselines.

## Unit gate and cleanup

`verify-unit.sh` runs the complete Python core/agent suites, including executable
adapter/runtime tests, and the experiment's Ruff checks. Run it on the MBP Linux
node with `HOBBY_SOURCE_SHA` set to the exact committed source head. Use the
shared quiet lock, at most two CPUs, and a 60-second heartbeat. The script does
not start a model or a desktop.

```sh
docker stop hobbylm-cua-eval-owned
docker rm hobbylm-cua-eval-owned
```

Keep cache artifacts only when another run needs them. Do not delete unrelated
Docker images, containers, model caches, or user processes.
