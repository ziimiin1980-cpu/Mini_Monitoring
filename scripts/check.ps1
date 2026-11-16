<#
.SYNOPSIS
    Проверки проекта: линтер, форматирование и тесты с покрытием.

.EXAMPLE
    .\scripts\check.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Не найдено виртуальное окружение: $python. Создайте его и установите requirements-dev.txt"
}

Push-Location $root
try {
    Write-Host "1/3 ruff check"
    & $python -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw "ruff check нашёл проблемы" }

    Write-Host "2/3 ruff format --check"
    & $python -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw "Код не отформатирован: выполните ruff format ." }

    Write-Host "3/3 pytest"
    & $python -m pytest -q --cov=app --cov-report=term-missing
    if ($LASTEXITCODE -ne 0) { throw "Тесты не прошли" }

    Write-Host ""
    Write-Host "Все проверки пройдены." -ForegroundColor Green
}
finally {
    Pop-Location
}
