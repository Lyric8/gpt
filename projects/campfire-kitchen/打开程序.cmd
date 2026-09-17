@echo off
setlocal
cd /d "%~dp0"
python tools\build.py || exit /b 1
start "" "%~dp0index.html"
