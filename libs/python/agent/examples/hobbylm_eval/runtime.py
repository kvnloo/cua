"""Pinned, offline FP32 text inference for the downstream HobbyLM experiment.

Model acquisition is separate from inference. Only the files recorded in the
adjacent artifact_manifest.json are accepted. HobbyLM's audited Python modules
are imported directly, not through Transformers' remote-code loader. No pickle
checkpoints, PEFT code execution, quantization, or desktop access is involved.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
import platform
import sys
import time
import types
from pathlib import Path
from functools import cache

CACHE_DIR = Path("/workspace/cache/hobbylm-cua")
TOKEN_BUDGET = 1024
MAX_NEW_TOKENS = 64
# Decimal bytes, not GiB. CUDA context/driver memory is outside this allocator.
GPU_LIMIT_BYTES = 5_000_000_000
_MANIFEST = Path(__file__).with_name("artifact_manifest.json")
_LORA_KEY = re.compile(r"base_model\.model\.(.+)\.lora_([AB])(?:\.default)?\.weight")
_TARGETS = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}


@cache
def _cpu_model() -> str | None:
    reported = platform.processor()
    if reported:
        return reported
    try:
        with Path("/proc/cpuinfo").open() as stream:
            for line in stream:
                key, separator, value = line.partition(":")
                if separator and key.strip() in {"model name", "Hardware", "Processor"} and value.strip():
                    return value.strip()
    except OSError:
        pass
    return None


def _verify_artifacts(path: str | Path, role: str) -> tuple[Path, dict]:
    directory = Path(path).expanduser().resolve(strict=True)
    if not directory.is_dir():
        raise ValueError(f"Expected a local model directory: {directory}")
    spec = json.loads(_MANIFEST.read_text())["models"][role]
    expected = spec["files"]
    # Unexpected configuration or checkpoint files can change HF loader behavior.
    for entry in directory.iterdir():
        if entry.name not in expected and entry.name != "__pycache__":
            raise ValueError(f"Unpinned artifact: {entry.name}")
    for filename, record in expected.items():
        artifact = directory / filename
        if not artifact.is_file() or artifact.stat().st_size != record["bytes"]:
            raise ValueError(f"Artifact size mismatch: {role}/{filename}")
        digest = hashlib.sha256()
        with artifact.open("rb") as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != record["sha256"]:
            raise ValueError(f"Artifact SHA256 mismatch: {role}/{filename}")
    return directory, spec


def _hobby_model_class(directory: Path):
    # These modules have already passed the release's pinned SHA256 checks.
    # A private package supplies their relative import without changing sys.path.
    package_name = "_cua_audited_hobbylm_" + hashlib.sha256(str(directory).encode()).hexdigest()[:16]
    package = types.ModuleType(package_name)
    package.__path__ = [str(directory)]
    sys.modules[package_name] = package
    try:
        for name in ("configuration_hobbylm", "modeling_hobbylm"):
            spec = importlib.util.spec_from_file_location(f"{package_name}.{name}", directory / f"{name}.py")
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot import audited module {name}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            # Ignore bytecode caches. Their content is not part of the manifest.
            source = directory / f"{name}.py"
            exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
        return module.HobbyLMForCausalLM
    except BaseException:
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_name + "."):
                del sys.modules[name]
        raise


def _merge_lora(model, state: dict, config: dict, torch) -> int:
    """Merge the published PEFT linear A/B weights with strict shape checks."""
    if (config.get("peft_type") != "LORA" or config.get("task_type") != "CAUSAL_LM"
            or config.get("bias") != "none" or config.get("fan_in_fan_out", False)
            or config.get("use_dora", False) or config.get("use_rslora", False)
            or config.get("modules_to_save") or config.get("rank_pattern")
            or config.get("alpha_pattern")):
        raise ValueError("Unsupported LoRA configuration")
    if set(config.get("target_modules", [])) != _TARGETS:
        raise ValueError("Unexpected LoRA target modules")
    rank, alpha = config.get("r"), config.get("lora_alpha")
    if type(rank) is not int or rank <= 0 or not isinstance(alpha, (int, float)) or not math.isfinite(alpha):
        raise ValueError("Invalid LoRA rank or alpha")
    pairs = {}
    for key, value in state.items():
        match = _LORA_KEY.fullmatch(key)
        if match is None:
            raise ValueError(f"Unexpected LoRA tensor: {key}")
        name, side = match.groups()
        if side in pairs.setdefault(name, {}):
            raise ValueError(f"Duplicate LoRA tensor: {name}/{side}")
        pairs[name][side] = value
    modules = dict(model.named_modules())
    expected = {name for name, module in modules.items()
                if name.rsplit(".", 1)[-1] in _TARGETS and isinstance(module, torch.nn.Linear)}
    if not pairs or set(pairs) != expected:
        raise ValueError("LoRA tensors do not cover exactly the model's target linear modules")
    # Validate every key and shape before modifying any model weight.
    for name, pair in pairs.items():
        if set(pair) != {"A", "B"}:
            raise ValueError(f"Incomplete LoRA pair: {name}")
        a, b, weight = pair["A"], pair["B"], modules[name].weight
        if (a.ndim != 2 or b.ndim != 2 or tuple(a.shape) != (rank, weight.shape[1])
                or tuple(b.shape) != (weight.shape[0], rank)):
            raise ValueError(f"LoRA shape mismatch: {name}")
        if a.dtype != torch.float32 or b.dtype != torch.float32 or weight.dtype != torch.float32:
            raise ValueError(f"LoRA merge requires FP32 tensors: {name}")
        if not bool(torch.isfinite(a).all()) or not bool(torch.isfinite(b).all()):
            raise ValueError(f"Non-finite LoRA tensor: {name}")
    with torch.no_grad():
        for name, pair in pairs.items():
            weight = modules[name].weight
            delta = pair["B"].to(weight.device) @ pair["A"].to(weight.device)
            delta.mul_(alpha / rank).add_(weight)
            if not bool(torch.isfinite(delta).all()):
                raise ValueError(f"Non-finite merged LoRA weight: {name}")
            weight.copy_(delta)
    return len(pairs)


class _TextRuntime:
    def _configure(self, device: str):
        import torch

        self._torch = torch
        self.device = torch.device(device)
        if self.device.type not in {"cpu", "cuda"}:
            raise ValueError("Only CPU and CUDA devices are supported")
        if self.device.type == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is unavailable. Select device='cpu'.")
            if self.device.index is None:
                self.device = torch.device("cuda", torch.cuda.current_device())
            total = torch.cuda.get_device_properties(self.device).total_memory
            torch.cuda.set_per_process_memory_fraction(min(GPU_LIMIT_BYTES / total, 0.9), self.device)
            # FP32 router decisions must not silently use TF32 matmul.
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
        return torch

    def _finish_loading(self):
        self.model.eval()
        for parameter in self.model.parameters():
            if parameter.is_floating_point() and parameter.dtype != self._torch.float32:
                raise ValueError("Model parameters must remain FP32")
        self.eos_ids = {self.tok.eos_token_id}
        configured = getattr(self.model.generation_config, "eos_token_id", None)
        self.eos_ids.update(configured if isinstance(configured, list) else [configured])
        self.eos_ids.discard(None)
        if not self.eos_ids:
            raise ValueError("The model must define an EOS token")

    def complete(self, system: str, user: str, max_new: int = 64) -> dict:
        if type(max_new) is not int or not 1 <= max_new <= MAX_NEW_TOKENS:
            raise ValueError(f"max_new must be an integer in [1, {MAX_NEW_TOKENS}]")
        if not isinstance(system, str) or not isinstance(user, str):
            raise TypeError("system and user must be strings")
        ids = self._encode(system, user)
        if not ids or len(ids) + max_new > TOKEN_BUDGET:
            raise ValueError(f"prompt {len(ids)} + output {max_new} exceeds {TOKEN_BUDGET}")
        torch = self._torch
        if self.device.type == "cuda":
            torch.cuda.synchronize(self.device)
        started = time.perf_counter()
        output, past, reason = [], None, "length"
        inputs = torch.tensor([ids], dtype=torch.long, device=self.device)
        with torch.inference_mode():
            for index in range(max_new):
                result = self.model(input_ids=inputs, past_key_values=past, use_cache=True,
                                    return_dict=True, **self._last_logits)
                next_id = int(result.logits[0, -1].argmax().item())
                if next_id in self.eos_ids:
                    reason = "eos"
                    break
                output.append(next_id)
                if index + 1 < max_new:
                    past = result.past_key_values
                    if past is None:
                        raise RuntimeError("The model did not return its KV cache")
                    inputs = torch.tensor([[next_id]], dtype=torch.long, device=self.device)
        if self.device.type == "cuda":
            torch.cuda.synchronize(self.device)
        seconds = time.perf_counter() - started
        return {"raw": self.tok.decode(output, skip_special_tokens=False, clean_up_tokenization_spaces=False),
                "seconds": seconds, "prompt_tokens": len(ids), "output_tokens": len(output),
                "total_tokens": len(ids) + len(output), "finish_reason": reason,
                "dtype": "float32",
                "hardware": {
                    "gpu_name": torch.cuda.get_device_name(self.device) if self.device.type == "cuda" else None,
                    "cpu_model": _cpu_model(),
                },
                # Allocator peaks since model loading, NOT total process VRAM.
                "memory": {
                    "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(self.device) if self.device.type == "cuda" else None,
                    "cuda_peak_reserved_bytes": torch.cuda.max_memory_reserved(self.device) if self.device.type == "cuda" else None,
                }}


class HobbyRuntime(_TextRuntime):
    _last_logits = {"logits_to_keep": 1}

    def __init__(self, base_path, adapter_path, device: str = "cpu"):
        base, base_spec = _verify_artifacts(base_path, "base")
        adapter, adapter_spec = _verify_artifacts(adapter_path, "adapter")
        config = json.loads((adapter / "adapter_config.json").read_text())
        if (config.get("revision") != base_spec["revision"]
                or config.get("base_model_name_or_path") != base_spec["repository"]):
            raise ValueError("The adapter does not target the pinned base revision")
        torch = self._configure(device)
        from safetensors.torch import load_file
        from transformers import GPT2TokenizerFast

        model_class = _hobby_model_class(base)
        self.tok = GPT2TokenizerFast.from_pretrained(str(base), local_files_only=True, cache_dir=str(CACHE_DIR / "hf"))
        self.model = model_class.from_pretrained(
            str(base), local_files_only=True, use_safetensors=True, torch_dtype=torch.float32,
            device_map={"": str(self.device)}, low_cpu_mem_usage=True, attn_implementation="sdpa",
            cache_dir=str(CACHE_DIR / "hf"),
        )
        merged = _merge_lora(self.model, load_file(str(adapter / "adapter_model.safetensors"), device="cpu"), config, torch)
        # eval() already disables bias updates. Also freeze the release's explicit rate.
        for module in self.model.modules():
            if hasattr(module, "bias_update_rate"):
                module.bias_update_rate = 0.0
        self.identity = {"base": base_spec, "adapter": adapter_spec, "merged_modules": merged, "dtype": "float32"}
        self._finish_loading()

    def _encode(self, system: str, user: str) -> list[int]:
        # Exact training format, deliberately NOT the instruct tokenizer template.
        return self.tok(f"SYSTEM: {system}\nUSER: {user}\nASSISTANT:", add_special_tokens=False).input_ids


class SmallLocalRuntime(_TextRuntime):
    """Qwen2.5-0.5B text control, not a substitute for a visual CUA model.

    The caller supplies the same system, action allowlist, and semantic user
    state as HobbyRuntime. Only the model's native chat serialization differs.
    """
    _last_logits = {"num_logits_to_keep": 1}

    def __init__(self, model_path, device: str = "cpu"):
        path, spec = _verify_artifacts(model_path, "baseline")
        torch = self._configure(device)
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tok = AutoTokenizer.from_pretrained(str(path), local_files_only=True, trust_remote_code=False, cache_dir=str(CACHE_DIR / "hf"))
        self.model = AutoModelForCausalLM.from_pretrained(
            str(path), local_files_only=True, trust_remote_code=False, use_safetensors=True,
            torch_dtype=torch.float32, device_map={"": str(self.device)}, low_cpu_mem_usage=True,
            attn_implementation="sdpa", cache_dir=str(CACHE_DIR / "hf"),
        )
        self.identity = {"baseline": spec, "dtype": "float32"}
        self._finish_loading()

    def _encode(self, system: str, user: str) -> list[int]:
        return self.tok.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tokenize=True, add_generation_prompt=True,
        )


def main(argv=None) -> int:
    """Serve one loaded runtime over JSONL. Failures exit nonzero on stderr."""
    import argparse
    import contextlib
    import os

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--runtime", choices=("hobby", "local"), required=True)
    parser.add_argument("--base", type=Path, default=CACHE_DIR / "models" / "hobbylm-1B-instruct")
    parser.add_argument("--adapter", type=Path, default=CACHE_DIR / "models" / "hobbylm-1B-computer-use")
    parser.add_argument("--model", type=Path, default=CACHE_DIR / "models" / "Qwen2.5-0.5B-Instruct")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HOME"] = str(CACHE_DIR / "hf")
    # Model/library diagnostics must not corrupt the machine-readable protocol.
    with contextlib.redirect_stdout(sys.stderr):
        if args.runtime == "hobby":
            engine = HobbyRuntime(args.base, args.adapter, device=args.device)
        else:
            engine = SmallLocalRuntime(args.model, device=args.device)
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        seed = request.pop("seed", 1729)
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        engine._torch.manual_seed(seed)
        with contextlib.redirect_stdout(sys.stderr):
            result = engine.complete(**request)
        print(json.dumps(result, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
