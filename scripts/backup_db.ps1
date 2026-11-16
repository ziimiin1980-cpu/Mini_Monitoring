<#
.SYNOPSIS
    Создаёт резервную копию базы данных Mini Monitoring через pg_dump.

.EXAMPLE
    .\scripts\backup_db.ps1

.EXAMPLE
    .\scripts\backup_db.ps1 -PgBin "D:\postgresql\bin" -BackupDir "D:\backups"
#>
param(
    [string]$PgBin = "",
    [string]$BackupDir = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not $BackupDir) {
    $BackupDir = Join-Path $root "backups"
}
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

function Find-PgDump {
    param([string]$Explicit)

    if ($Explicit) {
        $candidate = Join-Path $Explicit "pg_dump.exe"
        if (Test-Path $candidate) {
            return $candidate
        }
        throw "pg_dump.exe не найден в каталоге: $Explicit"
    }

    $fromPath = Get-Command pg_dump.exe -ErrorAction SilentlyContinue
    if ($fromPath) {
        return $fromPath.Source
    }

    $candidates = @(
        "D:\postgresql\bin\pg_dump.exe",
        "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe",
        "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe",
        "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) {
            return $path
        }
    }

    throw "pg_dump.exe не найден. Укажите каталог явно: .\scripts\backup_db.ps1 -PgBin 'D:\postgresql\bin'"
}

# Строку подключения берём из настроек приложения — один источник правды
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Не найдено виртуальное окружение: $python"
}

Push-Location $root
try {
    $databaseUrl = (& $python -c "from app.config import settings; print(settings.database_url)").Trim()
}
finally {
    Pop-Location
}

if (-not $databaseUrl) {
    throw "Не удалось прочитать DATABASE_URL (проверьте .env)"
}

# pg_dump не понимает драйвер в схеме, ему нужен обычный postgresql://
$pgUrl = $databaseUrl -replace '\+psycopg', ''

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $BackupDir "mini_monitoring-$stamp.dump"

$pgDump = Find-PgDump -Explicit $PgBin
& $pgDump "--dbname=$pgUrl" "--format=custom" "--file=$target"

if ($LASTEXITCODE -ne 0) {
    throw "pg_dump завершился с кодом $LASTEXITCODE"
}

$sizeKb = [math]::Round((Get-Item $target).Length / 1KB, 1)
Write-Host "Резервная копия создана: $target ($sizeKb КБ)"
