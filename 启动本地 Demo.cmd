@echo off
setlocal
cd /d "%~dp0"

where pnpm >nul 2>nul
if errorlevel 1 (
  echo 未检测到 pnpm。请先安装 Node.js 和 pnpm，然后重新双击此文件。
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo 未检测到 Python。请先安装 Python，然后重新双击此文件。
  pause
  exit /b 1
)

start "AestheticLens API" cmd /k "cd /d ""%~dp0backend"" ^&^& python -m uvicorn app.main:app --reload --port 8000"
start "AestheticLens Local Demo" cmd /k "cd /d ""%~dp0"" ^&^& pnpm dev"
timeout /t 5 /nobreak >nul
start "" "http://localhost:3000/"
