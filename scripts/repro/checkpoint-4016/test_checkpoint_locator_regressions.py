"""Real CPU save/load checks for canonical and historical checkpoint locators."""
from pathlib import Path
import shutil

import torch

from cua_s1.checkpoint import load_checkpoint_files, save_checkpoint_files


def save(location: Path, value: float = 7.0):
    return save_checkpoint_files(
        location, {"weight": torch.full((2, 3), value, dtype=torch.float32)},
        {"width": 3}, {"value": value},
    )


def assert_loads(location: Path, value: float = 7.0):
    state, config, metadata = load_checkpoint_files(location)
    assert set(state) == {"weight"}
    assert torch.equal(state["weight"], torch.full((2, 3), value, dtype=torch.float32))
    assert config == {"width": 3}
    assert metadata == {"value": value}


def put_stale_siblings(root: Path, *, json_sibling: bool, tensor_sibling: bool):
    old_weights, old_config = save(root / "older", value=-2.0)
    directory = root / "checkpoint"
    directory.mkdir()
    if json_sibling:
        shutil.copyfile(old_config, directory / "model.json")
    if tensor_sibling:
        shutil.copyfile(old_weights, directory / "config.safetensors")
    return directory


def test_clean_directory_and_both_returned_paths_roundtrip(tmp_path):
    directory = tmp_path / "checkpoint"
    weights, config = save(directory)
    for location in (directory, weights, config):
        assert_loads(location)


def test_custom_stem_retains_bidirectional_resolution(tmp_path):
    weights, config = save(tmp_path / "custom.safetensors")
    assert config == tmp_path / "custom.json"
    assert_loads(weights)
    assert_loads(config)


def test_unrelated_siblings_do_not_change_roundtrip(tmp_path):
    directory = tmp_path / "checkpoint"
    directory.mkdir()
    (directory / "notes.json").write_text("{}")
    weights, config = save(directory)
    assert_loads(weights)
    assert_loads(config)


def test_legacy_model_json_pair_without_canonical_config_still_loads(tmp_path):
    weights, config = save(tmp_path / "named.safetensors")
    weights.rename(tmp_path / "model.safetensors")
    config.rename(tmp_path / "model.json")
    assert not (tmp_path / "config.json").exists()
    assert_loads(tmp_path / "model.safetensors")
    assert_loads(tmp_path / "model.json")


def test_legacy_config_pair_without_canonical_weights_still_loads(tmp_path):
    weights, config = save(tmp_path / "config.safetensors")
    assert not (tmp_path / "model.safetensors").exists()
    assert_loads(weights)
    assert_loads(config)


def test_directory_locator_ignores_both_stale_same_stem_siblings(tmp_path):
    directory = put_stale_siblings(tmp_path, json_sibling=True, tensor_sibling=True)
    save(directory)
    assert_loads(directory)


def test_repeated_directory_save_reads_latest_checkpoint(tmp_path):
    directory = tmp_path / "checkpoint"
    save(directory, value=-2.0)
    weights, config = save(directory)
    for location in (directory, weights, config):
        assert_loads(location)


def test_returned_weights_path_ignores_stale_model_json(tmp_path):
    directory = put_stale_siblings(tmp_path, json_sibling=True, tensor_sibling=False)
    weights, _ = save(directory)
    assert_loads(directory)
    assert_loads(weights)


def test_returned_config_path_ignores_stale_config_safetensors(tmp_path):
    directory = put_stale_siblings(tmp_path, json_sibling=False, tensor_sibling=True)
    _, config = save(directory)
    assert_loads(directory)
    assert_loads(config)
