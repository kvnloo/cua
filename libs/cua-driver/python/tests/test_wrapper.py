"""Tests for the cua-driver Python wrapper."""

import errno
import importlib.util
import io
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest


def load_wrapper_module() -> Any:
    module_path = Path(__file__).resolve().parents[1] / "src/cua_driver/wrapper.py"
    spec = importlib.util.spec_from_file_location("cua_driver_wrapper", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_get_binary_path():
    """Test that get_binary_path returns a valid path."""
    get_binary_path = load_wrapper_module().get_binary_path

    # This will raise FileNotFoundError if binary doesn't exist
    # In CI, we need to build the package first for this to pass
    try:
        binary_path = get_binary_path()
        assert binary_path.exists()
        assert binary_path.name in ("cua-driver", "cua-driver.exe")
    except FileNotFoundError:
        # Expected in development without building
        pytest.skip("Binary not bundled yet (run build_wheel.py first)")


@pytest.mark.skipif(sys.platform == "win32", reason="Unix executable-bit behavior")
@pytest.mark.parametrize(
    "chmod_error",
    [
        PermissionError(errno.EPERM, "Operation not permitted"),
        OSError(errno.EROFS, "Read-only file system"),
    ],
    ids=["EPERM", "EROFS"],
)
def test_already_executable_bundle_needs_no_runtime_chmod(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, chmod_error: OSError
) -> None:
    """An installer-owned executable still launches and preserves its exit status."""
    wrapper = load_wrapper_module()
    binary = tmp_path / "cua_driver" / "bin" / "cua-driver"
    binary.parent.mkdir(parents=True)
    binary.symlink_to(sys.executable)
    assert os.access(binary, os.X_OK)
    monkeypatch.setattr(wrapper, "__file__", str(binary.parent.parent / "wrapper.py"))

    chmod = Mock(side_effect=chmod_error)
    monkeypatch.setattr(wrapper.os, "chmod", chmod)

    assert wrapper.run_cua_driver(["-c", "import sys; sys.exit(42)"]) == 42
    chmod.assert_not_called()


def test_missing_bundle_still_reports_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wrapper = load_wrapper_module()
    monkeypatch.setattr(wrapper, "__file__", str(tmp_path / "cua_driver" / "wrapper.py"))
    chmod = Mock(side_effect=AssertionError("must not chmod a missing binary"))
    monkeypatch.setattr(wrapper.os, "chmod", chmod)

    with pytest.raises(FileNotFoundError, match="binary not found"):
        wrapper.get_binary_path()
    chmod.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="Unix executable-bit behavior")
def test_nonexecutable_bundle_keeps_repair_and_permission_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Simulated missing execute access still tries the existing repair."""
    wrapper = load_wrapper_module()
    binary = tmp_path / "cua_driver" / "bin" / "cua-driver"
    binary.parent.mkdir(parents=True)
    binary.symlink_to(sys.executable)
    monkeypatch.setattr(wrapper, "__file__", str(binary.parent.parent / "wrapper.py"))
    monkeypatch.setattr(wrapper.os, "access", Mock(return_value=False))

    chmod = Mock(return_value=None)
    monkeypatch.setattr(wrapper.os, "chmod", chmod)
    assert wrapper.get_binary_path() == binary
    chmod.assert_called_once_with(binary, 0o755)

    denied = PermissionError("repair is forbidden")
    chmod.reset_mock(side_effect=True)
    chmod.side_effect = denied
    with pytest.raises(PermissionError) as captured:
        wrapper.get_binary_path()
    assert captured.value is denied
    chmod.assert_called_once_with(binary, 0o755)


def test_windows_binary_lookup_never_chmods(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wrapper = load_wrapper_module()
    binary = tmp_path / "cua_driver" / "bin" / "cua-driver.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"fixture")
    monkeypatch.setattr(wrapper, "__file__", str(binary.parent.parent / "wrapper.py"))
    monkeypatch.setattr(wrapper.sys, "platform", "win32")
    chmod = Mock(side_effect=AssertionError("Windows must not chmod"))
    monkeypatch.setattr(wrapper.os, "chmod", chmod)

    assert wrapper.get_binary_path() == binary
    chmod.assert_not_called()


def test_run_cua_driver_version(monkeypatch):
    """Test running cua-driver --version through the wrapper."""
    wrapper = load_wrapper_module()
    get_binary_path, run_cua_driver = wrapper.get_binary_path, wrapper.run_cua_driver

    try:
        binary_path = get_binary_path()
    except FileNotFoundError:
        pytest.skip("Binary not bundled yet")

    # Run with --version
    exit_code = run_cua_driver(["--version"])
    assert exit_code == 0


def test_wrapper_preserves_exit_code():
    """Test that the wrapper preserves the binary's exit code."""
    wrapper = load_wrapper_module()
    get_binary_path, run_cua_driver = wrapper.get_binary_path, wrapper.run_cua_driver

    try:
        binary_path = get_binary_path()
    except FileNotFoundError:
        pytest.skip("Binary not bundled yet")

    # Invalid command should return non-zero
    exit_code = run_cua_driver(["--this-flag-does-not-exist"])
    assert exit_code != 0


