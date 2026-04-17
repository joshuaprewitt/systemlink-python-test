# SystemLink Salt State — Install Python and the 18650 Battery Test package.
#
# Apply via SystemLink Systems Manager or directly with:
#   salt-call --local state.apply install

# ---------- 1. Install Python 3.12.9 ----------

download-python-installer:
  file.managed:
    - name: 'C:\Windows\Temp\python-3.12.9-amd64.exe'
    - source: 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe'
    - skip_verify: True

install-python:
  cmd.run:
    - name: >-
        "C:\Windows\Temp\python-3.12.9-amd64.exe"
        /quiet
        InstallAllUsers=1
        PrependPath=1
        "TargetDir=C:\Program Files\Python312"
        Include_launcher=1
    - shell: cmd
    - unless: >-
        "C:\Program Files\Python312\python.exe" --version
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

# ---------- 2. Install the test package via NI Package Manager ----------

install-18650-battery-test:
  cmd.run:
    - name: >-
        "C:\Program Files\National Instruments\NI Package Manager\nipkg.exe"
        install 18650-battery-test
        --accept-eulas
        --yes
    - unless: >-
        "C:\Program Files\National Instruments\NI Package Manager\nipkg.exe"
        info-installed 18650-battery-test
    - require:
      - cmd: install-python

# ---------- 3. Create venv if postinstall didn't run ----------

create-venv:
  cmd.run:
    - name: >-
        "C:\Program Files\Python312\python.exe" -m venv
        "C:\Program Files\NI\18650-battery-test\venv"
    - unless: powershell -Command "Test-Path 'C:\Program Files\NI\18650-battery-test\venv\Scripts\python.exe'"
    - require:
      - cmd: install-18650-battery-test

install-pip-deps:
  cmd.run:
    - name: >-
        "C:\Program Files\NI\18650-battery-test\venv\Scripts\pip.exe"
        install --no-cache-dir
        -r "C:\Program Files\NI\18650-battery-test\requirements.txt"
    - require:
      - cmd: create-venv
