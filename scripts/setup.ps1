# ==============================================================================
# Setup Script for Olist Sales Analytics Platform (Windows PowerShell)
#
# Process:
# 1. Create .env from .env.example
# 2. Initialize virtual environment using uv
# 3. Download Olist dataset from Kaggle
# 4. Start Docker Compose (Postgres + Airflow)
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "Initializing Olist Sales Analytics Platform Setup..." -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

# 1. Environment file setup
if (-not (Test-Path ".env")) {
    Write-Host "1. Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "   [OK] .env created. You can customize passwords in it if needed." -ForegroundColor Green
} else {
    Write-Host "1. .env file already exists. Skipping creation." -ForegroundColor Green
}

# 2. Check uv and install dependencies
Write-Host "2. Checking for 'uv' package manager..." -ForegroundColor Yellow
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "   [OK] 'uv' is installed." -ForegroundColor Green
} else {
    Write-Host "   [WARNING] 'uv' is not installed or not in PATH." -ForegroundColor Red
    Write-Host "   Please install it: 'pip install uv' or 'powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`"'" -ForegroundColor Cyan
    Exit 1
}

# Initialize virtual environment and install packages
Write-Host "   Installing ingestion dependencies..." -ForegroundColor Yellow
cd ingestion
uv venv
uv pip install -r pyproject.toml
cd ..

# 3. Download Kaggle data
Write-Host "3. Downloading Olist Brazilian E-Commerce dataset..." -ForegroundColor Yellow
cd ingestion
uv run python ../scripts/download_data.py
cd ..

# 4. Start Docker Containers
Write-Host "4. Launching Docker Containers (Postgres + Airflow)..." -ForegroundColor Yellow
if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    docker-compose up -d --build
} elseif (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose up -d --build
} else {
    Write-Host "   [WARNING] Docker is not running or not installed. Please start Docker Desktop and run:" -ForegroundColor Red
    Write-Host "   'docker compose up -d --build'" -ForegroundColor Cyan
    Exit 0
}

Write-Host "`n==============================================================================" -ForegroundColor Cyan
Write-Host "Setup Completed Successfully!" -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "Services are starting up:" -ForegroundColor Yellow
Write-Host "  - PostgreSQL: localhost:5432" -ForegroundColor Green
Write-Host "  - Airflow UI: http://localhost:8080 (User: admin / Pass: admin)" -ForegroundColor Green
Write-Host "`nTo start dbt transformation locally, run:" -ForegroundColor Yellow
Write-Host "  cd dbt_project" -ForegroundColor Cyan
Write-Host "  dbt deps" -ForegroundColor Cyan
Write-Host "  dbt snapshot" -ForegroundColor Cyan
Write-Host "  dbt run" -ForegroundColor Cyan
Write-Host "  dbt test" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan
