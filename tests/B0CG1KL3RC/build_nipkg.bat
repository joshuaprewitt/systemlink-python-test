@echo off
REM Build script for 18650 Battery Test nipkg
REM Run this on a Windows machine with NI Package Manager CLI installed.
REM
REM Usage:
REM   build_nipkg.bat
REM
REM Output:
REM   dist\18650-battery-test_1.0.0_windows_all.nipkg

setlocal enableextensions
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%
set BUILD_DIR=%PROJECT_DIR%build\nipkg
set DATA_DIR=%BUILD_DIR%\data\Program Files\NI\18650-battery-test
set CONTROL_DIR=%BUILD_DIR%\control
set DIST_DIR=%PROJECT_DIR%dist

echo === 18650 Battery Test — nipkg build ===

REM Clean previous build
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"

REM Create directory structure
mkdir "%DATA_DIR%"
mkdir "%CONTROL_DIR%"
mkdir "%DIST_DIR%"

REM Copy application source files
copy "%PROJECT_DIR%config.py" "%DATA_DIR%\"
copy "%PROJECT_DIR%initialization.py" "%DATA_DIR%\"
copy "%PROJECT_DIR%execution.py" "%DATA_DIR%\"
copy "%PROJECT_DIR%simulator.py" "%DATA_DIR%\"
copy "%PROJECT_DIR%main.py" "%DATA_DIR%\"
copy "%PROJECT_DIR%requirements.txt" "%DATA_DIR%\"

REM Copy control metadata
copy "%PROJECT_DIR%package\control" "%CONTROL_DIR%\"
copy "%PROJECT_DIR%package\instructions" "%CONTROL_DIR%\"
copy "%PROJECT_DIR%package\postinstall.bat" "%CONTROL_DIR%\"
copy "%PROJECT_DIR%package\preuninstall.bat" "%CONTROL_DIR%\"

REM Build the package
echo Building nipkg...
nipkg pack "%BUILD_DIR%" "%DIST_DIR%\18650-battery-test_1.0.0_windows_all.nipkg"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo === Build successful ===
    echo Package: %DIST_DIR%\18650-battery-test_1.0.0_windows_all.nipkg
    echo.
    echo To upload to SystemLink feed:
    echo   slcli feed package upload --feed "My Feed" --file "%DIST_DIR%\18650-battery-test_1.0.0_windows_all.nipkg"
) else (
    echo.
    echo === Build FAILED ===
    exit /b 1
)
