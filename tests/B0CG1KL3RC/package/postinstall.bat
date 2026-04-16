@echo off
REM Post-install script for 18650 Battery Test
REM Installs Python dependencies into a virtual environment

set INSTALL_DIR=C:\Program Files\NI\18650-battery-test
set VENV_DIR=%INSTALL_DIR%\venv

echo Creating Python virtual environment...
python -m venv "%VENV_DIR%"

echo Installing dependencies...
"%VENV_DIR%\Scripts\pip.exe" install --no-cache-dir -r "%INSTALL_DIR%\requirements.txt"

echo 18650 Battery Test installed successfully.
