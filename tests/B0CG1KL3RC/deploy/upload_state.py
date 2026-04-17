#!/usr/bin/env python
"""Upload the install.sls Salt state to SystemLink via the Systems State API.

Uses the import-state endpoint (multipart/form-data) so the full SLS content
(cmd.run, file.managed, etc.) is preserved — not just packages and feeds.

Usage:
    python upload_state.py                       # uses slcli active profile
    python upload_state.py --server URL --api-key KEY
    python upload_state.py --replace STATE_ID    # update an existing state
"""

import argparse
import json
import pathlib
import sys
import urllib.request
import urllib.error
import ssl
import uuid

SLS_FILE = pathlib.Path(__file__).with_name("install.sls")
STATE_NAME = "18650 Battery Test Provisioning"
STATE_DESCRIPTION = (
    "Installs Python 3.12.9, the 18650-battery-test nipkg, "
    "creates a venv, and installs pip dependencies."
)
DISTRIBUTION = "WINDOWS"
ARCHITECTURE = "X64"
USER_AGENT = "SystemLink-CLI/1.0"


def _credentials_from_slcli():
    """Read server URL and API key from the active slcli profile."""
    try:
        from nisystemlink.clients.core import HttpConfigurationManager

        mgr = HttpConfigurationManager()
        cfg = mgr.get_configuration()
        server = cfg.server_uri.rstrip("/")
        api_key = cfg.api_keys.get("x-ni-api-key", "")
        if server and api_key:
            return server, api_key
    except Exception:
        pass

    config_path = pathlib.Path.home() / ".config" / "slcli" / "config.json"
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        current = data.get("current-profile", "default")
        profile = data.get("profiles", {}).get(current, {})
        server = profile.get("server", "").rstrip("/")
        api_key = profile.get("api-key", "")
        if server and api_key:
            return server, api_key

    return None, None


def _build_multipart(fields: dict, file_path: pathlib.Path):
    """Return (content_type, body_bytes) for a multipart/form-data upload."""
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []

    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())

    file_bytes = file_path.read_bytes()
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="File"; '
        f'filename="{file_path.name}"\r\n'.encode()
    )
    parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    parts.append(file_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode())

    return f"multipart/form-data; boundary={boundary}", b"".join(parts)


def _api_request(url: str, api_key: str, body: bytes, content_type: str, method: str = "POST"):
    """Send an API request with standard headers."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("x-ni-api-key", api_key)
    req.add_header("Content-Type", content_type)
    req.add_header("User-Agent", USER_AGENT)

    try:
        resp = urllib.request.urlopen(req, context=ctx)
        result = json.loads(resp.read().decode())
        return result
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f"ERROR {e.code}: {body_text}", file=sys.stderr)
        sys.exit(1)


def import_state(server: str, api_key: str) -> dict:
    """Import the SLS file as a new state via POST /import-state."""
    fields = {
        "Name": STATE_NAME,
        "Description": STATE_DESCRIPTION,
        "Distribution": DISTRIBUTION,
        "Architecture": ARCHITECTURE,
    }
    content_type, body = _build_multipart(fields, SLS_FILE)
    result = _api_request(
        f"{server}/nisystemsstate/v1/import-state", api_key, body, content_type
    )
    print("State imported successfully!")
    print(json.dumps(result, indent=2))
    return result


def replace_state(server: str, api_key: str, state_id: str) -> dict:
    """Replace an existing state's SLS content via POST /replace-state-content."""
    fields = {
        "Id": state_id,
        "ChangeDescription": "Updated via upload_state.py",
    }
    content_type, body = _build_multipart(fields, SLS_FILE)
    result = _api_request(
        f"{server}/nisystemsstate/v1/replace-state-content", api_key, body, content_type
    )
    print(f"State {state_id} updated successfully!")
    print(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Upload SLS state to SystemLink Systems State service"
    )
    parser.add_argument("--server", help="SystemLink API URL")
    parser.add_argument("--api-key", help="SystemLink API key")
    parser.add_argument(
        "--replace",
        metavar="STATE_ID",
        help="Replace content of an existing state instead of creating a new one",
    )
    args = parser.parse_args()

    server = args.server
    api_key = args.api_key

    if not server or not api_key:
        auto_server, auto_key = _credentials_from_slcli()
        server = server or auto_server
        api_key = api_key or auto_key

    if not server or not api_key:
        print(
            "ERROR: No credentials found. Pass --server and --api-key, "
            "or configure slcli with 'slcli login'.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not SLS_FILE.exists():
        print(f"ERROR: SLS file not found: {SLS_FILE}", file=sys.stderr)
        sys.exit(1)

    print(f"Server:  {server}")
    print(f"File:    {SLS_FILE.name}")

    if args.replace:
        replace_state(server, api_key, args.replace)
    else:
        import_state(server, api_key)


if __name__ == "__main__":
    main()
