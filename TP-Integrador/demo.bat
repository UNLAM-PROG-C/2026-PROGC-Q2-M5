@echo off
rem Demo for the university: ten segments, both backends, CSV of times.
rem Usage: demo.bat                     (full demo)
rem        demo.bat --demo-seconds 3    (short, for testing)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python tools\run_demo.py %*
echo.
echo La tabla comparativa:  py tools\report_table.py
pause
