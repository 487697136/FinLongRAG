param(
    [string]$PsqlExe = "C:\Program Files\PostgreSQL\18\bin\psql.exe",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$SuperUser = "postgres",
    [string]$SuperPassword = "",
    [string]$AppUser = "finlongrag",
    [string]$AppPassword = "finlongrag",
    [string]$Database = "finlongrag"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PsqlExe)) {
    throw "psql.exe not found: $PsqlExe"
}

if (-not $AppPassword) {
    $secure = Read-Host "Password for application role '$AppUser'" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $AppPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

if (-not $SuperPassword) {
    $secure = Read-Host "PostgreSQL superuser password for '$SuperUser'" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $SuperPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

$env:PGPASSWORD = $SuperPassword

$escapedAppPassword = $AppPassword.Replace("'", "''")
$bootstrapSql = @"
DO `$`$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$AppUser') THEN
        CREATE ROLE $AppUser LOGIN PASSWORD '$escapedAppPassword';
    ELSE
        ALTER ROLE $AppUser WITH LOGIN PASSWORD '$escapedAppPassword';
    END IF;
END
`$`$;
"@

& $PsqlExe -h $HostName -p $Port -U $SuperUser -d postgres -v ON_ERROR_STOP=1 -c $bootstrapSql
if ($LASTEXITCODE -ne 0) {
    throw "failed to create or update PostgreSQL role '$AppUser'"
}

$dbExists = & $PsqlExe -h $HostName -p $Port -U $SuperUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$Database'"
if (($dbExists -join "").Trim() -ne "1") {
    & $PsqlExe -h $HostName -p $Port -U $SuperUser -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $Database OWNER $AppUser"
    if ($LASTEXITCODE -ne 0) {
        throw "failed to create database '$Database'"
    }
}

& $PsqlExe -h $HostName -p $Port -U $SuperUser -d $Database -v ON_ERROR_STOP=1 -c "GRANT ALL PRIVILEGES ON DATABASE $Database TO $AppUser"
if ($LASTEXITCODE -ne 0) {
    throw "failed to grant database privileges"
}

Write-Host "PostgreSQL initialized for FinLongRAG: postgresql://$AppUser:***@$HostName`:$Port/$Database" -ForegroundColor Green
