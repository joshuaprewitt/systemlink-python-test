# SystemLink Salt State — Install Python and the 18650 Battery Test package.
#
# Apply via SystemLink Systems Manager or directly with:
#   salt-call --local state.apply install
#
# Pillar / grain overrides:
#   python_version: "3.12.9"   (default shown)
#   nipkg_feed:     name of the SystemLink feed hosting the test package

{% set python_version = salt['pillar.get']('python_version', '3.12.9') %}
{% set python_major_minor = python_version.split('.')[:2] | join('.') %}
{% set python_installer = 'python-' ~ python_version ~ '-amd64.exe' %}
{% set python_url = 'https://www.python.org/ftp/python/' ~ python_version ~ '/' ~ python_installer %}
{% set python_install_dir = 'C:\\Program Files\\Python' ~ python_major_minor.replace('.', '') %}

# ---------- 1. Install Python ----------

download-python-installer:
  file.managed:
    - name: C:\Windows\Temp\{{ python_installer }}
    - source: {{ python_url }}
    - skip_verify: True

install-python:
  cmd.run:
    - name: >-
        "C:\Windows\Temp\{{ python_installer }}"
        /quiet
        InstallAllUsers=1
        PrependPath=1
        "TargetDir={{ python_install_dir }}"
        Include_launcher=1
    - shell: cmd
    - unless: >-
        "{{ python_install_dir }}\\python.exe" --version
    - require:
      - file: download-python-installer

add-python-to-path:
  win_path.exists:
    - name: '{{ python_install_dir }}'
    - require:
      - cmd: install-python

add-python-scripts-to-path:
  win_path.exists:
    - name: '{{ python_install_dir }}\Scripts'
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
        "{{ python_install_dir }}\\python.exe" -m venv
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
