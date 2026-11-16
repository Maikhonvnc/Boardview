@echo off
rem Abre direto o viewer do DigitalBoard (sem passar pelo hub).
cd /d "%~dp0"
call "%~dp0py.bat" || exit /b 1
start "Hub Boardview - servidor (NAO feche)" "%PY%" servidor.py
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8777/digital_viewer/index.html"
exit
