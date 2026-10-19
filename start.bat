@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 start.py
  exit /b %errorlevel%
)

where python >nul 2>&1
if %errorlevel%==0 (
  python start.py
  exit /b %errorlevel%
)

echo Python was not found. Install Python 3.10, 3.11, 3.12, or 3.13 from python.org and run start.bat again.
exit /b 1
