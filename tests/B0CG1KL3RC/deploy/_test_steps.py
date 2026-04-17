"""Run each install.sls step as an individual Salt job to find the hang."""
import json
import ssl
import sys
import time
import urllib.request
import urllib.error

SERVER = "https://demo-api.lifecyclesolutions.ni.com"
API_KEY = "D_QX7SLNROWBVWJfas8k2MgbWvUjNZN9UXunz8mq-G"
SYSTEM_ID = "Latitude_7420--SN-688W9K3--MAC-10-51-07-3C-0C-44"
CTX = ssl.create_default_context()


def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{SERVER}{path}", data=data, method=method)
    req.add_header("x-ni-api-key", API_KEY)
    req.add_header("User-Agent", "SystemLink-CLI/1.0")
    req.add_header("Content-Type", "application/json")
    try:
        raw = urllib.request.urlopen(req, context=CTX).read().decode()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except urllib.error.HTTPError as e:
        print(f"  API ERROR {e.code}: {e.read().decode()[:500]}")
        return None


def cancel_job(jid):
    """Cancel a stuck job."""
    body = [{"jid": jid, "systemId": SYSTEM_ID}]
    result = api("POST", "/nisysmgmt/v1/cancel-jobs", body)
    print(f"  Cancel result: {result}")


def run_cmd(description, cmd, timeout=120):
    """Submit a single cmd.run job and wait for it to complete."""
    print(f"\n{'='*60}")
    print(f"STEP: {description}")
    print(f"CMD:  {cmd[:120]}...")
    print(f"{'='*60}")

    job_body = {
        "tgt": [SYSTEM_ID],
        "fun": ["cmd.run"],
        "arg": [[cmd, {"__kwarg__": True, "shell": "cmd"}]],
        "metadata": {
            "queued": True,
            "timeout": timeout,
        },
    }

    result = api("POST", "/nisysmgmt/v1/jobs", job_body)
    if not result:
        print("  FAILED to create job!")
        return False

    jid = result.get("jid", "unknown")
    print(f"  JID: {jid}")

    # Poll for completion
    max_polls = timeout // 5 + 12  # extra buffer
    for i in range(max_polls):
        time.sleep(5)
        job = api("GET", f"/nisysmgmt/v1/jobs?jid={jid}")
        if isinstance(job, list) and job:
            job = job[0]
        if not job:
            continue
        state = job.get("state", "UNKNOWN")
        retcode = job.get("retcode", "")
        elapsed = (i + 1) * 5
        rc_str = f" retcode={retcode}" if retcode not in ("", None) else ""
        print(f"  [{elapsed:3d}s] {state}{rc_str}")

        if state in ("SUCCEEDED", "FAILED", "CANCELED", "TIMED_OUT"):
            ret = job.get("return", "")
            if ret:
                txt = json.dumps(ret, indent=2)
                # Show first 2000 chars of return
                print(f"  Return:\n{txt[:2000]}")
            if state == "SUCCEEDED":
                print(f"  >> PASSED")
                return True
            else:
                print(f"  >> FAILED ({state})")
                return False

    print(f"  >> TIMED OUT after {max_polls * 5}s - HANGING!")
    cancel_job(jid)
    return False


def run_state_single(description, state_sls_content, timeout=120):
    """Submit a single state.apply with a minimal SLS via the states API."""
    # For non-cmd.run states, we need state.apply
    # But for simplicity, let's test with cmd.run equivalents
    pass


if __name__ == "__main__":
    # First cancel the stuck job
    print("=== Cancelling stuck job 540edeb4 ===")
    cancel_job("540edeb4-00c6-4414-ac0f-39e94e97a507")
    time.sleep(5)

    results = []

    # Step 1: Check if Python is already installed
    ok = run_cmd(
        "Check Python 3.12 status",
        'powershell -Command "& \'C:\\Program Files\\Python312\\python.exe\' --version 2>&1"',
        timeout=30,
    )
    results.append(("Check Python", ok))

    # Step 2: Download Python installer (only if needed)
    ok = run_cmd(
        "Download Python installer",
        'powershell -Command "if (!(Test-Path \'C:\\Windows\\Temp\\python-3.12.9-amd64.exe\')) { Invoke-WebRequest -Uri \'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe\' -OutFile \'C:\\Windows\\Temp\\python-3.12.9-amd64.exe\' -UseBasicParsing; Write-Host \'Downloaded\' } else { Write-Host \'Already exists\' }"',
        timeout=120,
    )
    results.append(("Download Python", ok))

    # Step 3: Install Python (silent)
    ok = run_cmd(
        "Install Python 3.12.9",
        '"C:\\Windows\\Temp\\python-3.12.9-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1 TargetDir=C:\\PROGRA~1\\Python312 Include_launcher=1',
        timeout=300,
    )
    results.append(("Install Python", ok))

    # Step 4: Verify Python installed
    ok = run_cmd(
        "Verify Python installed",
        '"C:\\Program Files\\Python312\\python.exe" --version',
        timeout=30,
    )
    results.append(("Verify Python", ok))

    # Step 5: Add NI feed
    ok = run_cmd(
        "Add Battery-Test-18650 feed",
        '"C:\\Program Files\\National Instruments\\NI Package Manager\\nipkg.exe" feed-add Battery-Test-18650 "https://demo-api.lifecyclesolutions.ni.com/nifeed/v1/feeds/170e7b9d-9126-4fdf-a884-f6e42ea180b2/files"',
        timeout=60,
    )
    results.append(("Add feed", ok))

    # Step 6: Install nipkg package
    ok = run_cmd(
        "Install 18650-battery-test nipkg",
        '"C:\\Program Files\\National Instruments\\NI Package Manager\\nipkg.exe" install --accept-eulas --force-locked 18650-battery-test',
        timeout=300,
    )
    results.append(("Install nipkg", ok))

    # Step 7: Create venv
    ok = run_cmd(
        "Create Python venv",
        '"C:\\Program Files\\Python312\\python.exe" -m venv "C:\\Program Files\\NI\\18650-battery-test\\venv"',
        timeout=60,
    )
    results.append(("Create venv", ok))

    # Step 8: Pip install deps
    ok = run_cmd(
        "Pip install requirements",
        '"C:\\Program Files\\NI\\18650-battery-test\\venv\\Scripts\\pip.exe" install --no-cache-dir -r "C:\\Program Files\\NI\\18650-battery-test\\requirements.txt"',
        timeout=300,
    )
    results.append(("Pip install", ok))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
