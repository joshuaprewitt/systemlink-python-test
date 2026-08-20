"""Verify deployed battery-test files and venv on a target SystemLink system."""

import json
import time

import _deploy_state as d

TARGET = "Latitude_7420--SN-688W9K3--MAC-00-E0-4C-68-0D-88"

CMD = (
    "powershell -Command \""
    "$p1=Test-Path 'C:\\Program Files\\NI\\18650-battery-test\\venv\\Scripts\\python.exe'; "
    "$p2=Test-Path 'C:\\Program Files\\NI\\18650-battery-test\\venv\\Scripts\\pip.exe'; "
    "$p3=Test-Path 'C:\\Program Files\\NI\\18650-battery-test\\requirements.txt'; "
    "$p4=Test-Path 'C:\\Program Files\\NI\\18650-battery-test\\main.py'; "
    "if ($p1) { & 'C:\\Program Files\\NI\\18650-battery-test\\venv\\Scripts\\python.exe' --version }; "
    "Write-Output ('python={0}; pip={1}; req={2}; main={3}' -f $p1,$p2,$p3,$p4)"
    "\""
)

body = {
    "tgt": [TARGET],
    "fun": ["cmd.run"],
    "arg": [[CMD, {"__kwarg__": True, "shell": "cmd"}]],
    "metadata": {"queued": True, "timeout": 600},
}

created = d.api_post("/nisysmgmt/v1/jobs", body)
print("Create response:")
print(json.dumps(created, indent=2))
jid = created.get("jid") if isinstance(created, dict) else None
if not jid:
    raise SystemExit("No jid returned from job create")

for i in range(1, 61):
    raw = d.api_get(f"/nisysmgmt/v1/jobs?jid={jid}")
    job = raw[0] if isinstance(raw, list) and raw else raw
    state = job.get("state", "UNKNOWN") if isinstance(job, dict) else "UNKNOWN"
    print(f"Poll {i}: {state}")
    if state in {"SUCCEEDED", "FAILED", "CANCELED", "TIMED_OUT"}:
        print("Final job:")
        print(json.dumps(job, indent=2))
        break
    time.sleep(3)
