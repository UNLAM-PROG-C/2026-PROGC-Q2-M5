@echo off
rem Normal game (with the effects if CUDA works, numpy otherwise).
rem Usage: jugar.bat            (window 1280x720)
rem        jugar.bat --no-gpu   (without effects)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python main.py %*
