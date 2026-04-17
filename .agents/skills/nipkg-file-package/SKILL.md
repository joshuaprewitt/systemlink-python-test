---
name: nipkg-file-package
description: >-
  Build NI Package Manager file packages (.nipkg) for Windows and SystemLink deployment.
  Use when the user asks to assemble a file package, troubleshoot nipkg pack errors,
  choose installation target roots, create control or instructions metadata, or package
  a Python or test application for feed upload. Covers source tree layout, target root
  selection, build script structure, and common NI Package Manager CLI pitfalls.
---

# Building NI File Packages

Use this skill when the task is specifically about assembling or troubleshooting an
NI Package Manager file package.

## When to Use

- Creating a `.nipkg` from a folder of source files
- Building a deployable package for SystemLink feeds
- Choosing the correct `data/<target-root>/...` layout
- Fixing `nipkg pack` validation failures
- Adding package metadata, install scripts, or uninstall scripts

## Core Rules

1. A file package must contain these top-level entries before packing:
   - `debian-binary`
   - `control/`
   - `data/`
2. The control file must include `XB-Plugin: file`.
3. `nipkg pack` takes a source directory and a destination directory.
   - Use: `nipkg pack <source-dir> <destination-dir>`
   - Do not pass a full `.nipkg` file path as the second argument.
4. On Windows, files under `data/` must use NI Package Manager target root names.
   - `ProgramFiles` is valid.
   - `Program Files` is not valid.
5. For `Architecture: windows_all`, do not use 64-bit-only roots such as `ProgramFiles_64`.

## Required Package Layout

```text
<package-root>/
├── debian-binary
├── control/
│   ├── control
│   ├── instructions
│   ├── postinstall.bat        # optional
│   └── preuninstall.bat       # optional
└── data/
    └── ProgramFiles/
        └── NI/
            └── <package-name>/
                ├── main.py
                ├── requirements.txt
                └── ...
```

The `debian-binary` file should contain:

```text
2.0
```

## Minimal Control File

```text
Package: my-package
Version: 1.0.0
Section: test-applications
Architecture: windows_all
Maintainer: Team Name <team@example.com>
XB-Plugin: file
XB-UserVisible: yes
Description: Short description
 Extended description on the following lines.
```

**Note on `Depends`**: Only add `Depends:` entries for packages that are guaranteed to
exist in a registered feed on every target system. `ni-python` is not always available;
if you manage Python installation separately (e.g. via a Salt state), omit that dependency
and handle it through the deployment state instead.

## Minimal Instructions File

```ini
[Instructions]
postinstall=postinstall.bat
preuninstall=preuninstall.bat
```

## Windows Target Roots

Use the root names exactly as NI Package Manager expects under `data/`.

- `ProgramFiles` maps to `%SystemDrive%\Program Files` on 64-bit Windows and is equivalent to `ProgramFiles_64`
- `ProgramFiles_32` maps to `%SystemDrive%\Program Files (x86)`
- `ProgramData` maps to `%SystemDrive%\ProgramData`
- `Documents` maps to `%PUBLIC%\Documents`
- `Desktop` maps to `%PUBLIC%\Desktop`
- `Home` maps to `%PUBLIC%`
- `ProgramMenu` maps to `%ProgramData%\Microsoft\Windows\Start Menu\Programs`
- `Startup` maps to `%ProgramData%\Microsoft\Windows\Start Menu\Programs\StartUp`
- `System` is a toggling root for the Windows system directory

For NI-managed locations, use NIPaths roots prefixed with `ni-paths-`, for example:

- `ni-paths-NIPUBAPPDATADIR`
- `ni-paths-NIPMDIR`
- `ni-paths-NISHAREDDIR`

## Recommended Build Script Pattern

