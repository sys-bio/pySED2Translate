# Create a Python 3.13 virtual environment with every simulator backend installed (Windows).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1 [-Venv .venv]
# Requires uv (https://docs.astral.sh/uv/).  Run from the pySED2Translate directory.
# NOTE: written alongside the Linux script but not yet run on Windows.
param([string]$Venv = ".venv")
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSScriptRoot
uv python install 3.13
uv venv --python 3.13 $Venv
$Py = Join-Path $Venv "Scripts\python.exe"
uv pip install --python $Py -r (Join-Path $Here "requirements.txt")
$Wheel = Get-ChildItem -Path $Here -Filter "libsed2-*.whl" | Sort-Object Name | Select-Object -Last 1
if ($Wheel) {
    uv pip install --python $Py --force-reinstall --no-deps $Wheel.FullName
} else {
    Write-Host "NOTE: no libsed2-*.whl found in $Here; download one from https://github.com/sys-bio/SED2/releases/"
}
Write-Host "Done.  Activate with:  $Venv\Scripts\Activate.ps1   then run:  python scripts\smoke_test.py"
