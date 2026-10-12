"""Exercise the real Windows sampler logic with CPU-only process/token fixtures."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/ci/windows/run-jev-use-elevated-autostart.ps1"
PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(PWSH is None, reason="PowerShell 7 is required")

# Parse, but never execute, the platform entrypoint. Run only its actual sampler
# scriptblock with synthetic process enumeration, tokens, and sleep. No native
# process enumeration, token API, Driver, browser, or scheduled task is invoked.
PROBE = r"""
param([string]$ScriptPath, [string]$CasePath)
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw "script parse errors: $parseErrors" }
$command = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.CommandAst] -and
    $node.GetCommandName() -eq "Start-ThreadJob"
}, $true)
$worker = @($command.CommandElements | Where-Object {
    $_ -is [System.Management.Automation.Language.ScriptBlockExpressionAst]
})[0].ScriptBlock.GetScriptBlock()
$case = Get-Content -Raw -LiteralPath $CasePath | ConvertFrom-Json
$script:snapshotIndex = 0
$state = @{ Stop = $false; Browsers = [System.Collections.ArrayList]::new() }

class CuaTokenPosture {
    static [object] Read([int]$processId) {
        return [pscustomobject]@{
            Pid = $processId
            IntegrityRid = $(if ($processId -eq 999) { 0x3000 } else { 0x2000 })
            AdministratorsEnabled = $false
        }
    }
}
function Get-CimInstance {
    param($ClassName, $Filter, $ErrorAction)
    if ($Filter -like 'ProcessId=*') {
        return [pscustomobject]@{ Name = 'cua-driver.exe'; CommandLine = 'mock mcp' }
    }
    foreach ($process in $case.snapshots[$script:snapshotIndex]) {
        if ($process.PSObject.Properties['CreationDate'] -and
            $process.CreationDate -is [string] -and $process.CreationDate.StartsWith('2026-')) {
            $process.CreationDate = [datetime]::Parse($process.CreationDate).ToUniversalTime()
        }
        $process
    }
}
function Start-Sleep {
    param($Milliseconds)
    $script:snapshotIndex++
    if ($script:snapshotIndex -ge $case.snapshots.Count) { $state.Stop = $true }
}

$failure = $null
try { & $worker $state } catch { $failure = $_.Exception.Message }
[pscustomobject]@{
    error = $failure
    mains = @($state.Browsers | Where-Object { $_.Main -and $null -ne $_.Posture }).Count
    records = $state.Browsers.Count
} | ConvertTo-Json -Compress
"""


def process(pid, created="2026-10-01T10:00:00Z", *, main=True):
    return {
        "ProcessId": pid,
        "ParentProcessId": 999 if main else 7496,
        "Name": "chrome.exe",
        "CommandLine": "chrome.exe --user-data-dir=fixture" + ("" if main else " --type=renderer"),
        "CreationDate": created,
    }


def sample(tmp_path, snapshots):
    probe = tmp_path / "probe.ps1"
    probe.write_text(PROBE, encoding="utf-8")
    case = tmp_path / "case.json"
    case.write_text(json.dumps({"snapshots": snapshots}), encoding="utf-8")
    result = subprocess.run(
        [PWSH, "-NoLogo", "-NoProfile", "-File", str(probe), str(SCRIPT), str(case)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "snapshots,records",
    [
        (
            [
                [process(7496), process(2720, main=False)],
                [process(2720, "2026-10-01T10:00:01Z")],
            ],
            3,
        ),
        ([[process(7496)], [process(7496, "2026-10-01T10:00:01Z")]], 2),
        ([[process(7496), process(2720)], [process(7496), process(2720)]], 2),
        ([[process(7496), process(2720)]], 2),
    ],
    ids=[
        "recycled-child-pid",
        "recycled-main-pid",
        "repeated-samples",
        "distinct-pids",
    ],
)
def test_sampler_tracks_process_generations(tmp_path, snapshots, records):
    assert sample(tmp_path, snapshots) == {
        "error": None,
        "mains": 2,
        "records": records,
    }


@pytest.mark.parametrize("creation", [None, "", "unavailable"])
def test_sampler_rejects_unavailable_creation_time(tmp_path, creation):
    result = sample(tmp_path, [[process(7496, creation)]])
    assert (
        result["error"]
        == "cannot identify isolated browser process 7496: creation time unavailable"
    )
    assert result["records"] == 0


def test_sampler_rejects_missing_creation_property(tmp_path):
    row = process(7496)
    del row["CreationDate"]
    assert sample(tmp_path, [[row]])["error"] == (
        "cannot identify isolated browser process 7496: creation time unavailable"
    )


def test_sampler_does_not_trust_a_seen_pid_with_missing_creation_time(tmp_path):
    result = sample(tmp_path, [[process(7496), process(2720)], [process(7496, None)]])
    assert (
        result["error"]
        == "cannot identify isolated browser process 7496: creation time unavailable"
    )
    assert result["mains"] == 2
    assert result["records"] == 2


def test_sampler_errors_stop_the_outer_proof(tmp_path):
    # Execute the entrypoint's actual Receive-Job pipeline against a failed
    # harmless thread job. A missing-identity error must stop the proof even
    # when earlier samples had already met its process-count assertion.
    script = r"""
param([string]$ScriptPath)
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref]$tokens, [ref]$errors)
$receive = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.CommandAst] -and
    $node.GetCommandName() -eq 'Receive-Job'
}, $true).Parent.Extent.Text
$sampler = Start-ThreadJob { throw 'identity fixture unavailable' }
$sampler | Wait-Job | Out-Null
$stopped = $false
try { & ([scriptblock]::Create($receive)) } catch { $stopped = $true }
$sampler | Remove-Job -Force
$stopped | ConvertTo-Json -Compress
"""
    probe = tmp_path / "receive.ps1"
    probe.write_text(script, encoding="utf-8")
    result = subprocess.run(
        [PWSH, "-NoLogo", "-NoProfile", "-File", str(probe), str(SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(result.stdout) is True