```bat
@echo off
setlocal enableextensions

set SCRIPT_DIR=%~dp0
set BUILD_DIR=%SCRIPT_DIR%build\nipkg
set DIST_DIR=%SCRIPT_DIR%dist
set DATA_DIR=%BUILD_DIR%\data\ProgramFiles\NI\my-package
set CONTROL_DIR=%BUILD_DIR%\control
set NIPKG_EXE=nipkg

where nipkg >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    if exist "C:\Program Files\National Instruments\NI Package Manager\nipkg.exe" (
        set NIPKG_EXE=C:\Program Files\National Instruments\NI Package Manager\nipkg.exe
    ) else (
        echo NI Package Manager CLI not found.
        exit /b 1
    )
)

if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"

mkdir "%DATA_DIR%"
mkdir "%CONTROL_DIR%"
mkdir "%DIST_DIR%"
> "%BUILD_DIR%\debian-binary" echo 2.0

REM Copy payload files into %DATA_DIR%
REM Copy control metadata into %CONTROL_DIR%

"%NIPKG_EXE%" pack "%BUILD_DIR%" "%DIST_DIR%"
```

## Common Failures and Fixes

- `nipkg is not recognized`
  - Call `C:\Program Files\National Instruments\NI Package Manager\nipkg.exe` directly or add it to `PATH`.
- `The specified path ... is invalid`
  - The second `nipkg pack` argument should be a destination directory, not a full `.nipkg` filename.
- `Unknown root name: program files`
  - Use `ProgramFiles`, not `Program Files`.
- Root validation failures with `windows_all`
  - Avoid `_64`-only roots such as `ProgramFiles_64`.
- `Required package not found: 'ni-python (>= 3.10)'`
  - Remove the `Depends: ni-python` line from the control file. Install Python via a Salt state or other mechanism instead.

## Verification Steps

1. Run the build script.
2. Confirm a `.nipkg` appears in `dist/`.
3. Unpack it to verify the structure:

```powershell
& "C:\Program Files\National Instruments\NI Package Manager\nipkg.exe" unpack \
  "dist\my-package_1.0.0_windows_all.nipkg" \
  "build\verify-package"
```

4. Check that the unpacked package contains:
   - `control/control`
   - `debian-binary`
   - `data/ProgramFiles/...`

## SystemLink Context

For SystemLink deployment, file packages are appropriate when the application payload is a
set of files to be installed directly onto the test system, such as Python source, batch
scripts, configuration files, and requirements manifests. After building the `.nipkg`, upload
it to a feed with `slcli feed package upload` and deploy it through SystemLink software
deployment.

## Salt State (SLS) Deployment

When the target system needs prerequisites (e.g. Python) that are not available as nipkg
dependencies, create a Salt state file (`deploy/install.sls`) and apply it through
SystemLink Systems Manager. A typical SLS for a Python test package covers:

1. **Download and install Python** — use the official Windows installer with `/quiet`,
   `InstallAllUsers=1`, `PrependPath=1`. Quote `TargetDir` carefully:
   ```yaml
   install-python:
     cmd.run:
       - name: >-
           "C:\Windows\Temp\python-3.12.9-amd64.exe"
           /quiet InstallAllUsers=1 PrependPath=1
           "TargetDir=C:\Program Files\Python312"
           Include_launcher=1
       - shell: cmd
       - unless: >-
           "C:\Program Files\Python312\python.exe" --version
   ```
   **Critical**: Use `"TargetDir=C:\Program Files\Python312"` (quotes around the
   entire key=value pair). If only the path is quoted (`TargetDir="C:\Program Files\..."`)      the installer may truncate at the space.

2. **Add Python to PATH** — `win_path.exists` for both the install dir and `Scripts\`.

3. **Install the nipkg** — `nipkg.exe install <package> --accept-eulas --yes`,
   guarded by `nipkg.exe info-installed <package>`.

4. **Create venv and install pip deps** — safety net in case the nipkg `postinstall.bat`
   ran before Python was on PATH. Use `powershell -Command "Test-Path ..."` for the
   `unless` guard on Windows (not `test -d`).

Apply locally with:
```
& "C:\Program Files\National Instruments\Shared\salt-minion\salt-call.bat" --local state.apply install
```

Or push remotely through SystemLink Systems Manager.