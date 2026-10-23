"""Hermetic runtime behavior. No release weights, network, CUDA, or desktop.

Run with the isolated runtime environment. Tiny tensor operations exercise the
actual merge and decoder loop. The fake model only supplies controlled logits.
"""
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
_RUNTIME = Path(__file__).parents[1] / "examples" / "hobbylm_eval" / "runtime.py"
_spec = importlib.util.spec_from_file_location("hobbylm_eval_runtime_tests", _RUNTIME)
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)


class Tokenizer:
    eos_token_id = 9

    def __init__(self, ids=None):
        self.ids = [1, 2, 3] if ids is None else ids
        self.calls = []

    def __call__(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return types.SimpleNamespace(input_ids=self.ids)

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.ids

    def decode(self, ids, **kwargs):
        return " ".join(str(token) for token in ids)


class LogitModel:
    def __init__(self, tokens, cache=True):
        self.tokens = iter(tokens)
        self.calls = []
        self.cache = cache

    def __call__(self, **kwargs):
        assert torch.is_inference_mode_enabled()
        self.calls.append(kwargs)
        logits = torch.zeros(1, 1, 10)
        logits[0, 0, next(self.tokens)] = 1
        return types.SimpleNamespace(logits=logits, past_key_values=object() if self.cache else None)


def decoder(cls=runtime.HobbyRuntime, tokens=(4, 5, 9), ids=None, cache=True):
    instance = object.__new__(cls)
    instance._torch = torch
    instance.device = torch.device("cpu")
    instance.tok = Tokenizer(ids)
    instance.model = LogitModel(tokens, cache)
    instance.eos_ids = {9}
    return instance


def test_exact_native_training_prompt():
    instance = decoder()
    assert instance._encode("allowed actions", "request\nstate") == [1, 2, 3]
    assert instance.tok.calls == [("SYSTEM: allowed actions\nUSER: request\nstate\nASSISTANT:", {"add_special_tokens": False})]


def test_baseline_preserves_identical_system_and_semantic_state():
    instance = decoder(runtime.SmallLocalRuntime)
    instance._encode("same system and allowlist", "same request and state")
    assert instance.tok.calls == [([
        {"role": "system", "content": "same system and allowlist"},
        {"role": "user", "content": "same request and state"},
    ], {"tokenize": True, "add_generation_prompt": True})]


@pytest.mark.parametrize("cls,logit_key", [(runtime.HobbyRuntime, "logits_to_keep"), (runtime.SmallLocalRuntime, "num_logits_to_keep")])
def test_greedy_decoder_prefills_once_and_reuses_kv_cache(cls, logit_key):
    instance = decoder(cls)
    result = instance.complete("system", "state", max_new=4)
    assert result["raw"] == "4 5"
    assert result["prompt_tokens"] == 3
    assert result["output_tokens"] == 2
    assert result["total_tokens"] == 5
    assert result["finish_reason"] == "eos"
    assert result["seconds"] >= 0
    calls = instance.model.calls
    assert [call["input_ids"].tolist() for call in calls] == [[[1, 2, 3]], [[4]], [[5]]]
    assert calls[0]["past_key_values"] is None
    assert calls[1]["past_key_values"] is not None
    assert calls[2]["past_key_values"] is not calls[1]["past_key_values"]
    assert all(call["use_cache"] and call[logit_key] == 1 for call in calls)


def test_length_bound_does_not_run_an_extra_forward():
    instance = decoder(tokens=(4, 5))
    result = instance.complete("s", "u", max_new=2)
    assert result["finish_reason"] == "length"
    assert result["output_tokens"] == 2
    assert len(instance.model.calls) == 2


def test_eos_first_produces_empty_output():
    instance = decoder(tokens=(9,))
    result = instance.complete("s", "u")
    assert result["raw"] == ""
    assert result["output_tokens"] == 0
    assert len(instance.model.calls) == 1


def test_calls_do_not_share_conversation_cache():
    instance = decoder(tokens=(9, 9))
    instance.complete("s", "one")
    instance.complete("s", "two")
    assert all(call["past_key_values"] is None for call in instance.model.calls)


@pytest.mark.parametrize("max_new", [0, -1, 65, True, 1.5, "2"])
def test_rejects_invalid_generation_budget_before_forward(max_new):
    instance = decoder()
    with pytest.raises(ValueError, match="max_new must be an integer"):
        instance.complete("s", "u", max_new=max_new)
    assert not instance.model.calls


def test_enforces_combined_1024_token_budget_without_truncation():
    instance = decoder(ids=[1] * 1023, tokens=(4,))
    with pytest.raises(ValueError, match="prompt 1023 \\+ output 2 exceeds 1024"):
        instance.complete("s", "u", max_new=2)
    assert not instance.model.calls
    assert instance.complete("s", "u", max_new=1)["total_tokens"] == 1024


def test_missing_kv_cache_fails_instead_of_recomputing():
    instance = decoder(cache=False)
    with pytest.raises(RuntimeError, match="did not return its KV cache"):
        instance.complete("s", "u", max_new=2)


def lora_fixture():
    model = torch.nn.Module()
    model.q_proj = torch.nn.Linear(3, 2, bias=False)
    with torch.no_grad():
        model.q_proj.weight.zero_()
    state = {
        "base_model.model.q_proj.lora_A.weight": torch.tensor([[1.0, 2.0, 3.0]]),
        "base_model.model.q_proj.lora_B.weight": torch.tensor([[2.0], [4.0]]),
    }
    config = {"peft_type": "LORA", "task_type": "CAUSAL_LM", "bias": "none", "r": 1,
              "lora_alpha": 2, "target_modules": sorted(runtime._TARGETS)}
    return model, state, config


def test_merges_peft_safetensors_orientation_and_alpha_rank_scale():
    model, state, config = lora_fixture()
    assert runtime._merge_lora(model, state, config, torch) == 1
    torch.testing.assert_close(model.q_proj.weight, torch.tensor([[4.0, 8.0, 12.0], [8.0, 16.0, 24.0]]))


@pytest.mark.parametrize("defect,message", [
    ("unknown", "Unexpected LoRA tensor"), ("missing", "Incomplete LoRA pair"),
    ("shape", "LoRA shape mismatch"), ("nan", "Non-finite LoRA tensor"),
    ("dtype", "requires FP32"), ("target", "cover exactly"),
])
def test_rejects_unsafe_adapter_before_weight_mutation(defect, message):
    model, state, config = lora_fixture()
    a = "base_model.model.q_proj.lora_A.weight"
    b = "base_model.model.q_proj.lora_B.weight"
    if defect == "unknown":
        state["executable"] = torch.ones(1)
    elif defect == "missing":
        del state[b]
    elif defect == "shape":
        state[a] = torch.ones(1, 4)
    elif defect == "nan":
        state[a][0, 0] = float("nan")
    elif defect == "dtype":
        state[a] = state[a].half()
    else:
        state = {key.replace("q_proj", "v_proj"): value for key, value in state.items()}
    with pytest.raises(ValueError, match=message):
        runtime._merge_lora(model, state, config, torch)
    assert not bool(model.q_proj.weight.any())


def test_rejects_overflow_in_merged_weights():
    model, state, config = lora_fixture()
    state["base_model.model.q_proj.lora_A.weight"].fill_(torch.finfo(torch.float32).max)
    with pytest.raises(ValueError, match="Non-finite merged LoRA weight"):
        runtime._merge_lora(model, state, config, torch)
    assert not bool(model.q_proj.weight.any())


@pytest.mark.parametrize("option,value", [("fan_in_fan_out", True), ("use_dora", True), ("use_rslora", True), ("bias", "all"), ("r", 0)])
def test_rejects_unsupported_lora_recipe(option, value):
    model, state, config = lora_fixture()
    config[option] = value
    with pytest.raises(ValueError, match="Unsupported LoRA|Invalid LoRA"):
        runtime._merge_lora(model, state, config, torch)


def test_artifact_hash_size_and_unpinned_file_checks(tmp_path, monkeypatch):
    directory = tmp_path / "model"
    directory.mkdir()
    artifact = directory / "config.json"
    artifact.write_bytes(b"good")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"models": {"base": {"files": {"config.json": {
        "sha256": hashlib.sha256(b"good").hexdigest(), "bytes": 4,
    }}}}}))
    monkeypatch.setattr(runtime, "_MANIFEST", manifest)
    assert runtime._verify_artifacts(directory, "base")[0] == directory
    artifact.write_bytes(b"evil")
    with pytest.raises(ValueError, match="Artifact SHA256 mismatch"):
        runtime._verify_artifacts(directory, "base")
    artifact.write_bytes(b"shorter than expected")
    with pytest.raises(ValueError, match="Artifact size mismatch"):
        runtime._verify_artifacts(directory, "base")
    artifact.write_bytes(b"good")
    (directory / "adapter_config.json").write_text("{}")
    with pytest.raises(ValueError, match="Unpinned artifact"):
        runtime._verify_artifacts(directory, "base")


