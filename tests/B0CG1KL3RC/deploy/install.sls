# SystemLink Salt State ??? Install Python and the 18650 Battery Test package.
#
# Apply via SystemLink Systems Manager or directly with:
#   salt-call --local state.apply install

# ---------- 1. Install Python 3.12.9 ----------

download-python-installer:
  file.managed:
    - name: 'C:\Windows\Temp\python-3.12.9-amd64.exe'
    - source: 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe'
    - skip_verify: True
    - unless: >-
        powershell -Command "& 'C:\Program Files\Python312\python.exe' --version 2>&1 | Select-String -Quiet '3.12.9'"

install-python:
  cmd.run:
    - name: >-
        "C:\Windows\Temp\python-3.12.9-amd64.exe"
        /quiet
        InstallAllUsers=1
        PrependPath=1
        TargetDir=C:\PROGRA~1\Python312
        Include_launcher=1
    - shell: cmd
    - unless: >-
        powershell -Command "$regPy64 = Get-ChildItem 'HKLM:\SOFTWARE\Python\PythonCore' -ErrorAction SilentlyContinue; if ($regPy64) { exit 0 }; $regPy32 = Get-ChildItem 'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore' -ErrorAction SilentlyContinue; if ($regPy32) { exit 0 }; if (Test-Path 'C:\Program Files\Python312\python.exe') { exit 0 }; if (Test-Path 'C:\Program Files (x86)\Python312\python.exe') { exit 0 }; exit 1"
    - require:
      - file: download-python-installer

add-python-to-path:
  win_path.exists:
    - name: 'C:\Program Files\Python312'
    - require:
      - cmd: install-python

add-python-scripts-to-path:
  win_path.exists:
    - name: 'C:\Program Files\Python312\Scripts'
    - require:
      - cmd: install-python

# ---------- 2. Register feed and install the test package ----------

add-battery-test-feed:
  pkgrepo.managed:
    - name: Battery-Test-18650
    - uri: "https://demo-api.lifecyclesolutions.ni.com/nifeed/v1/feeds/170e7b9d-9126-4fdf-a884-f6e42ea180b2/files"
    - enabled: true
    - compressed: false
    - trusted: true
    - require:
      - cmd: install-python

install-battery-test-package:
  pkg.installed:
    - install_recommends: true
    - pkgs:
      - 18650-battery-test: 1.0.1.0
    - require:
      - pkgrepo: add-battery-test-feed

# ---------- 3. Create venv if postinstall didn't run ----------

create-venv:
  cmd.run:
    - name: >-
        "C:\Program Files\Python312\python.exe" -m venv
        --clear
        "C:\Program Files\NI\18650-battery-test\venv"
    - require:
      - pkg: install-battery-test-package

ensure-venv-pip:
  cmd.run:
    - name: >-
        "C:\Program Files\NI\18650-battery-test\venv\Scripts\python.exe"
        -m ensurepip --upgrade
    - unless: powershell -Command "Test-Path 'C:\Program Files\NI\18650-battery-test\venv\Scripts\pip.exe'"
    - require:
      - cmd: create-venv

install-pip-deps:
  cmd.run:
    - name: >-
        "C:\Program Files\NI\18650-battery-test\venv\Scripts\python.exe"
        -m pip
        install --no-cache-dir
        -r "C:\Program Files\NI\18650-battery-test\requirements.txt"
    - require:
      - cmd: ensure-venv-pip

