"""Find Josh's Laptop system ID and explore the Jobs API."""
import json
import ssl
import sys
import urllib.request
import urllib.error

SERVER = "https://demo-api.lifecyclesolutions.ni.com"
API_KEY = "D_QX7SLNROWBVWJfas8k2MgbWvUjNZN9UXunz8mq-G"
UA = "SystemLink-CLI/1.0"
CTX = ssl.create_default_context()


def api_get(path):
    req = urllib.request.Request(f"{SERVER}{path}", method="GET")
    req.add_header("x-ni-api-key", API_KEY)
    req.add_header("User-Agent", UA)
    try:
        resp = urllib.request.urlopen(req, context=CTX)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"ERROR {e.code} on GET {path}: {e.read().decode()[:500]}", file=sys.stderr)
        return None


def api_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{SERVER}{path}", data=data, method="POST")
    req.add_header("x-ni-api-key", API_KEY)
    req.add_header("User-Agent", UA)
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, context=CTX)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"ERROR {e.code} on POST {path}: {e.read().decode()[:500]}", file=sys.stderr)
        return None


def find_system(name_fragment):
    # Try query-systems with DEFAULT projection to get all fields
    body = {"take": 200}
    result = api_post("/nisysmgmt/v1/query-systems", body)
    if result:
        for s in result.get("data", []):
            if s is None:
                continue
            alias = s.get("alias", "") or ""
            hostname = s.get("hostname", "") or ""
            sid = s.get("id", "")
            state = s.get("state", "")
            if alias or hostname:
                print(f"  {sid}  alias={alias}  host={hostname}  state={state}")
            if name_fragment.lower() in alias.lower() or name_fragment.lower() in hostname.lower():
                return sid
    return None


if __name__ == "__main__":
    SYSTEM_ID = "Latitude_7420--SN-688W9K3--MAC-10-51-07-3C-0C-44"
    TARGET_WORKSPACE = "07f93ff9-7d8c-4732-b91e-2d16c5ecc5d8"  # PM Demos

    import pathlib
    import uuid

    SLS_FILE = pathlib.Path(r"C:\Github\systemlink-python-test\tests\B0CG1KL3RC\deploy\install.sls")

    # Step 1: Find existing state in PM Demos workspace
    print("=== Finding existing state in PM Demos ===")
    states = api_get("/nisystemsstate/v1/states")
    target_state_id = None
    if states:
        for s in states.get("states", states if isinstance(states, list) else []):
            if isinstance(s, dict):
                name = s.get("name", "")
                ws = s.get("workspace", "")
                sid = s.get("id", "")
                if "18650" in name or "Battery" in name:
                    print(f"  {sid}  ws={ws}  name={name}")
                    if ws == TARGET_WORKSPACE:
                        target_state_id = sid

    if not target_state_id:
        print("No existing state found in PM Demos. Listing all states:")
        if states:
            for s in states.get("states", states if isinstance(states, list) else []):
                if isinstance(s, dict):
                    print(f"  {s.get('id')}  ws={s.get('workspace')}  name={s.get('name')}")
        sys.exit(1)

    print(f"\nTarget state: {target_state_id}")

    # Step 2: Replace state content with our SLS
    print("\n=== Replacing state content ===")
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in {"Id": target_state_id, "ChangeDescription": "Updated via deploy script"}.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())
    file_bytes = SLS_FILE.read_bytes()
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="File"; filename="install.sls"\r\n'.encode())
    parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    parts.append(file_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"

    url = f"{SERVER}/nisystemsstate/v1/replace-state-content"
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("x-ni-api-key", API_KEY)
    req.add_header("Content-Type", content_type)
    req.add_header("User-Agent", UA)
    try:
        resp = urllib.request.urlopen(req, context=ctx)
        state_result = json.loads(resp.read().decode())
        print(f"State updated: {state_result.get('id')}")
    except urllib.error.HTTPError as e:
        print(f"Replace error {e.code}: {e.read().decode()[:500]}", file=sys.stderr)
        sys.exit(1)

    # Step 3: Deploy the state via job
    print(f"\n=== Deploying state {target_state_id} to Josh's Laptop ===")
    job_body = {
        "tgt": [SYSTEM_ID],
        "fun": ["state.apply", "system.get_reboot_required_witnessed"],
        "metadata": {
            "queued": True,
            "timeout": 86400,
        },
        "arg": [
            [target_state_id, {"__kwarg__": True, "test": False}],
            [],
        ],
    }

    result = api_post("/nisysmgmt/v1/jobs", job_body)
    if result:
        jid = result.get("jid", "unknown")
        print(f"Job created! JID: {jid}")

        # Poll for completion
        import time
        print("\n=== Monitoring job ===")
        for attempt in range(60):
            job = api_get(f"/nisysmgmt/v1/jobs?jid={jid}")
            if isinstance(job, list) and job:
                job = job[0]
            if job:
                state = job.get("state", "UNKNOWN")
                print(f"  [{attempt+1}] State: {state}")
                if state in ("SUCCEEDED", "FAILED", "CANCELED", "TIMED_OUT"):
                    print("\nFinal result:")
                    print(json.dumps(job, indent=2))
                    break
            time.sleep(10)
        else:
            print("Timed out waiting for job to complete.")
    else:
        print("Failed to create job.", file=sys.stderr)
        sys.exit(1)
