@echo off
REM ============================================================
REM  Atualiza todo o Hub Boardview DJI de uma vez.
REM  Rode depois de: adicionar placas, fotos, PDFs de referencia,
REM  preencher cadernos, ou baixar JSONs novos do Digital Board.
REM ============================================================
setlocal
call "%~dp0py.bat" || exit /b 1
rem (o PY vem do py.bat)
set BV=%~dp0
for /f "delims=" %%D in ('"%PY%" "%~dp0paths.py" --drones') do set "DRONES=%%D"

echo.
echo === 1/6  Fundos (foto sob os pads) das placas novas ===
"%PY%" "%BV%batch_bg.py" "%DRONES%" --apply

echo.
echo === 2/6  Netlists ===
for /d %%D in ("%DRONES%\*") do "%PY%" "%BV%export_netlist.py" "%%D" "%BV%Netlists" >nul 2>&1

echo.
echo === 3/6  Cadernos de medicao ===
"%PY%" "%BV%gen_all_sheets.py" "%DRONES%" "%BV%Cadernos"

echo.
echo === 4/6  Malhas (busca net-componentes) ===
for /r "%DRONES%" %%F in (*.pcb) do (
  echo %%~nxF | findstr /b "._" >nul || "%PY%" "%BV%gen_malhas.py" "%%F" "%BV%Malhas" "%BV%Malhas-templates" >nul 2>&1
)

echo.
echo === 5/6  Dados do Visualizador local (boards\*.js) ===
for /r "%DRONES%" %%F in (*.pcb) do (
  echo %%~nxF | findstr /b "._" >nul || "%PY%" "%BV%export_board.py" "%%F" "%BV%boards" >nul 2>&1
)

echo.
echo === 6/7  Juntar placas por drone (arquivo unico p/ OBV) + foto combinada ===
"%PY%" "%BV%gen_merged_all.py"
"%PY%" "%BV%merge_bg.py"

echo === 7/8  Anexar mapas + indice de modelos + gerar HUB ===
"%PY%" "%BV%attach_refs.py"
"%PY%" "%BV%gen_models_index.py"
echo [miniaturas do hub]

"%PY%" "%BV%gen_thumbs.py"



"%PY%" "%BV%gen_hub.py"

echo.
echo === 8/8  Viewer DigitalBoard: fotos por metade + indice por modelo ===
REM  Demora: ~4 min por placa (a escolha de rotacao/metade/espelho e medida, nao
REM  chutada). Para refazer so uma: foto_viewer.py "parte do nome".
"%PY%" "%BV%foto_viewer.py"
"%PY%" "%BV%gen_modelos.py"

echo.
echo === Pronto! Abra o hub com Viewer.bat ===
pause
