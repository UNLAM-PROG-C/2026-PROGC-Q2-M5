@echo off
rem Install with CUDA: needs an NVIDIA card and CUDA 13 (see INSTALACION.md).
rem The toolchain folder has to be next to the repository.
cd /d "%~dp0"
if not exist .venv (
    py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pip install -r requirements-gpu.txt
echo.
echo Verificando la GPU (si falla, el juego usa numpy):
python tools\gpu_selftest.py
pause
