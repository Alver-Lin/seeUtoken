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
    $Version = (& $Python packaging/metadata.py).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read application version.' }
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
    & $Python -m PyInstaller --noconfirm --clean --distpath build/windows/app --workpath build/windows/pyinstaller packaging/windows/seeUtoken.spec
    if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
    $Compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    $Iscc = if ($Compiler) { $Compiler.Source } else { Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }
    if (-not (Test-Path $Iscc)) { throw 'Install Inno Setup 6 (https://jrsoftware.org/isdl.php) to build the upgrade installer.' }
    & $Iscc "/DAppVersion=$Version" "/DAppBinary=$ProjectRoot\build\windows\app\seeUtoken.exe" "/DOutputPath=$ProjectRoot\dist" "/DIconFile=$ProjectRoot\build\windows\assets\icon.ico" packaging/windows/installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
    $Artifact = Join-Path $ProjectRoot "dist\seeUtoken-V$Version.exe"
    $Hash = (Get-FileHash $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash  seeUtoken-V$Version.exe" | Set-Content "$Artifact.sha256" -Encoding ascii
    Write-Host "Built: $Artifact"
} finally { Pop-Location }
