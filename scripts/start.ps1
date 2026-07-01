param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 7860,
    [string]$CondaExe = "D:\Anaconda3\Scripts\conda.exe",
    [string]$EnvRoot = "D:\Anaconda3",
    [string]$EnvName = "finlongrag-py312",
    [switch]$ForceFrontendBuild,
    [switch]$SkipFrontendBuild,
    [switch]$NoBrowser,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$FrontendRoot = Join-Path $ProjectRoot "frontend"
function Find-CondaExe {
    param([string]$Preferred)
    if ($Preferred -and (Test-Path -LiteralPath $Preferred)) {
        return $Preferred
    }
    $candidates = @(
        "E:\Anaconda3\Scripts\conda.exe",
        "D:\Anaconda3\Scripts\conda.exe",
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "C:\ProgramData\anaconda3\Scripts\conda.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    $fromPath = Get-Command conda -ErrorAction SilentlyContinue
    if ($fromPath) {
        return $fromPath.Source
    }
    return $null
}

function Resolve-EnvRoot {
    param([string]$CondaExePath, [string]$Preferred)
    if ($Preferred -and (Test-Path -LiteralPath $Preferred)) {
        return [System.IO.Path]::GetFullPath($Preferred)
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Split-Path (Split-Path $CondaExePath -Parent) -Parent) ""))
}

$CondaLauncher = Find-CondaExe $CondaExe

$PythonLauncher = $null
try {
    $PythonLauncher = (Get-Command py -ErrorAction Stop).Source
} catch {
    try {
        $PythonLauncher = (Get-Command python -ErrorAction Stop).Source
    } catch {
        $PythonLauncher = $null
    }
}

$UseConda = [bool]$CondaLauncher
if ($UseConda) {
    $EnvRoot = Resolve-EnvRoot -CondaExePath $CondaLauncher -Preferred $EnvRoot
    $EnvPrefix = Join-Path (Join-Path $EnvRoot "envs") $EnvName
    $PythonExe = Join-Path $EnvPrefix "python.exe"
} else {
    $EnvPrefix = Join-Path $ProjectRoot ".venv"
    $PythonExe = Join-Path $EnvPrefix "Scripts\python.exe"
}
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

    if (Test-Path -LiteralPath $envPath) {
        return
    }

    if (-not (Test-Path -LiteralPath $examplePath)) {
        throw ".env.example not found."
    }

    $lines = Get-Content -LiteralPath $examplePath
    $secretLine = $lines | Where-Object { $_ -match '^FINLONGRAG_SECRET_KEY=' } | Select-Object -First 1
    if (-not $secretLine -or $secretLine -match 'change-me') {
        $bytes = New-Object byte[] 48
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $secret = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
    } else {
        $secret = $secretLine.Split('=', 2)[1]
    }

    foreach ($line in $lines) {
        if ($line -notmatch '^\s*([A-Z0-9_]+)=(.*)$') {
            continue
        }

        $name = $matches[1]
        $value = $matches[2]
        if ($name -eq 'FINLONGRAG_SECRET_KEY') {
            [System.Environment]::SetEnvironmentVariable($name, $secret, 'Process')
            continue
        }

        if ([string]::IsNullOrWhiteSpace([System.Environment]::GetEnvironmentVariable($name, 'Process'))) {
            [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }

    [System.Environment]::SetEnvironmentVariable('FINLONGRAG_SECRET_KEY', $secret, 'Process')
    Write-Step "Loaded environment variables from .env.example."
}

function Ensure-PythonEnv {
    if ($UseConda) {
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
            & (Join-Path $PSScriptRoot "setup_env.ps1") -CondaExe $CondaLauncher -EnvRoot $EnvRoot -EnvName $EnvName -SkipTests
            if ($LASTEXITCODE -ne 0) {
                throw "Environment setup failed."
            }
        }
    } else {
        if (-not $PythonLauncher) {
            throw "No usable Python launcher found. Install Python 3.12 or Conda, then try again."
        }

        if (-not (Test-Path -LiteralPath $PythonExe)) {
            Write-Step "Python virtual environment not found. Creating .venv with Python 3.12..."
            Invoke-Native $PythonLauncher @("-3.12", "-m", "venv", $EnvPrefix) "python venv"
        }
    }

    $check = @"
import importlib
for module in ["fastapi", "uvicorn", "sqlalchemy", "pydantic", "jwt", "cryptography", "psycopg", "opendataloader_pdf", "pypdf"]:
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

function Ensure-JavaRuntime {
    $javaCandidates = @(
        "E:\Apps\Java\jdk-11",
        $env:JAVA11_HOME,
        $env:JAVA_HOME,
        "E:\java_JDK\OpenJDK17U-jdk_x64_windows_hotspot_17.0.17_10\jdk-17.0.17+10"
    ) | Where-Object { $_ -and (Test-Path -LiteralPath (Join-Path $_ "bin\java.exe")) }

    foreach ($candidate in $javaCandidates) {
        $javaExe = Join-Path $candidate "bin\java.exe"
        $versionText = Get-JavaVersionText $javaExe
        if ($versionText -match 'version "(\d+)(?:\.(\d+))?') {
            $major = [int]$matches[1]
            if ($major -eq 1 -and $matches[2]) { $major = [int]$matches[2] }
            if ($major -ge 11) {
                $env:JAVA_HOME = $candidate
                $env:JAVA11_HOME = if (Test-Path -LiteralPath "E:\Apps\Java\jdk-11") { "E:\Apps\Java\jdk-11" } else { $candidate }
                $env:Path = "$(Join-Path $candidate "bin");$env:Path"
                Write-Step "Using Java $major from $candidate."
                return
            }
        }
    }

    throw "Java 11+ is required for opendataloader-pdf. Install it under E:\Apps\Java\jdk-11 or set JAVA_HOME."
}

function Get-JavaVersionText {
    param([string]$JavaExe)

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $JavaExe
    $startInfo.Arguments = "-version"
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        return (($stderr, $stdout) | Where-Object { $_ }) -join "`n"
    }
    finally {
        $process.Dispose()
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
Ensure-JavaRuntime
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
