"""Operator identity resolution for SystemLink test applications.

Resolves a human-readable operator name from multiple sources in priority order:
1. SYSTEMLINK_TEST_OPERATOR environment variable (orchestration override)
2. Work-item identity fields resolved through the niuser API
3. Triggering Salt job metadata.user_login from execution history
4. Logged-in OS user (local/manual execution)
5. Work-item assigned_to raw value as last resort
"""

import getpass
import json
import logging
import os
import re
import ssl
import urllib.error
import urllib.request

from nisystemlink.clients.core import HttpConfiguration, HttpConfigurationManager
from nisystemlink.clients.work_item.models import WorkItem

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


def normalize_display_name(value: str) -> str:
    """Normalize names from 'Last, First' to 'First Last'."""
    text = (value or "").strip()
    if not text:
        return text
    if "," not in text:
        return text
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) < 2:
        return text
    return " ".join(parts[1:] + [parts[0]])


def fetch_json(cfg: HttpConfiguration, relative_path: str) -> dict | list | None:
    """GET a SystemLink API path using the configuration API key."""
    api_key = (cfg.api_keys or {}).get("x-ni-api-key")
    if not api_key:
        return None

    url = f"{cfg.server_uri.rstrip('/')}{relative_path}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("x-ni-api-key", api_key)
    req.add_header("User-Agent", "SystemLink-CLI/1.0")

    with urllib.request.urlopen(req, context=ssl.create_default_context()) as resp:
        return json.loads(resp.read().decode())


def lookup_user_by_id(
    user_id: str,
    configuration: HttpConfiguration | None,
) -> str | None:
    """Resolve a user UUID to a display name via the niuser API."""
    if not _UUID_RE.match(user_id):
        return None

    try:
        cfg = configuration or HttpConfigurationManager.get_configuration()
        body = fetch_json(cfg, f"/niuser/v1/users/{user_id}")
        if not isinstance(body, dict):
            return None
        login = body.get("login") or body.get("name")
        if login:
            return normalize_display_name(str(login))
    except urllib.error.HTTPError:
        logger.debug("Unable to resolve user id %s via niuser", user_id, exc_info=True)
    except Exception:
        logger.debug("Unexpected error resolving user id %s", user_id, exc_info=True)

    return None


def lookup_job_creator(
    work_item: WorkItem,
    configuration: HttpConfiguration | None,
) -> str | None:
    """Resolve the triggering job's creator display name from execution history."""
    history = work_item.execution_history or []
    latest_job_id = None

    for entry in reversed(history):
        if not entry or not entry.job_ids:
            continue
        if entry.job_ids[0]:
            latest_job_id = entry.job_ids[0]
            break

    if not latest_job_id:
        return None

    try:
        cfg = configuration or HttpConfigurationManager.get_configuration()
        body = fetch_json(cfg, f"/nisysmgmt/v1/jobs?jid={latest_job_id}")
        job = body[0] if isinstance(body, list) and body else body
        if not isinstance(job, dict):
            return None
        login = ((job.get("metadata") or {}).get("user_login") or "").strip()
        if login:
            return normalize_display_name(login)
    except Exception:
        logger.debug("Unable to resolve creator from job %s", latest_job_id, exc_info=True)

    return None


def resolve_operator(
    work_item: WorkItem,
    configuration: HttpConfiguration | None,
) -> str:
    """Resolve the operator name for a test result.

    Priority:
    1) ``SYSTEMLINK_TEST_OPERATOR`` environment variable.
    2) Work-item identity fields resolved via niuser.
    3) Triggering Salt job metadata.user_login from execution history.
    4) Logged-in OS user (local/manual execution).
    5) work_item.assigned_to raw value as last resort.
    """
    env_operator = (os.environ.get("SYSTEMLINK_TEST_OPERATOR") or "").strip()
    if env_operator:
        return env_operator

    identity_candidates = [
        work_item.assigned_to,
        work_item.requested_by,
        work_item.created_by,
    ]

    saw_uuid = False
    for candidate in identity_candidates:
        value = (candidate or "").strip()
        if not value:
            continue
        if _UUID_RE.match(value):
            saw_uuid = True
            resolved = lookup_user_by_id(value, configuration)
            if resolved:
                return resolved
            continue
        if value.endswith("$"):
            continue
        return normalize_display_name(value)

    if saw_uuid:
        resolved = lookup_job_creator(work_item, configuration)
        if resolved:
            return resolved

    local_user = (getpass.getuser() or "").strip()
    if local_user and not local_user.endswith("$"):
        return local_user

    return normalize_display_name(work_item.assigned_to or "unassigned")
