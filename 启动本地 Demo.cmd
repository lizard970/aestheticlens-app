@echo off
chcp 65001 >nul

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
start "AestheticLens API" /D "%~dp0backend" cmd /k python -m uvicorn app.main:app --reload --port 8000
start "AestheticLens Local Demo" /D "%~dp0" cmd /k pnpm dev
start "" "http://localhost:3000/"
