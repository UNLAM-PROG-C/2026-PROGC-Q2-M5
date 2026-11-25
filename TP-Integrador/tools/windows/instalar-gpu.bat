@echo off
rem Install with CUDA: needs an NVIDIA card and CUDA 13 (see INSTALACION.md).
rem The toolchain folder has to be next to the repository.
set "PY_VERSION=3.12"
set "PY_URL=https://www.python.org/downloads/windows/"
cd /d "%~dp0..\.." || exit /b 1
py -%PY_VERSION% --version >nul 2>&1 || goto :no_python
if not exist .venv (
    py -%PY_VERSION% -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r tools\requirements\requirements-dev.txt
python -m pip install -r tools\requirements\requirements-gpu.txt
echo.
echo Verificando la GPU (si falla, el juego usa numpy):
python tools\gpu_selftest.py
pause
exit /b 0

:no_python
echo.
echo Falta Python %PY_VERSION%. Instalalo desde python.org:
echo   %PY_URL%
echo Despues volve a correr este instalador.
pause
exit /b 1
