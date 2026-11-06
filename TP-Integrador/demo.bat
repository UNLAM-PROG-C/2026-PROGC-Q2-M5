@echo off
rem Demo for the university: ten segments, both backends, CSV of times.
rem Usage: demo.bat                     (full demo)
rem        demo.bat --demo-seconds 3    (short, for testing)
cd /d "%~dp0"
rem The venv lives here on the notebook (instalar-*.bat) and two levels up on the GPU PC.
if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) else (call ..\..\.venv\Scripts\activate.bat)
python tools\run_demo.py %*
echo.
echo La tabla comparativa:  py tools\report_table.py
pause
