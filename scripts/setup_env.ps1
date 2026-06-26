param(
    [string]$CondaExe = "E:\Anaconda3\Scripts\conda.exe",
    [string]$EnvRoot = "E:\Anaconda3",
    [string]$EnvName = "finlongrag-py312",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvRoot = [System.IO.Path]::GetFullPath($EnvRoot)
$EnvPrefix = Join-Path (Join-Path $EnvRoot "envs") $EnvName
$CondaPkgs = Join-Path $EnvRoot "pkgs"
$PipCache = Join-Path $EnvRoot "pip-cache"
$PythonUserBase = Join-Path $EnvRoot "python-user"
$TempDir = Join-Path $EnvRoot "temp"

foreach ($path in @($EnvRoot, (Join-Path $EnvRoot "envs"), $CondaPkgs, $PipCache, $PythonUserBase, $TempDir)) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
}

$env:CONDA_ENVS_PATH = Join-Path $EnvRoot "envs"
$env:CONDA_PKGS_DIRS = $CondaPkgs
$env:PIP_CACHE_DIR = $PipCache
$env:PYTHONUSERBASE = $PythonUserBase
$env:PYTHONNOUSERSITE = "1"
$env:TEMP = $TempDir
$env:TMP = $TempDir

if (-not (Test-Path -LiteralPath $CondaExe)) {
    throw "Conda executable not found: $CondaExe"
}

function Invoke-Native {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Description
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $EnvPrefix "python.exe"))) {
    Invoke-Native $CondaExe @("create", "-p", $EnvPrefix, "python=3.12", "pip", "-y") "conda create"
}

$PythonExe = Join-Path $EnvPrefix "python.exe"
Invoke-Native $PythonExe @("-m", "pip", "install", "--no-cache-dir", "-r", (Join-Path $ProjectRoot "requirements-dev.txt")) "pip install requirements"
Invoke-Native $PythonExe @("-m", "pip", "install", "--no-cache-dir", "-e", $ProjectRoot, "--no-deps") "pip install project"

if (-not $SkipTests) {
    Push-Location $ProjectRoot
    try {
        Invoke-Native $PythonExe @("-m", "pytest") "pytest"
        Invoke-Native $PythonExe @("-m", "compileall", "src", "scripts", "tests") "compileall"
    }
    finally {
        Pop-Location
    }
}

Write-Host "FinLongRAG environment is ready:"
Write-Host "  $EnvPrefix"
Write-Host "Use this Python:"
Write-Host "  $PythonExe"