def test_constructor_uses_only_local_safetensors_and_fp32(tmp_path, monkeypatch):
    model, state, config = lora_fixture()
    config.update(revision="pinned", base_model_name_or_path="base/repo")
    (tmp_path / "adapter_config.json").write_text(json.dumps(config))
    model.generation_config = types.SimpleNamespace(eos_token_id=9)
    loads = []

    def from_pretrained(path, **kwargs):
        loads.append((path, kwargs))
        return model

    tokenizer = Tokenizer()
    tokenizer_loads = []

    def tokenizer_from_pretrained(path, **kwargs):
        tokenizer_loads.append(kwargs)
        return tokenizer

    monkeypatch.setattr(runtime, "_verify_artifacts", lambda path, role: (tmp_path, {"revision": "pinned", "repository": "base/repo"}))
    monkeypatch.setattr(runtime, "_hobby_model_class", lambda path: types.SimpleNamespace(from_pretrained=from_pretrained))
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.GPT2TokenizerFast = types.SimpleNamespace(from_pretrained=tokenizer_from_pretrained)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    import safetensors.torch
    monkeypatch.setattr(safetensors.torch, "load_file", lambda path, device: state)
    instance = runtime.HobbyRuntime(tmp_path, tmp_path)
    assert not model.training
    assert instance.identity["merged_modules"] == 1
    assert loads[0][1]["local_files_only"] is True
    assert loads[0][1]["use_safetensors"] is True
    assert loads[0][1]["torch_dtype"] == torch.float32
    assert loads[0][1]["device_map"] == {"": "cpu"}
    assert "trust_remote_code" not in loads[0][1]
    assert tokenizer_loads[0]["local_files_only"] is True
    assert all(parameter.dtype == torch.float32 for parameter in model.parameters())


