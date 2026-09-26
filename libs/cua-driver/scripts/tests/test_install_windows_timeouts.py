"""Windows installer network-timeout guards.

The bash (install.sh, _install-rust.sh) and Python (build_wheel.py)
installers bound every network fetch with an explicit timeout so a stalled
connection fails fast instead of hanging the install. The Windows path
(install.ps1, _install-common.psm1) makes the same network calls via
Invoke-WebRequest / Invoke-RestMethod, so the metadata-fetch call sites
must carry -TimeoutSec as well.

The large-asset zip download in Get-ReleaseZip is deliberately excluded:
it already relies on PowerShell's built-in per-request bound, and a short
hard timeout would kill slow-but-alive downloads. The small metadata
fetches (module bootstrap, GitHub API pages) have no such excuse.

No pwsh on Linux CI hosts, so these checks are static: they assert the
flag is present on the exact call sites. A missing flag is the regression.
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent

# (file, regex matching the call site) for the metadata fetches that must
# carry -TimeoutSec. The zip download in Get-ReleaseZip is excluded on
# purpose (see module docstring).
REQUIRED_TIMEOUT_SITES = [
    (
        "install.ps1",
        re.compile(r"^\s*\$body = Invoke-RestMethod -Uri \$Url -UseBasicParsing\b"),
        "module bootstrap fetch",
    ),
    (
        "install.ps1",
        re.compile(
            r"^\s*\$batch = Invoke-RestMethod -Uri \$uri "
            r"-Headers \(Get-GitHubApiHeaders\) -UseBasicParsing\b"
        ),
        "GitHub API pagination fetch",
    ),
    (
        "_install-common.psm1",
        re.compile(r"^\s*\$body = Invoke-RestMethod -Uri \$Url -UseBasicParsing\b"),
        "shared-module bootstrap fetch",
    ),
]


def _source_lines(filename: str) -> list[str]:
    return (SCRIPTS_DIR / filename).read_text(encoding="utf-8").splitlines()


def test_windows_metadata_fetches_bound_network_waits() -> None:
    """Every Windows installer metadata fetch carries -TimeoutSec."""
    for filename, pattern, label in REQUIRED_TIMEOUT_SITES:
        matches = [ln for ln in _source_lines(filename) if pattern.search(ln)]
        assert matches, f"{filename}: {label} call site not found (pattern drifted?)"
        for line in matches:
            assert "-TimeoutSec" in line, (
                f"{filename}: {label} has no -TimeoutSec — "
                f"a stalled connection hangs the install: {line.strip()}"
            )
            value = int(re.search(r"-TimeoutSec\s+(\d+)", line).group(1))
            assert value > 0, f"{filename}: {label} has a non-positive -TimeoutSec"


def test_windows_zip_download_still_present_and_excluded() -> None:
    """Pin the deliberate exclusion: the zip download stays flag-free."""
    lines = _source_lines("install.ps1")
    download = [
        ln
        for ln in lines
        if re.search(r"^\s*Invoke-WebRequest -Uri \$url -OutFile \$zipPath\b", ln)
    ]
    assert len(download) == 1, "Get-ReleaseZip download call site moved or duplicated"
    assert "-TimeoutSec" not in download[0], (
        "zip download unexpectedly gained -TimeoutSec; revisit the exclusion "
        "rationale in the module docstring before tightening it"
    )
