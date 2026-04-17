#!/usr/bin/env python
"""Create a SystemLink Systems State for the 18650-battery-test package.

SystemLink states use the ``pkgrepo.managed`` / ``pkg.installed`` Salt model,
not arbitrary SLS files.  This script calls ``POST /nisystemsstate/v1/states``
with the package definition.

Usage:
    python upload_state.py                       # uses slcli active profile
    python upload_state.py --server URL --api-key KEY
"""

import argparse
import json
import pathlib
import sys
import urllib.request
import urllib.error
import ssl

STATE_NAME = "18650 Battery Test Provisioning"
STATE_DESCRIPTION = "Installs the 18650-battery-test nipkg package."
DISTRIBUTION = "WINDOWS"
ARCHITECTURE = "X64"
PACKAGES = [
    {"name": "18650-battery-test", "version": "1.0.0", "installRecommends": True},
]
FEEDS: list[dict] = []  # add feed dicts here if the package is hosted on a custom feed


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


def create_state(server: str, api_key: str) -> dict:
    """POST a new state to /nisystemsstate/v1/states."""
    state_body = {
        "name": STATE_NAME,
        "description": STATE_DESCRIPTION,
        "distribution": DISTRIBUTION,
        "architecture": ARCHITECTURE,
        "feeds": FEEDS,
        "packages": PACKAGES,
    }

    body = json.dumps(state_body).encode()
    url = f"{server}/nisystemsstate/v1/states"
    ctx = ssl.create_default_context()

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("x-ni-api-key", api_key)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "SystemLink-CLI/1.0")

    try:
        resp = urllib.request.urlopen(req, context=ctx)
        result = json.loads(resp.read().decode())
        print("State created successfully!")
        print(json.dumps(result, indent=2))
        return result
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f"ERROR {e.code}: {body_text}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Create a SystemLink Systems State for the test package"
    )
    parser.add_argument("--server", help="SystemLink API URL")
    parser.add_argument("--api-key", help="SystemLink API key")
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

    print(f"Server: {server}")
    create_state(server, api_key)


if __name__ == "__main__":
    main()
