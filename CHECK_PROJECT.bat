@echo off
setlocal
cd /d "%~dp0"
set "FILES=-f docker-compose.yml"
if exist "models\multilingual-e5-base-q4_k.gguf" set "FILES=-f docker-compose.yml -f docker-compose.e5.yml"

docker info >nul 2>nul
if errorlevel 1 goto :dockerfail

echo [1/3] Python compile check inside app container...
docker compose %FILES% exec -T app python -m compileall -q app.py backend scripts seed.py tests
if errorlevel 1 goto :fail

echo [2/3] Pytest inside app container...
docker compose %FILES% exec -T app python -m pytest -q
if errorlevel 1 goto :fail

echo [3/3] Optional host JavaScript syntax check...
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is not installed on the host; JS syntax check skipped.
) else (
  for /r static\js %%f in (*.js) do node --check "%%f" >nul
  if errorlevel 1 goto :fail
)

echo.
echo Project checks passed.
pause
exit /b 0

:dockerfail
echo Docker Engine is not running. Start Docker Desktop first.
pause
exit /b 1

:fail
echo.
echo Project check failed. Copy the error above.
pause
exit /b 1
