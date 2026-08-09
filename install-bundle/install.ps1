# S.A.R.A installer — Windows (PowerShell)
# Run from the S.A.R.A repo root:  powershell -ExecutionPolicy Bypass -File install-bundle\install.ps1
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$Py = if ($env:PYTHON) { $env:PYTHON } else { "python" }
Write-Host "== S.A.R.A installer =="
Write-Host "   repo  : $RepoRoot"
Write-Host "   python: $(& $Py --version 2>&1)"

# 0) Bootstrap core files from the bundled src/ if missing.
$SrcBundle = Join-Path $RepoRoot "install-bundle\src"
if (-not (Test-Path (Join-Path $RepoRoot "sara.py")) -or -not (Test-Path (Join-Path $RepoRoot "sara")) -or -not (Test-Path (Join-Path $RepoRoot "web"))) {
    Write-Host "== checking for S.A.R.A source bundle =="
    if (Test-Path (Join-Path $SrcBundle "sara.py") -and (Test-Path (Join-Path $SrcBundle "sara")) -and (Test-Path (Join-Path $SrcBundle "web"))) {
        Write-Host "   source bundle found: $SrcBundle"
        # Copy the COMPLETE bundle (all top-level .py launchers/modules +
        # sara/ package + web/ assets) so sara.py can import its siblings.
        if (Test-Path (Join-Path $RepoRoot "sara")) { Remove-Item (Join-Path $RepoRoot "sara") -Recurse -Force }
        if (Test-Path (Join-Path $RepoRoot "web")) { Remove-Item (Join-Path $RepoRoot "web") -Recurse -Force }
        Copy-Item (Join-Path $SrcBundle "*") $RepoRoot -Recurse -Force
        Write-Host "   core files restored from: $SrcBundle"
    } else {
        Write-Host "No local S.A.R.A source bundle was found."
        Write-Host "Checked: install-bundle\src"
        exit 1
    }
}

echo "✅ install-bundle/ (the installer scripts)"
echo "✅ requirements.txt (the dependencies)"
echo "✅ sara.py (the actual entry point)"
echo "✅ sara/ (the core agent package)"
echo "✅ web/ (the UI assets)"

# 1) Create a local virtualenv
$Venv = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $Venv)) {
    Write-Host "== creating virtualenv =="
    & $Py -m venv $Venv
}

# 2) Install dependencies (Windows venv activates via Scripts\Activate.ps1)
$Activate = Join-Path $Venv "Scripts\Activate.ps1"
. $Activate
Write-Host "== installing dependencies =="
pip install --upgrade pip | Out-Null
pip install -r (Join-Path $RepoRoot "install-bundle\requirements.txt")

# 3) Convenience launcher (batch file on PATH-less double-click)
$Bin = Join-Path $RepoRoot "bin"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
$Bat = Join-Path $Bin "sara.bat"
@"
@echo off
REM S.A.R.A launcher — activates the venv and runs the unified entry point.
set "HERE=%~dp0.."
call "%HERE%\.venv\Scripts\activate.bat"
python "%HERE%\sara.py" %*
"@ | Set-Content -NoNewline $Bat

Write-Host ""
Write-Host "== DONE =="
Write-Host "Run the agent:"
Write-Host "  $Bat                 # interactive CLI"
Write-Host "  $Bat 'your question' # one-shot"
Write-Host "  $Bat web             # web UI at http://localhost:8800"
Write-Host ""
Write-Host "NOTE: S.A.R.A defaults to Nous Portal + stepfun/step-3.7-flash:free."
Write-Host "      Edit config.json -> base_url / model / provider, or use /status."