def test_baseline_loader_disables_remote_code(tmp_path, monkeypatch):
    model, _, _ = lora_fixture()
    model.generation_config = types.SimpleNamespace(eos_token_id=[8, 9])
    loads = []

    def model_load(path, **kwargs):
        loads.append(kwargs)
        return model

    def tokenizer_load(path, **kwargs):
        loads.append(kwargs)
        return Tokenizer()

    monkeypatch.setattr(runtime, "_verify_artifacts", lambda path, role: (tmp_path, {"revision": "pinned"}))
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoModelForCausalLM = types.SimpleNamespace(from_pretrained=model_load)
    fake_transformers.AutoTokenizer = types.SimpleNamespace(from_pretrained=tokenizer_load)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    instance = runtime.SmallLocalRuntime(tmp_path)
    assert instance.eos_ids == {8, 9}
    assert all(call["local_files_only"] is True and call["trust_remote_code"] is False for call in loads)
    assert loads[1]["torch_dtype"] == torch.float32
    assert loads[1]["use_safetensors"] is True


def test_audited_import_ignores_unverified_bytecode(tmp_path, monkeypatch):
    (tmp_path / "configuration_hobbylm.py").write_text("VALUE = 7\n")
    (tmp_path / "modeling_hobbylm.py").write_text(
        "from .configuration_hobbylm import VALUE\n"
        "class HobbyLMForCausalLM:\n"
        "    value = VALUE\n"
    )
    from importlib.machinery import SourceFileLoader

    def reject_cached_loader(*args):
        raise AssertionError("Audited source must not execute through a bytecode cache")

    monkeypatch.setattr(SourceFileLoader, "exec_module", reject_cached_loader)
    try:
        cls = runtime._hobby_model_class(tmp_path)
        assert cls.value == 7
    finally:
        prefix = "_cua_audited_hobbylm_" + hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]
        for name in list(sys.modules):
            if name == prefix or name.startswith(prefix + "."):
                del sys.modules[name]


