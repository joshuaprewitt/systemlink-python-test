@echo off
REM Pre-uninstall script for 18650 Battery Test
REM Removes the virtual environment and application directory

set INSTALL_DIR=C:\Program Files\NI\18650-battery-test

echo Removing virtual environment...
if exist "%INSTALL_DIR%\venv" rmdir /s /q "%INSTALL_DIR%\venv"

echo 18650 Battery Test uninstalled.
