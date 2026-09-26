"""Tests for cua-driver wheel build helpers."""

import importlib.util
from pathlib import Path


def load_build_wheel_module():
    module_path = Path(__file__).resolve().parents[1] / "build_wheel.py"
    spec = importlib.util.spec_from_file_location("build_wheel", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_wheel_tags_are_platform_specific():
    build_wheel = load_build_wheel_module()

    assert build_wheel.get_wheel_tag("darwin", "universal") == "py3-none-macosx_13_0_universal2"
    assert build_wheel.get_wheel_tag("linux", "x86_64") == "py3-none-manylinux_2_31_x86_64"
    assert build_wheel.get_wheel_tag("linux", "arm64") == "py3-none-manylinux_2_31_aarch64"
    assert build_wheel.get_wheel_tag("windows", "x86_64") == "py3-none-win_amd64"
    assert build_wheel.get_wheel_tag("windows", "arm64") == "py3-none-win_arm64"


def test_release_archives_include_cli_and_uniffi_library():
    build_wheel = load_build_wheel_module()

    _, darwin_files = build_wheel.get_release_url("1.2.3", "darwin", "universal")
    _, linux_files = build_wheel.get_release_url("1.2.3", "linux", "x86_64")
    _, windows_files = build_wheel.get_release_url("1.2.3", "windows", "arm64")

    assert darwin_files == ["cua-driver", "libcua_driver_sdk.dylib"]
    assert linux_files == ["cua-driver", "libcua_driver_sdk.so"]
    assert windows_files == [
        "cua-driver.exe",
        "cua-driver-uia.exe",
        "cua_driver_sdk.dll",
    ]


def test_license_metadata_stays_legacy_upload_compatible():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject_text = pyproject.read_text()

    assert 'license = { text = "MIT" }' in pyproject_text
    assert 'license = "MIT"' not in pyproject_text


def test_release_download_uses_network_timeout(monkeypatch):
    """A stalled release download must fail fast instead of hanging the build."""
    import pytest

    build_wheel = load_build_wheel_module()
    seen = {}

    def fake_urlopen(url, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("no network in test")

    monkeypatch.setattr(build_wheel.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="Failed to download"):
        build_wheel.download_file("https://example.invalid/x.tar.gz", Path("/tmp/x"), "abc")

    assert seen.get("timeout") == build_wheel._NETWORK_TIMEOUT_SECS


def test_checksums_fetch_uses_network_timeout(monkeypatch):
    """A stalled checksums fetch must fail fast instead of hanging the build."""
    import pytest

    build_wheel = load_build_wheel_module()
    seen = {}

    def fake_urlopen(url, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("no network in test")

    monkeypatch.setattr(build_wheel.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="Failed to fetch or parse checksums"):
        build_wheel.get_expected_sha256("0.0.0", "x.tar.gz")

    assert seen.get("timeout") == build_wheel._NETWORK_TIMEOUT_SECS