def test_subprocess_args(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that subprocess is called with correct arguments."""
    wrapper = load_wrapper_module()
    mock_binary = Path("/fake/path/cua-driver")
    mock_run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(wrapper, "get_binary_path", Mock(return_value=mock_binary))
    monkeypatch.setattr(wrapper.subprocess, "run", mock_run)

    stdin_path = tmp_path / "stdin"
    stdin_path.write_text("")
    with (
        stdin_path.open() as stdin,
        (tmp_path / "stdout").open("w") as stdout,
        (tmp_path / "stderr").open("w") as stderr,
    ):
        monkeypatch.setattr(sys, "stdin", stdin)
        monkeypatch.setattr(sys, "stdout", stdout)
        monkeypatch.setattr(sys, "stderr", stderr)

        wrapper.run_cua_driver(["mcp", "--help"])

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == [str(mock_binary), "mcp", "--help"]
        assert call_args[1]["stdin"] is stdin
        assert call_args[1]["stdout"] is stdout
        assert call_args[1]["stderr"] is stderr
        assert call_args[1]["env"]["CUA_DRIVER_INSTALL_CHANNEL"] == "python_package"


@pytest.mark.parametrize("stream_name", ["stdin", "stdout", "stderr"])
def test_subprocess_falls_back_for_fileno_less_stdio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stream_name: str
) -> None:
    """A captured stream falls back without changing usable descriptors."""
    wrapper = load_wrapper_module()
    monkeypatch.setattr(wrapper, "get_binary_path", Mock(return_value=Path(sys.executable)))

    stdin_path = tmp_path / "stdin"
    stdin_path.write_text("")
    with (
        stdin_path.open() as stdin,
        (tmp_path / "stdout").open("w") as stdout,
        (tmp_path / "stderr").open("w") as stderr,
    ):
        streams = {"stdin": stdin, "stdout": stdout, "stderr": stderr}
        streams[stream_name] = io.StringIO()
        for name, stream in streams.items():
            monkeypatch.setattr(sys, name, stream)

        exit_code = wrapper.run_cua_driver(["-c", "pass"])

        assert exit_code == 0


@pytest.mark.parametrize("descriptor", [None, -1, "1"])
def test_stdio_falls_back_for_invalid_fileno(descriptor: object) -> None:
    """A non-descriptor fileno result is not forwarded to subprocess."""
    wrapper = load_wrapper_module()
    stream = Mock()
    stream.fileno.return_value = descriptor

    assert wrapper._stdio_with_fileno(stream) is None


def test_subprocess_preserves_exact_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stdio fallback does not change the child's exit-code contract."""
    wrapper = load_wrapper_module()
    monkeypatch.setattr(
        wrapper, "get_binary_path", Mock(return_value=Path("/fake/path/cua-driver"))
    )
    monkeypatch.setattr(wrapper.subprocess, "run", Mock(return_value=Mock(returncode=42)))

    assert wrapper.run_cua_driver(["--version"]) == 42


def test_subprocess_preserves_explicit_install_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An update/install caller's bounded channel takes precedence."""
    wrapper = load_wrapper_module()
    mock_run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(
        wrapper, "get_binary_path", Mock(return_value=Path("/fake/path/cua-driver"))
    )
    monkeypatch.setattr(wrapper.subprocess, "run", mock_run)
    monkeypatch.setenv("CUA_DRIVER_INSTALL_CHANNEL", "update_apply")

    wrapper.run_cua_driver(["--version"])

    child_env = mock_run.call_args.kwargs["env"]
    assert child_env["CUA_DRIVER_INSTALL_CHANNEL"] == "update_apply"
    assert os.environ["CUA_DRIVER_INSTALL_CHANNEL"] == "update_apply"


def test_keyboard_interrupt_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that KeyboardInterrupt returns exit code 130."""
    wrapper = load_wrapper_module()
    monkeypatch.setattr(
        wrapper, "get_binary_path", Mock(return_value=Path("/fake/path/cua-driver"))
    )
    monkeypatch.setattr(wrapper.subprocess, "run", Mock(side_effect=KeyboardInterrupt()))

    exit_code = wrapper.run_cua_driver(["mcp"])
    assert exit_code == 130