def test_cuda_allocator_cap_is_at_most_five_decimal_gigabytes(monkeypatch):
    calls = []
    total = 12 * 1024**3
    fake_torch = types.ModuleType("torch")
    fake_torch.device = torch.device
    fake_torch.cuda = types.SimpleNamespace(
        is_available=lambda: True,
        get_device_properties=lambda device: types.SimpleNamespace(total_memory=total),
        set_per_process_memory_fraction=lambda fraction, device: calls.append((fraction, device)),
    )
    fake_torch.backends = types.SimpleNamespace(
        cuda=types.SimpleNamespace(matmul=types.SimpleNamespace(allow_tf32=True)),
        cudnn=types.SimpleNamespace(allow_tf32=True),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    instance = object.__new__(runtime.HobbyRuntime)
    instance._configure("cuda:0")
    assert runtime.GPU_LIMIT_BYTES == 5_000_000_000
    assert calls[0][0] * total <= 5_000_000_000
    assert calls[0][1] == torch.device("cuda:0")
    assert fake_torch.backends.cuda.matmul.allow_tf32 is False


@pytest.mark.parametrize("variant", ["hobby", "local"])
def test_jsonl_cli_loads_once_preserves_requests_and_applies_seeds(variant, monkeypatch, capsys):
    import io
    import os

    requests, seeds, loads = [], [], []

    class Engine:
        def __init__(self, *args, **kwargs):
            loads.append((args, kwargs))
            self._torch = types.SimpleNamespace(manual_seed=seeds.append)
            print("loader diagnostic")

        def complete(self, **request):
            requests.append(request)
            print("model diagnostic")
            return {"raw": "DONE", "seconds": 0.5, "prompt_tokens": 3, "output_tokens": 1}

    monkeypatch.setattr(runtime, "HobbyRuntime", Engine)
    monkeypatch.setattr(runtime, "SmallLocalRuntime", Engine)
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        '{"system":"same","user":"state1","max_new":32,"seed":40}\n'
        '{"system":"same","user":"state2","max_new":64}\n'
    ))
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HOME"):
        monkeypatch.setenv(name, "")
    assert runtime.main(["--runtime", variant, "--base", "/base", "--adapter", "/adapter",
                         "--model", "/baseline", "--device", "cpu"]) == 0
    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.out.splitlines()]
    assert lines[0] == {"ready": True}
    assert len(lines) == 3
    assert all(result["raw"] == "DONE" for result in lines[1:])
    assert len(loads) == 1
    assert loads[0][0] == ((Path("/base"), Path("/adapter")) if variant == "hobby" else (Path("/baseline"),))
    assert loads[0][1] == {"device": "cpu"}
    assert seeds == [40, 1729]
    assert requests == [{"system": "same", "user": "state1", "max_new": 32},
                        {"system": "same", "user": "state2", "max_new": 64}]
    assert "loader diagnostic" in captured.err and "model diagnostic" in captured.err
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["HF_HOME"] == str(runtime.CACHE_DIR / "hf")


def test_cpu_completion_reports_no_cuda_measurement():
    result = decoder(tokens=(9,)).complete("s", "u")
    assert result["memory"] == {"cuda_peak_allocated_bytes": None, "cuda_peak_reserved_bytes": None}


def test_completion_reports_cpu_model_and_fp32(monkeypatch):
    monkeypatch.setattr(runtime, "_cpu_model", lambda: "Unit CPU")
    result = decoder(tokens=(9,)).complete("s", "u")
    assert result["hardware"] == {"gpu_name": None, "cpu_model": "Unit CPU"}
    assert result["dtype"] == "float32"


def test_completion_queries_the_selected_cuda_device_not_the_current_device(monkeypatch):
    instance = decoder(tokens=(9,))
    instance.device = torch.device("cuda:1")
    queried = []

    def gpu_name(device):
        queried.append(device)
        return "Unit GPU 1"

    instance._torch = types.SimpleNamespace(
        long=torch.long,
        tensor=lambda values, **kwargs: torch.tensor(values, dtype=kwargs["dtype"]),
        inference_mode=torch.inference_mode,
        cuda=types.SimpleNamespace(
            synchronize=lambda device: None,
            get_device_name=gpu_name,
            max_memory_allocated=lambda device: 123,
            max_memory_reserved=lambda device: 456,
        ),
    )
    monkeypatch.setattr(runtime, "_cpu_model", lambda: "Unit CPU")
    result = instance.complete("s", "u", max_new=1)
    assert queried == [torch.device("cuda:1")]
    assert result["hardware"] == {"gpu_name": "Unit GPU 1", "cpu_model": "Unit CPU"}
    assert result["memory"] == {"cuda_peak_allocated_bytes": 123, "cuda_peak_reserved_bytes": 456}
