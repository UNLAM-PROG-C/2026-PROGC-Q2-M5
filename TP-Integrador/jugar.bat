@echo off
rem Normal game (with the effects if CUDA works, numpy otherwise).
rem Usage: jugar.bat            (window 1280x720)
rem        jugar.bat --sin-efectos  (without effects; --no-gpu still works)
cd /d "%~dp0"
rem The venv lives here on the notebook (instalar-*.bat) and two levels up on the GPU PC.
if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) else (call ..\..\.venv\Scripts\activate.bat)
python main.py %*
