@echo off
REM Build script for 18650 Battery Test nipkg
REM Run this on a Windows machine with NI Package Manager CLI installed.
REM
REM Usage:
REM   build_nipkg.bat
REM
REM Output:
REM   dist\18650-battery-test_<auto-version>_windows_all.nipkg

setlocal enableextensions
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%
set BUILD_DIR=%PROJECT_DIR%build\nipkg
set DATA_DIR=%BUILD_DIR%\data\ProgramFiles\NI\18650-battery-test
set CONTROL_DIR=%BUILD_DIR%\control
set DIST_DIR=%PROJECT_DIR%dist
set CONTROL_TEMPLATE=%PROJECT_DIR%package\control
set VERSION_FILE=%PROJECT_DIR%package\version.txt
set BUILD_NUMBER_FILE=%PROJECT_DIR%package\build_number.txt
set DEPLOY_SLS=%PROJECT_DIR%deploy\install.sls
set NIPKG_EXE=nipkg
set PACKAGE_VERSION=
set BASE_VERSION=
set NEXT_BUILD=

echo === 18650 Battery Test — nipkg build ===

REM Read base version (e.g. 1.0.1) and next build number, then increment the counter.
set /p BASE_VERSION=<"%VERSION_FILE%"
set /p NEXT_BUILD=<"%BUILD_NUMBER_FILE%"
if "%BASE_VERSION%"=="" (
    echo Failed to read package\version.txt.
    exit /b 1
)
if "%NEXT_BUILD%"=="" set NEXT_BUILD=0
set /a NEXT_BUILD=0+NEXT_BUILD 2>nul
if %ERRORLEVEL% NEQ 0 set NEXT_BUILD=0
set PACKAGE_VERSION=%BASE_VERSION%.%NEXT_BUILD%
set /a WRITE_BUILD=NEXT_BUILD+1
if "%WRITE_BUILD%"=="" set WRITE_BUILD=1
>"%BUILD_NUMBER_FILE%" echo(%WRITE_BUILD%
echo Version for this build: %PACKAGE_VERSION%

where nipkg >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    if exist "C:\Program Files\National Instruments\NI Package Manager\nipkg.exe" (
        set NIPKG_EXE=C:\Program Files\National Instruments\NI Package Manager\nipkg.exe
    ) else (
        echo NI Package Manager CLI not found. Install NI Package Manager or add nipkg to PATH.
        exit /b 1
    )
)

REM Clean previous build
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"

REM Create directory structure
mkdir "%DATA_DIR%"
mkdir "%CONTROL_DIR%"
mkdir "%DIST_DIR%"
> "%BUILD_DIR%\debian-binary" echo 2.0

REM Copy application source files
copy "%PROJECT_DIR%config.py" "%DATA_DIR%\"
copy "%PROJECT_DIR%initialization.py" "%DATA_DIR%\"
copy "%PROJECT_DIR%execution.py" "%DATA_DIR%\"
copy "%PROJECT_DIR%simulator.py" "%DATA_DIR%\"
copy "%PROJECT_DIR%main.py" "%DATA_DIR%\"
copy "%PROJECT_DIR%requirements.txt" "%DATA_DIR%\"

REM Copy control metadata
copy "%CONTROL_TEMPLATE%" "%CONTROL_DIR%\control.template" >nul
powershell -NoProfile -Command "$p='%CONTROL_DIR%\control.template'; $o='%CONTROL_DIR%\control'; (Get-Content -Raw $p) -replace '(?m)^Version:\s*.*$','Version: %PACKAGE_VERSION%' | Set-Content -Encoding Default $o"
if %ERRORLEVEL% NEQ 0 (
    echo Failed to stamp package version into control file.
    exit /b 1
)
del "%CONTROL_DIR%\control.template" >nul 2>nul

if exist "%DEPLOY_SLS%" (
    powershell -NoProfile -Command "$p='%DEPLOY_SLS%'; (Get-Content -Raw $p) -replace '(?m)^\s*-\s*18650-battery-test:\s*.*$','      - 18650-battery-test: %PACKAGE_VERSION%' | Set-Content -Encoding Default $p"
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to update deploy\install.sls with package version.
        exit /b 1
    )
)

copy "%PROJECT_DIR%package\instructions" "%CONTROL_DIR%\"
copy "%PROJECT_DIR%package\postinstall.bat" "%CONTROL_DIR%\"
copy "%PROJECT_DIR%package\preuninstall.bat" "%CONTROL_DIR%\"

REM Build the package
echo Building nipkg...
"%NIPKG_EXE%" pack "%BUILD_DIR%" "%DIST_DIR%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo === Build successful ===
    echo Package: %DIST_DIR%\18650-battery-test_%PACKAGE_VERSION%_windows_all.nipkg
    echo.
    echo To upload to SystemLink feed:
    echo   slcli feed package upload --feed "My Feed" --file "%DIST_DIR%\18650-battery-test_%PACKAGE_VERSION%_windows_all.nipkg"
) else (
    echo.
    echo === Build FAILED ===
    exit /b 1
)
