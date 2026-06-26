param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 7860,
    [string]$CondaExe = "E:\Anaconda3\Scripts\conda.exe",
    [string]$EnvRoot = "E:\Anaconda3",
    [string]$EnvName = "finlongrag-py312",
    [switch]$ForceFrontendBuild,
    [switch]$SkipFrontendBuild,
    [switch]$NoBrowser,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$EnvRoot = [System.IO.Path]::GetFullPath($EnvRoot)
$EnvPrefix = Join-Path (Join-Path $EnvRoot "envs") $EnvName
$PythonExe = Join-Path $EnvPrefix "python.exe"
$Url = "http://${HostName}:${Port}"

function Write-Step {
    param([string]$Message)
    Write-Host "[FinLongRAG] $Message" -ForegroundColor Cyan
}

function Invoke-Native {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Description,
        [string]$WorkingDirectory = $ProjectRoot
    )

    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Description failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Test-PortOpen {
    param([string]$HostName, [int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(350)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Ensure-EnvFile {
    $envPath = Join-Path $ProjectRoot ".env"
    $examplePath = Join-Path $ProjectRoot ".env.example"
    if (-not (Test-Path -LiteralPath $envPath)) {
        if (-not (Test-Path -LiteralPath $examplePath)) {
            throw ".env.example not found."
        }
        Copy-Item -LiteralPath $examplePath -Destination $envPath
        Write-Step "Created .env from .env.example."
    }

    $lines = Get-Content -LiteralPath $envPath
    $secretLine = $lines | Where-Object { $_ -match '^FINLONGRAG_SECRET_KEY=' } | Select-Object -First 1
    if (-not $secretLine -or $secretLine -match 'change-me') {
        $bytes = New-Object byte[] 48
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $secret = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
        $found = $false
        $updated = foreach ($line in $lines) {
            if ($line -match '^FINLONGRAG_SECRET_KEY=') {
                $found = $true
                "FINLONGRAG_SECRET_KEY=$secret"
            } else {
                $line
            }
        }
        if (-not $found) {
            $updated += "FINLONGRAG_SECRET_KEY=$secret"
        }
        Set-Content -LiteralPath $envPath -Value $updated -Encoding UTF8
        Write-Step "Generated FINLONGRAG_SECRET_KEY in .env."
    }
}

function Ensure-PythonEnv {
    $env:CONDA_ENVS_PATH = Join-Path $EnvRoot "envs"
    $env:CONDA_PKGS_DIRS = Join-Path $EnvRoot "pkgs"
    $env:PIP_CACHE_DIR = Join-Path $EnvRoot "pip-cache"
    $env:PYTHONUSERBASE = Join-Path $EnvRoot "python-user"
    $env:PYTHONNOUSERSITE = "1"
    $env:TEMP = Join-Path $EnvRoot "temp"
    $env:TMP = Join-Path $EnvRoot "temp"

    foreach ($path in @($env:CONDA_ENVS_PATH, $env:CONDA_PKGS_DIRS, $env:PIP_CACHE_DIR, $env:PYTHONUSERBASE, $env:TEMP)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }

    if (-not (Test-Path -LiteralPath $PythonExe)) {
        Write-Step "Python environment not found. Running scripts\setup_env.ps1 -SkipTests..."
        & (Join-Path $PSScriptRoot "setup_env.ps1") -CondaExe $CondaExe -EnvRoot $EnvRoot -EnvName $EnvName -SkipTests
        if ($LASTEXITCODE -ne 0) {
            throw "Environment setup failed."
        }
    }

    $check = @"
import importlib
for module in ["fastapi", "uvicorn", "sqlalchemy", "pydantic", "jwt"]:
    importlib.import_module(module)
print("ok")
"@
    $result = $check | & $PythonExe -
    if ($LASTEXITCODE -ne 0 -or ($result -join "`n") -notmatch "ok") {
        Write-Step "Python dependencies look incomplete. Installing requirements..."
        Invoke-Native $PythonExe @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements.txt")) "pip install requirements"
        Invoke-Native $PythonExe @("-m", "pip", "install", "-e", $ProjectRoot, "--no-deps") "pip install project"
    }
}

function Ensure-Frontend {
    if ($SkipFrontendBuild) {
        return
    }

    $distIndex = Join-Path $FrontendRoot "dist\index.html"
    $nodeModules = Join-Path $FrontendRoot "node_modules"
    $packageJson = Join-Path $FrontendRoot "package.json"
    $packageLock = Join-Path $FrontendRoot "package-lock.json"

    if (-not (Test-Path -LiteralPath $packageJson)) {
        Write-Step "Frontend package.json not found. Skipping frontend build."
        return
    }

    if (-not (Test-Path -LiteralPath $nodeModules)) {
        Write-Step "Installing frontend dependencies..."
        Invoke-Native "npm" @("install") "npm install" $FrontendRoot
    }

    $needsBuild = $ForceFrontendBuild -or (-not (Test-Path -LiteralPath $distIndex))
    if (-not $needsBuild -and (Test-Path -LiteralPath $packageLock)) {
        $needsBuild = (Get-Item -LiteralPath $packageLock).LastWriteTimeUtc -gt (Get-Item -LiteralPath $distIndex).LastWriteTimeUtc
    }

    if ($needsBuild) {
        Write-Step "Building frontend..."
        Invoke-Native "npm" @("run", "build") "npm run build" $FrontendRoot
    }
}

Set-Location $ProjectRoot
Ensure-EnvFile
Ensure-PythonEnv
Ensure-Frontend

if (Test-PortOpen $HostName $Port) {
    Write-Step "Service is already running at $Url."
    if (-not $NoBrowser) {
        Start-Process $Url
    }
    exit 0
}

if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($TargetUrl)
        Start-Sleep -Seconds 2
        Start-Process $TargetUrl
    } -ArgumentList $Url | Out-Null
}

Write-Step "Starting FinLongRAG at $Url ..."
$serveArgs = @((Join-Path $ProjectRoot "scripts\serve.py"), "--host", $HostName, "--port", "$Port")
if ($DryRun) {
    $serveArgs += "--dry-run"
}
& $PythonExe @serveArgs
