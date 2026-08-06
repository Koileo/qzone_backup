@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import aiohttp, demjson3, loguru, lxml, PIL, qrcode, requests" 2>nul
  if errorlevel 1 (
    echo 运行依赖尚未安装，请先执行：python -m pip install -e .
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" main.py
) else (
  python main.py
)

echo.
pause
