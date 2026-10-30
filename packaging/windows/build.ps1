param([switch]$SkipInstall, [switch]$SkipFrontend, [string]$PythonPath)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
if ($env:OS -ne 'Windows_NT') { throw 'Build the Windows EXE on Windows 10/11 x64.' }
$ProjectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Push-Location $ProjectRoot
try {
    $Python = if ($PythonPath) { (Resolve-Path -LiteralPath $PythonPath).Path } else { Join-Path $ProjectRoot '.venv-windows\Scripts\python.exe' }
    if (-not (Test-Path $Python)) {
        py -3.12 -m venv .venv-windows
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 x64 with the Python launcher.' }
    }
    if (-not $SkipInstall) {
        & $Python -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
        & $Python -m pip install -r packaging/windows/requirements-build.txt
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    }
    if (-not $SkipFrontend) {
        Push-Location frontend
        try {
            npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
            npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        } finally { Pop-Location }
    }
    & $Python -m unittest discover -s tests
    if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }
    & $Python packaging/windows/prepare.py
    if ($LASTEXITCODE -ne 0) { throw 'Resource preparation failed.' }
    & $Python -m PyInstaller --noconfirm --clean --distpath dist --workpath build/windows/pyinstaller packaging/windows/seeUtoken.spec
    if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
    $Artifact = Join-Path $ProjectRoot 'dist\seeUtoken-V1.0.2.exe'
    $Hash = (Get-FileHash $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash  seeUtoken-V1.0.2.exe" | Set-Content "$Artifact.sha256" -Encoding ascii
    Write-Host "Built: $Artifact"
} finally { Pop-Location }
