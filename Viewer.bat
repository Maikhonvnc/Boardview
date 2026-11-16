@echo off
rem Abre o HUB local (fotos, OBV, DigitalBoard, PDFs) no navegador.
rem O servidor precisa ficar aberto: feche a janela preta para parar.
cd /d "%~dp0"
call "%~dp0py.bat" || exit /b 1
start "Hub Boardview - servidor (NAO feche)" "%PY%" servidor.py
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8777/HUB.html"
exit
