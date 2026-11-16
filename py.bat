@echo off
rem Descobre o Python desta maquina e devolve em %PY%. Antes cada .bat tinha o
rem caminho do msys2 cravado; quando o msys2 sumiu, nada mais rodava.
if defined PY if exist "%PY%" exit /b 0
for %%P in (
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "C:\msys64\mingw64\bin\python.exe"
) do if exist %%~P set "PY=%%~P" & exit /b 0
for /f "delims=" %%P in ('where python 2^>nul') do set "PY=%%P" & exit /b 0
echo ERRO: Python nao encontrado. Instale o Python 3 ou defina PY=caminho\python.exe
exit /b 1
