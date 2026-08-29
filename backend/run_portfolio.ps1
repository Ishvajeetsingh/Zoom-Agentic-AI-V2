$ErrorActionPreference = "Stop"

$envFile = Join-Path $PSScriptRoot ".env.portfolio.local"

if (-not (Test-Path $envFile)) {
    Write-Host "ERROR: .env.portfolio.local was not found."
    exit 1
}

Write-Host ""
Write-Host "Loading portfolio environment..."

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()

    if (
        $line -and
        -not $line.StartsWith("#") -and
        $line.Contains("=")
    ) {
        $parts = $line.Split("=", 2)

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()

        [Environment]::SetEnvironmentVariable(
            $name,
            $value,
            "Process"
        )
    }
}

Write-Host ""
Write-Host "Checking portfolio environment..."

python -c "from app.core.config import settings; from urllib.parse import urlparse; u=settings.database_url.replace('postgresql+psycopg://','postgresql://'); print('DEMO =', settings.public_demo_mode); print('DB HOST =', urlparse(u).hostname); print('LLM =', settings.llm_provider); print('GROQ KEY =', bool(settings.groq_api_key))"

Write-Host ""
Write-Host "Starting portfolio backend..."
Write-Host ""

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000