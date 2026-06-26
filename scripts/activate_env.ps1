param(
    [string]$CondaExe = "E:\Anaconda3\Scripts\conda.exe",
    [string]$EnvRoot = "E:\Anaconda3",
    [string]$EnvName = "finlongrag-py312"
)

$ErrorActionPreference = "Stop"

$EnvRoot = [System.IO.Path]::GetFullPath($EnvRoot)
$EnvPrefix = Join-Path (Join-Path $EnvRoot "envs") $EnvName
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

if (-not (Test-Path -LiteralPath (Join-Path $EnvPrefix "python.exe"))) {
    throw "Environment not found: $EnvPrefix. Run scripts\setup_env.ps1 first."
}

if (-not (Test-Path -LiteralPath $CondaExe)) {
    throw "Conda executable not found: $CondaExe"
}

(& $CondaExe "shell.powershell" "hook") | Out-String | Invoke-Expression
conda activate $EnvPrefix
