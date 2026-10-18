@echo off
cd /d "%~dp0.."
docker info >nul 2>&1
if errorlevel 1 (
  echo Please start Docker Desktop first.
  pause
  exit /b 1
)
echo Building and starting SushiCTF. This may take several minutes...
docker compose up --build --wait --wait-timeout 300
if errorlevel 1 (
  docker compose ps
  docker compose logs --tail 30
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8080/"
echo Ready: http://127.0.0.1:8080/
pause
