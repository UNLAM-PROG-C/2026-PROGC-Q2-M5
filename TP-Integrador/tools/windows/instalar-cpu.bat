@echo off
rem CPU-only install: the game runs with the numpy effects (no CUDA).
rem Usage: double click, or  instalar-cpu.bat  from a terminal.
cd /d "%~dp0..\.." || exit /b 1
if not exist .venv (
    py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r tools\requirements\requirements-dev.txt
echo.
echo Listo. Para jugar: tools\windows\jugar.bat
pause
